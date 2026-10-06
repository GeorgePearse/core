#![allow(dead_code)]

use memetics::error::{Result, other};
use memetics::github::GitHubApi;
use memetics::model::{Adapter, Tools};
use memetics::validation::Validator;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

pub fn git(path: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args(["-c", "user.name=Test", "-c", "user.email=test@example.com"])
        .args(args)
        .current_dir(path)
        .output()
        .expect("git runs");
    assert!(
        out.status.success(),
        "git {args:?}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

pub fn commit(path: &Path, files: &[(&str, Option<&str>)]) -> String {
    for (name, text) in files {
        let dest = path.join(name);
        match text {
            Some(text) => {
                std::fs::create_dir_all(dest.parent().unwrap()).unwrap();
                std::fs::write(&dest, text).unwrap();
            }
            None => std::fs::remove_file(&dest).unwrap(),
        }
    }
    git(path, &["add", "-A"]);
    git(path, &["commit", "-qm", "fixture"]);
    git(path, &["rev-parse", "HEAD"])
}

pub fn init_repo(path: &Path) {
    std::fs::create_dir_all(path).unwrap();
    git(path, &["init", "-q", "-b", "main"]);
}

pub struct FakeGitHub {
    pub repos: HashMap<String, PathBuf>,
    pub private: Mutex<HashMap<String, bool>>,
    pub calls: Mutex<Vec<(String, String, Option<String>)>>,
    pub pulls: Mutex<Vec<Value>>,
    pub lose_create: AtomicBool,
}

impl FakeGitHub {
    pub fn new(repos: &[(&str, &Path)]) -> Self {
        FakeGitHub {
            repos: repos
                .iter()
                .map(|(r, p)| (r.to_string(), p.to_path_buf()))
                .collect(),
            private: Mutex::new(repos.iter().map(|(r, _)| (r.to_string(), true)).collect()),
            calls: Mutex::new(vec![]),
            pulls: Mutex::new(vec![]),
            lose_create: AtomicBool::new(false),
        }
    }

    fn fresh(&self, pr: &mut Value) -> Value {
        let repo = &self.repos[pr["repo"].as_str().unwrap()];
        pr["head"]["sha"] = git(repo, &["rev-parse", pr["branch"].as_str().unwrap()]).into();
        pr.clone()
    }

    pub fn pull_count(&self) -> usize {
        self.pulls.lock().unwrap().len()
    }

    pub fn pr(&self, index: usize) -> Value {
        self.pulls.lock().unwrap()[index].clone()
    }

    pub fn edit_pr(&self, index: usize, f: impl FnOnce(&mut Value)) {
        f(&mut self.pulls.lock().unwrap()[index]);
    }

    pub fn upstream_calls(&self, repo: &str) -> usize {
        self.calls
            .lock()
            .unwrap()
            .iter()
            .filter(|c| c.0 == repo)
            .count()
    }
}

impl GitHubApi for FakeGitHub {
    fn token(&self) -> Result<String> {
        Ok("fixture-token-never-sent".into())
    }

    fn head(
        &self,
        repo: &str,
        reference: &str,
        etag: Option<&str>,
    ) -> Result<(Option<String>, Option<String>)> {
        self.calls
            .lock()
            .unwrap()
            .push((repo.into(), reference.into(), etag.map(String::from)));
        let sha = git(&self.repos[repo], &["rev-parse", reference]);
        Ok(((etag != Some(sha.as_str())).then(|| sha.clone()), Some(sha)))
    }

    fn metadata(&self, repo: &str) -> Result<Value> {
        Ok(json!({"private": self.private.lock().unwrap()[repo]}))
    }

    fn remote(&self, repo: &str) -> String {
        self.repos[repo].display().to_string()
    }

    fn pull(&self, _repo: &str, number: i64) -> Result<Value> {
        let mut pulls = self.pulls.lock().unwrap();
        Ok(self.fresh(&mut pulls[number as usize - 1]))
    }

    fn find_pull(&self, repo: &str, branch: &str) -> Result<Option<Value>> {
        let mut pulls = self.pulls.lock().unwrap();
        Ok(pulls
            .iter_mut()
            .rev()
            .find(|p| p["repo"] == repo && p["branch"] == branch)
            .map(|p| self.fresh(p)))
    }

    fn create_pull(
        &self,
        repo: &str,
        branch: &str,
        base: &str,
        title: &str,
        body: &str,
    ) -> Result<Value> {
        let mut pulls = self.pulls.lock().unwrap();
        let number = pulls.len() + 1;
        let mut pr = json!({
            "number": number, "repo": repo, "branch": branch, "base": {"ref": base}, "head": {},
            "title": title, "body": body, "draft": true, "state": "open", "merged_at": null,
            "html_url": format!("https://github.com/{repo}/pull/{number}"),
        });
        let result = self.fresh(&mut pr);
        pulls.push(pr);
        if self.lose_create.swap(false, Ordering::SeqCst) {
            return Err(other("response lost after GitHub created the PR"));
        }
        Ok(result)
    }

    fn update_pull(&self, _repo: &str, number: i64, body: &str) -> Result<Value> {
        let mut pulls = self.pulls.lock().unwrap();
        let pr = &mut pulls[number as usize - 1];
        pr["body"] = body.into();
        Ok(self.fresh(pr))
    }
}

type Override = Box<dyn Fn(&Value, &mut dyn Tools) -> Value + Send + Sync>;

#[derive(Default)]
pub struct FixtureModel {
    pub calls: Mutex<Vec<Value>>,
    pub override_with: Mutex<Option<Override>>,
}

impl FixtureModel {
    pub fn count(&self) -> usize {
        self.calls.lock().unwrap().len()
    }
}

pub fn value_in(text: &str) -> i64 {
    text.trim()
        .rsplit('=')
        .next()
        .unwrap()
        .trim()
        .parse()
        .unwrap()
}

impl Adapter for FixtureModel {
    fn adapt(&self, context: &Value, tools: &mut dyn Tools) -> Result<Value> {
        self.calls.lock().unwrap().push(context.clone());
        if let Some(f) = self.override_with.lock().unwrap().as_ref() {
            return Ok(f(context, tools));
        }
        let source = context["upstream_change"]["files"]
            .as_array()
            .unwrap()
            .iter()
            .find(|f| f["after"].is_string())
            .unwrap();
        let value = value_in(source["after"].as_str().unwrap());
        Ok(json!({
            "decision": "adapt",
            "reason": "Port the upstream value and regression coverage.",
            "changes": [
                {"path": "value.py", "content": format!("VALUE = {value}\n")},
                {"path": "test_value.py", "content": format!("from value import VALUE\nassert VALUE == {value}\n")},
            ],
        }))
    }
}

/// Fixtures contain only these controlled checks; production always uses Docker.
#[derive(Default)]
pub struct FixtureValidator {
    pub calls: AtomicUsize,
    pub fail: AtomicBool,
    pub advance_after_first: Mutex<Option<PathBuf>>,
}

impl Validator for FixtureValidator {
    fn run(&self, checkout: &Path, _config: &Value) -> Result<Value> {
        let calls = self.calls.fetch_add(1, Ordering::SeqCst) + 1;
        let value = std::fs::read_to_string(checkout.join("value.py")).unwrap_or_default();
        let test = std::fs::read_to_string(checkout.join("test_value.py")).unwrap_or_default();
        let ok =
            !value.is_empty() && test.contains(&format!("assert VALUE == {}", value_in(&value)));
        let failed = self.fail.load(Ordering::SeqCst);
        if calls == 1
            && let Some(down) = self.advance_after_first.lock().unwrap().as_ref()
        {
            commit(down, &[("new.txt", Some("new base\n"))]);
        }
        Ok(json!({
            "passed": ok && !failed,
            "runner": "fixture",
            "image": "fixture",
            "results": [{"command": "python3 test_value.py", "exit_code": if ok && !failed { 0 } else { 1 }, "output": ""}],
        }))
    }
}
