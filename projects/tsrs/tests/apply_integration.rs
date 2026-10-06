use anyhow::{Context, Result};
use assert_cmd::cargo::cargo_bin_cmd;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use tempfile::TempDir;

fn copy_dir_filtered(src: &Path, dst: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;

    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let name = entry.file_name();
        if name == "__pycache__" {
            continue;
        }
        let src_path = entry.path();
        let dst_path = dst.join(&name);
        if entry.file_type()?.is_dir() {
            copy_dir_filtered(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, &dst_path)?;
        }
    }

    Ok(())
}

fn fixture_path(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("test_packages/test_minify")
        .join(relative)
}

const PATTERNS_SOURCE: &str = include_str!("../test_packages/test_minify/src/patterns.py");

fn extract_pattern_match_source() -> &'static str {
    PATTERNS_SOURCE
        .split("PATTERN_MATCH_SOURCE = \"\"\"")
        .nth(1)
        .and_then(|rest| rest.split("\"\"\"").next())
        .expect("pattern source constant missing")
}

fn materialize_pattern_fixture(dst_dir: &Path) -> Result<()> {
    let pattern_path = dst_dir.join("patterns.py");
    let content = format!(
        "\"\"\"Structural pattern matching fixture for apply tests.\"\"\"\n\n{}",
        extract_pattern_match_source()
    );
    fs::write(pattern_path, content)?;
    Ok(())
}

#[test]
fn apply_plan_rewrites_single_file() -> Result<()> {
    let temp = TempDir::new()?;
    let src = fixture_path("src/simple_module.py");
    let dst = temp.path().join("simple_module.py");
    fs::copy(&src, &dst)?;

    let plan_path = temp.path().join("plan.json");

    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan")
        .arg(&dst)
        .output()
        .context("failed to execute tsrs-cli minify-plan")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    fs::write(&plan_path, &plan_output.stdout)?;

    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan")
        .arg(&dst)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--in-place")
        .output()
        .context("failed to execute tsrs-cli apply-plan")?;

    anyhow::ensure!(
        apply_output.status.success(),
        "apply-plan exited with {}. stderr: {}",
        apply_output.status,
        String::from_utf8_lossy(&apply_output.stderr)
    );

    let rewritten = fs::read_to_string(&dst)?;
    assert!(!rewritten.contains("message"));
    assert!(!rewritten.contains("suffix"));
    assert!(rewritten.contains("Hello"));

    Ok(())
}

#[test]
fn apply_plan_json_requires_stats() -> Result<()> {
    let temp = TempDir::new()?;
    let src = fixture_path("src/simple_module.py");
    let dst = temp.path().join("simple_module.py");
    fs::copy(&src, &dst)?;
    let original = fs::read_to_string(&dst)?;

    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan")
        .arg(&dst)
        .output()
        .context("failed to execute tsrs-cli minify-plan for json flag test")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    let plan_path = temp.path().join("plan.json");
    fs::write(&plan_path, &plan_output.stdout)?;

    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan")
        .arg(&dst)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--json")
        .output()
        .context("failed to execute tsrs-cli apply-plan --json")?;

    assert!(
        !apply_output.status.success(),
        "apply-plan --json should fail without --stats"
    );
    let stderr = String::from_utf8(apply_output.stderr)?;
    assert!(stderr.contains("--json requires --stats"));

    let after = fs::read_to_string(&dst)?;
    assert_eq!(after, original, "failing invocation should not modify file");

    Ok(())
}

