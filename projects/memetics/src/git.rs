//! Immutable upstream cache and isolated destination checkouts.

use crate::config::{canonical, digest, in_scope, safe_path, strings, write_scopes};
use crate::db::{Row, Store, text};
use crate::error::{Result, blocked, other};
use crate::github::GitHubApi;
use serde_json::{Map, Value, json};
use std::collections::BTreeSet;
use std::io::{Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::time::Duration;
use wait_timeout::ChildExt;

pub fn clean_env() -> Vec<(String, String)> {
    std::env::vars()
        .filter(|(k, _)| {
            ["PATH", "HOME", "LANG", "SSL_CERT_FILE", "SSL_CERT_DIR"].contains(&k.as_str())
        })
        .collect()
}

pub struct Output {
    /// `None` when the process was killed by a signal or timed out.
    pub code: Option<i32>,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
}

impl Output {
    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.stdout).into_owned()
    }
}

/// Run with captured output, optional stdin, and a hard deadline.
pub fn run_with_timeout(
    command: &mut Command,
    timeout: Duration,
    input: Option<&[u8]>,
) -> Result<Output> {
    command
        .stdin(if input.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command.spawn()?;
    if let Some(data) = input {
        let mut stdin = child.stdin.take().unwrap();
        let data = data.to_vec();
        std::thread::spawn(move || {
            let _ = stdin.write_all(&data);
        });
    }
    let mut out = child.stdout.take().unwrap();
    let mut err = child.stderr.take().unwrap();
    let out_thread = std::thread::spawn(move || {
        let mut buffer = Vec::new();
        let _ = out.read_to_end(&mut buffer);
        buffer
    });
    let err_thread = std::thread::spawn(move || {
        let mut buffer = Vec::new();
        let _ = err.read_to_end(&mut buffer);
        buffer
    });
    let status = match child.wait_timeout(timeout)? {
        Some(status) => status,
        None => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(other(format!(
                "command timed out after {} seconds",
                timeout.as_secs()
            )));
        }
    };
    Ok(Output {
        code: status.code(),
        stdout: out_thread.join().unwrap_or_default(),
        stderr: err_thread.join().unwrap_or_default(),
    })
}

fn has_symlink_within(root: &Path, relative: &str) -> bool {
    let mut current = root.to_path_buf();
    for part in relative.split('/').filter(|p| !p.is_empty() && *p != ".") {
        current.push(part);
        if current
            .symlink_metadata()
            .is_ok_and(|m| m.file_type().is_symlink())
        {
            return true;
        }
    }
    false
}

pub struct Git {
    pub store: Store,
    pub github: Arc<dyn GitHubApi>,
    askpass: PathBuf,
}

impl Git {
    pub fn new(store: Store, github: Arc<dyn GitHubApi>) -> Result<Self> {
        let askpass = store.root.join("askpass.sh");
        std::fs::write(
            &askpass,
            "#!/bin/sh\ncase \"$1\" in *Username*) printf \"%s\\n\" x-access-token;; *) printf \"%s\\n\" \"$MEMETICS_GIT_TOKEN\";; esac\n",
        )?;
        std::fs::set_permissions(&askpass, std::fs::Permissions::from_mode(0o700))?;
        Ok(Git {
            store,
            github,
            askpass,
        })
    }

