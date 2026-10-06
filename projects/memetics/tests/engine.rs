mod common;

use common::*;
use memetics::config::validate;
use memetics::db::{Row, Store, int, opt_text, text};
use memetics::engine::Engine;
use memetics::model::Tools;
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::Ordering;

struct Fixture {
    _tmp: tempfile::TempDir,
    up: PathBuf,
    down: PathBuf,
    before: String,
    after: String,
    store: Store,
    github: Arc<FakeGitHub>,
    model: Arc<FixtureModel>,
    validator: Arc<FixtureValidator>,
    engine: Engine,
    config: Value,
}

impl Fixture {
    fn new() -> Self {
        Self::with_upstream(
            &[("value.py", Some("VALUE = 1\n"))],
            &[("value.py", Some("VALUE = 2\n"))],
        )
    }

    fn with_upstream(first: &[(&str, Option<&str>)], second: &[(&str, Option<&str>)]) -> Self {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path().to_path_buf();
        let (up, down) = (root.join("up"), root.join("down"));
        init_repo(&up);
        init_repo(&down);
        let before = commit(&up, first);
        commit(
            &down,
            &[
                ("value.py", Some("VALUE = 1\n")),
                (
                    "test_value.py",
                    Some("from value import VALUE\nassert VALUE == 1\n"),
                ),
            ],
        );
        let after = commit(&up, second);
        let store = Store::open(root.join("state")).unwrap();
        let github = Arc::new(FakeGitHub::new(&[("owner/up", &up), ("owner/down", &down)]));
        let model = Arc::new(FixtureModel::default());
        let validator = Arc::new(FixtureValidator::default());
        let engine = Engine::new(
            store.clone(),
            github.clone(),
            model.clone(),
            Some(validator.clone()),
            60,
            20,
        )
        .unwrap();
        let config = json!({
            "id": "value",
            "enabled": true,
            "concern": "value handling",
            "upstream": {"repository": "owner/up", "ref": "main", "baseline_commit": before, "paths": ["value.py"]},
            "destination": {"repository": "owner/down", "base_ref": "main", "paths": ["value.py"], "test_paths": ["test_value.py"]},
            "adaptation": {"instructions": "Follow upstream", "validation_commands": ["python3 test_value.py"]},
        });
        Fixture {
            _tmp: tmp,
            up,
            down,
            before,
            after,
            store,
            github,
            model,
            validator,
            engine,
            config,
        }
    }

    fn register(&self) {
        self.store
            .register(std::slice::from_ref(&self.config))
            .unwrap();
    }

    fn restarted(&self) -> Engine {
        Engine::new(
            Store::open(&self.store.root).unwrap(),
            self.github.clone(),
            self.model.clone(),
            Some(self.validator.clone()),
            60,
            20,
        )
        .unwrap()
    }

    fn job(&self) -> Row {
        self.store
            .one("SELECT * FROM jobs ORDER BY id DESC LIMIT 1", [])
            .unwrap()
            .unwrap()
    }

    fn status(&self) -> String {
        text(&self.job(), "status")
    }

    fn tick(&self) {
        self.engine.tick(1, true).unwrap();
    }

    fn count(&self, sql: &str) -> i64 {
        int(&self.store.one(sql, []).unwrap().unwrap(), "n")
    }

    fn adopted(&self) -> Option<String> {
        opt_text(
            &self
                .store
                .one("SELECT adopted FROM listeners", [])
                .unwrap()
                .unwrap(),
            "adopted",
        )
    }
}

#[test]
fn end_to_end_and_restart_dedup() {
    let f = Fixture::new();
    f.register();
    f.tick();
    assert_eq!(f.status(), "proposed");
    assert_eq!(f.github.pull_count(), 1);
    let pr = f.github.pr(0);
    assert_eq!(pr["draft"], true);
    let body = pr["body"].as_str().unwrap();
    assert!(body.contains(&f.after));
    assert!(body.contains("Validation: **passed**"));
    let branch = pr["branch"].as_str().unwrap();
    assert_eq!(
        git(&f.down, &["show", &format!("{branch}:value.py")]),
        "VALUE = 2"
    );
    f.restarted().tick(1, true).unwrap();
    assert_eq!(f.model.count(), 1);
    assert_eq!(f.github.pull_count(), 1);
    assert_eq!(f.adopted(), None);
}

