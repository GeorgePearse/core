//! A serial, restartable coordinator. SQLite persists work; flock excludes competing workers.

use crate::anchors;
use crate::config::{canonical, digest, safe_path, strings, truthy};
use crate::db::{Row, Store, int, now, opt_text, text};
use crate::error::{Error, Result, blocked, other};
use crate::git::Git;
use crate::github::GitHubApi;
use crate::model::{Adapter, Tools};
use crate::validation::{DockerValidator, Validator};
use rusqlite::params;
use rusqlite::types::Value as Sql;
use serde_json::{Value, json};
use std::fs::File;
use std::os::fd::AsRawFd;
use std::path::PathBuf;
use std::sync::Arc;

pub const START: &str = "<!-- memetics:start -->";
pub const END: &str = "<!-- memetics:end -->";

pub struct WorkerLock(File);

impl Drop for WorkerLock {
    fn drop(&mut self) {
        unsafe { libc::flock(self.0.as_raw_fd(), libc::LOCK_UN) };
    }
}

pub struct Engine {
    pub store: Store,
    pub github: Arc<dyn GitHubApi>,
    pub model: Arc<dyn Adapter>,
    pub validator: Arc<dyn Validator>,
    pub git: Git,
    pub poll_seconds: f64,
    pub daily_calls: i64,
}

fn sql_text(value: impl Into<String>) -> Sql {
    Sql::Text(value.into())
}

fn char_tail(text: &str, n: usize) -> String {
    let count = text.chars().count();
    text.chars().skip(count.saturating_sub(n)).collect()
}

/// Upstream symbols whose normalised hash differs between the change's before and after files.
pub fn changed_symbols(change: &Value, symbols: &[String]) -> Vec<Value> {
    let files = change["files"].as_array().cloned().unwrap_or_default();
    let side = |key: &str, path_key: &str| -> Vec<anchors::Symbol> {
        files
            .iter()
            .filter_map(|f| {
                Some((
                    f[path_key].as_str()?.to_string(),
                    f[key].as_str()?.to_string(),
                ))
            })
            .flat_map(|(path, content)| anchors::symbols(&path, &content))
            .collect()
    };
    let before = side("before", "previous_path");
    let after = side("after", "path");
    let mut changed = Vec::new();
    for name in symbols {
        let old = anchors::find(&before, name);
        let new = anchors::find(&after, name)
            .or_else(|| old.and_then(|o| after.iter().find(|s| s.hash == o.hash)));
        match (old, new) {
            (None, None) => {}
            (Some(o), Some(n)) if o.hash == n.hash => {}
            (o, n) => changed.push(json!({
                "symbol": name,
                "before": o.map(|s| s.text.clone()),
                "after": n.map(|s| s.text.clone()),
                "before_hash": o.map(|s| s.hash.clone()),
                "after_hash": n.map(|s| s.hash.clone()),
            })),
        }
    }
    changed
}

struct JobTools<'a> {
    engine: &'a Engine,
    job_id: i64,
    mirror: Option<PathBuf>,
    after: String,
    checkout: PathBuf,
    config: Value,
}

