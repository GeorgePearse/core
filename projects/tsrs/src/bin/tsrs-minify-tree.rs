use anyhow::{bail, Context, Result};
use std::collections::{BTreeSet, HashMap, HashSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use toml::Value;

fn main() {
    if let Err(error) = run() {
        eprintln!("error: {}", error);
        for cause in error.chain().skip(1) {
            eprintln!("  caused by: {}", cause);
        }
        std::process::exit(2);
    }
}

fn run() -> Result<()> {
    let mut args = env::args_os().skip(1);
    let root = match args.next() {
        Some(path) => PathBuf::from(path),
        None => env::current_dir().context("determine current directory")?,
    };

    if args.next().is_some() {
        bail!("usage: tsrs-minify-tree [path]");
    }

    let canonical_root = root
        .canonicalize()
        .with_context(|| format!("canonicalizing project root {}", root.display()))?;

    let mut visited = HashSet::new();
    traverse_package(canonical_root, &mut visited)
}

fn traverse_package(dir: PathBuf, visited: &mut HashSet<PathBuf>) -> Result<()> {
    if !visited.insert(dir.clone()) {
        return Ok(());
    }

    let config = load_package_config(&dir)?;

    for dependency in &config.dependencies {
        if let Some(entry) = config.local_dependencies.get(dependency) {
            let dependency_dir = dir.join(&entry.relative).canonicalize().with_context(|| {
                format!(
                    "canonicalizing local dependency {dependency} (path {}) from {}",
                    entry.relative.display(),
                    dir.display()
                )
            })?;
            traverse_package(dependency_dir, visited)?;
        }
    }

    minify_package(&dir, &config.name)
}

fn load_package_config(dir: &Path) -> Result<PackageConfig> {
    let pyproject_path = dir.join("pyproject.toml");
    let contents = fs::read_to_string(&pyproject_path)
        .with_context(|| format!("reading {}", pyproject_path.display()))?;

    let document: Value = toml::from_str(&contents)
        .with_context(|| format!("parsing {}", pyproject_path.display()))?;

    let project = document
        .get("project")
        .and_then(Value::as_table)
        .context("pyproject.toml missing [project] table")?;

    let name = project
        .get("name")
        .and_then(Value::as_str)
        .context("pyproject.toml missing project.name")?
        .to_string();

    let mut dependencies = Vec::new();
    if let Some(array) = project.get("dependencies").and_then(Value::as_array) {
        for item in array {
            if let Some(raw) = item.as_str() {
                if let Some(normalized) = extract_dependency_name(raw) {
                    if !dependencies.contains(&normalized) {
                        dependencies.push(normalized);
                    }
                }
            }
        }
    }

    let mut local_dependencies = HashMap::new();
    if let Some(table) = document
        .get("tool")
        .and_then(Value::as_table)
        .and_then(|tool| tool.get("tsrs"))
        .and_then(Value::as_table)
        .and_then(|tsrs| tsrs.get("local-dependencies"))
        .and_then(Value::as_table)
    {
        for (key, value) in table {
            let path_str = value.as_str().with_context(|| {
                format!("tool.tsrs.local-dependencies.{key} must be a string path")
            })?;
            local_dependencies.insert(
                normalize_package_key(key),
                LocalDependency {
                    relative: PathBuf::from(path_str),
                },
            );
        }
    }

    Ok(PackageConfig {
        name,
        dependencies,
        local_dependencies,
    })
}

fn minify_package(dir: &Path, package_name: &str) -> Result<()> {
    let targets = discover_module_targets(dir, package_name)?;
    if targets.is_empty() {
        bail!(
            "no module targets found for package {package_name} in {}",
            dir.display()
        );
    }

    for target in targets {
        eprintln!("minifying {}", target.path.display());

        let mut command = Command::new("tsrs-cli");
        match target.kind {
            TargetKind::Directory => {
                command.arg("minify-dir");
            }
            TargetKind::File => {
                command.arg("minify");
            }
        }

        command.arg(&target.path);
        command.arg("--in-place");
        command.current_dir(dir);
        command.stdout(Stdio::inherit());
        command.stderr(Stdio::inherit());

        let status = command.status().with_context(|| {
            format!(
                "failed to spawn tsrs-cli while minifying {}",
                target.path.display()
            )
        })?;

        if !status.success() {
            bail!(
                "tsrs-cli exited with status {} while processing {}",
                status,
                target.path.display()
            );
        }
    }

    Ok(())
}

fn discover_module_targets(dir: &Path, package_name: &str) -> Result<Vec<ModuleTarget>> {
    let mut results = Vec::new();
    let mut seen = HashSet::new();
    let module_names = module_name_candidates(package_name);

    for module_name in module_names {
        let src_root = dir.join("src");
        push_target(
            &mut results,
            &mut seen,
            src_root.join(&module_name),
            TargetKind::Directory,
        );
        push_target(
            &mut results,
            &mut seen,
            src_root.join(format!("{module_name}.py")),
            TargetKind::File,
        );
        push_target(
            &mut results,
            &mut seen,
            dir.join(&module_name),
            TargetKind::Directory,
        );
        push_target(
            &mut results,
            &mut seen,
            dir.join(format!("{module_name}.py")),
            TargetKind::File,
        );
    }

    Ok(results)
}

fn push_target(
    results: &mut Vec<ModuleTarget>,
    seen: &mut HashSet<PathBuf>,
    candidate: PathBuf,
    kind: TargetKind,
) {
    match kind {
        TargetKind::Directory => {
            if candidate.is_dir() && seen.insert(candidate.clone()) {
                results.push(ModuleTarget {
                    path: candidate,
                    kind,
                });
            }
        }
        TargetKind::File => {
            if candidate.is_file() && seen.insert(candidate.clone()) {
                results.push(ModuleTarget {
                    path: candidate,
                    kind,
                });
            }
        }
    }
}

fn module_name_candidates(project_name: &str) -> Vec<String> {
    let top_level = project_name
        .split('.')
        .next()
        .map(str::trim)
        .unwrap_or("")
        .to_string();
    let mut set = BTreeSet::new();

    if !top_level.is_empty() {
        set.insert(top_level.clone());
        set.insert(top_level.to_ascii_lowercase());
        let underscored = top_level.replace('-', "_");
        set.insert(underscored.clone());
        set.insert(underscored.to_ascii_lowercase());
    }

    set.into_iter().filter(|entry| !entry.is_empty()).collect()
}

fn extract_dependency_name(raw: &str) -> Option<String> {
    let before_marker = raw.split(';').next()?.trim();
    let before_url = before_marker.split('@').next()?.trim();
    let mut end = before_url.len();
    for (idx, ch) in before_url.char_indices() {
        if matches!(
            ch,
            '[' | ' ' | '\t' | '\r' | '\n' | '<' | '>' | '=' | '!' | '~' | ','
        ) {
            end = idx;
            break;
        }
    }
    let candidate = before_url[..end].trim();
    if candidate.is_empty() {
        None
    } else {
        Some(normalize_package_key(candidate))
    }
}

fn normalize_package_key(input: &str) -> String {
    let mut normalized = String::with_capacity(input.len());
    for ch in input.chars() {
        match ch {
            'A'..='Z' => normalized.push(ch.to_ascii_lowercase()),
            '-' | '_' | '.' => normalized.push('-'),
            _ => normalized.push(ch.to_ascii_lowercase()),
        }
    }
    normalized
}

struct PackageConfig {
    name: String,
    dependencies: Vec<String>,
    local_dependencies: HashMap<String, LocalDependency>,
}

struct LocalDependency {
    relative: PathBuf,
}

struct ModuleTarget {
    path: PathBuf,
    kind: TargetKind,
}

#[derive(Clone, Copy)]
enum TargetKind {
    Directory,
    File,
}
