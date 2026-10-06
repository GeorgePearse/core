use anyhow::{self, bail, Context};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use tempfile::TempDir;

fn copy_dir_filtered(src: &Path, dst: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;

    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();

        if name_str == ".venv" || name_str == ".pytest_cache" {
            continue;
        }

        let src_path = entry.path();
        let dst_path = dst.join(&name);

        if entry.file_type()?.is_dir() {
            copy_dir_filtered(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, dst_path)?;
        }
    }

    Ok(())
}

fn uv_available() -> bool {
    Command::new("uv")
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn python_executable() -> PathBuf {
    std::env::var_os("PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            if cfg!(windows) {
                PathBuf::from("python")
            } else {
                PathBuf::from("python3")
            }
        })
}

fn venv_bin(venv: &Path, tool: &str) -> PathBuf {
    if cfg!(windows) {
        venv.join("Scripts").join(format!("{tool}.exe"))
    } else {
        venv.join("bin").join(tool)
    }
}

fn run_command(cmd: &mut Command, context: &str) -> anyhow::Result<()> {
    let status = cmd
        .status()
        .with_context(|| format!("failed to {context}"))?;
    anyhow::ensure!(
        status.success(),
        "command to {context} exited with {status}"
    );
    Ok(())
}

fn create_venv(venv_dir: &Path) -> anyhow::Result<()> {
    if uv_available() {
        let mut command = Command::new("uv");
        command.arg("venv").arg(venv_dir);
        return run_command(
            &mut command,
            &format!("create virtualenv using uv at {}", venv_dir.display()),
        );
    }

    let python = python_executable();
    let mut command = Command::new(&python);
    command.arg("-m").arg("venv").arg(venv_dir);
    run_command(
        &mut command,
        &format!("create virtualenv using {}", python.display()),
    )
}

fn install_package(venv_dir: &Path, package_dir: &Path) -> anyhow::Result<()> {
    let python = venv_bin(venv_dir, "python");

    if uv_available() {
        let mut command = Command::new("uv");
        command
            .arg("pip")
            .arg("install")
            .arg("--quiet")
            .arg("--python")
            .arg(&python)
            .arg(package_dir);
        if run_command(
            &mut command,
            &format!("install package from {} using uv", package_dir.display()),
        )
        .is_ok()
        {
            return Ok(());
        }
    }

    let mut command = Command::new(&python);
    command.arg("-m").arg("ensurepip").arg("--upgrade");
    let _ = run_command(
        &mut command,
        &format!("bootstrap pip for venv {}", venv_dir.display()),
    );

    let mut command = Command::new(&python);
    command
        .arg("-m")
        .arg("pip")
        .arg("install")
        .arg("--quiet")
        .arg(package_dir);
    run_command(
        &mut command,
        &format!("install package from {}", package_dir.display()),
    )
}

fn site_packages_path(venv: &Path) -> anyhow::Result<PathBuf> {
    if cfg!(windows) {
        let candidate = venv.join("Lib").join("site-packages");
        if candidate.is_dir() {
            return Ok(candidate);
        }
    } else {
        let lib_dir = venv.join("lib");
        if lib_dir.is_dir() {
            for entry in fs::read_dir(&lib_dir)? {
                let entry = entry?;
                let path = entry.path();
                if path.is_dir() {
                    let site = path.join("site-packages");
                    if site.is_dir() {
                        return Ok(site);
                    }
                }
            }
        }
    }

    bail!("could not locate site-packages under {}", venv.display());
}

fn package_exists(site_packages: &Path, name: &str) -> anyhow::Result<bool> {
    if site_packages.join(name).exists() {
        return Ok(true);
    }

    for entry in fs::read_dir(site_packages)? {
        let entry = entry?;
        let candidate = entry.file_name();
        let candidate_str = candidate.to_string_lossy();
        if candidate_str == name
            || candidate_str == format!("{name}.py")
            || candidate_str.starts_with(&format!("{name}-"))
                && candidate_str.ends_with(".dist-info")
        {
            return Ok(true);
        }
    }

    Ok(false)
}