#[test]
fn two_listeners_share_poll_and_index() {
    let f = Fixture::new();
    let mut second = f.config.clone();
    second["id"] = "second".into();
    f.store.register(&[f.config.clone(), second]).unwrap();
    f.engine.tick(2, true).unwrap();
    assert_eq!(f.github.upstream_calls("owner/up"), 1);
    assert_eq!(f.count("SELECT count(*) n FROM changes"), 1);
    assert_eq!(f.count("SELECT count(*) n FROM blobs"), 2);
    assert_eq!(f.model.count(), 2);
    assert_eq!(f.github.pull_count(), 2);
    assert!(
        !f.store
            .rows(
                "SELECT * FROM blob_search WHERE blob_search MATCH 'VALUE'",
                []
            )
            .unwrap()
            .is_empty()
    );
}

#[test]
fn registration_catches_up_on_304_and_pause_is_sticky() {
    let f = Fixture::new();
    f.register();
    f.tick();
    let mut late = f.config.clone();
    late["id"] = "late".into();
    f.store.register(&[late]).unwrap();
    f.tick();
    assert_eq!(f.github.pull_count(), 2);
    f.store.enable("value", false).unwrap();
    f.store.enable("late", false).unwrap();
    f.register();
    let calls = f.github.calls.lock().unwrap().len();
    f.engine.poll(true).unwrap();
    assert_eq!(f.github.calls.lock().unwrap().len(), calls);
    let enabled = f
        .store
        .one("SELECT enabled FROM listeners WHERE id=?", ["value"])
        .unwrap()
        .unwrap();
    assert_eq!(int(&enabled, "enabled"), 0);
}

#[test]
fn update_open_pr_preserves_body_and_history() {
    let f = Fixture::new();
    f.register();
    f.tick();
    let branch = f.github.pr(0)["branch"].as_str().unwrap().to_string();
    let old = git(&f.down, &["rev-parse", &branch]);
    f.github.edit_pr(0, |pr| {
        pr["body"] = format!(
            "Human introduction\n{}\nHuman notes",
            pr["body"].as_str().unwrap()
        )
        .into();
    });
    let latest = commit(&f.up, &[("value.py", Some("VALUE = 3\n"))]);
    f.tick();
    assert_eq!(f.status(), "proposed");
    assert_eq!(f.github.pull_count(), 1);
    let body = f.github.pr(0)["body"].as_str().unwrap().to_string();
    assert!(body.starts_with("Human introduction"));
    assert!(body.ends_with("Human notes"));
    assert!(body.contains(&latest));
    git(&f.down, &["merge-base", "--is-ancestor", &old, &branch]);
    assert_eq!(
        git(&f.down, &["show", &format!("{branch}:value.py")]),
        "VALUE = 3"
    );
}

#[test]
fn lost_create_response_recovers_without_second_pr_or_model_call() {
    let f = Fixture::new();
    f.register();
    f.github.lose_create.store(true, Ordering::SeqCst);
    f.tick();
    assert_eq!(f.status(), "delivering");
    f.store.execute("UPDATE jobs SET not_before=0", []).unwrap();
    f.restarted().tick(1, true).unwrap();
    assert_eq!(f.status(), "proposed");
    assert_eq!(f.github.pull_count(), 1);
    assert_eq!(f.model.count(), 1);
}

#[test]
fn human_branch_changes_block_overwrite() {
    let f = Fixture::new();
    f.register();
    f.tick();
    let branch = f.github.pr(0)["branch"].as_str().unwrap().to_string();
    git(&f.down, &["checkout", "-q", &branch]);
    let human = commit(&f.down, &[("notes.txt", Some("human work\n"))]);
    git(&f.down, &["checkout", "-q", "main"]);
    commit(&f.up, &[("value.py", Some("VALUE = 3\n"))]);
    f.tick();
    assert_eq!(f.status(), "blocked");
    assert_eq!(git(&f.down, &["rev-parse", &branch]), human);
    assert_eq!(f.model.count(), 1);
}

#[test]
fn close_declines_without_reopening() {
    let f = Fixture::new();
    f.register();
    f.tick();
    f.github.edit_pr(0, |pr| pr["state"] = "closed".into());
    f.tick();
    assert_eq!(f.status(), "declined");
    assert_eq!(f.github.pull_count(), 1);
    assert_eq!(f.adopted(), None);
}

