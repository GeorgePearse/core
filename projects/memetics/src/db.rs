//! SQLite is the authority for registrations, cached changes, and delivery receipts.

use crate::config::{canonical, digest, validate};
use crate::error::{Result, invalid};
use rusqlite::types::{Value as Sql, ValueRef};
use rusqlite::{Connection, OptionalExtension, Params, params};
use serde_json::{Map, Value, json};
use std::collections::HashSet;
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub type Row = Map<String, Value>;

const SCHEMA: &str = "
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, repo TEXT NOT NULL, ref TEXT NOT NULL, head TEXT, etag TEXT,
 next_poll REAL NOT NULL DEFAULT 0, error TEXT, polls INTEGER NOT NULL DEFAULT 0,
 UNIQUE(repo, ref));
CREATE TABLE IF NOT EXISTS listeners (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), config TEXT NOT NULL,
 config_hash TEXT NOT NULL, enabled INTEGER NOT NULL, observed TEXT, decided TEXT NOT NULL,
 adopted TEXT, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS changes (
 id TEXT PRIMARY KEY, repo TEXT NOT NULL, before_sha TEXT NOT NULL, after_sha TEXT NOT NULL,
 data TEXT NOT NULL, created REAL NOT NULL, UNIQUE(repo,before_sha,after_sha));
CREATE TABLE IF NOT EXISTS blobs (
 repo TEXT NOT NULL, sha TEXT NOT NULL, content TEXT NOT NULL, PRIMARY KEY(repo,sha));
CREATE VIRTUAL TABLE IF NOT EXISTS blob_search USING fts5(repo UNINDEXED, sha UNINDEXED, content);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, listener_id TEXT NOT NULL REFERENCES listeners(id),
 config TEXT NOT NULL, config_hash TEXT NOT NULL, before_sha TEXT NOT NULL, after_sha TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
 not_before REAL NOT NULL DEFAULT 0, reason TEXT, evidence TEXT, delivery TEXT,
 created REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(listener_id, config_hash, after_sha));
CREATE TABLE IF NOT EXISTS proposals (
 listener_id TEXT PRIMARY KEY REFERENCES listeners(id), repo TEXT NOT NULL, number INTEGER NOT NULL,
 url TEXT NOT NULL, branch TEXT NOT NULL, head_sha TEXT NOT NULL, upstream_sha TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'open');
CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, received REAL NOT NULL);
CREATE TABLE IF NOT EXISTS idea_verdicts (
 revision TEXT NOT NULL, idea_id TEXT NOT NULL, choice TEXT NOT NULL, confidence REAL NOT NULL,
 reason TEXT NOT NULL, judge TEXT NOT NULL, method TEXT NOT NULL, evidence TEXT, created REAL NOT NULL,
 PRIMARY KEY(revision, idea_id));
";

pub fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