fn run_slim_case_internal(project_subdir: &str) -> anyhow::Result<(TempDir, PathBuf)> {
    let temp = TempDir::new()?;

    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_src = fixture_root.join("used_pkg");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join(project_subdir);

    let used_dst = temp.path().join("used_pkg");
    copy_dir_filtered(&used_src, &used_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join(project_subdir);
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .with_context(|| format!("failed to execute tsrs-cli slim for {}", project_subdir))?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    Ok((temp, slim_dir))
}

fn run_slim_case(project_subdir: &str) -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal(project_subdir)?;

    let site_packages = site_packages_path(&slim_dir)?;
    let used_present = package_exists(&site_packages, "used_pkg")?;
    let unused_present = package_exists(&site_packages, "unused_pkg")?;

    anyhow::ensure!(
        used_present,
        "expected used_pkg to be present in {}",
        site_packages.display()
    );
    anyhow::ensure!(
        !unused_present,
        "expected unused_pkg to be pruned from {}",
        site_packages.display()
    );

    Ok(())
}

fn dist_info_exists(site_packages: &Path, slug: &str) -> anyhow::Result<bool> {
    for entry in fs::read_dir(site_packages)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        if name_str.contains(slug) && name_str.ends_with(".dist-info") {
            return Ok(true);
        }
    }
    Ok(false)
}

#[test]
fn analyze_reports_installed_package_from_fixture() -> anyhow::Result<()> {
    let temp = TempDir::new()?;

    let fixture = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("test_packages/test_unused_function/package_one");
    let workdir = temp.path().join("package_one");
    copy_dir_filtered(&fixture, &workdir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &workdir)?;

    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("analyze")
        .arg(&venv_dir)
        .output()
        .context("failed to execute tsrs-cli analyze")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli analyze exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        stdout.contains("package_one"),
        "expected analyze output to mention package_one, got:\n{}",
        stdout
    );

    Ok(())
}

#[test]
fn analyze_reports_single_module_and_package() -> anyhow::Result<()> {
    let temp = TempDir::new()?;

    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_mod_src = fixture_root.join("used_mod");
    let used_pkg_src = fixture_root.join("used_pkg");

    let used_mod_dst = temp.path().join("used_mod");
    copy_dir_filtered(&used_mod_src, &used_mod_dst)?;
    let used_pkg_dst = temp.path().join("used_pkg");
    copy_dir_filtered(&used_pkg_src, &used_pkg_dst)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_mod_dst)?;
    install_package(&venv_dir, &used_pkg_dst)?;

    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("analyze")
        .arg(&venv_dir)
        .output()
        .context("failed to execute tsrs-cli analyze for single module + package")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli analyze exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout)?;
    assert!(
        stdout.contains("used_pkg"),
        "expected analyze output to mention used_pkg, got:\n{}",
        stdout
    );
    assert!(
        stdout.contains("used_mod"),
        "expected analyze output to mention used_mod, got:\n{}",
        stdout
    );

    Ok(())
}

#[test]
fn analyze_reports_namespace_package() -> anyhow::Result<()> {
    let temp = TempDir::new()?;

    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_ns_src = fixture_root.join("used_ns_pkg");

    let used_ns_dst = temp.path().join("used_ns_pkg");
    copy_dir_filtered(&used_ns_src, &used_ns_dst)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_ns_dst)?;

    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("analyze")
        .arg(&venv_dir)
        .output()
        .context("failed to execute tsrs-cli analyze for namespace package")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli analyze exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout)?;
    assert!(
        stdout.contains("used_ns_pkg"),
        "expected analyze output to mention used_ns_pkg, got:\n{}",
        stdout
    );

    Ok(())
}

#[test]
fn slim_keeps_used_package_direct_import() -> anyhow::Result<()> {
    run_slim_case("project")
}

#[test]
fn slim_keeps_used_package_from_import() -> anyhow::Result<()> {
    run_slim_case("project_from_import")
}

#[test]
fn slim_keeps_used_package_alias_import() -> anyhow::Result<()> {
    run_slim_case("project_alias_import")
}

#[test]
fn slim_keeps_used_package_submodule_import() -> anyhow::Result<()> {
    run_slim_case("project_submodule_import")
}

#[test]
fn slim_keeps_used_package_wildcard_import() -> anyhow::Result<()> {
    run_slim_case("project_wildcard_import")
}

#[test]
fn slim_keeps_used_package_reexport_attr() -> anyhow::Result<()> {
    run_slim_case("project_reexport_get_tool")
}

#[test]
fn slim_keeps_used_package_alias_function_import() -> anyhow::Result<()> {
    run_slim_case("project_alias_function")
}