    pub fn run(&self, args: &[&str], cwd: Option<&Path>, check: bool) -> Result<Output> {
        let mut command = Command::new("git");
        command
            .arg("-c")
            .arg("core.hooksPath=/dev/null")
            .args(args)
            .env_clear()
            .envs(clean_env())
            .env("GIT_CONFIG_GLOBAL", "/dev/null")
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_TERMINAL_PROMPT", "0")
            .env("GIT_ASKPASS", &self.askpass)
            .env("MEMETICS_GIT_TOKEN", self.github.token()?)
            .env("GIT_AUTHOR_NAME", "Memetics")
            .env("GIT_AUTHOR_EMAIL", "memetics@users.noreply.github.com")
            .env("GIT_COMMITTER_NAME", "Memetics")
            .env("GIT_COMMITTER_EMAIL", "memetics@users.noreply.github.com");
        if let Some(dir) = cwd {
            command.current_dir(dir);
        }
        let out = run_with_timeout(&mut command, Duration::from_secs(180), None)?;
        if check && out.code != Some(0) {
            let error = String::from_utf8_lossy(&out.stderr);
            let tail: String = error
                .chars()
                .rev()
                .take(1500)
                .collect::<Vec<_>>()
                .into_iter()
                .rev()
                .collect();
            return Err(other(format!("git {} failed: {tail}", args[0])));
        }
        Ok(out)
    }

    fn ok(&self, args: &[&str], cwd: &Path) -> Result<bool> {
        Ok(self.run(args, Some(cwd), false)?.code == Some(0))
    }

    pub fn mirror(&self, repo: &str, sha: &str) -> Result<PathBuf> {
        let path = self
            .store
            .root
            .join("mirrors")
            .join(digest(&json!(repo.to_lowercase())));
        if !path.exists() {
            std::fs::create_dir_all(path.parent().unwrap())?;
            self.run(&["init", "--bare", path.to_str().unwrap()], None, true)?;
            self.run(
                &["remote", "add", "origin", &self.github.remote(repo)],
                Some(&path),
                true,
            )?;
        }
        if !self.ok(&["cat-file", "-e", &format!("{sha}^{{commit}}")], &path)? {
            self.run(
                &["fetch", "--filter=blob:none", "--no-tags", "origin", sha],
                Some(&path),
                true,
            )?;
        }
        Ok(path)
    }

    pub fn blob(&self, repo: &str, mirror: &Path, sha: &str) -> Result<String> {
        if let Some(found) = self.store.one(
            "SELECT content FROM blobs WHERE repo=? AND sha=?",
            rusqlite::params![repo, sha],
        )? {
            return Ok(text(&found, "content"));
        }
        let size: u64 = self
            .run(&["cat-file", "-s", sha], Some(mirror), true)?
            .text()
            .trim()
            .parse()
            .map_err(|_| other("unreadable blob size"))?;
        if size > 100_000 {
            return Err(blocked("changed file exceeds the 100 KB context limit"));
        }
        let data = self
            .run(&["cat-file", "blob", sha], Some(mirror), true)?
            .stdout;
        let content = String::from_utf8(data)
            .map_err(|_| blocked("binary change needs manual assessment"))?;
        if content.contains('\0') {
            return Err(blocked("binary change needs manual assessment"));
        }
        self.store.cache_blob(repo, sha, &content)?;
        Ok(content)
    }

    fn file_at(
        &self,
        repo: &str,
        mirror: &Path,
        commit: &str,
        path: &str,
    ) -> Result<Option<String>> {
        let tree = self
            .run(&["ls-tree", "-z", commit, "--", path], Some(mirror), true)?
            .text();
        if tree.is_empty() {
            return Ok(None);
        }
        let meta: Vec<&str> = tree
            .split('\t')
            .next()
            .unwrap_or_default()
            .split_whitespace()
            .collect();
        let [mode, kind, sha] = meta[..] else {
            return Err(other("unexpected ls-tree output"));
        };
        if kind != "blob" || mode == "120000" {
            return Err(blocked(
                "changed symlink or submodule requires manual assessment",
            ));
        }
        self.blob(repo, mirror, sha).map(Some)
    }

