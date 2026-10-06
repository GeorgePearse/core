use crate::anchors;
use crate::db::{Store, opt_text, text};
use crate::engine::Engine;
use crate::error::{Error, Result, invalid, other};
use crate::github::{GitHub, GitHubApi, quote};
use crate::ideas::{self, MANIFEST, Manifest};
use crate::judge::{self, CheckOptions, Target};
use crate::model::Model;
use crate::server;
use base64::Engine as _;
use clap::{CommandFactory, Parser, Subcommand};
use rusqlite::types::Value as Sql;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

#[derive(Parser)]
#[command(
    name = "memetics",
    about = "Standing upstream listeners and automatic adaptation PRs"
)]
struct Cli {
    /// State directory (database, mirrors and retained work directories).
    #[arg(long, global = true, env = "MEMETICS_STATE")]
    state: Option<PathBuf>,
    #[command(subcommand)]
    command: Commands,
}

#[derive(clap::Args)]
struct WorkerArgs {
    #[arg(long, default_value_t = 60)]
    poll_seconds: i64,
    #[arg(long, default_value_t = 20)]
    daily_model_calls: i64,
}

#[derive(Subcommand)]
enum Commands {
    /// Register or update listeners from a version 1 manifest.
    Register {
        manifest: PathBuf,
    },
    Pause {
        listener: String,
    },
    Resume {
        listener: String,
    },
    Status,
    ShowJob {
        id: i64,
    },
    /// Explicitly retry a blocked or waiting job.
    Retry {
        id: i64,
    },
    /// Full-text search over indexed upstream blobs.
    Search {
        query: String,
        #[arg(long)]
        repository: String,
    },
    /// Run the worker loop (or a single tick with --once).
    Run {
        #[command(flatten)]
        worker: WorkerArgs,
        #[arg(long)]
        once: bool,
        #[arg(long)]
        force_poll: bool,
        #[arg(long, default_value_t = 1)]
        max_jobs: i64,
    },
    /// Serve the dashboard and API while running the worker.
    Serve {
        #[command(flatten)]
        worker: WorkerArgs,
        #[arg(long, default_value = "127.0.0.1")]
        host: String,
        #[arg(long, default_value_t = 8776)]
        port: u16,
    },
    /// List the ideas in memetics.md, or check that their anchors still resolve.
    Ideas {
        #[arg(long, default_value = MANIFEST)]
        manifest: PathBuf,
        #[arg(long)]
        check: bool,
        /// Update line hints and moved or renamed anchors.
        #[arg(long)]
        fix: bool,
        /// Accept current content: fill missing hashes and re-hash changed anchors.
        #[arg(long)]
        rehash: bool,
        #[arg(long)]
        json: bool,
    },
    /// Which idea covers PATH[:LINE]?
    Locate {
        target: String,
        #[arg(long, default_value = MANIFEST)]
        manifest: PathBuf,
    },
    /// Judge whether a commit (REV or BASE..HEAD, or --staged) changed any recorded idea.
    CheckCommit {
        revision: Option<String>,
        #[arg(long)]
        staged: bool,
        #[arg(long, default_value_t = 0.7)]
        threshold: f64,
        /// Require a memetics.md amendment for refines_idea instead of warning.
        #[arg(long)]
        strict_refines: bool,
        /// Rewrite moved or renamed anchors in memetics.md (and stage it with --staged).
        #[arg(long)]
        update_anchors: bool,
        #[arg(long, default_value = "text", value_parser = ["text", "json", "markdown"])]
        format: String,
        #[arg(long, default_value = ".")]
        repo: PathBuf,
    },
    /// Install the idea-drift git hook.
    InstallHook {
        #[arg(long, default_value = "pre-commit", value_parser = ["pre-commit", "post-commit"])]
        kind: String,
        #[arg(long)]
        force: bool,
        #[arg(long, default_value = ".")]
        repo: PathBuf,
    },
    /// Print memetics.md source lines for an upstream repository: its CITATION.cff/codemeta.json
    /// identifier, or a SWHID-anchored code source for --path/--symbol.
    Cite {
        repository: String,
        #[arg(long, default_value = "HEAD")]
        r#ref: String,
        #[arg(long)]
        path: Option<String>,
        #[arg(long)]
        symbol: Option<String>,
    },
}