#[test]
fn apply_plan_dir_rewrites_all_files() -> Result<()> {
    let temp = TempDir::new()?;
    let src_dir = fixture_path("src");
    let dst_dir = temp.path().join("src");
    copy_dir_filtered(&src_dir, &dst_dir)?;
    materialize_pattern_fixture(&dst_dir)?;

    let plan_path = temp.path().join("plan.json");

    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan-dir")
        .arg(&dst_dir)
        .arg("--out")
        .arg(&plan_path)
        .output()
        .context("failed to execute tsrs-cli minify-plan-dir")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan-dir exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan-dir")
        .arg(&dst_dir)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--in-place")
        .output()
        .context("failed to execute tsrs-cli apply-plan-dir")?;

    anyhow::ensure!(
        apply_output.status.success(),
        "apply-plan-dir exited with {}. stderr: {}",
        apply_output.status,
        String::from_utf8_lossy(&apply_output.stderr)
    );

    let rewritten_simple = fs::read_to_string(dst_dir.join("simple_module.py"))?;
    assert!(!rewritten_simple.contains("message"));
    assert!(!rewritten_simple.contains("suffix"));

    let rewritten_nested = fs::read_to_string(dst_dir.join("nested/calculator.py"))?;
    assert!(!rewritten_nested.contains("total"));

    let rewritten_class = fs::read_to_string(dst_dir.join("class_methods.py"))?;
    assert!(rewritten_class.contains("total ="));

    Ok(())
}

#[test]
fn apply_plan_accepts_plan_from_stdin() -> Result<()> {
    let temp = TempDir::new()?;
    let src = fixture_path("src/simple_module.py");
    let dst = temp.path().join("simple_module.py");
    fs::copy(&src, &dst)?;

    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan")
        .arg(&dst)
        .output()
        .context("failed to execute tsrs-cli minify-plan for stdin test")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    let plan_json = String::from_utf8(plan_output.stdout)?;

    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan")
        .arg(&dst)
        .arg("--plan-stdin")
        .arg("--in-place")
        .write_stdin(plan_json)
        .output()
        .context("failed to execute tsrs-cli apply-plan with stdin plan")?;

    anyhow::ensure!(
        apply_output.status.success(),
        "apply-plan with stdin exited with {}. stderr: {}",
        apply_output.status,
        String::from_utf8_lossy(&apply_output.stderr)
    );

    let rewritten = fs::read_to_string(&dst)?;
    assert!(!rewritten.contains("message"));
    assert!(!rewritten.contains("suffix"));

    Ok(())
}

#[test]
fn apply_plan_dir_rejects_out_dir_inside_input() -> Result<()> {
    let temp = TempDir::new()?;
    let src_dir = fixture_path("src");
    let dst_dir = temp.path().join("src");
    copy_dir_filtered(&src_dir, &dst_dir)?;
    materialize_pattern_fixture(&dst_dir)?;

    let plan_path = temp.path().join("plan.json");
    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan-dir")
        .arg(&dst_dir)
        .arg("--out")
        .arg(&plan_path)
        .output()
        .context("failed to execute tsrs-cli minify-plan-dir for rejection test")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan-dir exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    let out_dir = dst_dir.join("nested_output");
    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan-dir")
        .arg(&dst_dir)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--out-dir")
        .arg(&out_dir)
        .output()
        .context("failed to execute tsrs-cli apply-plan-dir for rejection test")?;

    anyhow::ensure!(
        !apply_output.status.success(),
        "apply-plan-dir should reject out-dir inside input"
    );

    let stderr = String::from_utf8(apply_output.stderr)?;
    assert!(
        stderr.contains("--out-dir cannot be inside the input directory"),
        "unexpected stderr: {}",
        stderr
    );

    let original = fs::read_to_string(dst_dir.join("simple_module.py"))?;
    assert!(
        original.contains("message"),
        "input files should remain untouched"
    );

    Ok(())
}