#[test]
fn merge_records_adopted_revision() {
    let f = Fixture::new();
    f.register();
    f.tick();
    f.github.edit_pr(0, |pr| {
        pr["state"] = "closed".into();
        pr["merged_at"] = "now".into();
    });
    f.tick();
    assert_eq!(f.status(), "adopted");
    assert_eq!(f.adopted().as_deref(), Some(f.after.as_str()));
}

#[test]
fn failed_validation_is_visible_on_draft() {
    let f = Fixture::new();
    f.register();
    f.validator.fail.store(true, Ordering::SeqCst);
    f.tick();
    assert_eq!(f.status(), "proposed");
    assert!(f.github.pr(0)["body"].as_str().unwrap().contains("BLOCKED"));
    let evidence: Value = serde_json::from_str(&text(&f.job(), "evidence")).unwrap();
    assert_eq!(evidence["validation"]["passed"], false);
}

#[test]
fn private_source_cannot_leak_to_public_destination() {
    let f = Fixture::new();
    f.register();
    f.github
        .private
        .lock()
        .unwrap()
        .insert("owner/down".into(), false);
    f.tick();
    assert_eq!(f.status(), "blocked");
    assert_eq!(f.model.count(), 0);
    assert_eq!(f.github.pull_count(), 0);
}

#[test]
fn out_of_scope_model_edit_never_publishes() {
    let f = Fixture::new();
    f.register();
    *f.model.override_with.lock().unwrap() = Some(Box::new(|_, _| {
        json!({"decision": "adapt", "reason": "bad edit",
            "changes": [{"path": ".github/workflows/oops.yml", "content": "oops"}]})
    }));
    f.tick();
    assert_eq!(f.status(), "blocked");
    assert_eq!(f.github.pull_count(), 0);
}

#[test]
fn budget_waits_without_spinning_or_spending() {
    let mut f = Fixture::new();
    f.register();
    f.engine.daily_calls = 0;
    f.tick();
    assert_eq!(f.status(), "retry");
    assert_eq!(int(&f.job(), "attempts"), 0);
    assert_eq!(f.model.count(), 0);
}

#[test]
fn model_can_classify_semantic_change_outside_original_path() {
    let f = Fixture::new();
    git(&f.up, &["mv", "value.py", "renamed.py"]);
    git(
        &f.up,
        &[
            "-c",
            "user.name=T",
            "-c",
            "user.email=t@e",
            "commit",
            "-qm",
            "rename",
        ],
    );
    f.register();
    f.tick();
    assert_eq!(f.status(), "proposed");
    let calls = f.model.calls.lock().unwrap();
    let paths: Vec<&str> = calls[0]["upstream_change"]["files"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x["path"].as_str().unwrap())
        .collect();
    assert!(paths.contains(&"renamed.py"));
}

#[test]
fn force_push_blocks_instead_of_assuming_linear_history() {
    let f = Fixture::new();
    git(&f.up, &["checkout", "-q", "--orphan", "replacement"]);
    git(&f.up, &["rm", "-q", "-rf", "."]);
    commit(&f.up, &[("value.py", Some("VALUE = 9\n"))]);
    git(&f.up, &["branch", "-M", "main"]);
    f.register();
    f.tick();
    assert_eq!(f.status(), "blocked");
    assert_eq!(f.model.count(), 0);
}

#[test]
fn destination_base_advance_revalidates() {
    let f = Fixture::new();
    f.register();
    *f.validator.advance_after_first.lock().unwrap() = Some(f.down.clone());
    f.tick();
    assert_eq!(f.status(), "proposed");
    assert_eq!(f.validator.calls.load(Ordering::SeqCst), 2);
    let branch = f.github.pr(0)["branch"].as_str().unwrap().to_string();
    assert_eq!(
        git(&f.down, &["show", &format!("{branch}:new.txt")]),
        "new base"
    );
}

#[test]
fn registration_validates_atomically_and_rejects_traversal() {
    let f = Fixture::new();
    let mut invalid = f.config.clone();
    invalid["id"] = "bad".into();
    invalid["destination"]["paths"] = json!(["../outside"]);
    assert!(f.store.register(&[f.config.clone(), invalid]).is_err());
    assert!(
        f.store
            .rows("SELECT * FROM listeners", [])
            .unwrap()
            .is_empty()
    );
    let mut merging = f.config.clone();
    merging["delivery"] = json!({"auto_merge": true});
    assert!(validate(&merging).is_err());
}