#[test]
fn slim_keeps_used_package_submodule_alias_import() -> anyhow::Result<()> {
    run_slim_case("project_submodule_alias")
}

#[test]
fn slim_keeps_used_package_submodule_wildcard_import() -> anyhow::Result<()> {
    run_slim_case("project_submodule_wildcard")
}

#[test]
fn slim_keeps_used_package_multiline_import() -> anyhow::Result<()> {
    run_slim_case("project_multiline_import")
}

#[test]
fn slim_keeps_used_package_function_scope_import() -> anyhow::Result<()> {
    run_slim_case("project_function_scope_import")
}

#[test]
fn slim_keeps_used_package_try_except_import() -> anyhow::Result<()> {
    run_slim_case("project_try_except_import")
}

#[test]
fn slim_keeps_used_package_if_block_import() -> anyhow::Result<()> {
    run_slim_case("project_if_block_import")
}

#[test]
fn slim_keeps_used_package_backslash_import() -> anyhow::Result<()> {
    run_slim_case("project_backslash_import")
}

#[test]
fn slim_keeps_used_package_multi_import_statement() -> anyhow::Result<()> {
    run_slim_case("project_multi_import")
}

#[test]
fn slim_keeps_used_package_submodule_alias_item() -> anyhow::Result<()> {
    run_slim_case("project_submodule_alias_item")
}

#[test]
fn slim_keeps_used_package_relative_import() -> anyhow::Result<()> {
    run_slim_case("project_package_relative")
}

#[test]
fn slim_copies_used_metadata() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project")?;
    let site_packages = site_packages_path(&slim_dir)?;

    let used_metadata = dist_info_exists(&site_packages, "used_pkg")?;
    assert!(used_metadata, "expected used_pkg dist-info to be present");

    Ok(())
}

#[test]
fn slim_prunes_unused_metadata() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project")?;
    let site_packages = site_packages_path(&slim_dir)?;

    let unused_metadata = dist_info_exists(&site_packages, "unused_pkg")?;
    assert!(
        !unused_metadata,
        "expected unused_pkg dist-info to be removed"
    );

    Ok(())
}

#[test]
fn slim_preserves_package_resources() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project_resource_access")?;
    let site_packages = site_packages_path(&slim_dir)?;
    let resource_path = site_packages
        .join("used_pkg")
        .join("resources")
        .join("config.json");
    assert!(
        resource_path.exists(),
        "expected config.json to be copied to slim venv"
    );

    Ok(())
}

#[test]
fn slim_preserves_nested_template_resources() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project_resource_template")?;
    let site_packages = site_packages_path(&slim_dir)?;
    let template_path = site_packages
        .join("used_pkg")
        .join("resources")
        .join("templates")
        .join("welcome.txt");
    assert!(
        template_path.exists(),
        "expected welcome.txt to be copied to slim venv"
    );

    Ok(())
}

#[test]
fn slim_preserves_pkgutil_resource_access() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project_resource_pkgutil")?;
    let site_packages = site_packages_path(&slim_dir)?;
    let resource_path = site_packages
        .join("used_pkg")
        .join("resources")
        .join("config.json");
    assert!(
        resource_path.exists(),
        "expected config.json to be present for pkgutil access"
    );

    Ok(())
}

#[test]
fn slim_preserves_resources_files_api() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project_resource_files")?;
    let site_packages = site_packages_path(&slim_dir)?;
    let resource_path = site_packages
        .join("used_pkg")
        .join("resources")
        .join("config.json");
    assert!(
        resource_path.exists(),
        "expected config.json to remain for files() API access"
    );

    Ok(())
}

#[test]
fn slim_prunes_dynamic_imported_package() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project_dynamic_import")?;
    let site_packages = site_packages_path(&slim_dir)?;
    let used_present = package_exists(&site_packages, "used_pkg")?;
    assert!(
        !used_present,
        "tsrs should surface dynamic import limitations by pruning used_pkg"
    );

    Ok(())
}

#[test]
fn slim_prunes_type_checking_import() -> anyhow::Result<()> {
    let (_temp, slim_dir) = run_slim_case_internal("project_type_checking_import")?;
    let site_packages = site_packages_path(&slim_dir)?;
    let used_present = package_exists(&site_packages, "used_pkg")?;
    assert!(
        !used_present,
        "TYPE_CHECKING-only imports should be pruned from the slim venv"
    );

    Ok(())
}