impl Tools for JobTools<'_> {
    fn charge(&mut self) -> Result<()> {
        let count = self.engine.store.one(
            "SELECT count(*) AS n FROM model_calls WHERE started>?",
            [now() - 86400.0],
        )?;
        if count.map(|r| int(&r, "n")).unwrap_or(0) >= self.engine.daily_calls {
            return Err(other("daily model call budget reached during adaptation"));
        }
        self.engine.store.execute(
            "INSERT INTO model_calls VALUES(?,?)",
            params![self.job_id, now()],
        )?;
        Ok(())
    }

    fn read_upstream(&mut self, path: &str) -> Result<String> {
        safe_path(path)?;
        let mirror = self
            .mirror
            .as_ref()
            .ok_or_else(|| other("upstream mirror unavailable"))?;
        let spec = format!("{}:{path}", self.after);
        let size = self
            .engine
            .git
            .run(&["cat-file", "-s", &spec], Some(mirror), true)?
            .text();
        if size.trim().parse::<u64>().unwrap_or(u64::MAX) > 100_000 {
            return Err(other("file exceeds the 100 KB lookup limit"));
        }
        let data = self
            .engine
            .git
            .run(&["cat-file", "blob", &spec], Some(mirror), true)?
            .stdout;
        String::from_utf8(data).map_err(|_| other("binary file"))
    }

    fn read_destination(&mut self, path: &str) -> Result<String> {
        safe_path(path)?;
        let file = self.checkout.join(path);
        let meta = file.symlink_metadata()?;
        if !meta.is_file() || meta.len() > 100_000 {
            return Err(other("not a regular file under 100 KB"));
        }
        String::from_utf8(std::fs::read(file)?).map_err(|_| other("binary file"))
    }

    fn search_destination(&mut self, query: &str) -> Result<String> {
        if query.trim().is_empty() {
            return Err(other("empty query"));
        }
        let out = self
            .engine
            .git
            .run(
                &["grep", "-n", "-I", "-F", "-e", query],
                Some(&self.checkout),
                false,
            )?
            .text();
        Ok(out.lines().take(200).collect::<Vec<_>>().join("\n"))
    }

    fn validate(&mut self, changes: &Value) -> Result<Value> {
        let outcome = self
            .engine
            .git
            .apply(&self.checkout, changes, &self.config)
            .and_then(|_| self.engine.validator.run(&self.checkout, &self.config));
        self.engine.git.run(
            &["reset", "-q", "--hard", "HEAD"],
            Some(&self.checkout),
            true,
        )?;
        self.engine
            .git
            .run(&["clean", "-fdq"], Some(&self.checkout), true)?;
        let result = outcome?;
        let results: Vec<Value> = result["results"]
            .as_array()
            .into_iter()
            .flatten()
            .map(|r| {
                json!({"command": r["command"], "exit_code": r["exit_code"],
                "output": char_tail(r["output"].as_str().unwrap_or_default(), 4000)})
            })
            .collect();
        Ok(json!({"passed": result["passed"], "results": results}))
    }
}

impl Engine {
    pub fn new(
        store: Store,
        github: Arc<dyn GitHubApi>,
        model: Arc<dyn Adapter>,
        validator: Option<Arc<dyn Validator>>,
        poll_seconds: i64,
        daily_calls: i64,
    ) -> Result<Self> {
        store.execute(
            "CREATE TABLE IF NOT EXISTS model_calls(job_id INTEGER, started REAL NOT NULL)",
            [],
        )?;
        Ok(Engine {
            git: Git::new(store.clone(), github.clone())?,
            store,
            github,
            model,
            validator: validator.unwrap_or_else(|| Arc::new(DockerValidator)),
            poll_seconds: poll_seconds.max(10) as f64,
            daily_calls,
        })
    }

