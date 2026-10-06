use anyhow::{Context, Result};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use tempfile::TempDir;
use toml::Value;

fn copy_dir_filtered(src: &Path, dst: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;

    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();

        if name_str == "__pycache__" || name_str == ".venv" {
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

fn run_command(cmd: &mut Command, context: &str) -> Result<()> {
    let status = cmd
        .status()
        .with_context(|| format!("failed to {context}"))?;
    anyhow::ensure!(
        status.success(),
        "command to {context} exited with {status}"
    );
    Ok(())
}

fn create_venv(venv_dir: &Path) -> Result<()> {
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

fn bootstrap_pip(python: &Path) -> Result<()> {
    let mut command = Command::new(python);
    command.arg("-m").arg("ensurepip").arg("--upgrade");
    // If ensurepip is unavailable we ignore the failure and rely on an existing pip.
    let _ = command.status();
    Ok(())
}

fn install_package(venv_dir: &Path, package_dir: &Path) -> Result<()> {
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

    bootstrap_pip(&python)?;

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

fn install_requirement(venv_dir: &Path, requirement: &str) -> Result<()> {
    let python = venv_bin(venv_dir, "python");
    let wheelhouse = wheelhouse_dir();

    if uv_available() {
        let mut command = Command::new("uv");
        command
            .arg("pip")
            .arg("install")
            .arg("--quiet")
            .arg("--python")
            .arg(&python)
            .arg("--no-cache-dir");
        if let Some(ref wheelhouse) = wheelhouse {
            command
                .arg("--find-links")
                .arg(wheelhouse)
                .arg("--no-index");
        }
        command.arg(requirement);
        if run_command(
            &mut command,
            &format!("install requirement {requirement} using uv"),
        )
        .is_ok()
        {
            return Ok(());
        }
    }

    bootstrap_pip(&python)?;

    let mut command = Command::new(&python);
    command
        .arg("-m")
        .arg("pip")
        .arg("install")
        .arg("--quiet")
        .arg("--no-cache-dir");
    if let Some(ref wheelhouse) = wheelhouse {
        command
            .arg("--find-links")
            .arg(wheelhouse)
            .arg("--no-index");
    }
    command.arg(requirement);
    run_command(&mut command, &format!("install requirement {requirement}"))
}

fn load_pyproject(package_dir: &Path) -> Result<Option<Value>> {
    let path = package_dir.join("pyproject.toml");
    if !path.exists() {
        return Ok(None);
    }
    let content =
        fs::read_to_string(&path).with_context(|| format!("failed to read {}", path.display()))?;
    let value: Value =
        toml::from_str(&content).with_context(|| format!("failed to parse {}", path.display()))?;
    Ok(Some(value))
}

fn distribution_name(pyproject: &Value) -> Option<&str> {
    pyproject
        .get("project")
        .and_then(|section| section.get("name"))
        .and_then(Value::as_str)
}

fn project_dependencies(pyproject: &Value) -> Vec<String> {
    pyproject
        .get("project")
        .and_then(|section| section.get("dependencies"))
        .and_then(Value::as_array)
        .map(|deps| {
            deps.iter()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect()
        })
        .unwrap_or_default()
}

fn local_dependency_map(pyproject: &Value) -> HashMap<String, PathBuf> {
    let mut map = HashMap::new();
    let tool = match pyproject.get("tool") {
        Some(value) => value,
        None => return map,
    };
    let tsrs = match tool.get("tsrs") {
        Some(value) => value,
        None => return map,
    };
    let table = match tsrs.get("local-dependencies") {
        Some(value) => value,
        None => return map,
    };
    if let Some(deps) = table.as_table() {
        for (key, value) in deps {
            if let Some(path_str) = value.as_str() {
                map.insert(key.clone(), PathBuf::from(path_str));
            }
        }
    }
    map
}

fn module_candidates(package_dir: &Path, distribution: &str) -> Vec<PathBuf> {
    let mut result = Vec::new();
    let module = distribution.replace('-', "_");
    let src_dir = package_dir.join("src");
    let src_pkg = src_dir.join(&module);
    if src_pkg.is_dir() {
        result.push(src_pkg);
    }
    let direct_pkg = package_dir.join(&module);
    if direct_pkg.is_dir() {
        result.push(direct_pkg);
    }
    let direct_file = package_dir.join(format!("{module}.py"));
    if direct_file.is_file() {
        result.push(direct_file);
    }
    if result.is_empty() {
        if let Ok(entries) = fs::read_dir(package_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() && path.join("__init__.py").is_file() {
                    result.push(path);
                }
            }
        }
    }
    result
}

fn run_minify_target(target: &Path) -> Result<()> {
    let output = if target.is_dir() {
        assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
            .arg("minify-dir")
            .arg(target)
            .arg("--in-place")
            .output()
            .with_context(|| {
                format!(
                    "failed to execute tsrs-cli minify-dir on {}",
                    target.display()
                )
            })?
    } else {
        assert_cmd::cargo::cargo_bin_cmd!("tsrs-cli")
            .arg("minify")
            .arg(target)
            .arg("--in-place")
            .output()
            .with_context(|| format!("failed to execute tsrs-cli minify on {}", target.display()))?
    };

    anyhow::ensure!(
        output.status.success(),
        "tsrs-cli minify command failed for {}. stderr: {}",
        target.display(),
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}

fn minify_dependency_tree(package_dir: &Path, visited: &mut HashSet<PathBuf>) -> Result<()> {
    let canonical = fs::canonicalize(package_dir)
        .with_context(|| format!("failed to canonicalize {}", package_dir.display()))?;
    if !visited.insert(canonical.clone()) {
        return Ok(());
    }

    let Some(pyproject) = load_pyproject(&canonical)? else {
        return Ok(());
    };

    let local_map = local_dependency_map(&pyproject);
    for requirement in project_dependencies(&pyproject) {
        let name = requirement
            .split(|c| c == ' ' || c == '=' || c == '<' || c == '>' || c == '!')
            .next()
            .unwrap_or_default()
            .trim();
        if name.is_empty() {
            continue;
        }
        if let Some(relative) = local_map.get(name) {
            let dependency_path = canonical.join(relative);
            minify_dependency_tree(&dependency_path, visited)?;
        }
    }

    if let Some(distribution) = distribution_name(&pyproject) {
        for target in module_candidates(&canonical, distribution) {
            run_minify_target(&target)?;
        }
    }

    Ok(())
}

fn wheelhouse_dir() -> Option<PathBuf> {
    if let Ok(custom) = std::env::var("TSRS_WHEELHOUSE") {
        let path = PathBuf::from(custom);
        if path.is_dir() {
            return Some(path);
        }
    }

    let default = Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/.wheelhouse");
    if default.is_dir() {
        Some(default)
    } else {
        None
    }
}

#[test]
fn minified_dependency_keeps_consumer_tests_green() -> Result<()> {
    let temp = TempDir::new()?;

    let fixture_root =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("test_packages/test_minify_dependency");
    let dependency_src = fixture_root.join("dependency_pkg");
    let core_src = fixture_root.join("core_pkg");
    let consumer_src = fixture_root.join("consumer_pkg");

    let dependency_dst = temp.path().join("dependency_pkg");
    copy_dir_filtered(&dependency_src, &dependency_dst)?;
    let core_dst = temp.path().join("core_pkg");
    copy_dir_filtered(&core_src, &core_dst)?;
    let consumer_dst = temp.path().join("consumer_pkg");
    copy_dir_filtered(&consumer_src, &consumer_dst)?;

    let mut visited = HashSet::new();
    minify_dependency_tree(&dependency_dst, &mut visited)?;

    let dependency_source =
        fs::read_to_string(dependency_dst.join("minify_dep").join("__init__.py"))?;
    anyhow::ensure!(
        !dependency_source.contains("message"),
        "expected local variable names to be minified"
    );
    let core_source = fs::read_to_string(core_dst.join("minify_core").join("__init__.py"))?;
    anyhow::ensure!(
        !core_source.contains("total += extra"),
        "expected transitive dependency locals to be minified"
    );

    let venv_dir = temp.path().join("venv");
    create_venv(&venv_dir)?;
    install_package(&venv_dir, &core_dst)?;
    install_package(&venv_dir, &dependency_dst)?;
    install_package(&venv_dir, &consumer_dst)?;
    install_requirement(&venv_dir, "pytest")?;

    let mut pytest = Command::new(venv_bin(&venv_dir, "python"));
    pytest
        .arg("-m")
        .arg("pytest")
        .arg("-q")
        .current_dir(&consumer_dst);
    run_command(
        &mut pytest,
        "run consumer pytest suite after minifying dependency",
    )?;

    Ok(())
}