fn usage_error(message: &str) -> ! {
    Cli::command()
        .error(clap::error::ErrorKind::ValueValidation, message)
        .exit()
}

fn print(value: &Value) {
    println!(
        "{}",
        serde_json::to_string_pretty(value).unwrap_or_default()
    );
}

pub fn main() -> i32 {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_env("MEMETICS_LOG"))
        .with_writer(std::io::stderr)
        .init();
    let cli = Cli::parse();
    match run(cli) {
        Ok(code) => code,
        Err(e) => {
            eprintln!("error: {e}");
            1
        }
    }
}

fn state_dir(cli: &Cli) -> PathBuf {
    cli.state.clone().unwrap_or_else(|| {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
        PathBuf::from(home).join(".local/share/memetics")
    })
}

fn engine(store: &Store, worker: &WorkerArgs) -> Result<Engine> {
    Engine::new(
        store.clone(),
        Arc::new(GitHub::from_env()),
        Arc::new(Model::from_env()?),
        None,
        worker.poll_seconds,
        worker.daily_model_calls,
    )
}

fn run(cli: Cli) -> Result<i32> {
    let store = || Store::open(state_dir(&cli));
    match &cli.command {
        Commands::Register { manifest } => {
            let data: Value = serde_json::from_str(&std::fs::read_to_string(manifest)?)?;
            let listeners = data["listeners"].as_array().filter(|l| !l.is_empty());
            let (Some(1), Some(listeners)) = (data["version"].as_i64(), listeners) else {
                usage_error("a version 1 manifest with listeners is required");
            };
            print(&json!({"registered": store()?.register(listeners)?}));
        }
        Commands::Pause { listener } | Commands::Resume { listener } => {
            let enabled = matches!(cli.command, Commands::Resume { .. });
            store()?.enable(listener, enabled)?;
            print(&json!({"listener": listener, "enabled": enabled}));
        }
        Commands::Status => print(&store()?.status()?),
        Commands::ShowJob { id } => {
            let job = store()?.one("SELECT * FROM jobs WHERE id=?", [id])?;
            let out = job.map(|mut job| {
                for field in ["config", "evidence", "delivery"] {
                    if let Some(raw) = opt_text(&job, field) {
                        job.insert(
                            field.into(),
                            serde_json::from_str(&raw).unwrap_or(Value::String(raw)),
                        );
                    }
                }
                Value::Object(job)
            });
            print(&out.unwrap_or(Value::Null));
        }
        Commands::Retry { id } => {
            let store = store()?;
            let job = store.one("SELECT * FROM jobs WHERE id=?", [id])?;
            let Some(job) = job.filter(|j| {
                ["blocked", "retry", "delivering"].contains(&text(j, "status").as_str())
            }) else {
                usage_error("only blocked or waiting jobs can be retried");
            };
            let status = if opt_text(&job, "delivery").is_some() {
                "delivering"
            } else {
                "retry"
            };
            store.set_job(
                *id,
                status,
                &[
                    ("attempts", Sql::Integer(0)),
                    ("not_before", Sql::Real(0.0)),
                    ("reason", Sql::Text("explicit retry requested".into())),
                ],
            )?;
            print(&json!({"retry": id}));
        }
        Commands::Search { query, repository } => {
            print(&json!(store()?.search(query, repository)?))
        }
        Commands::Run {
            worker,
            once,
            force_poll,
            max_jobs,
        } => {
            let engine = engine(&store()?, worker)?;
            loop {
                print(&engine.tick(*max_jobs, *force_poll)?);
                if *once {
                    break;
                }
                std::thread::sleep(Duration::from_secs(worker.poll_seconds.clamp(1, 5) as u64));
            }
        }
        Commands::Serve { worker, host, port } => {
            let store = store()?;
            let engine = engine(&store, worker)?;
            server::serve(
                store,
                engine,
                host,
                *port,
                worker.poll_seconds.clamp(1, 5) as u64,
            )?;
        }
        Commands::Ideas {
            manifest,
            check,
            fix,
            rehash,
            json,
        } => return ideas_command(manifest, *check, *fix, *rehash, *json),
        Commands::Locate { target, manifest } => return locate(manifest, target),
        Commands::CheckCommit {
            revision,
            staged,
            threshold,
            strict_refines,
            update_anchors,
            format,
            repo,
        } => {
            let options = CheckOptions {
                repo: repo.canonicalize()?,
                target: Target::parse(revision.as_deref(), *staged)?,
                threshold: *threshold,
                strict_refines: *strict_refines,
                update_anchors: *update_anchors,
            };
            let judge = judge::from_env();
            let store = store()?;
            let mut report = judge::check_commit(&options, judge.as_deref().ok(), Some(&store))?;
            if let Err(e) = &judge
                && !report.errors.is_empty()
            {
                report.notes.push(format!("judge unavailable: {e}"));
            }
            let rendered = report.render(format);
            if !rendered.is_empty() {
                println!("{rendered}");
            }
            return Ok(report.exit_code());
        }
        Commands::InstallHook { kind, force, repo } => {
            let path = judge::install_hook(repo, kind, *force)?;
            println!("installed {}", path.display());
        }
        Commands::Cite {
            repository,
            r#ref,
            path,
            symbol,
        } => return cite(repository, r#ref, path.as_deref(), symbol.as_deref()),
    }
    Ok(0)
}

fn load(manifest: &Path) -> Result<(PathBuf, Manifest)> {
    let text = std::fs::read_to_string(manifest)
        .map_err(|e| invalid(format!("{}: {e}", manifest.display())))?;
    let root = manifest
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
        .to_path_buf();
    Ok((root, Manifest::parse(&text)?))
}

fn tracked_sources(root: &Path) -> Vec<(String, String)> {
    let mut command = std::process::Command::new("git");
    command.args(["ls-files", "-z"]).current_dir(root);
    let Ok(out) = crate::git::run_with_timeout(&mut command, Duration::from_secs(60), None) else {
        return vec![];
    };
    out.text()
        .split('\0')
        .filter(|p| anchors::supported(p))
        .filter_map(|p| {
            std::fs::read_to_string(root.join(p))
                .ok()
                .map(|c| (p.to_string(), c))
        })
        .collect()
}

fn ideas_command(
    manifest_path: &Path,
    check: bool,
    fix: bool,
    rehash: bool,
    as_json: bool,
) -> Result<i32> {
    let (root, mut manifest) = load(manifest_path)?;
    if !(check || fix || rehash) {
        if as_json {
            print(&json!(manifest.ideas));
        } else {
            for idea in &manifest.ideas {
                println!("{}: {}", idea.id, idea.statement);
                for source in &idea.sources {
                    println!("    source {}", source.render());
                }
                for anchor in &idea.code {
                    let lines = anchor
                        .lines
                        .map(|(a, b)| format!(":{a}-{b}"))
                        .unwrap_or_default();
                    println!(
                        "    code   {}{lines} {}",
                        anchor.path,
                        anchor.symbol.clone().unwrap_or_default()
                    );
                }
            }
        }
        return Ok(0);
    }
    let read = |path: &str| std::fs::read_to_string(root.join(path)).ok();
    let others = || tracked_sources(&root);
    let before = manifest.render();
    let results = ideas::check(&mut manifest, &read, &others, fix, rehash);
    let failing = |status: &str| match status {
        "ok" | "anchored" => false,
        "moved" => !(fix || rehash),
        "changed" => !rehash,
        _ => true,
    };
    if as_json {
        print(&json!(results));
    } else {
        for r in &results {
            println!("{:<10} {}: {} {}", r.status, r.idea, r.anchor, r.detail);
        }
    }
    if (fix || rehash) && manifest.render() != before {
        std::fs::write(manifest_path, manifest.render())?;
        eprintln!("updated {}", manifest_path.display());
    }
    Ok(if results.iter().any(|r| failing(r.status)) {
        1
    } else {
        0
    })
}

fn locate(manifest_path: &Path, target: &str) -> Result<i32> {
    let (root, manifest) = load(manifest_path)?;
    let (path, line) = match target.rsplit_once(':') {
        Some((p, l)) if l.parse::<usize>().is_ok() => (p, l.parse::<usize>().ok()),
        _ => (target, None),
    };
    let path = path.trim_start_matches("./");
    let content = std::fs::read_to_string(root.join(path)).ok();
    let mut found = false;
    for idea in &manifest.ideas {
        for anchor in idea.code.iter().filter(|a| a.path == path) {
            let lines = content
                .as_deref()
                .and_then(|c| anchors::current(path, c, anchor.symbol.as_deref()))
                .map(|(_, l, _)| l)
                .or(anchor.lines);
            let covered = match (line, lines) {
                (None, _) => true,
                (Some(n), Some((a, b))) => a <= n && n <= b,
                (Some(_), None) => false,
            };
            if covered {
                found = true;
                let span = lines.map(|(a, b)| format!(":{a}-{b}")).unwrap_or_default();
                println!(
                    "{}  {path}{span} {}  — {}",
                    idea.id,
                    anchor.symbol.clone().unwrap_or_default(),
                    idea.statement
                );
            }
        }
    }
    if !found {
        println!("no idea in {} covers {target}", manifest_path.display());
    }
    Ok(if found { 0 } else { 1 })
}

fn fetch(github: &GitHub, repo: &str, path: &str, reference: &str) -> Result<Option<String>> {
    let api = format!(
        "/repos/{repo}/contents/{}?ref={}",
        path.split('/').map(quote).collect::<Vec<_>>().join("/"),
        quote(reference)
    );
    match github.request(reqwest::Method::GET, &api, None, None) {
        Ok((Some(data), _)) => {
            let encoded: String = data["content"]
                .as_str()
                .unwrap_or_default()
                .split_whitespace()
                .collect();
            let bytes = base64::engine::general_purpose::STANDARD
                .decode(encoded)
                .map_err(|e| other(e.to_string()))?;
            Ok(Some(String::from_utf8_lossy(&bytes).into_owned()))
        }
        Ok((None, _)) => Ok(None),
        Err(Error::GitHub { status: 404, .. }) => Ok(None),
        Err(e) => Err(e),
    }
}

fn cite(
    repository: &str,
    reference: &str,
    path: Option<&str>,
    symbol: Option<&str>,
) -> Result<i32> {
    let repo = crate::config::repo_name(&json!(repository))?;
    let github = GitHub::from_env();
    let reference = if reference == "HEAD" {
        github.metadata(&repo)?["default_branch"]
            .as_str()
            .unwrap_or("main")
            .to_string()
    } else {
        reference.to_string()
    };
    let sha = github
        .head(&repo, &reference, None)?
        .0
        .ok_or_else(|| other("upstream revision unavailable"))?;
    let origin = format!("https://github.com/{repo}");
    if let Some(path) = path {
        crate::config::safe_path(path)?;
        let content = fetch(&github, &repo, path, &sha)?
            .ok_or_else(|| other(format!("{path} not found at {sha}")))?;
        let (hash, (a, b), _) = anchors::current(path, &content, symbol).ok_or_else(|| {
            other(format!(
                "symbol {} not found in {path}",
                symbol.unwrap_or_default()
            ))
        })?;
        let symbol = symbol.map(|s| format!(" symbol={s}")).unwrap_or_default();
        println!(
            "- source: code swh:1:rev:{sha};origin={origin};path=/{path};lines={a}-{b} repo={origin}{symbol} hash={hash}"
        );
        return Ok(0);
    }
    for file in ["CITATION.cff", "codemeta.json"] {
        if let Some(text) = fetch(&github, &repo, file, &sha)?
            && let Some(id) = ideas::citation_identifier(&text)
        {
            println!("- source: paper {id}");
            eprintln!("from {file} at {origin}/blob/{sha}/{file}");
            return Ok(0);
        }
    }
    eprintln!("no DOI or arXiv identifier in CITATION.cff or codemeta.json at {sha}");
    Ok(1)
}