#[test]
fn slim_preserves_native_library_files() -> anyhow::Result<()> {
    let temp = TempDir::new()?;

    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_native_src = fixture_root.join("used_native");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_native_resource");

    let used_native_dst = temp.path().join("used_native");
    copy_dir_filtered(&used_native_src, &used_native_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_native_resource");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_native_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for native resource project")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    let native_lib = site_packages
        .join("used_native")
        .join("libs")
        .join("libdummy.so");
    assert!(
        native_lib.exists(),
        "expected libdummy.so to be copied to the slim virtual environment"
    );

    let unused_present = package_exists(&site_packages, "unused_pkg")?;
    assert!(
        !unused_present,
        "expected unused_pkg to be pruned from {}",
        site_packages.display()
    );

    Ok(())
}

#[test]
fn slim_keeps_both_used_packages() -> anyhow::Result<()> {
    let temp = TempDir::new()?;

    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_src = fixture_root.join("used_pkg");
    let used2_src = fixture_root.join("used_pkg2");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_two_used_packages");

    let used_dst = temp.path().join("used_pkg");
    copy_dir_filtered(&used_src, &used_dst)?;
    let used2_dst = temp.path().join("used_pkg2");
    copy_dir_filtered(&used2_src, &used2_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_two_used_packages");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_dst)?;
    install_package(&venv_dir, &used2_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_two_used_packages")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(package_exists(&site_packages, "used_pkg")?);
    assert!(package_exists(&site_packages, "used_pkg2")?);
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_single_module_distribution() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_mod_src = fixture_root.join("used_mod");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_single_module_import");

    let used_mod_dst = temp.path().join("used_mod");
    copy_dir_filtered(&used_mod_src, &used_mod_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_single_module_import");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_mod_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_single_module_import")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(site_packages.join("used_mod.py").exists());
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_dash_pkg_distribution() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let dash_src = fixture_root.join("dash_pkg");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_dash_import");

    let dash_dst = temp.path().join("dash_pkg");
    copy_dir_filtered(&dash_src, &dash_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_dash_import");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &dash_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for dash-pkg project")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(
        package_exists(&site_packages, "dash_pkg")?,
        "expected dash_pkg to be present in {}",
        site_packages.display()
    );
    assert!(
        !package_exists(&site_packages, "unused_pkg")?,
        "expected unused_pkg to be pruned from {}",
        site_packages.display()
    );

    Ok(())
}

#[test]
fn slim_prunes_unused_transitive_dependency() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_pkg_extra_src = fixture_root.join("used_pkg_extra");
    let extra_dep_src = fixture_root.join("extra_dep");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_extra_dep_unused");

    let used_pkg_extra_dst = temp.path().join("used_pkg_extra");
    copy_dir_filtered(&used_pkg_extra_src, &used_pkg_extra_dst)?;
    let extra_dep_dst = temp.path().join("extra_dep");
    copy_dir_filtered(&extra_dep_src, &extra_dep_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_extra_dep_unused");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &extra_dep_dst)?;
    install_package(&venv_dir, &used_pkg_extra_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_extra_dep_unused")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(package_exists(&site_packages, "used_pkg_extra")?);
    assert!(!package_exists(&site_packages, "extra_dep")?);
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_namespace_package() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_ns_src = fixture_root.join("used_ns_pkg");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_namespace_import");

    let used_ns_dst = temp.path().join("used_ns_pkg");
    copy_dir_filtered(&used_ns_src, &used_ns_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_namespace_import");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_ns_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_namespace_import")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(package_exists(&site_packages, "used_ns_pkg")?);
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_only_used_pkg2() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_pkg_src = fixture_root.join("used_pkg");
    let used_pkg2_src = fixture_root.join("used_pkg2");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_only_used_pkg2");

    let used_pkg_dst = temp.path().join("used_pkg");
    copy_dir_filtered(&used_pkg_src, &used_pkg_dst)?;
    let used_pkg2_dst = temp.path().join("used_pkg2");
    copy_dir_filtered(&used_pkg2_src, &used_pkg2_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_only_used_pkg2");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_pkg_dst)?;
    install_package(&venv_dir, &used_pkg2_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_only_used_pkg2")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(!package_exists(&site_packages, "used_pkg")?);
    assert!(package_exists(&site_packages, "used_pkg2")?);
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_namespace_package_split_across_distributions() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_ns_src = fixture_root.join("used_ns_pkg");
    let used_ns_part_src = fixture_root.join("used_ns_pkg_part");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_namespace_multipkg");

    let used_ns_dst = temp.path().join("used_ns_pkg");
    copy_dir_filtered(&used_ns_src, &used_ns_dst)?;
    let used_ns_part_dst = temp.path().join("used_ns_pkg_part");
    copy_dir_filtered(&used_ns_part_src, &used_ns_part_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_namespace_multipkg");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_ns_dst)?;
    install_package(&venv_dir, &used_ns_part_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_namespace_multipkg")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(site_packages.join("used_ns_pkg").join("sub").exists());
    assert!(site_packages.join("used_ns_pkg").join("extra").exists());
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_used_transitive_dependency() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_pkg_transitive_src = fixture_root.join("used_pkg_transitive");
    let extra_dep_src = fixture_root.join("extra_dep");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_used_transitive");

    let used_pkg_transitive_dst = temp.path().join("used_pkg_transitive");
    copy_dir_filtered(&used_pkg_transitive_src, &used_pkg_transitive_dst)?;
    let extra_dep_dst = temp.path().join("extra_dep");
    copy_dir_filtered(&extra_dep_src, &extra_dep_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_used_transitive");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &extra_dep_dst)?;
    install_package(&venv_dir, &used_pkg_transitive_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_used_transitive")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(package_exists(&site_packages, "used_pkg_transitive")?);
    assert!(package_exists(&site_packages, "extra_dep")?);
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_prunes_unused_module_from_py_modules_distribution() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let multi_mod_src = fixture_root.join("multi_mod");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_select_alpha");

    let multi_mod_dst = temp.path().join("multi_mod");
    copy_dir_filtered(&multi_mod_src, &multi_mod_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_select_alpha");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &multi_mod_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_select_alpha")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(site_packages.join("alpha.py").exists());
    assert!(!site_packages.join("beta.py").exists());
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_implicit_namespace_package() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_ns_src = fixture_root.join("used_ns_implicit");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_implicit_namespace_import");

    let used_ns_dst = temp.path().join("used_ns_implicit");
    copy_dir_filtered(&used_ns_src, &used_ns_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_implicit_namespace_import");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_ns_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for implicit namespace project")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(site_packages.join("used_ns_implicit").join("sub").exists());
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}

#[test]
fn slim_keeps_used_package_import_chain_subpkg() -> anyhow::Result<()> {
    run_slim_case("project_import_chain_subpkg")
}

#[test]
fn slim_keeps_used_package_from_pkg_import_subpkg() -> anyhow::Result<()> {
    run_slim_case("project_from_pkg_import_subpkg")
}

#[test]
fn slim_keeps_src_layout_package_and_typed_marker() -> anyhow::Result<()> {
    let temp = TempDir::new()?;
    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_slim_packages");
    let used_src_layout_src = fixture_root.join("used_src_layout");
    let unused_src = fixture_root.join("unused_pkg");
    let project_src = fixture_root.join("project_src_layout_import");

    let used_src_layout_dst = temp.path().join("used_src_layout");
    copy_dir_filtered(&used_src_layout_src, &used_src_layout_dst)?;
    let unused_dst = temp.path().join("unused_pkg");
    copy_dir_filtered(&unused_src, &unused_dst)?;
    let project_dir = temp.path().join("project_src_layout_import");
    copy_dir_filtered(&project_src, &project_dir)?;

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &used_src_layout_dst)?;
    install_package(&venv_dir, &unused_dst)?;

    let slim_dir = temp.path().join("slim-venv");
    let output = assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
        .arg("slim")
        .arg(&project_dir)
        .arg(&venv_dir)
        .arg("--output")
        .arg(&slim_dir)
        .output()
        .context("failed to execute tsrs-cli slim for project_src_layout_import")?;

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli slim exited with {}. stderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let site_packages = site_packages_path(&slim_dir)?;
    assert!(package_exists(&site_packages, "used_src_layout")?);
    assert!(site_packages
        .join("used_src_layout")
        .join("py.typed")
        .exists());
    assert!(!package_exists(&site_packages, "unused_pkg")?);

    Ok(())
}