#[test]
fn apply_plan_in_place_with_backup_ext_creates_backup() -> Result<()> {
    let temp = TempDir::new()?;
    let src = fixture_path("src/simple_module.py");
    let dst = temp.path().join("simple_module.py");
    fs::copy(&src, &dst)?;

    let original = fs::read_to_string(&dst)?;

    let plan_path = temp.path().join("plan.json");
    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan")
        .arg(&dst)
        .output()
        .context("failed to execute tsrs-cli minify-plan for backup test")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    fs::write(&plan_path, &plan_output.stdout)?;

    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan")
        .arg(&dst)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--in-place")
        .arg("--backup-ext")
        .arg(".bak")
        .output()
        .context("failed to execute tsrs-cli apply-plan with backup")?;

    anyhow::ensure!(
        apply_output.status.success(),
        "apply-plan with backup exited with {}. stderr: {}",
        apply_output.status,
        String::from_utf8_lossy(&apply_output.stderr)
    );

    let mut backup_os = dst.as_os_str().to_os_string();
    backup_os.push(".bak");
    let backup_path = PathBuf::from(backup_os);

    let backup_content = fs::read_to_string(&backup_path)?;
    assert_eq!(
        backup_content, original,
        "backup file should match original"
    );

    let rewritten = fs::read_to_string(&dst)?;
    assert!(!rewritten.contains("message"));
    assert!(!rewritten.contains("suffix"));

    Ok(())
}

#[test]
fn apply_plan_dry_run_keeps_original() -> Result<()> {
    let temp = TempDir::new()?;
    let src = fixture_path("src/simple_module.py");
    let dst = temp.path().join("simple_module.py");
    fs::copy(&src, &dst)?;

    let baseline = fs::read_to_string(&dst)?;

    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan")
        .arg(&dst)
        .output()
        .context("failed to execute tsrs-cli minify-plan")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    let plan_path = temp.path().join("plan.json");
    fs::write(&plan_path, &plan_output.stdout)?;

    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan")
        .arg(&dst)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--dry-run")
        .output()
        .context("failed to execute tsrs-cli apply-plan --dry-run")?;

    anyhow::ensure!(
        apply_output.status.success(),
        "apply-plan --dry-run exited with {}. stderr: {}",
        apply_output.status,
        String::from_utf8_lossy(&apply_output.stderr)
    );

    let after = fs::read_to_string(&dst)?;
    assert_eq!(baseline, after, "dry run should not modify the file");

    Ok(())
}

#[test]
fn apply_plan_dir_with_out_dir_writes_results() -> Result<()> {
    let temp = TempDir::new()?;
    let src_dir = fixture_path("src");
    let dst_dir = temp.path().join("src");
    copy_dir_filtered(&src_dir, &dst_dir)?;
    materialize_pattern_fixture(&dst_dir)?;

    let plan_path = temp.path().join("plan.json");

    let plan_output = cargo_bin_cmd!("tsrs-cli")
        .arg("minify-plan-dir")
        .arg(&dst_dir)
        .arg("--out")
        .arg(&plan_path)
        .output()
        .context("failed to execute tsrs-cli minify-plan-dir")?;

    anyhow::ensure!(
        plan_output.status.success(),
        "minify-plan-dir exited with {}. stderr: {}",
        plan_output.status,
        String::from_utf8_lossy(&plan_output.stderr)
    );

    let out_dir = temp.path().join("out");

    let apply_output = cargo_bin_cmd!("tsrs-cli")
        .arg("apply-plan-dir")
        .arg(&dst_dir)
        .arg("--plan")
        .arg(&plan_path)
        .arg("--out-dir")
        .arg(&out_dir)
        .output()
        .context("failed to execute tsrs-cli apply-plan-dir --out-dir")?;

    anyhow::ensure!(
        apply_output.status.success(),
        "apply-plan-dir --out-dir exited with {}. stderr: {}",
        apply_output.status,
        String::from_utf8_lossy(&apply_output.stderr)
    );

    let original_simple = fs::read_to_string(dst_dir.join("simple_module.py"))?;
    assert!(original_simple.contains("message"));

    let rewritten_simple = fs::read_to_string(out_dir.join("simple_module.py"))?;
    assert!(!rewritten_simple.contains("message"));

    let rewritten_patterns = fs::read_to_string(out_dir.join("patterns.py"))?;
    assert!(rewritten_patterns.contains("match"));

    let rewritten_class = fs::read_to_string(out_dir.join("class_methods.py"))?;
    assert!(rewritten_class.contains("total ="));

    Ok(())
}
