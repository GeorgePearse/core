mod common;

use common::{commit, git, init_repo};
use memetics::db::{Store, text};
use memetics::error::Result;
use memetics::ideas::Manifest;
use memetics::judge::{CheckOptions, Judge, JudgeRequest, Report, Target, check_commit};
use serde_json::{Value, json};
use std::path::Path;
use std::sync::Mutex;

const LOOKUP: &str = "pub fn find(sorted: &[i32], target: i32) -> Option<usize> {
    let (mut lo, mut hi) = (0, sorted.len());
    while lo < hi {
        let mid = (lo + hi) / 2;
        if sorted[mid] == target {
            return Some(mid);
        } else if sorted[mid] < target {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    None
}

pub fn unrelated() -> i32 {
    1
}
";

const MANIFEST: &str = "# Memetics\n\n## binary-search\n- idea: Look up values in a sorted slice by binary search.\n- source: paper doi:10.1145/3597503.3639187\n- code: src/lib.rs symbol=find\n";

struct FakeJudge {
    reply: Value,
    requests: Mutex<Vec<JudgeRequest>>,
}

impl FakeJudge {
    fn new(choice: &str, confidence: f64) -> Self {
        FakeJudge {
            reply: json!({"choice": choice, "confidence": confidence, "reason": "fake",
                "evidence": {"anchor": "a1", "hunks": ["h1"]}}),
            requests: Mutex::new(vec![]),
        }
    }
}

impl Judge for FakeJudge {
    fn name(&self) -> String {
        "fake".into()
    }
    fn judge(&self, request: &JudgeRequest) -> Result<Value> {
        self.requests.lock().unwrap().push(request.clone());
        Ok(self.reply.clone())
    }
}

struct PanicJudge;

impl Judge for PanicJudge {
    fn name(&self) -> String {
        "panic".into()
    }
    fn judge(&self, _: &JudgeRequest) -> Result<Value> {
        panic!("the cheap structural check should have short-circuited the judge");
    }
}

fn repo() -> (tempfile::TempDir, std::path::PathBuf) {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("repo");
    init_repo(&path);
    commit(
        &path,
        &[
            ("src/lib.rs", Some(LOOKUP)),
            ("memetics.md", Some(MANIFEST)),
        ],
    );
    let status = std::process::Command::new(env!("CARGO_BIN_EXE_memetics"))
        .args(["ideas", "--rehash"])
        .current_dir(&path)
        .status()
        .unwrap();
    assert!(status.success());
    git(&path, &["commit", "-qam", "anchor"]);
    (tmp, path)
}

fn check(path: &Path, judge: &dyn Judge, strict: bool, update: bool) -> Report {
    let options = CheckOptions {
        repo: path.to_path_buf(),
        target: Target::Commit("HEAD".into()),
        threshold: 0.7,
        strict_refines: strict,
        update_anchors: update,
    };
    check_commit(&options, Some(judge), None).unwrap()
}

#[test]
fn rehash_fills_symbol_anchor() {
    let (_tmp, path) = repo();
    let manifest =
        Manifest::parse(&std::fs::read_to_string(path.join("memetics.md")).unwrap()).unwrap();
    let anchor = &manifest.ideas[0].code[0];
    assert!(anchor.hash.is_some());
    assert_eq!(anchor.lines, Some((1, 14)));
}

#[test]
fn only_hunks_overlapping_an_anchor_reach_the_judge() {
    let (_tmp, path) = repo();
    commit(
        &path,
        &[("src/lib.rs", Some(&LOOKUP.replace("    1\n", "    2\n")))],
    );
    let report = check(&path, &PanicJudge, false, false);
    assert!(report.verdicts.is_empty(), "{report:?}");
    commit(
        &path,
        &[(
            "src/lib.rs",
            Some(&LOOKUP.replace("(lo + hi) / 2", "lo + (hi - lo) / 2")),
        )],
    );
    let judge = FakeJudge::new("refines_idea", 0.9);
    let report = check(&path, &judge, false, false);
    let requests = judge.requests.lock().unwrap();
    assert_eq!(requests.len(), 1);
    assert_eq!(requests[0].hunks.len(), 1);
    assert!(requests[0].hunks[0].text.contains("lo + (hi - lo) / 2"));
    assert!(requests[0].anchors[0].before.contains("(lo + hi) / 2"));
    assert_eq!(report.verdicts[0].method, "judge");
}

#[test]
fn cheap_check_short_circuits_formatting_and_comment_edits() {
    let (_tmp, path) = repo();
    let reformatted = LOOKUP.replace(
        "let mid = (lo + hi) / 2;",
        "// midpoint\n        let mid = (lo+hi)/2;",
    );
    commit(&path, &[("src/lib.rs", Some(&reformatted))]);
    let report = check(&path, &PanicJudge, false, false);
    assert_eq!(report.verdicts.len(), 1);
    assert_eq!(
        (
            report.verdicts[0].choice.as_str(),
            report.verdicts[0].method.as_str()
        ),
        ("same_idea", "cheap")
    );
    assert_eq!(report.exit_code(), 0);
}

#[test]
fn rename_updates_anchors_and_passes() {
    let (_tmp, path) = repo();
    commit(
        &path,
        &[(
            "src/lib.rs",
            Some(&format!(
                "// header\n{}",
                LOOKUP.replace("pub fn find", "pub fn search")
            )),
        )],
    );
    let report = check(&path, &PanicJudge, false, true);
    assert_eq!(report.verdicts[0].status, "pass");
    assert_eq!(report.verdicts[0].method, "cheap");
    let manifest =
        Manifest::parse(&std::fs::read_to_string(path.join("memetics.md")).unwrap()).unwrap();
    let anchor = &manifest.ideas[0].code[0];
    assert_eq!(anchor.symbol.as_deref(), Some("search"));
    assert_eq!(anchor.lines, Some((2, 15)));
}

#[test]
fn verdict_without_evidence_is_an_error() {
    let (_tmp, path) = repo();
    commit(
        &path,
        &[(
            "src/lib.rs",
            Some(&LOOKUP.replace("(lo + hi) / 2", "lo + (hi - lo) / 2")),
        )],
    );
    for evidence in [
        json!(null),
        json!({"anchor": "a9", "hunks": ["h1"]}),
        json!({"anchor": "a1", "hunks": []}),
    ] {
        let mut judge = FakeJudge::new("same_idea", 0.99);
        judge.reply["evidence"] = evidence;
        let report = check(&path, &judge, false, false);
        assert_eq!(report.verdicts[0].status, "error");
        assert_eq!(report.exit_code(), 2);
    }
}

#[test]
fn refines_warns_unless_strict_and_amendment_excuses_it() {
    let (_tmp, path) = repo();
    commit(
        &path,
        &[(
            "src/lib.rs",
            Some(&LOOKUP.replace("(lo + hi) / 2", "lo + (hi - lo) / 2")),
        )],
    );
    let judge = FakeJudge::new("refines_idea", 0.95);
    let report = check(&path, &judge, false, false);
    assert_eq!(
        (report.verdicts[0].status.as_str(), report.exit_code()),
        ("warn", 0)
    );
    let report = check(&path, &judge, true, false);
    assert_eq!(
        (report.verdicts[0].status.as_str(), report.exit_code()),
        ("fail", 1)
    );
    let manifest = std::fs::read_to_string(path.join("memetics.md")).unwrap();
    commit(
        &path,
        &[
            (
                "src/lib.rs",
                Some(
                    &LOOKUP
                        .replace("(lo + hi) / 2", "lo + (hi - lo) / 2")
                        .replace("Some(mid)", "Some(mid as usize)"),
                ),
            ),
            (
                "memetics.md",
                Some(&manifest.replace("by binary search.", "by overflow-safe binary search.")),
            ),
        ],
    );
    let report = check(&path, &judge, true, false);
    assert_eq!(
        (report.verdicts[0].status.as_str(), report.exit_code()),
        ("pass", 0)
    );
}

#[test]
fn different_idea_fails_and_is_stored_with_its_method() {
    let (tmp, path) = repo();
    commit(&path, &[("src/lib.rs", Some(&LOOKUP.replace(
        "    let (mut lo, mut hi) = (0, sorted.len());\n    while lo < hi {\n        let mid = (lo + hi) / 2;\n        if sorted[mid] == target {\n            return Some(mid);\n        } else if sorted[mid] < target {\n            lo = mid + 1;\n        } else {\n            hi = mid;\n        }\n    }\n    None\n",
        "    sorted.iter().position(|&x| x == target)\n")))]);
    let store = Store::open(tmp.path().join("state")).unwrap();
    let options = CheckOptions {
        repo: path.clone(),
        target: Target::Commit("HEAD".into()),
        threshold: 0.7,
        strict_refines: false,
        update_anchors: false,
    };
    let judge = FakeJudge::new("different_idea", 0.92);
    let report = check_commit(&options, Some(&judge), Some(&store)).unwrap();
    assert_eq!(
        (report.verdicts[0].status.as_str(), report.exit_code()),
        ("fail", 1)
    );
    let row = store
        .one("SELECT * FROM idea_verdicts", [])
        .unwrap()
        .unwrap();
    assert_eq!(
        (text(&row, "choice").as_str(), text(&row, "method").as_str()),
        ("different_idea", "judge")
    );
    let again = check_commit(&options, Some(&PanicJudge), Some(&store)).unwrap();
    assert!(again.verdicts[0].judge.contains("cached"));
}

#[test]
fn staged_check_and_hook_install() {
    let (_tmp, path) = repo();
    std::fs::write(
        path.join("src/lib.rs"),
        LOOKUP.replace("pub fn find", "pub fn lookup"),
    )
    .unwrap();
    git(&path, &["add", "-A"]);
    let options = CheckOptions {
        repo: path.clone(),
        target: Target::Staged,
        threshold: 0.7,
        strict_refines: false,
        update_anchors: true,
    };
    let report = check_commit(&options, Some(&PanicJudge), None).unwrap();
    assert_eq!(report.verdicts[0].method, "cheap");
    assert!(git(&path, &["diff", "--cached", "--name-only"]).contains("memetics.md"));
    let hook = memetics::judge::install_hook(&path, "pre-commit", false).unwrap();
    assert!(
        std::fs::read_to_string(&hook)
            .unwrap()
            .contains("check-commit --staged --update-anchors")
    );
    std::fs::write(&hook, "#!/bin/sh\necho mine\n").unwrap();
    assert!(memetics::judge::install_hook(&path, "pre-commit", false).is_err());
}