#[test]
fn running_job_recovers_after_restart() {
    let f = Fixture::new();
    f.register();
    f.engine.poll(true).unwrap();
    f.store
        .set_job(
            int(&f.job(), "id"),
            "running",
            &[("attempts", rusqlite::types::Value::Integer(1))],
        )
        .unwrap();
    f.engine.tick(1, false).unwrap();
    assert_eq!(f.status(), "proposed");
    assert_eq!(int(&f.job(), "attempts"), 2);
}

#[test]
fn process_lock_excludes_another_worker() {
    let f = Fixture::new();
    let _held = f.engine.lock().unwrap();
    let error = f.engine.tick(1, false).unwrap_err();
    assert!(error.to_string().contains("already running"));
}

const PRUNER_BEFORE: &str = "def prune(items, limit):\n    return items[:limit]\n\n\ndef unrelated():\n    return 1\n\nVALUE = 1\n";

fn symbol_fixture(after: &str) -> Fixture {
    let f = Fixture::with_upstream(
        &[("pruner.py", Some(PRUNER_BEFORE))],
        &[("pruner.py", Some(after))],
    );
    let mut config = f.config.clone();
    config["upstream"]["symbols"] = json!(["prune"]);
    config["upstream"]["baseline_commit"] = f.before.clone().into();
    f.store.register(&[config]).unwrap();
    f
}

#[test]
fn unrelated_upstream_edit_does_not_trigger() {
    let f = symbol_fixture(
        &PRUNER_BEFORE
            .replace("return 1", "return 2")
            .replace("items[:limit]", "items[ : limit ]  # same"),
    );
    f.tick();
    assert_eq!(f.status(), "unchanged");
    assert!(text(&f.job(), "reason").contains("prune"));
    assert_eq!(f.model.count(), 0);
    assert_eq!(f.github.pull_count(), 0);
}

#[test]
fn upstream_symbol_hash_change_triggers_adaptation() {
    let f = symbol_fixture(
        &PRUNER_BEFORE
            .replace("items[:limit]", "items[-limit:]")
            .replace("VALUE = 1", "VALUE = 2"),
    );
    f.tick();
    assert_eq!(f.model.count(), 1);
    let calls = f.model.calls.lock().unwrap();
    assert_eq!(calls[0]["changed_symbols"][0]["symbol"], "prune");
    assert!(
        calls[0]["changed_symbols"][0]["after"]
            .as_str()
            .unwrap()
            .contains("items[-limit:]")
    );
    drop(calls);
    assert_eq!(f.status(), "proposed");
    assert!(
        f.github.pr(0)["body"]
            .as_str()
            .unwrap()
            .contains("Changed upstream symbols: `prune`")
    );
}

#[test]
fn agent_tools_look_up_both_repos_validate_and_charge_budget() {
    let f = Fixture::new();
    f.register();
    *f.model.override_with.lock().unwrap() = Some(Box::new(|_, tools: &mut dyn Tools| {
        tools.charge().unwrap();
        let upstream = tools.read_upstream("value.py").unwrap();
        let local = tools.read_destination("test_value.py").unwrap();
        assert!(tools.read_destination("../escape").is_err());
        let hits = tools.search_destination("VALUE").unwrap();
        let bad = tools
            .validate(&json!([{"path": "value.py", "content": "VALUE = 2\n"}]))
            .unwrap();
        let changes = json!([
            {"path": "value.py", "content": "VALUE = 2\n"},
            {"path": "test_value.py", "content": "from value import VALUE\nassert VALUE == 2\n"},
        ]);
        let good = tools.validate(&changes).unwrap();
        let scope = tools.validate(&json!([{"path": "other.py", "content": "x"}]));
        assert!(scope.is_err());
        json!({"decision": "adapt", "reason": format!(
            "upstream {} local {} hits {} first {} second {}",
            upstream.trim(), local.lines().count(), hits.lines().count(), bad["passed"], good["passed"]),
            "changes": changes})
    }));
    f.tick();
    assert_eq!(f.status(), "proposed");
    let evidence: Value = serde_json::from_str(&text(&f.job(), "evidence")).unwrap();
    assert_eq!(
        evidence["model_decision"]["reason"],
        "upstream VALUE = 2 local 2 hits 3 first false second true"
    );
    assert_eq!(f.count("SELECT count(*) n FROM model_calls"), 1);
    assert_eq!(f.validator.calls.load(Ordering::SeqCst), 3);
}