    pub fn change(&self, repo: &str, before: &str, after: &str) -> Result<Value> {
        let key = digest(&json!([repo.to_lowercase(), before, after]));
        if let Some(cached) = self
            .store
            .one("SELECT data FROM changes WHERE id=?", [&key])?
        {
            return Ok(serde_json::from_str(&text(&cached, "data"))?);
        }
        let mirror = self.mirror(repo, before)?;
        self.mirror(repo, after)?;
        if !self.ok(&["merge-base", "--is-ancestor", before, after], &mirror)? {
            return Err(blocked(
                "upstream history diverged; register a reconciled baseline",
            ));
        }
        let output = self
            .run(
                &[
                    "diff",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--name-status",
                    "-z",
                    "-M",
                    before,
                    after,
                    "--",
                ],
                Some(&mirror),
                true,
            )?
            .text();
        let parts: Vec<&str> = output.trim_end_matches('\0').split('\0').collect();
        let mut files: Vec<Value> = Vec::new();
        let mut i = 0;
        while i + 1 < parts.len() && !parts[i].is_empty() {
            let status = parts[i];
            let old = parts[i + 1];
            let mut path = old;
            i += 2;
            if status.starts_with('R') || status.starts_with('C') {
                path = parts.get(i).copied().unwrap_or_default();
                i += 1;
            }
            files.push(json!({
                "status": status,
                "path": path,
                "previous_path": old,
                "before": self.file_at(repo, &mirror, before, old)?,
                "after": self.file_at(repo, &mirror, after, path)?,
            }));
            if files.len() > 100 || canonical(&Value::Array(files.clone())).len() > 300_000 {
                return Err(blocked(
                    "upstream change exceeds bounded context; narrow the baseline after review",
                ));
            }
        }
        let result = json!({"repository": repo, "before": before, "after": after, "files": files});
        self.store.execute(
            "INSERT OR IGNORE INTO changes VALUES(?,?,?,?,?,?)",
            rusqlite::params![
                key,
                repo,
                before,
                after,
                canonical(&result),
                crate::db::now()
            ],
        )?;
        Ok(result)
    }

    pub fn remote_head(&self, repo: &str, branch: &str) -> Result<Option<String>> {
        let output = self
            .run(
                &[
                    "ls-remote",
                    "--heads",
                    &self.github.remote(repo),
                    &format!("refs/heads/{branch}"),
                ],
                None,
                true,
            )?
            .text();
        Ok(output.split_whitespace().next().map(String::from))
    }

    pub fn checkout(
        &self,
        job_id: i64,
        repo: &str,
        base: &str,
        proposal: Option<&Row>,
    ) -> Result<PathBuf> {
        let path = self.store.root.join("work").join(job_id.to_string());
        if path.exists() {
            std::fs::remove_dir_all(&path)?;
        }
        std::fs::create_dir_all(path.parent().unwrap())?;
        self.run(
            &[
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                &self.github.remote(repo),
                path.to_str().unwrap(),
            ],
            None,
            true,
        )?;
        let start = proposal
            .map(|p| text(p, "head_sha"))
            .unwrap_or_else(|| base.to_string());
        self.run(&["checkout", "--detach", &start], Some(&path), true)?;
        if proposal.is_some() && !self.ok(&["merge", "--no-edit", base], &path)? {
            return Err(blocked(
                "destination base conflicts with the open proposal; reconcile human changes",
            ));
        }
        Ok(path)
    }

    pub fn context(&self, path: &Path, config: &Value) -> Result<Map<String, Value>> {
        let scopes = write_scopes(config);
        let tracked = self.run(&["ls-files", "-z"], Some(path), true)?.text();
        let mut files = Map::new();
        for name in tracked
            .trim_end_matches('\0')
            .split('\0')
            .filter(|n| !n.is_empty())
        {
            let selected = in_scope(name, &scopes)
                || name.ends_with("AGENTS.md")
                || ["README.md", "pyproject.toml", "package.json", "go.mod"].contains(&name);
            if !selected {
                continue;
            }
            safe_path(name)?;
            let file = path.join(name);
            if has_symlink_within(path, name) || !file.is_file() {
                return Err(blocked(
                    "destination context contains a symlink or unsupported file",
                ));
            }
            let content = String::from_utf8(std::fs::read(&file)?)
                .map_err(|_| blocked("destination context contains binary data"))?;
            files.insert(name.to_string(), Value::String(content));
            if files.len() > 80 || canonical(&Value::Object(files.clone())).len() > 200_000 {
                return Err(blocked(
                    "destination context exceeds bounds; narrow configured paths",
                ));
            }
        }
        Ok(files)
    }

