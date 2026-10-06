//! Live check against the real Jev judge. Run with
//! `AI_GATEWAY_API_KEY=… cargo test --test live_jev -- --ignored --nocapture`.

mod common;

use common::{commit, git, init_repo};
use memetics::judge::{CheckOptions, Target, check_commit, from_env};

const BASE: &str = "pub fn find(sorted: &[i32], target: i32) -> Option<usize> {
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
";

const RENAMED: &str = "pub fn find(sorted: &[i32], target: i32) -> Option<usize> {
    let (mut low, mut high) = (0, sorted.len());
    while low < high {
        let middle = (low + high) / 2;
        if sorted[middle] == target {
            return Some(middle);
        } else if sorted[middle] < target {
            low = middle + 1;
        } else {
            high = middle;
        }
    }
    None
}
";

const OPTIMISED: &str = "pub fn find(sorted: &[i32], target: i32) -> Option<usize> {
    let (mut low, mut high) = (0, sorted.len());
    while low < high {
        let middle = low + (high - low) / 2;
        match sorted[middle].cmp(&target) {
            std::cmp::Ordering::Equal => return Some(middle),
            std::cmp::Ordering::Less => low = middle + 1,
            std::cmp::Ordering::Greater => high = middle,
        }
    }
    None
}
";

const LINEAR: &str = "pub fn find(sorted: &[i32], target: i32) -> Option<usize> {
    sorted.iter().position(|&value| value == target)
}
";

#[test]
#[ignore = "calls the live Jev judge"]
fn jev_classifies_rename_refinement_and_replacement() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("repo");
    init_repo(&path);
    commit(
        &path,
        &[
            ("src/lib.rs", Some(BASE)),
            (
                "memetics.md",
                Some(
                    "## binary-search\n- idea: Find a value in a sorted slice by binary search, halving the candidate range each step.\n- code: src/lib.rs symbol=find\n",
                ),
            ),
        ],
    );
    let judge = from_env().expect("configure the Jev judge (AI_GATEWAY_API_KEY)");
    let mut results = Vec::new();
    for (label, code, expected) in [
        ("pure rename", RENAMED, "same_idea"),
        ("small optimisation", OPTIMISED, "refines_idea"),
        ("swapped algorithm", LINEAR, "different_idea"),
    ] {
        commit(&path, &[("src/lib.rs", Some(code))]);
        let options = CheckOptions {
            repo: path.clone(),
            target: Target::Commit("HEAD".into()),
            threshold: 0.7,
            strict_refines: false,
            update_anchors: false,
        };
        let report = check_commit(&options, Some(judge.as_ref()), None).unwrap();
        let verdict = &report.verdicts[0];
        println!(
            "{label}: {} confidence={:.3} method={} judge={} evidence={} reason={}",
            verdict.choice,
            verdict.confidence,
            verdict.method,
            verdict.judge,
            verdict.evidence,
            verdict.reason
        );
        results.push((label, verdict.choice.clone(), expected));
        let _ = git(&path, &["log", "-1", "--format=%h"]);
    }
    for (label, got, expected) in results {
        assert_eq!(got, expected, "{label}");
    }
}