    pub fn lock(&self) -> Result<WorkerLock> {
        let file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(self.store.root.join("worker.lock"))?;
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(other("another Memetics worker is already running"));
        }
        Ok(WorkerLock(file))
    }

    fn authorized(&self, job: &Row) -> Result<Row> {
        let listener = self.store.one(
            "SELECT * FROM listeners WHERE id=?",
            [text(job, "listener_id")],
        )?;
        match listener {
            Some(l)
                if int(&l, "enabled") != 0
                    && text(&l, "config_hash") == text(job, "config_hash") =>
            {
                Ok(l)
            }
            _ => Err(blocked(
                "listener paused or changed during adaptation; publication stopped",
            )),
        }
    }

    fn private(&self, repo: &str) -> Result<bool> {
        Ok(self.github.metadata(repo)?["private"]
            .as_bool()
            .unwrap_or(true))
    }

    pub fn poll(&self, force: bool) -> Result<()> {
        let sources = self.store.rows(
            "SELECT * FROM sources s WHERE EXISTS
            (SELECT 1 FROM listeners l WHERE l.source_id=s.id AND l.enabled=1)",
            [],
        )?;
        for source in sources {
            let id = text(&source, "id");
            let mut head = opt_text(&source, "head");
            if force || source["next_poll"].as_f64().unwrap_or(0.0) <= now() {
                let polled = self
                    .github
                    .head(&text(&source, "repo"), &text(&source, "ref"), opt_text(&source, "etag").as_deref())
                    .and_then(|(new_head, etag)| {
                        head = new_head.or(head.clone());
                        if head.is_none() {
                            return Err(other("conditional response without a saved upstream revision"));
                        }
                        self.store.execute(
                            "UPDATE sources SET head=?,etag=?,next_poll=?,error=NULL,polls=polls+1 WHERE id=?",
                            params![head, etag, now() + self.poll_seconds, id],
                        )?;
                        Ok(())
                    });
                if let Err(e) = polled {
                    let delay = self.poll_seconds.max(e.retry_after().unwrap_or(60) as f64);
                    self.store.execute(
                        "UPDATE sources SET error=?,next_poll=? WHERE id=?",
                        params![e.to_string(), now() + delay, id],
                    )?;
                    continue;
                }
            }
            if let Some(head) = head {
                // New registrations catch up even when the shared source returned 304.
                self.store.enqueue(&id, &head)?;
            }
        }
        Ok(())
    }

    pub fn reconcile(&self) -> Result<()> {
        for proposal in self
            .store
            .rows("SELECT * FROM proposals WHERE state='open'", [])?
        {
            let listener_id = text(&proposal, "listener_id");
            let result = (|| -> Result<()> {
                let pr = self
                    .github
                    .pull(&text(&proposal, "repo"), int(&proposal, "number"))?;
                if pr["state"] != "closed" {
                    return Ok(());
                }
                let state = if truthy(pr.get("merged_at")) {
                    if pr["head"]["sha"].as_str() == Some(&text(&proposal, "head_sha")) {
                        "adopted"
                    } else {
                        "modified"
                    }
                } else {
                    "declined"
                };
                let mut conn = self.store.connect()?;
                let tx = conn.transaction()?;
                tx.execute(
                    "UPDATE proposals SET state=? WHERE listener_id=?",
                    params![state, listener_id],
                )?;
                tx.execute(
                    "UPDATE jobs SET status=?,updated=? WHERE listener_id=? AND status='proposed'",
                    params![state, now(), listener_id],
                )?;
                if state == "adopted" {
                    tx.execute(
                        "UPDATE listeners SET adopted=? WHERE id=?",
                        params![text(&proposal, "upstream_sha"), listener_id],
                    )?;
                }
                tx.commit()?;
                Ok(())
            })();
            if let Err(e) = result {
                // A failed read must not be treated as a closed or missing PR.
                self.store.execute(
                    "UPDATE sources SET error=? WHERE id=(SELECT source_id FROM listeners WHERE id=?)",
                    params![format!("PR reconciliation: {e}"), listener_id],
                )?;
            }
        }
        Ok(())
    }

    pub fn tick(&self, max_jobs: i64, force: bool) -> Result<Value> {
        let _lock = self.lock()?;
        // No other worker owns these jobs after acquiring the process lock.
        self.store.execute(
            "UPDATE jobs SET status='retry',reason='worker interrupted before publication' WHERE status='running'",
            [],
        )?;
        self.reconcile()?;
        self.poll(force)?;
        let jobs = self.store.rows(
            "SELECT j.* FROM jobs j JOIN listeners l ON l.id=j.listener_id
            WHERE l.enabled=1 AND j.status IN ('queued','retry','delivering') AND j.not_before<=?
            ORDER BY j.id LIMIT ?",
            params![now(), max_jobs],
        )?;
        for job in jobs {
            self.work(&job)?;
        }
        self.store.status()
    }

    fn work(&self, job: &Row) -> Result<()> {
        let id = int(job, "id");
        let attempts = int(job, "attempts") + 1;
        if attempts > 3 {
            return self.store.set_job(
                id,
                "blocked",
                &[(
                    "reason",
                    sql_text("retry budget exhausted; inspect the job before retrying"),
                )],
            );
        }
        let has_delivery = opt_text(job, "delivery").is_some();
        self.store.set_job(
            id,
            if has_delivery {
                "delivering"
            } else {
                "running"
            },
            &[("attempts", Sql::Integer(attempts))],
        )?;
        match self.attempt(job) {
            Ok(()) => Ok(()),
            Err(Error::Blocked(reason)) => {
                self.store
                    .set_job(id, "blocked", &[("reason", sql_text(reason))])
            }
            Err(e) => {
                let saved = self
                    .store
                    .one("SELECT delivery FROM jobs WHERE id=?", [id])?;
                let delivering = saved.is_some_and(|r| opt_text(&r, "delivery").is_some());
                let wait = (30 * attempts).max(e.retry_after().unwrap_or(0)) as f64;
                self.store.set_job(
                    id,
                    if delivering { "delivering" } else { "retry" },
                    &[
                        ("reason", sql_text(e.to_string())),
                        ("not_before", Sql::Real(now() + wait)),
                    ],
                )
            }
        }
    }

    fn attempt(&self, job: &Row) -> Result<()> {
        let id = int(job, "id");
        self.authorized(job)?;
        if let Some(delivery) = opt_text(job, "delivery") {
            return self.deliver(job, serde_json::from_str(&delivery)?);
        }
        let config: Value = serde_json::from_str(&text(job, "config"))?;
        let source_repo = config["upstream"]["repository"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        let destination = &config["destination"];
        let dest_repo = destination["repository"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        let base_ref = destination["base_ref"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        if self.private(&source_repo)? && !self.private(&dest_repo)? {
            return Err(blocked(
                "private upstream evidence cannot be published to a public destination",
            ));
        }
        let proposal = self.store.one(
            "SELECT * FROM proposals WHERE listener_id=? AND state='open'",
            [text(job, "listener_id")],
        )?;
        if let Some(p) = &proposal {
            let pr = self.github.pull(&text(p, "repo"), int(p, "number"))?;
            if pr["state"] != "open"
                || pr["head"]["sha"].as_str() != Some(&text(p, "head_sha"))
                || pr["base"]["ref"].as_str() != Some(&base_ref)
            {
                return Err(blocked(
                    "open proposal changed outside Memetics; reconcile before updating",
                ));
            }
            if self
                .git
                .remote_head(&dest_repo, &text(p, "branch"))?
                .as_deref()
                != Some(&text(p, "head_sha"))
            {
                return Err(blocked(
                    "proposal branch has human edits; refusing to overwrite",
                ));
            }
        }
        let (before_sha, after_sha) = (text(job, "before_sha"), text(job, "after_sha"));
        let change = self.git.change(&source_repo, &before_sha, &after_sha)?;
        if change["files"].as_array().is_none_or(|f| f.is_empty()) {
            return self
                .store
                .finish(job, "irrelevant", "upstream tree did not change", &change);
        }
        let symbols = strings(config["upstream"].get("symbols"));
        let changed = changed_symbols(&change, &symbols);
        if !symbols.is_empty() && changed.is_empty() {
            let reason = format!(
                "anchored upstream symbols unchanged: {}",
                symbols.join(", ")
            );
            return self.store.finish(job, "unchanged", &reason, &json!({
                "upstream_before": before_sha, "upstream_after": after_sha,
                "changed_files": change["files"].as_array().map(|f| f.iter().map(|x| x["path"].clone()).collect::<Vec<_>>()),
            }));
        }
        let base = self
            .github
            .head(&dest_repo, &base_ref, None)?
            .0
            .ok_or_else(|| other("destination base revision unavailable"))?;
        let path = self
            .git
            .checkout(id, &dest_repo, &base, proposal.as_ref())?;
        let files = self.git.context(&path, &config)?;
        let decisions = self.store.rows(
            "SELECT after_sha,status,reason FROM jobs WHERE listener_id=?
            AND status IN ('declined','irrelevant','already_present','adopted','unchanged') ORDER BY id DESC LIMIT 20",
            [text(job, "listener_id")],
        )?;
        let count = self
            .store
            .one(
                "SELECT count(*) AS n FROM model_calls WHERE started>?",
                [now() - 86400.0],
            )?
            .map(|r| int(&r, "n"))
            .unwrap_or(0);
        if count >= self.daily_calls {
            // Budget waiting is not a model attempt or a blocked listener.
            return self.store.set_job(
                id,
                "retry",
                &[
                    ("attempts", Sql::Integer(int(job, "attempts"))),
                    ("not_before", Sql::Real(now() + 3600.0)),
                    ("reason", sql_text("daily model call budget reached")),
                ],
            );
        }
        let mut context = json!({
            "listener": config,
            "upstream_change": change,
            "destination_base": base,
            "destination_files": files,
            "prior_decisions": decisions,
        });
        if !symbols.is_empty() {
            context["changed_symbols"] = Value::Array(changed.clone());
        }
        let mut tools = JobTools {
            engine: self,
            job_id: id,
            mirror: self.git.mirror(&source_repo, &after_sha).ok(),
            after: after_sha.clone(),
            checkout: path.clone(),
            config: config.clone(),
        };
        let decision = self.model.adapt(&context, &mut tools)?;
        let mut evidence = json!({
            "upstream_before": before_sha,
            "upstream_after": after_sha,
            "destination_base": base,
            "model_decision": decision,
        });
        if !symbols.is_empty() {
            evidence["changed_symbols"] = changed
                .iter()
                .map(|c| c["symbol"].clone())
                .collect::<Vec<_>>()
                .into();
        }
        self.authorized(job)?;
        let verdict = decision["decision"].as_str().unwrap_or_default();
        let reason = decision["reason"].as_str().unwrap_or_default();
        if verdict == "blocked" {
            return self.store.set_job(
                id,
                "blocked",
                &[
                    ("reason", sql_text(reason)),
                    ("evidence", sql_text(canonical(&evidence))),
                ],
            );
        }
        if verdict != "adapt" {
            return self.store.finish(job, verdict, reason, &evidence);
        }
        self.git.apply(
            &path,
            decision.get("changes").unwrap_or(&Value::Null),
            &config,
        )?;
        evidence["validation"] = self.validator.run(&path, &config)?;
        self.authorized(job)?;
        let listener_id = text(job, "listener_id");
        let commit = self.git.commit(&path, &listener_id)?;
        let branch = match &proposal {
            Some(p) => text(p, "branch"),
            None => format!(
                "memetics/{}-{}",
                &digest(&json!([listener_id, text(job, "config_hash")]))[..12],
                &after_sha[..12.min(after_sha.len())]
            ),
        };
        let delivery = json!({
            "repo": dest_repo,
            "base_ref": base_ref,
            "base_sha": base,
            "branch": branch,
            "commit": commit,
            "expected": proposal.as_ref().map(|p| text(p, "head_sha")),
            "workdir": path.to_string_lossy(),
            "evidence": evidence,
            "prior_number": proposal.as_ref().map(|p| int(p, "number")),
        });
        // Persist the entire intent before the first external write.
        self.store.set_job(
            id,
            "delivering",
            &[
                ("delivery", sql_text(canonical(&delivery))),
                ("evidence", sql_text(canonical(&evidence))),
            ],
        )?;
        self.deliver(job, delivery)
    }

    pub fn body(&self, job: &Row, delivery: &Value) -> String {
        let evidence = &delivery["evidence"];
        let config: Value = serde_json::from_str(&text(job, "config")).unwrap_or_default();
        let repo = config["upstream"]["repository"]
            .as_str()
            .unwrap_or_default();
        let checks = &evidence["validation"];
        let reason: String = evidence["model_decision"]["reason"]
            .as_str()
            .unwrap_or_default()
            .chars()
            .take(5000)
            .collect();
        let mut lines = vec![
            START.to_string(),
            format!("Listener: `{}`", text(job, "listener_id")),
            String::new(),
            config["concern"].as_str().unwrap_or_default().to_string(),
            String::new(),
            format!("Upstream: [{repo}](https://github.com/{repo})"),
            format!(
                "[Implementation comparison](https://github.com/{repo}/compare/{}...{})",
                text(job, "before_sha"),
                text(job, "after_sha")
            ),
            format!(
                "Destination base: `{}`",
                delivery["base_sha"].as_str().unwrap_or_default()
            ),
        ];
        if let Some(symbols) = evidence["changed_symbols"]
            .as_array()
            .filter(|s| !s.is_empty())
        {
            let names: Vec<String> = symbols
                .iter()
                .filter_map(|s| s.as_str())
                .map(|s| format!("`{s}`"))
                .collect();
            lines.push(format!("Changed upstream symbols: {}", names.join(", ")));
        }
        lines.extend([
            String::new(),
            reason,
            String::new(),
            format!(
                "Validation: **{}**",
                if checks["passed"] == json!(true) {
                    "passed"
                } else {
                    "BLOCKED — checks failed or unavailable"
                }
            ),
            format!(
                "Runner: Docker, image `{}`; network disabled.",
                checks["image"].as_str().unwrap_or_default()
            ),
        ]);
        for result in checks["results"].as_array().into_iter().flatten() {
            let code = match &result["exit_code"] {
                Value::Null => "None".to_string(),
                v => v.to_string(),
            };
            lines.extend([
                String::new(),
                format!(
                    "- `{}` → exit {code}",
                    result["command"].as_str().unwrap_or_default()
                ),
                "<details><summary>Output (tail)</summary>".into(),
                String::new(),
                "```text".into(),
                char_tail(result["output"].as_str().unwrap_or_default(), 3000)
                    .replace("```", "` ` `"),
                "```".into(),
                "</details>".into(),
            ]);
        }
        lines.extend([
            String::new(),
            "Generated from pinned source evidence. Review the adaptation and any intentional deviations before merging.".into(),
            format!("Durable run: `{}`. Requested by the owner who registered this listener.", int(job, "id")),
            END.into(),
        ]);
        lines.join("\n")
    }

    fn deliver(&self, job: &Row, mut delivery: Value) -> Result<()> {
        self.authorized(job)?;
        let config: Value = serde_json::from_str(&text(job, "config"))?;
        let repo = delivery["repo"].as_str().unwrap_or_default().to_string();
        let branch = delivery["branch"].as_str().unwrap_or_default().to_string();
        let base_ref = delivery["base_ref"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        // Recheck visibility immediately before publishing retained source evidence.
        if self.private(
            config["upstream"]["repository"]
                .as_str()
                .unwrap_or_default(),
        )? && !self.private(&repo)?
        {
            return Err(blocked(
                "destination visibility would expose private source evidence",
            ));
        }
        let path = PathBuf::from(delivery["workdir"].as_str().unwrap_or_default());
        if !path.exists() {
            return Err(blocked(
                "retained checkout is missing; inspect remote publication before recovery",
            ));
        }
        let has_section = |pr: &Value| {
            let body = pr["body"].as_str().unwrap_or_default();
            body.contains(START) && body.contains(END)
        };
        if let Some(existing) = self.github.find_pull(&repo, &branch)? {
            if existing["state"] == "closed" {
                // A lost create response followed by a human close must not reopen the PR.
                self.record_proposal(job, &delivery, &existing)?;
                return self.reconcile();
            }
            if existing["base"]["ref"].as_str() != Some(&base_ref) {
                return Err(blocked("proposal base branch changed outside Memetics"));
            }
            if !has_section(&existing) {
                return Err(blocked(
                    "generated PR section was removed; preserve the human-edited body",
                ));
            }
        }
        let latest = self
            .github
            .head(&repo, &base_ref, None)?
            .0
            .ok_or_else(|| other("destination base revision unavailable"))?;
        if Some(latest.as_str()) != delivery["base_sha"].as_str() {
            let remote = self.git.remote_head(&repo, &branch)?;
            let known = [delivery["expected"].as_str(), delivery["commit"].as_str()];
            if !known.contains(&remote.as_deref()) {
                return Err(blocked(
                    "proposal branch changed while destination base advanced",
                ));
            }
            self.git
                .run(&["fetch", "origin", &latest], Some(&path), true)?;
            if self
                .git
                .run(&["merge", "--no-edit", &latest], Some(&path), false)?
                .code
                != Some(0)
            {
                return Err(blocked("new destination base conflicts with adaptation"));
            }
            delivery["base_sha"] = latest.clone().into();
            delivery["evidence"]["destination_base"] = latest.into();
            delivery["evidence"]["validation"] = self.validator.run(&path, &config)?;
            delivery["expected"] = remote.into();
            delivery["commit"] = self
                .git
                .run(&["rev-parse", "HEAD"], Some(&path), true)?
                .text()
                .trim()
                .into();
            self.store.set_job(
                int(job, "id"),
                "delivering",
                &[
                    ("delivery", sql_text(canonical(&delivery))),
                    ("evidence", sql_text(canonical(&delivery["evidence"]))),
                ],
            )?;
        }
        self.authorized(job)?;
        let commit = delivery["commit"].as_str().unwrap_or_default().to_string();
        self.git.publish(
            &path,
            &repo,
            &branch,
            &commit,
            delivery["expected"].as_str(),
        )?;
        let body = self.body(job, &delivery);
        let pr = match self.github.find_pull(&repo, &branch)? {
            Some(existing) => {
                if existing["state"] != "open" {
                    self.record_proposal(job, &delivery, &existing)?;
                    return self.reconcile();
                }
                if !has_section(&existing) {
                    return Err(blocked(
                        "generated PR section was removed; preserve the human-edited body",
                    ));
                }
                let old = existing["body"].as_str().unwrap_or_default();
                let before = old.split_once(START).map(|(b, _)| b).unwrap_or_default();
                let after = old.split_once(END).map(|(_, a)| a).unwrap_or_default();
                self.github.update_pull(
                    &repo,
                    int_value(&existing["number"]),
                    &format!("{before}{body}{after}"),
                )?
            }
            None => {
                let title: String = format!("feat: follow upstream {}", text(job, "listener_id"))
                    .chars()
                    .take(120)
                    .collect();
                self.github
                    .create_pull(&repo, &branch, &base_ref, &title, &body)?
            }
        };
        self.record_proposal(job, &delivery, &pr)
    }

    fn record_proposal(&self, job: &Row, delivery: &Value, pr: &Value) -> Result<()> {
        let url = pr["html_url"].as_str().unwrap_or_default();
        let listener_id = text(job, "listener_id");
        let mut conn = self.store.connect()?;
        let tx = conn.transaction()?;
        tx.execute(
            "INSERT INTO proposals(listener_id,repo,number,url,branch,head_sha,upstream_sha,state)
            VALUES(?,?,?,?,?,?,?,'open') ON CONFLICT(listener_id) DO UPDATE SET repo=excluded.repo,
            number=excluded.number,url=excluded.url,branch=excluded.branch,head_sha=excluded.head_sha,
            upstream_sha=excluded.upstream_sha,state='open'",
            params![
                listener_id,
                delivery["repo"].as_str(),
                int_value(&pr["number"]),
                url,
                delivery["branch"].as_str(),
                delivery["commit"].as_str(),
                text(job, "after_sha")
            ],
        )?;
        tx.execute(
            "UPDATE jobs SET status='proposed',reason=?,updated=? WHERE id=?",
            params![url, now(), int(job, "id")],
        )?;
        tx.execute(
            "UPDATE listeners SET decided=? WHERE id=?",
            params![text(job, "after_sha"), listener_id],
        )?;
        tx.commit()?;
        Ok(())
    }
}

fn int_value(value: &Value) -> i64 {
    value.as_i64().unwrap_or_default()
}