    /// Apply model edits, enforcing the destination write boundary.
    pub fn apply(&self, path: &Path, changes: &Value, config: &Value) -> Result<()> {
        let scopes = write_scopes(config);
        let edits = match changes.as_array() {
            Some(edits) if (1..=20).contains(&edits.len()) => edits,
            _ => return Err(blocked("adaptation must provide 1-20 file edits")),
        };
        if canonical(changes).len() > 200_000 {
            return Err(blocked("adaptation exceeds output size limit"));
        }
        let mut seen = BTreeSet::new();
        for edit in edits {
            let name = edit
                .get("path")
                .and_then(Value::as_str)
                .ok_or_else(|| other("model edit has no path"))?;
            safe_path(name)?;
            if seen.contains(name) || !in_scope(name, &scopes) {
                return Err(blocked(format!(
                    "model edit is duplicated or outside authorized paths: {name}"
                )));
            }
            seen.insert(name.to_string());
            if has_symlink_within(path, name) {
                return Err(blocked("model edit traverses a symlink"));
            }
            let dest = path.join(name);
            match edit.get("content") {
                None | Some(Value::Null) => {
                    if dest.is_file() {
                        std::fs::remove_file(&dest)?;
                    }
                }
                Some(Value::String(content)) => {
                    std::fs::create_dir_all(dest.parent().unwrap())?;
                    std::fs::write(&dest, content)?;
                }
                Some(_) => return Err(blocked("file content must be a string or null")),
            }
        }
        // Only explicit, validated paths can be staged.
        let mut args = vec!["add", "--"];
        args.extend(seen.iter().map(String::as_str));
        self.run(&args, Some(path), true)?;
        let staged = self
            .run(&["diff", "--cached", "--name-only"], Some(path), true)?
            .text();
        if staged.trim().is_empty() {
            return Err(blocked(
                "model reported adaptation but produced no implementation changes",
            ));
        }
        let implementation = strings(config["destination"].get("paths"));
        if !staged.lines().any(|name| in_scope(name, &implementation)) {
            return Err(blocked(
                "adaptation contains no change to the configured implementation",
            ));
        }
        self.run(&["diff", "--cached", "--check"], Some(path), true)?;
        Ok(())
    }

    pub fn commit(&self, path: &Path, listener_id: &str) -> Result<String> {
        self.run(
            &[
                "commit",
                "-m",
                &format!("feat: adapt upstream implementation for {listener_id} (AI)"),
            ],
            Some(path),
            true,
        )?;
        Ok(self
            .run(&["rev-parse", "HEAD"], Some(path), true)?
            .text()
            .trim()
            .to_string())
    }

    pub fn publish(
        &self,
        path: &Path,
        repo: &str,
        branch: &str,
        commit: &str,
        expected: Option<&str>,
    ) -> Result<()> {
        let remote = self.remote_head(repo, branch)?;
        if remote.as_deref() == Some(commit) {
            return Ok(()); // A previous attempt already pushed this exact commit.
        }
        if remote.as_deref() != expected {
            return Err(blocked(
                "proposal branch changed outside Memetics; refusing to overwrite it",
            ));
        }
        if let Some(expected) = expected
            && !self.ok(&["merge-base", "--is-ancestor", expected, commit], path)?
        {
            return Err(blocked("proposal update would rewrite history"));
        }
        // Compare-and-swap the ref after verifying that this is an append-only update.
        self.run(
            &[
                "push",
                &format!(
                    "--force-with-lease=refs/heads/{branch}:{}",
                    expected.unwrap_or_default()
                ),
                "origin",
                &format!("{commit}:refs/heads/{branch}"),
            ],
            Some(path),
            true,
        )?;
        Ok(())
    }
}