pub fn text(row: &Row, key: &str) -> String {
    row.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

pub fn int(row: &Row, key: &str) -> i64 {
    row.get(key).and_then(Value::as_i64).unwrap_or_default()
}

pub fn opt_text(row: &Row, key: &str) -> Option<String> {
    row.get(key)
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
        .map(String::from)
}

fn to_json(value: ValueRef<'_>) -> Value {
    match value {
        ValueRef::Null => Value::Null,
        ValueRef::Integer(i) => i.into(),
        ValueRef::Real(f) => json!(f),
        ValueRef::Text(t) => String::from_utf8_lossy(t).into_owned().into(),
        ValueRef::Blob(b) => hex::encode(b).into(),
    }
}

fn collect(conn: &Connection, sql: &str, args: impl Params) -> Result<Vec<Row>> {
    let mut stmt = conn.prepare(sql)?;
    let names: Vec<String> = stmt.column_names().iter().map(|s| s.to_string()).collect();
    let rows = stmt.query_map(args, |r| {
        let mut row = Map::new();
        for (i, name) in names.iter().enumerate() {
            row.insert(name.clone(), to_json(r.get_ref(i)?));
        }
        Ok(row)
    })?;
    Ok(rows.collect::<rusqlite::Result<_>>()?)
}

#[derive(Clone, Debug)]
pub struct Store {
    pub root: PathBuf,
    pub path: PathBuf,
}

impl Store {
    pub fn open(root: impl AsRef<Path>) -> Result<Store> {
        std::fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(root.as_ref())?;
        let root = root.as_ref().canonicalize()?;
        let path = root.join("state.sqlite3");
        let store = Store { root, path };
        store.connect()?.execute_batch(SCHEMA)?;
        std::fs::set_permissions(&store.path, std::fs::Permissions::from_mode(0o600))?;
        Ok(store)
    }

    pub fn connect(&self) -> Result<Connection> {
        let conn = Connection::open(&self.path)?;
        conn.busy_timeout(Duration::from_secs(30))?;
        conn.query_row("PRAGMA journal_mode=WAL", [], |_| Ok(()))?;
        conn.execute_batch("PRAGMA foreign_keys=ON")?;
        Ok(conn)
    }

    pub fn rows(&self, sql: &str, args: impl Params) -> Result<Vec<Row>> {
        collect(&self.connect()?, sql, args)
    }

    pub fn one(&self, sql: &str, args: impl Params) -> Result<Option<Row>> {
        Ok(self.rows(sql, args)?.into_iter().next())
    }

    pub fn execute(&self, sql: &str, args: impl Params) -> Result<i64> {
        let conn = self.connect()?;
        conn.execute(sql, args)?;
        Ok(conn.last_insert_rowid())
    }

    pub fn register(&self, configs: &[Value]) -> Result<Vec<String>> {
        // Validate the whole request before mutating any standing authorization.
        let configs = configs.iter().map(validate).collect::<Result<Vec<_>>>()?;
        let ids: Vec<String> = configs
            .iter()
            .map(|c| c["id"].as_str().unwrap().to_string())
            .collect();
        if ids.iter().collect::<HashSet<_>>().len() != ids.len() {
            return Err(invalid("duplicate listener ids in manifest"));
        }
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        for (c, id) in configs.iter().zip(&ids) {
            let repo = c["upstream"]["repository"].as_str().unwrap().to_lowercase();
            let reference = c["upstream"]["ref"].as_str().unwrap();
            let sid = digest(&json!([repo, reference]));
            let hash = digest(c);
            let old: Option<String> = tx
                .query_row("SELECT config_hash FROM listeners WHERE id=?", [id], |r| {
                    r.get(0)
                })
                .optional()?;
            if old.as_deref() == Some(hash.as_str()) {
                continue; // Re-import does not resume a manually paused listener.
            }
            if old.is_some() {
                let exists = |sql: &str| -> Result<bool> {
                    Ok(tx.query_row(sql, [id], |_| Ok(())).optional()?.is_some())
                };
                if exists("SELECT 1 FROM proposals WHERE listener_id=? AND state='open'")? {
                    return Err(invalid(
                        "close or merge the open proposal before changing its listener configuration",
                    ));
                }
                if exists(
                    "SELECT 1 FROM jobs WHERE listener_id=? AND (status IN ('running','delivering') OR (status='blocked' AND delivery IS NOT NULL))",
                )? {
                    return Err(invalid(
                        "listener has in-flight work; reconcile it before changing configuration",
                    ));
                }
            }
            tx.execute(
                "INSERT OR IGNORE INTO sources(id,repo,ref) VALUES(?,?,?)",
                params![sid, c["upstream"]["repository"].as_str(), reference],
            )?;
            tx.execute(
                "INSERT INTO listeners(id,source_id,config,config_hash,enabled,decided,updated)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET source_id=excluded.source_id,
                config=excluded.config,config_hash=excluded.config_hash,enabled=excluded.enabled,
                decided=excluded.decided,observed=NULL,adopted=NULL,updated=excluded.updated",
                params![
                    id,
                    sid,
                    canonical(c),
                    hash,
                    c["enabled"].as_bool() == Some(true),
                    c["upstream"]["baseline_commit"].as_str(),
                    now()
                ],
            )?;
            tx.execute(
                "UPDATE jobs SET status='superseded' WHERE listener_id=? AND status IN ('queued','retry','blocked')",
                [id],
            )?;
            tx.execute("UPDATE sources SET next_poll=0 WHERE id=?", [&sid])?;
        }
        tx.commit()?;
        Ok(ids)
    }

    pub fn enable(&self, listener_id: &str, enabled: bool) -> Result<()> {
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        if tx
            .query_row("SELECT 1 FROM listeners WHERE id=?", [listener_id], |_| {
                Ok(())
            })
            .optional()?
            .is_none()
        {
            return Err(invalid("unknown listener"));
        }
        tx.execute(
            "UPDATE listeners SET enabled=?,updated=? WHERE id=?",
            params![enabled, now(), listener_id],
        )?;
        if enabled {
            tx.execute(
                "UPDATE sources SET next_poll=0 WHERE id=(SELECT source_id FROM listeners WHERE id=?)",
                [listener_id],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    pub fn enqueue(&self, source_id: &str, head: &str) -> Result<()> {
        let now = now();
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        let listeners = collect(
            &tx,
            "SELECT * FROM listeners WHERE source_id=? AND enabled=1",
            [source_id],
        )?;
        for listener in listeners {
            let id = text(&listener, "id");
            tx.execute(
                "UPDATE listeners SET observed=? WHERE id=?",
                params![head, id],
            )?;
            if head == text(&listener, "decided") {
                continue;
            }
            // Do not replace an uncertain publication or restart a blocked generation.
            if tx
                .query_row(
                    "SELECT 1 FROM jobs WHERE listener_id=? AND status IN ('running','delivering','blocked')",
                    [&id],
                    |_| Ok(()),
                )
                .optional()?
                .is_some()
            {
                continue;
            }
            tx.execute(
                "UPDATE jobs SET status='superseded',updated=? WHERE listener_id=? AND status IN ('queued','retry') AND after_sha<>?",
                params![now, id, head],
            )?;
            tx.execute(
                "INSERT OR IGNORE INTO jobs(listener_id,config,config_hash,before_sha,after_sha,created,updated)
                VALUES(?,?,?,?,?,?,?)",
                params![
                    id,
                    text(&listener, "config"),
                    text(&listener, "config_hash"),
                    text(&listener, "decided"),
                    head,
                    now,
                    now
                ],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    pub fn set_job(&self, job_id: i64, status: &str, fields: &[(&str, Sql)]) -> Result<()> {
        const ALLOWED: [&str; 6] = [
            "reason",
            "evidence",
            "delivery",
            "attempts",
            "not_before",
            "before_sha",
        ];
        if fields.iter().any(|(k, _)| !ALLOWED.contains(k)) {
            return Err(invalid("invalid job fields"));
        }
        let mut names: Vec<&str> = fields.iter().map(|(k, _)| *k).collect();
        let mut values: Vec<Sql> = fields.iter().map(|(_, v)| v.clone()).collect();
        names.extend(["status", "updated"]);
        values.extend([Sql::Text(status.into()), Sql::Real(now())]);
        values.push(Sql::Integer(job_id));
        let assignments: Vec<String> = names.iter().map(|k| format!("{k}=?")).collect();
        self.execute(
            &format!("UPDATE jobs SET {} WHERE id=?", assignments.join(",")),
            rusqlite::params_from_iter(values),
        )?;
        Ok(())
    }

    pub fn finish(&self, job: &Row, status: &str, reason: &str, evidence: &Value) -> Result<()> {
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        tx.execute(
            "UPDATE jobs SET status=?,reason=?,evidence=?,updated=? WHERE id=?",
            params![status, reason, canonical(evidence), now(), int(job, "id")],
        )?;
        tx.execute(
            "UPDATE listeners SET decided=? WHERE id=? AND config_hash=?",
            params![
                text(job, "after_sha"),
                text(job, "listener_id"),
                text(job, "config_hash")
            ],
        )?;
        tx.commit()?;
        Ok(())
    }

    pub fn cache_blob(&self, repo: &str, sha: &str, content: &str) -> Result<()> {
        let mut conn = self.connect()?;
        let tx = conn.transaction()?;
        if tx.execute(
            "INSERT OR IGNORE INTO blobs VALUES(?,?,?)",
            params![repo, sha, content],
        )? > 0
        {
            tx.execute(
                "INSERT INTO blob_search(repo,sha,content) VALUES(?,?,?)",
                params![repo, sha, content],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    pub fn search(&self, query: &str, repository: &str) -> Result<Vec<Row>> {
        self.rows(
            "SELECT repo,sha,snippet(blob_search,2,'[',']','…',24) AS excerpt
            FROM blob_search WHERE blob_search MATCH ? AND repo=? LIMIT 20",
            params![query, repository],
        )
    }

    pub fn status(&self) -> Result<Value> {
        Ok(json!({
            "sources": self.rows("SELECT * FROM sources", [])?,
            "listeners": self.rows(
                "SELECT id,source_id,enabled,observed,decided,adopted,updated FROM listeners", [])?,
            "jobs": self.rows(
                "SELECT id,listener_id,status,after_sha,attempts,reason,updated FROM jobs ORDER BY id DESC LIMIT 100", [])?,
            "proposals": self.rows("SELECT * FROM proposals", [])?,
            "cache": self.one(
                "SELECT (SELECT count(*) FROM changes) AS changes, (SELECT count(*) FROM blobs) AS blobs", [])?,
        }))
    }
}
