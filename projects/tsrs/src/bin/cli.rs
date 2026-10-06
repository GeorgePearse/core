//! CLI for tree-shaking operations
#![allow(
    clippy::too_many_lines,
    clippy::similar_names,
    clippy::uninlined_format_args,
    clippy::map_unwrap_or,
    clippy::redundant_closure_for_method_calls,
    clippy::ptr_arg,
    clippy::manual_let_else,
    clippy::field_reassign_with_default,
    clippy::too_many_arguments,
    clippy::fn_params_excessive_bools,
    clippy::explicit_iter_loop,
    clippy::single_match_else
)]

use anyhow::{bail, Context};
use clap::{ArgAction, Parser, Subcommand};
use dunce::canonicalize as dunce_canonicalize;
use encoding_rs::{Encoding, UTF_16BE, UTF_16LE, UTF_8};
use globset::{GlobBuilder, GlobSet, GlobSetBuilder};
use ignore::WalkBuilder;
use num_cpus;
use rayon::prelude::*;
use rayon::ThreadPoolBuilder;
use serde::{Deserialize, Serialize};
use similar::TextDiff;
use std::borrow::Cow;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::ffi::OsString;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process;
use std::sync::Arc;
use tracing::{debug, error, info, warn};
use tracing_subscriber::filter::EnvFilter;
use tsrs::{CallGraphAnalyzer, Minifier, MinifyPlan, VenvAnalyzer, VenvSlimmer};
use walkdir;

const DEFAULT_EXCLUDES: &[&str] = &["**/.git/**", "**/__pycache__/**", "**/.venv/**"];

#[derive(Parser)]
#[command(name = "tsrs")]
#[command(about = "Tree-shaking in Rust for Python", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,

    /// Reduce logging to warnings and errors
    #[arg(global = true, short = 'q', long = "quiet")]
    quiet: bool,

    /// Increase logging verbosity (-v, -vv)
    #[arg(global = true, short = 'v', long = "verbose", action = ArgAction::Count)]
    verbose: u8,
}

#[derive(Subcommand)]
enum Commands {
    /// Analyze a virtual environment
    Analyze {
        /// Path to the virtual environment
        #[arg(value_name = "VENV_PATH")]
        venv_path: PathBuf,
    },

    /// Create a slim version of a virtual environment based on code imports
    Slim {
        /// Path to the Python code directory to analyze
        #[arg(value_name = "PYTHON_DIRECTORY")]
        code_path: PathBuf,

        /// Path to the source virtual environment
        #[arg(value_name = "VENV_PATH")]
        venv_path: PathBuf,

        /// Path for the output slim venv (default: .venv-slim)
        #[arg(short, long, value_name = "OUTPUT_PATH")]
        output: Option<PathBuf>,
    },

    /// Print a planned rename map for locals in a Python file
    MinifyPlan {
        /// Path to the Python source file
        #[arg(value_name = "PYTHON_FILE")]
        python_file: PathBuf,
    },

    /// Generate rename plans for every Python file in a directory tree
    MinifyPlanDir {
        /// Directory containing Python sources to analyze
        #[arg(value_name = "INPUT_DIR")]
        input_dir: PathBuf,

        /// Path where the plan bundle JSON should be written
        #[arg(long, value_name = "PLAN_FILE")]
        out: PathBuf,

        /// Glob pattern to include (repeatable). Defaults to "**/*.py"
        #[arg(long, value_name = "GLOB")]
        include: Vec<String>,

        /// File containing newline-delimited include globs
        #[arg(long, value_name = "FILE")]
        include_file: Option<PathBuf>,

        /// Glob pattern to exclude (repeatable)
        #[arg(long, value_name = "GLOB")]
        exclude: Vec<String>,

        /// File containing newline-delimited exclude globs
        #[arg(long, value_name = "FILE")]
        exclude_file: Option<PathBuf>,

        /// Limit parallel workers when planning
        #[arg(long, value_name = "N")]
        jobs: Option<usize>,

        /// Include hidden files and directories
        #[arg(long)]
        include_hidden: bool,

        /// Follow symlinks when traversing directories
        #[arg(long)]
        follow_symlinks: bool,

        /// Force case-insensitive glob matching (defaults to on for Windows)
        #[arg(long, value_name = "BOOL")]
        glob_case_insensitive: Option<bool>,

        /// Maximum directory depth to traverse (root depth = 1)
        #[arg(long, value_name = "N")]
        max_depth: Option<usize>,

        /// Respect .gitignore files when scanning
        #[arg(long)]
        respect_gitignore: bool,
    },

    /// Apply a precomputed rename plan to a Python file
    ApplyPlan {
        /// Path to the Python source file
        #[arg(value_name = "PYTHON_FILE")]
        python_file: PathBuf,

        /// Path to the JSON plan file produced by `minify-plan`
        #[arg(long, value_name = "PLAN_FILE")]
        plan: Option<PathBuf>,

        /// Read the plan JSON from stdin
        #[arg(long)]
        plan_stdin: bool,

        /// Rewrite the file in place instead of printing the rewritten code
        #[arg(long)]
        in_place: bool,

        /// Perform a dry run without writing any files
        #[arg(long)]
        dry_run: bool,

        /// Create a backup of the original file with the given suffix (requires --in-place)
        #[arg(long, value_name = "EXT")]
        backup_ext: Option<String>,

        /// Print rename statistics for the file
        #[arg(long)]
        stats: bool,

        /// Emit rename statistics in JSON format (requires --stats)
        #[arg(long)]
        json: bool,

        /// Write stats summary to a JSON file
        #[arg(long, value_name = "JSON_FILE")]
        output_json: Option<PathBuf>,

        /// Exit with a non-zero status if any bailouts occur
        #[arg(long)]
        fail_on_bailout: bool,

        /// Exit with a non-zero status if any errors occur
        #[arg(long)]
        fail_on_error: bool,

        /// Exit with a non-zero status if any changes are made
        #[arg(long)]
        fail_on_change: bool,

        /// Show unified diffs for rewritten files
        #[arg(long)]
        diff: bool,

        /// Number of context lines to include in diffs (default: 3)
        #[arg(long, value_name = "N", default_value_t = 3)]
        diff_context: usize,

        /// Read Python source from stdin instead of a file
        #[arg(long, conflicts_with_all = ["in_place", "backup_ext"])]
        stdin: bool,

        /// Write rewritten source to stdout regardless of quiet mode
        #[arg(long)]
        stdout: bool,
    },

    /// Apply precomputed rename plans to every file in a directory tree
    ApplyPlanDir {
        /// Directory containing Python sources to process
        #[arg(value_name = "INPUT_DIR")]
        input_dir: PathBuf,

        /// Path to the JSON plan bundle produced by `minify-plan-dir`
        #[arg(long, value_name = "PLAN_FILE")]
        plan: PathBuf,

        /// Directory where rewritten files should be written
        #[arg(long, value_name = "OUTPUT_DIR")]
        out_dir: Option<PathBuf>,

        /// Rewrite files in place instead of mirroring to an output directory
        #[arg(long)]
        in_place: bool,

        /// Perform a dry run and print status without writing files
        #[arg(long)]
        dry_run: bool,

        /// Create a backup of rewritten files with the given suffix (requires --in-place)
        #[arg(long, value_name = "EXT")]
        backup_ext: Option<String>,

        /// Glob pattern to include (repeatable). Defaults to "**/*.py"
        #[arg(long, value_name = "GLOB")]
        include: Vec<String>,

        /// File containing newline-delimited include globs
        #[arg(long, value_name = "FILE")]
        include_file: Option<PathBuf>,

        /// Glob pattern to exclude (repeatable)
        #[arg(long, value_name = "GLOB")]
        exclude: Vec<String>,

        /// File containing newline-delimited exclude globs
        #[arg(long, value_name = "FILE")]
        exclude_file: Option<PathBuf>,

        /// Print per-file rename counts and totals in the summary
        #[arg(long)]
        stats: bool,

        /// Emit stats summary as JSON (requires --stats)
        #[arg(long)]
        json: bool,

        /// Write stats summary to a JSON file
        #[arg(long, value_name = "JSON_FILE")]
        output_json: Option<PathBuf>,

        /// Limit parallel workers when rewriting files
        #[arg(long, value_name = "N")]
        jobs: Option<usize>,

        /// Exit with a non-zero status if any bailouts occur
        #[arg(long)]
        fail_on_bailout: bool,

        /// Exit with a non-zero status if any errors occur
        #[arg(long)]
        fail_on_error: bool,

        /// Exit with a non-zero status if any changes are made
        #[arg(long)]
        fail_on_change: bool,

        /// Show unified diffs for rewritten files
        #[arg(long)]
        diff: bool,

        /// Number of context lines to include in diffs (default: 3)
        #[arg(long, value_name = "N", default_value_t = 3)]
        diff_context: usize,

        /// Include hidden files and directories
        #[arg(long)]
        include_hidden: bool,

        /// Follow symlinks when traversing directories
        #[arg(long)]
        follow_symlinks: bool,

        /// Force case-insensitive glob matching (defaults to on for Windows)
        #[arg(long, value_name = "BOOL")]
        glob_case_insensitive: Option<bool>,

        /// Maximum directory depth to traverse (root depth = 1)
        #[arg(long, value_name = "N")]
        max_depth: Option<usize>,

        /// Respect .gitignore files when scanning
        #[arg(long)]
        respect_gitignore: bool,
    },

    /// Rewrite a Python file using safe local renames
    Minify {
        /// Path to the Python source file
        #[arg(value_name = "PYTHON_FILE")]
        python_file: PathBuf,

        /// Rewrite the file in place instead of printing the rewritten code
        #[arg(long)]
        in_place: bool,

        /// Perform a dry run without writing any files
        #[arg(long)]
        dry_run: bool,

        /// Create a backup of the original file with the given suffix (requires --in-place)
        #[arg(long, value_name = "EXT")]
        backup_ext: Option<String>,

        /// Print rename statistics for the file
        #[arg(long)]
        stats: bool,

        /// Emit rename statistics in JSON format (requires --stats)
        #[arg(long)]
        json: bool,

        /// Write stats summary to a JSON file
        #[arg(long, value_name = "JSON_FILE")]
        output_json: Option<PathBuf>,

        /// Exit with a non-zero status if any bailouts occur
        #[arg(long)]
        fail_on_bailout: bool,

        /// Exit with a non-zero status if any errors occur
        #[arg(long)]
        fail_on_error: bool,

        /// Exit with a non-zero status if any changes are made
        #[arg(long)]
        fail_on_change: bool,

        /// Show unified diffs for rewritten files
        #[arg(long)]
        diff: bool,

        /// Number of context lines to include in diffs (default: 3)
        #[arg(long, value_name = "N", default_value_t = 3)]
        diff_context: usize,

        /// Read Python source from stdin instead of a file
        #[arg(long, conflicts_with_all = ["in_place", "backup_ext"])]
        stdin: bool,

        /// Write rewritten source to stdout regardless of quiet mode
        #[arg(long)]
        stdout: bool,

        /// Remove dead code (unreachable functions) in addition to minification
        #[arg(long)]
        remove_dead_code: bool,
    },

    /// Rewrite all Python files in a directory tree using safe local renames
    MinifyDir {
        /// Directory containing Python sources to process
        #[arg(value_name = "INPUT_DIR")]
        input_dir: PathBuf,

        /// Directory where rewritten files should be written
        #[arg(long, value_name = "OUTPUT_DIR")]
        out_dir: Option<PathBuf>,

        /// Rewrite files in place instead of mirroring to an output directory
        #[arg(long)]
        in_place: bool,

        /// Perform a dry run and print status without writing files
        #[arg(long)]
        dry_run: bool,

        /// Create a backup of rewritten files with the given suffix (requires --in-place)
        #[arg(long, value_name = "EXT")]
        backup_ext: Option<String>,

        /// Glob pattern to include (repeatable). Defaults to "**/*.py"
        #[arg(long, value_name = "GLOB")]
        include: Vec<String>,

        /// File containing newline-delimited include globs
        #[arg(long, value_name = "FILE")]
        include_file: Option<PathBuf>,

        /// Glob pattern to exclude (repeatable)
        #[arg(long, value_name = "GLOB")]
        exclude: Vec<String>,

        /// File containing newline-delimited exclude globs
        #[arg(long, value_name = "FILE")]
        exclude_file: Option<PathBuf>,

        /// Print per-file rename counts and totals in the summary
        #[arg(long)]
        stats: bool,

        /// Emit stats summary as JSON (requires --stats)
        #[arg(long)]
        json: bool,

        /// Write stats summary to a JSON file
        #[arg(long, value_name = "JSON_FILE")]
        output_json: Option<PathBuf>,

        /// Limit parallel workers when rewriting files
        #[arg(long, value_name = "N")]
        jobs: Option<usize>,

        /// Exit with a non-zero status if any bailouts occur
        #[arg(long)]
        fail_on_bailout: bool,

        /// Exit with a non-zero status if any errors occur
        #[arg(long)]
        fail_on_error: bool,

        /// Exit with a non-zero status if any changes are made
        #[arg(long)]
        fail_on_change: bool,

        /// Show unified diffs for rewritten files
        #[arg(long)]
        diff: bool,

        /// Number of context lines to include in diffs (default: 3)
        #[arg(long, value_name = "N", default_value_t = 3)]
        diff_context: usize,

        /// Include hidden files and directories
        #[arg(long)]
        include_hidden: bool,

        /// Follow symlinks when traversing directories
        #[arg(long)]
        follow_symlinks: bool,

        /// Force case-insensitive glob matching (defaults to on for Windows)
        #[arg(long, value_name = "BOOL")]
        glob_case_insensitive: Option<bool>,

        /// Maximum directory depth to traverse (root depth = 1)
        #[arg(long, value_name = "N")]
        max_depth: Option<usize>,

        /// Respect .gitignore files when scanning
        #[arg(long)]
        respect_gitignore: bool,

        /// Remove dead code (unreachable functions) in addition to minification
        #[arg(long)]
        remove_dead_code: bool,
    },

    /// End-to-end optimization: analyze code, detect dead code, create slim venv, and minify
    Optimize {
        /// Path to the Python code directory to analyze
        #[arg(value_name = "CODE_DIR")]
        code_dir: PathBuf,

        /// Path to the source virtual environment
        #[arg(value_name = "VENV_PATH")]
        venv_path: PathBuf,

        /// Output directory for optimized code and slim venv
        #[arg(long, value_name = "OUTPUT_DIR")]
        output: Option<PathBuf>,

        /// Create slim venv in OUTPUT_DIR/.venv-slim (default: true)
        #[arg(long)]
        create_slim_venv: bool,

        /// Create minified code in OUTPUT_DIR/src-minified (default: true)
        #[arg(long)]
        minify_code: bool,

        /// Generate dead code reports (JSON, HTML, DOT)
        #[arg(long)]
        generate_reports: bool,

        /// Output directory for reports (default: OUTPUT_DIR/reports)
        #[arg(long, value_name = "REPORTS_DIR")]
        reports_dir: Option<PathBuf>,

        /// Print dead code report to stdout
        #[arg(long)]
        print_report: bool,

        /// Print summary statistics
        #[arg(long)]
        stats: bool,

        /// Limit parallel workers
        #[arg(long, value_name = "N")]
        jobs: Option<usize>,

        /// Dry run without making changes
        #[arg(long)]
        dry_run: bool,
    },
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    // Setup logging
    let level = if cli.quiet {
        "warn"
    } else if cli.verbose >= 2 {
        "debug"
    } else {
        "info"
    };
    let env_filter = EnvFilter::new(level);

    tracing_subscriber::fmt()
        .with_env_filter(env_filter)
        .with_writer(std::io::stderr)
        .with_target(false)
        .init();

    match cli.command {
        Commands::Analyze { venv_path } => {
            analyze(&venv_path)?;
        }
        Commands::Slim {
            code_path,
            venv_path,
            output,
        } => {
            slim(&code_path, &venv_path, output)?;
        }
        Commands::MinifyPlan { python_file } => {
            minify_plan(&python_file)?;
        }
        Commands::MinifyPlanDir {
            input_dir,
            out,
            include,
            include_file,
            exclude,
            exclude_file,
            jobs,
            include_hidden,
            follow_symlinks,
            glob_case_insensitive,
            max_depth,
            respect_gitignore,
        } => {
            minify_plan_dir_with_depth(
                &input_dir,
                &out,
                &include,
                include_file.as_ref(),
                &exclude,
                exclude_file.as_ref(),
                jobs,
                include_hidden,
                follow_symlinks,
                glob_case_insensitive,
                max_depth,
                respect_gitignore,
                cli.quiet,
            )?;
        }
        Commands::Minify {
            python_file,
            in_place,
            dry_run,
            backup_ext,
            stats,
            json,
            output_json,
            fail_on_bailout,
            fail_on_error,
            fail_on_change,
            diff,
            diff_context,
            stdin,
            stdout,
            remove_dead_code,
        } => {
            let (stats_result, stdout_bytes) = if stdin {
                if in_place {
                    anyhow::bail!("--stdin cannot be combined with --in-place");
                }
                if backup_ext.is_some() {
                    anyhow::bail!("--stdin cannot be combined with --backup-ext");
                }

                let mut buffer = Vec::new();
                std::io::stdin().read_to_end(&mut buffer)?;
                let (source, metadata) = decode_python_bytes(&buffer, "stdin")?;

                // Generate minification plan
                let mut plan = Minifier::plan_from_source("stdin", &source)?;

                // Filter plan if --remove-dead-code is requested
                if remove_dead_code {
                    let dead_code = detect_dead_code(&source, "stdin", cli.quiet)?;
                    plan = filter_plan_for_dead_code(plan, &dead_code);
                }

                let fake_path = PathBuf::from("stdin");
                let (stats, bytes) = apply_plan_to_file(
                    &fake_path,
                    &source,
                    &metadata,
                    &plan,
                    false,
                    dry_run,
                    None,
                    stats,
                    json,
                    cli.quiet,
                    output_json.as_deref(),
                    fail_on_bailout,
                    fail_on_error,
                    fail_on_change,
                    diff,
                    diff_context,
                    stdout,
                )?;
                (stats, bytes)
            } else {
                // Read source code
                let (source, metadata) = read_python(&python_file)?;
                let module_name = python_file
                    .file_stem()
                    .and_then(|stem| stem.to_str())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| python_file.to_string_lossy().to_string());

                // Generate minification plan
                let mut plan = Minifier::plan_from_source(&module_name, &source)?;

                // Filter plan if --remove-dead-code is requested
                if remove_dead_code {
                    let dead_code = detect_dead_code(&source, &module_name, cli.quiet)?;
                    plan = filter_plan_for_dead_code(plan, &dead_code);
                }

                let (stats, bytes) = apply_plan_to_file(
                    &python_file,
                    &source,
                    &metadata,
                    &plan,
                    in_place,
                    dry_run,
                    backup_ext.as_deref(),
                    stats,
                    json,
                    cli.quiet,
                    output_json.as_deref(),
                    fail_on_bailout,
                    fail_on_error,
                    fail_on_change,
                    diff,
                    diff_context,
                    stdout,
                )?;
                (stats, bytes)
            };

            if let Some(bytes) = stdout_bytes {
                std::io::stdout().write_all(&bytes)?;
            }

            if fail_on_bailout || fail_on_error || fail_on_change {
                let code = compute_exit_code(
                    &stats_result,
                    fail_on_bailout,
                    fail_on_error,
                    fail_on_change,
                );
                process::exit(code);
            }
        }
        Commands::ApplyPlan {
            python_file,
            plan,
            plan_stdin,
            in_place,
            dry_run,
            backup_ext,
            stats,
            json,
            output_json,
            fail_on_bailout,
            fail_on_error,
            fail_on_change,
            diff,
            diff_context,
            stdin,
            stdout,
        } => {
            let plan_from_stdin = plan_stdin || plan.as_ref().is_some_and(|p| p.as_os_str() == "-");
            let plan_path = plan.as_ref().and_then(|p| {
                if p.as_os_str() == "-" {
                    None
                } else {
                    Some(p.clone())
                }
            });

            if !plan_from_stdin && plan_path.is_none() {
                bail!("--plan <file> is required unless --plan-stdin or --plan - is used");
            }

            let (stats_result, stdout_bytes) = if stdin {
                if in_place {
                    anyhow::bail!("--stdin cannot be combined with --in-place");
                }
                if backup_ext.is_some() {
                    anyhow::bail!("--stdin cannot be combined with --backup-ext");
                }

                if plan_from_stdin {
                    let mut buffer = Vec::new();
                    std::io::stdin().read_to_end(&mut buffer)?;
                    let (source, metadata, plan_bundle) = split_source_and_plan(&buffer)?;
                    let fake_path = PathBuf::from("stdin");
                    apply_plan_to_file(
                        &fake_path,
                        &source,
                        &metadata,
                        &plan_bundle,
                        false,
                        dry_run,
                        None,
                        stats,
                        json,
                        cli.quiet,
                        output_json.as_deref(),
                        fail_on_bailout,
                        fail_on_error,
                        fail_on_change,
                        diff,
                        diff_context,
                        stdout,
                    )?
                } else {
                    let plan_path = plan_path.expect("plan path available");
                    let mut buffer = Vec::new();
                    std::io::stdin().read_to_end(&mut buffer)?;
                    let (source, metadata) = decode_python_bytes(&buffer, "stdin source")?;
                    let plan_json = fs::read_to_string(&plan_path)?;
                    let plan_bundle: MinifyPlan =
                        serde_json::from_str(&plan_json).context("failed to parse plan JSON")?;
                    let fake_path = PathBuf::from("stdin");
                    apply_plan_to_file(
                        &fake_path,
                        &source,
                        &metadata,
                        &plan_bundle,
                        false,
                        dry_run,
                        None,
                        stats,
                        json,
                        cli.quiet,
                        output_json.as_deref(),
                        fail_on_bailout,
                        fail_on_error,
                        fail_on_change,
                        diff,
                        diff_context,
                        stdout,
                    )?
                }
            } else {
                if plan_from_stdin {
                    let (source, metadata) = read_python(&python_file)?;
                    let mut plan_bytes = Vec::new();
                    std::io::stdin().read_to_end(&mut plan_bytes)?;
                    if plan_bytes.is_empty() {
                        bail!("no plan JSON provided on stdin");
                    }
                    let plan_bundle: MinifyPlan = serde_json::from_slice(&plan_bytes)
                        .context("failed to parse plan JSON from stdin")?;
                    apply_plan_to_file(
                        &python_file,
                        &source,
                        &metadata,
                        &plan_bundle,
                        in_place,
                        dry_run,
                        backup_ext.as_deref(),
                        stats,
                        json,
                        cli.quiet,
                        output_json.as_deref(),
                        fail_on_bailout,
                        fail_on_error,
                        fail_on_change,
                        diff,
                        diff_context,
                        stdout,
                    )?
                } else {
                    let plan_path = plan_path.expect("plan path available");
                    apply_plan(
                        &python_file,
                        &plan_path,
                        in_place,
                        dry_run,
                        backup_ext.as_deref(),
                        stats,
                        json,
                        cli.quiet,
                        output_json.as_deref(),
                        fail_on_bailout,
                        fail_on_error,
                        fail_on_change,
                        diff,
                        diff_context,
                        stdout,
                    )?
                }
            };

            if let Some(bytes) = stdout_bytes {
                std::io::stdout().write_all(&bytes)?;
            }

            if fail_on_bailout || fail_on_error || fail_on_change {
                let code = compute_exit_code(
                    &stats_result,
                    fail_on_bailout,
                    fail_on_error,
                    fail_on_change,
                );
                process::exit(code);
            }
        }
        Commands::MinifyDir {
            input_dir,
            out_dir,
            in_place,
            dry_run,
            backup_ext,
            include,
            include_file,
            exclude,
            exclude_file,
            stats,
            json,
            output_json,
            jobs,
            fail_on_bailout,
            fail_on_error,
            fail_on_change,
            diff,
            diff_context,
            include_hidden,
            follow_symlinks,
            glob_case_insensitive,
            max_depth,
            respect_gitignore,
            remove_dead_code,
        } => {
            let stats_result = minify_dir_with_depth(
                &input_dir,
                out_dir,
                &include,
                include_file.as_ref(),
                &exclude,
                exclude_file.as_ref(),
                backup_ext.as_deref(),
                in_place,
                dry_run,
                stats,
                json,
                include_hidden,
                follow_symlinks,
                glob_case_insensitive,
                cli.quiet,
                output_json.as_deref(),
                jobs,
                fail_on_bailout,
                fail_on_error,
                fail_on_change,
                diff,
                diff_context,
                respect_gitignore,
                max_depth,
                remove_dead_code,
            )?;

            if fail_on_bailout || fail_on_error || fail_on_change {
                let code = compute_exit_code(
                    &stats_result,
                    fail_on_bailout,
                    fail_on_error,
                    fail_on_change,
                );
                process::exit(code);
            }
        }
        Commands::Optimize {
            code_dir,
            venv_path,
            output,
            create_slim_venv,
            minify_code,
            generate_reports,
            reports_dir,
            print_report,
            stats,
            jobs,
            dry_run,
        } => {
            optimize(
                &code_dir,
                &venv_path,
                output,
                create_slim_venv,
                minify_code,
                generate_reports,
                reports_dir,
                print_report,
                stats,
                jobs,
                dry_run,
                cli.quiet,
            )?;
        }
        Commands::ApplyPlanDir {
            input_dir,
            plan,
            out_dir,
            in_place,
            dry_run,
            backup_ext,
            include,
            include_file,
            exclude,
            exclude_file,
            stats,
            json,
            output_json,
            jobs,
            fail_on_bailout,
            fail_on_error,
            fail_on_change,
            diff,
            diff_context,
            include_hidden,
            follow_symlinks,
            glob_case_insensitive,
            max_depth,
            respect_gitignore,
        } => {
            let stats_result = apply_plan_dir_with_depth(
                &input_dir,
                &plan,
                out_dir,
                &include,
                include_file.as_ref(),
                &exclude,
                exclude_file.as_ref(),
                backup_ext.as_deref(),
                in_place,
                dry_run,
                stats,
                json,
                include_hidden,
                follow_symlinks,
                glob_case_insensitive,
                cli.quiet,
                output_json.as_deref(),
                jobs,
                fail_on_bailout,
                fail_on_error,
                fail_on_change,
                diff,
                diff_context,
                respect_gitignore,
                max_depth,
            )?;

            if fail_on_bailout || fail_on_error || fail_on_change {
                let code = compute_exit_code(
                    &stats_result,
                    fail_on_bailout,
                    fail_on_error,
                    fail_on_change,
                );
                process::exit(code);
            }
        }
    }

    Ok(())
}

fn analyze(venv_path: &PathBuf) -> anyhow::Result<()> {
    println!("Analyzing venv at: {}", venv_path.display());

    let analyzer = VenvAnalyzer::new(venv_path)?;
    let info = analyzer.analyze()?;

    println!("\nVenv Information:");
    println!("  Path: {}", info.path.display());
    if let Some(version) = info.python_version {
        println!("  Python Version: {}", version);
    }
    println!("  Packages: {}", info.packages.len());
    println!("\nInstalled Packages:");
    for package in &info.packages {
        if let Some(version) = &package.version {
            println!("  - {} ({})", package.name, version);
        } else {
            println!("  - {}", package.name);
        }
    }

    Ok(())
}

fn slim(code_path: &PathBuf, venv_path: &PathBuf, output: Option<PathBuf>) -> anyhow::Result<()> {
    let output_path = output.unwrap_or_else(|| {
        let parent = venv_path
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
        let mut path = parent;
        path.push(".venv-slim");
        path
    });

    println!("Creating slim venv...");
    println!("  Code directory: {}", code_path.display());
    println!("  Source venv: {}", venv_path.display());
    println!("  Output venv: {}", output_path.display());

    let slimmer = VenvSlimmer::new_with_output(code_path, venv_path, &output_path)?;
    slimmer.slim()?;

    println!("\nSlim venv created successfully!");
    println!("Output: {}", output_path.display());

    Ok(())
}

fn optimize(
    code_dir: &PathBuf,
    venv_path: &PathBuf,
    output: Option<PathBuf>,
    create_slim_venv: bool,
    minify_code: bool,
    generate_reports: bool,
    reports_dir: Option<PathBuf>,
    print_report: bool,
    stats: bool,
    jobs: Option<usize>,
    dry_run: bool,
    quiet: bool,
) -> anyhow::Result<()> {
    let output_dir = output.unwrap_or_else(|| {
        let mut path = code_dir
            .parent()
            .unwrap_or_else(|| std::path::Path::new("."))
            .to_path_buf();
        path.push("tsrs-optimized");
        path
    });

    if !quiet {
        println!("🔍 TSRS End-to-End Optimization");
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("📁 Code directory: {}", code_dir.display());
        println!("📦 Virtual environment: {}", venv_path.display());
        println!("📍 Output directory: {}", output_dir.display());
        println!();
    }

    // Step 1: Analyze imports and build call graph
    if !quiet {
        println!("Step 1: Analyzing code structure...");
    }

    let mut analyzer = CallGraphAnalyzer::new();

    // Scan all Python files and build call graph
    for entry in walkdir::WalkDir::new(code_dir)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().and_then(|s| s.to_str()) == Some("py"))
    {
        if let Ok((source, _)) = read_python(entry.path()) {
            let package = entry
                .path()
                .strip_prefix(code_dir)
                .ok()
                .and_then(|p| p.parent())
                .map(|p| p.display().to_string())
                .unwrap_or_else(|| "root".to_string());

            let _ = analyzer.analyze_source(&package, &source);
        }
    }

    let dead_code = analyzer.find_dead_code();
    let reachable_count = analyzer.compute_reachable().len();

    if !quiet && !dead_code.is_empty() {
        println!("  ✓ Found {} dead functions", dead_code.len());
    }
    if !quiet {
        println!("  ✓ {} reachable functions", reachable_count);
    }

    // Step 2: Create slim venv if requested
    if create_slim_venv {
        if !quiet {
            println!("\nStep 2: Creating slim virtual environment...");
        }

        let slim_venv_path = output_dir.join(".venv-slim");

        if !dry_run {
            if !output_dir.exists() {
                fs::create_dir_all(&output_dir)?;
            }
            let slimmer = VenvSlimmer::new_with_output(code_dir, venv_path, &slim_venv_path)?;
            slimmer.slim()?;
        }

        if !quiet {
            println!("  ✓ Slim venv created");
        }
    }

    // Step 3: Minify code if requested
    if minify_code {
        if !quiet {
            println!("\nStep 3: Minifying code...");
        }

        let minified_dir = output_dir.join("src-minified");

        if !dry_run {
            let includes = vec!["**/*.py".to_string()];
            minify_dir_with_depth(
                code_dir,
                Some(minified_dir.clone()),
                &includes,
                None,
                &[],
                None,
                None,
                false,
                dry_run,
                stats,
                false,
                false,
                false,
                None,
                quiet,
                None,
                jobs,
                false,
                false,
                false,
                false,
                0,
                false,
                None,
                true,
            )?;
        }

        if !quiet {
            println!("  ✓ Code minified");
        }
    }

    // Step 4: Generate reports if requested
    if generate_reports || print_report {
        if !quiet {
            println!("\nStep 4: Generating reports...");
        }

        let report_dir = reports_dir.unwrap_or_else(|| output_dir.join("reports"));

        if !dry_run && generate_reports {
            fs::create_dir_all(&report_dir)?;

            // Create dead code report
            let exports = analyzer.get_all_exports();
            let mut all_exports = Vec::new();
            for (_pkg, names) in exports {
                all_exports.extend(names);
            }

            let report = tsrs::DeadCodeReport::new(
                "root".to_string(),
                reachable_count + dead_code.len(),
                dead_code
                    .iter()
                    .map(|(_, name)| (name.clone(), "Unreachable from entry points".to_string()))
                    .collect(),
                analyzer
                    .compute_reachable()
                    .iter()
                    .map(|_| "live".to_string())
                    .collect::<Vec<_>>()
                    .into_iter()
                    .zip(std::iter::repeat(""))
                    .map(|(s, _)| s)
                    .collect::<Vec<_>>(),
                analyzer
                    .get_entry_points()
                    .iter()
                    .map(|_| "entry".to_string())
                    .collect::<Vec<_>>()
                    .into_iter()
                    .zip(std::iter::repeat(""))
                    .map(|(s, _)| s)
                    .collect::<Vec<_>>(),
                all_exports,
            );

            // Write JSON report
            let json_path = report_dir.join("dead_code.json");
            fs::write(&json_path, report.to_json())?;

            // Write HTML report
            let html_path = report_dir.join("dead_code.html");
            fs::write(&html_path, report.to_html())?;

            if !quiet {
                println!("  ✓ JSON report: {}", json_path.display());
                println!("  ✓ HTML report: {}", html_path.display());
            }
        }

        if print_report {
            let report = tsrs::DeadCodeReport::new(
                "root".to_string(),
                reachable_count + dead_code.len(),
                dead_code
                    .iter()
                    .map(|(_, name)| (name.clone(), "Unreachable from entry points".to_string()))
                    .collect(),
                vec![],
                vec![],
                vec![],
            );

            println!("\n{}", report.to_json());
        }
    }

    if !quiet {
        println!("\n✅ Optimization complete!");
        println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        println!("📊 Summary:");
        println!("   Dead functions: {}", dead_code.len());
        println!("   Reachable functions: {}", reachable_count);
        println!("   Output directory: {}", output_dir.display());
    }

    Ok(())
}

fn minify_plan(file_path: &PathBuf) -> anyhow::Result<()> {
    let (source, _) = read_python(file_path)?;
    let module_name = file_path
        .file_stem()
        .and_then(|stem| stem.to_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| file_path.to_string_lossy().to_string());

    let plan = Minifier::plan_from_source(&module_name, &source)?;
    let plan_json = serde_json::to_string_pretty(&plan)?;
    println!("{}", plan_json);

    Ok(())
}

/// Detect and report dead code in Python source
fn detect_dead_code(
    source: &str,
    package_name: &str,
    quiet: bool,
) -> anyhow::Result<Vec<(usize, String)>> {
    let mut analyzer = CallGraphAnalyzer::new();
    analyzer.analyze_source(package_name, source)?;

    let dead_code = analyzer.find_dead_code();

    if !dead_code.is_empty() && !quiet {
        info!("Found {} unreachable function(s):", dead_code.len());
        for (_, func_name) in &dead_code {
            info!("  - {}", func_name);
        }
    }

    // Convert FunctionId to usize for return
    let result = dead_code
        .into_iter()
        .map(|(func_id, name)| (func_id.0, name))
        .collect();

    Ok(result)
}

/// Filter a MinifyPlan to exclude dead code functions
fn filter_plan_for_dead_code(mut plan: MinifyPlan, dead_code: &[(usize, String)]) -> MinifyPlan {
    // Create set of dead function names for fast lookup
    let dead_names: HashSet<&str> = dead_code.iter().map(|(_, name)| name.as_str()).collect();

    // Filter functions: remove those that are dead code
    plan.functions.retain(|func| {
        // Extract simple name from qualified_name (last component after .)
        let simple_name = func
            .qualified_name
            .split('.')
            .last()
            .unwrap_or(&func.qualified_name);

        // Keep function if it's not in the dead code list
        !dead_names.contains(simple_name)
    });

    plan
}

fn minify(
    file_path: &PathBuf,
    in_place: bool,
    dry_run: bool,
    backup_ext: Option<&str>,
    show_stats: bool,
    json_output: bool,
    quiet: bool,
    output_json: Option<&Path>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    force_stdout: bool,
) -> anyhow::Result<(DirStats, Option<Vec<u8>>)> {
    minify_file(
        file_path,
        in_place,
        dry_run,
        backup_ext,
        show_stats,
        json_output,
        quiet,
        output_json,
        fail_on_bailout,
        fail_on_error,
        fail_on_change,
        diff,
        diff_context,
        force_stdout,
    )
}

fn apply_plan(
    file_path: &PathBuf,
    plan_path: &PathBuf,
    in_place: bool,
    dry_run: bool,
    backup_ext: Option<&str>,
    show_stats: bool,
    json_output: bool,
    quiet: bool,
    output_json: Option<&Path>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    force_stdout: bool,
) -> anyhow::Result<(DirStats, Option<Vec<u8>>)> {
    if json_output && !show_stats {
        anyhow::bail!("--json requires --stats");
    }

    let plan_file = fs::read_to_string(plan_path)?;
    let plan: MinifyPlan = serde_json::from_str(&plan_file)?;

    let (source, metadata) = read_python(file_path)?;

    apply_plan_to_file(
        file_path,
        &source,
        &metadata,
        &plan,
        in_place,
        dry_run,
        backup_ext,
        show_stats,
        json_output,
        quiet,
        output_json,
        fail_on_bailout,
        fail_on_error,
        fail_on_change,
        diff,
        diff_context,
        force_stdout,
    )
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct DirStats {
    processed: usize,
    rewritten: usize,
    skipped_no_change: usize,
    bailouts: usize,
    errors: usize,
    total_renames: usize,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    files: Vec<FileStats>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    reasons: BTreeMap<String, usize>,
}

#[derive(Debug, Serialize, Deserialize)]
struct FileStats {
    path: String,
    renames: usize,
    status: String,
}

fn canonicalize_directory(path: &Path) -> anyhow::Result<PathBuf> {
    dunce_canonicalize(path).with_context(|| format!("failed to canonicalize {}", path.display()))
}

fn normalize_output_path_guard(path: &Path) -> anyhow::Result<PathBuf> {
    let cwd = std::env::current_dir().with_context(|| "failed to resolve current directory")?;
    let abs = if path.is_absolute() {
        path.to_path_buf()
    } else {
        cwd.join(path)
    };

    let mut cursor = abs.as_path();
    let mut suffix: Vec<OsString> = Vec::new();

    while !cursor.exists() {
        if let Some(name) = cursor.file_name() {
            suffix.push(name.to_os_string());
        }
        match cursor.parent() {
            Some(parent) => cursor = parent,
            None => break,
        }
    }

    let base = if cursor.exists() {
        dunce_canonicalize(cursor)
            .with_context(|| format!("failed to canonicalize {}", cursor.display()))?
    } else {
        dunce_canonicalize(&cwd)?
    };

    let mut normalized = base;
    for component in suffix.iter().rev() {
        normalized.push(component);
    }

    Ok(normalized)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum LineEnding {
    Lf,
    Crlf,
}

#[derive(Clone, Copy, Debug)]
struct TextMetadata {
    encoding: Option<&'static Encoding>,
    line_ending: LineEnding,
    had_trailing_newline: bool,
    had_bom: bool,
}

fn print_file_status(path: &str, status: &str, renames: usize, show_stats: bool, quiet: bool) {
    if quiet {
        return;
    }
    if show_stats {
        println!("• {} → {} (renames: {})", path, status, renames);
    } else {
        println!("• {} → {}", path, status);
    }
}

fn print_summary(
    stats: &DirStats,
    show_stats: bool,
    json_output: bool,
    dry_run: bool,
    output_label: &str,
    output_json: Option<&Path>,
) -> anyhow::Result<()> {
    let message = if dry_run {
        if show_stats {
            format!(
                "Dry run complete: {} files matched → {} minified, {} skipped, {} bailouts, {} errors, {} renames. Output: {}",
                stats.processed,
                stats.rewritten,
                stats.skipped_no_change,
                stats.bailouts,
                stats.errors,
                stats.total_renames,
                output_label,
            )
        } else {
            format!(
                "Dry run complete: {} files matched → {} minified, {} skipped, {} bailouts, {} errors. Output: {}",
                stats.processed,
                stats.rewritten,
                stats.skipped_no_change,
                stats.bailouts,
                stats.errors,
                output_label,
            )
        }
    } else if show_stats {
        format!(
            "Processed {} files → {} minified, {} skipped, {} bailouts, {} errors, {} renames. Output: {}",
            stats.processed,
            stats.rewritten,
            stats.skipped_no_change,
            stats.bailouts,
            stats.errors,
            stats.total_renames,
            output_label,
        )
    } else {
        format!(
            "Processed {} files → {} minified, {} skipped, {} bailouts, {} errors. Output: {}",
            stats.processed,
            stats.rewritten,
            stats.skipped_no_change,
            stats.bailouts,
            stats.errors,
            output_label,
        )
    };

    println!("{}", message);
    info!("{}", message);

    if show_stats && json_output {
        println!("{}", serde_json::to_string_pretty(stats)?);
    }

    if let Some(path) = output_json {
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                fs::create_dir_all(parent)?;
            }
        }
        let file = fs::File::create(path)?;
        serde_json::to_writer_pretty(file, stats)?;
    }

    Ok(())
}

fn compute_exit_code(
    stats: &DirStats,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
) -> i32 {
    let mut code = 0;
    if fail_on_error && stats.errors > 0 {
        code |= 1;
    }
    if fail_on_bailout && stats.bailouts > 0 {
        code |= 2;
    }
    if fail_on_change && stats.rewritten > 0 {
        code |= 4;
    }
    code
}

fn bump_reason(stats: &mut DirStats, reason: &str) {
    *stats.reasons.entry(reason.to_string()).or_insert(0) += 1;
}

fn detect_pep263_encoding(bytes: &[u8]) -> Option<&'static Encoding> {
    fn extract(line: &str) -> Option<&'static Encoding> {
        if !line.trim_start().starts_with('#') {
            return None;
        }
        let lower = line.to_lowercase();
        if let Some(idx) = lower.find("coding") {
            let mut rest = &line[idx + "coding".len()..];
            rest =
                rest.trim_start_matches(|c: char| matches!(c, ' ' | '\t' | ':' | '=' | '-' | '*'));
            let label: String = rest
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
                .collect();
            if !label.is_empty() {
                let trimmed = label.trim();
                if let Some(enc) = Encoding::for_label(trimmed.as_bytes()) {
                    return Some(enc);
                }
                let fallback: String = trimmed.chars().filter(|c| *c != '-' && *c != '_').collect();
                if !fallback.is_empty() {
                    if let Some(enc) = Encoding::for_label(fallback.as_bytes()) {
                        return Some(enc);
                    }
                }
            }
        }
        None
    }

    let mut lines = bytes.split(|&b| b == b'\n');
    for _ in 0..2 {
        if let Some(line_bytes) = lines.next() {
            if let Ok(line_str) = std::str::from_utf8(line_bytes) {
                if let Some(enc) = extract(line_str) {
                    return Some(enc);
                }
            }
        }
    }
    None
}

fn decode_python_bytes(bytes: &[u8], label: &str) -> anyhow::Result<(String, TextMetadata)> {
    let encoding = if bytes.starts_with(b"\xEF\xBB\xBF") {
        Some(UTF_8)
    } else if bytes.starts_with(&[0xFF, 0xFE]) {
        Some(UTF_16LE)
    } else if bytes.starts_with(&[0xFE, 0xFF]) {
        Some(UTF_16BE)
    } else {
        detect_pep263_encoding(bytes)
    };

    let effective = encoding.unwrap_or(UTF_8);
    let (decoded, had_errors) = effective.decode_without_bom_handling(bytes);
    if had_errors {
        anyhow::bail!("failed to decode {} using {}", label, effective.name());
    }

    let mut content = decoded.into_owned();

    let mut has_crlf = false;
    let mut has_plain_lf = false;
    let bytes_view = content.as_bytes();
    let mut i = 0;
    while i < bytes_view.len() {
        if bytes_view[i] == b'\r' {
            if i + 1 < bytes_view.len() && bytes_view[i + 1] == b'\n' {
                has_crlf = true;
                i += 1;
            } else {
                has_plain_lf = true;
            }
        } else if bytes_view[i] == b'\n' {
            if i == 0 || bytes_view[i - 1] != b'\r' {
                has_plain_lf = true;
            }
        }
        i += 1;
    }

    let line_ending = if has_crlf && !has_plain_lf {
        LineEnding::Crlf
    } else {
        LineEnding::Lf
    };

    if matches!(line_ending, LineEnding::Crlf) {
        content = content.replace("\r\n", "\n");
    }

    let had_trailing_newline = content.ends_with('\n');

    let had_bom = match encoding {
        Some(enc) if enc == UTF_8 && bytes.starts_with(b"\xEF\xBB\xBF") => true,
        Some(enc) if enc == UTF_16LE && bytes.starts_with(&[0xFF, 0xFE]) => true,
        Some(enc) if enc == UTF_16BE && bytes.starts_with(&[0xFE, 0xFF]) => true,
        _ => false,
    };

    let metadata = TextMetadata {
        encoding,
        line_ending,
        had_trailing_newline,
        had_bom,
    };

    Ok((content, metadata))
}

fn read_python(path: &Path) -> anyhow::Result<(String, TextMetadata)> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    decode_python_bytes(&bytes, &path.display().to_string())
}

fn split_source_and_plan(buffer: &[u8]) -> anyhow::Result<(String, TextMetadata, MinifyPlan)> {
    for (idx, byte) in buffer.iter().enumerate() {
        if *byte == b'{' {
            if let Ok(plan) = serde_json::from_slice::<MinifyPlan>(&buffer[idx..]) {
                let python_bytes = &buffer[..idx];
                let (source, metadata) =
                    decode_python_bytes(python_bytes, "stdin source with plan")?;
                return Ok((source, metadata, plan));
            }
        }
    }
    bail!("failed to split source and plan from stdin; provide valid plan JSON after the source");
}

fn read_pattern_file(path: &Path) -> anyhow::Result<Vec<String>> {
    let contents = fs::read_to_string(path)
        .with_context(|| format!("failed to read pattern file {}", path.display()))?;
    let mut patterns = Vec::new();
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        patterns.push(trimmed.to_string());
    }
    Ok(patterns)
}

fn build_walker(
    root: &Path,
    include_hidden: bool,
    follow_symlinks: bool,
    max_depth: Option<usize>,
    respect_gitignore: bool,
) -> ignore::Walk {
    let mut builder = WalkBuilder::new(root);
    builder.follow_links(follow_symlinks);
    builder.standard_filters(false);
    builder.hidden(!include_hidden);
    builder.max_depth(max_depth);
    builder.require_git(false);

    if respect_gitignore {
        builder
            .git_ignore(true)
            .git_global(true)
            .git_exclude(true)
            .parents(true)
            .ignore(true);
    } else {
        builder
            .git_ignore(false)
            .git_global(false)
            .git_exclude(false)
            .parents(false)
            .ignore(false);
    }

    builder.build()
}

fn encode_python(content: &str, metadata: &TextMetadata, label: &str) -> anyhow::Result<Vec<u8>> {
    let mut adjusted = content.replace("\r\n", "\n");
    if matches!(metadata.line_ending, LineEnding::Crlf) {
        adjusted = adjusted.replace("\n", "\r\n");
    }

    let newline = match metadata.line_ending {
        LineEnding::Lf => "\n",
        LineEnding::Crlf => "\r\n",
    };

    if metadata.had_trailing_newline {
        if !adjusted.ends_with(newline) {
            while adjusted.ends_with('\n') || adjusted.ends_with('\r') {
                adjusted.pop();
            }
            adjusted.push_str(newline);
        }
    } else if matches!(metadata.line_ending, LineEnding::Crlf) {
        if adjusted.ends_with("\r\n") {
            adjusted.truncate(adjusted.len() - 2);
        } else if adjusted.ends_with('\n') {
            adjusted.pop();
        }
    } else {
        while adjusted.ends_with('\n') || adjusted.ends_with('\r') {
            adjusted.pop();
        }
    }

    let encoder = metadata.encoding.unwrap_or(UTF_8);
    let mut output: Vec<u8> = Vec::new();
    if std::ptr::eq(encoder, UTF_16LE) || std::ptr::eq(encoder, UTF_16BE) {
        if metadata.had_bom {
            if std::ptr::eq(encoder, UTF_16LE) {
                output.extend_from_slice(&[0xFF, 0xFE]);
            } else {
                output.extend_from_slice(&[0xFE, 0xFF]);
            }
        }
        for unit in adjusted.encode_utf16() {
            let bytes = if std::ptr::eq(encoder, UTF_16LE) {
                unit.to_le_bytes()
            } else {
                unit.to_be_bytes()
            };
            output.extend_from_slice(&bytes);
        }
        return Ok(output);
    }

    let (encoded, output_encoding, had_errors) = encoder.encode(&adjusted);
    if had_errors || !std::ptr::eq(output_encoding, encoder) {
        anyhow::bail!("failed to encode {} using {}", label, encoder.name());
    }

    if metadata.had_bom {
        if std::ptr::eq(encoder, UTF_8) {
            output.extend_from_slice(b"\xEF\xBB\xBF");
        }
    }
    match encoded {
        Cow::Borrowed(bytes) => output.extend_from_slice(bytes),
        Cow::Owned(buffer) => output.extend_from_slice(&buffer),
    }
    Ok(output)
}

fn write_python(path: &Path, content: &str, metadata: &TextMetadata) -> anyhow::Result<()> {
    let bytes = encode_python(content, metadata, &path.display().to_string())?;
    fs::write(path, bytes)?;
    Ok(())
}

fn make_unified_diff(path: &str, original: &str, rewritten: &str, context: usize) -> String {
    let diff = TextDiff::from_lines(original, rewritten);
    diff.unified_diff()
        .header(&format!("a/{}", path), &format!("b/{}", path))
        .context_radius(context)
        .to_string()
}

const PLAN_BUNDLE_VERSION: u32 = 1;

#[derive(Debug, Serialize, Deserialize)]
struct PlanBundle {
    #[serde(default = "default_plan_version")]
    version: u32,
    files: Vec<PlanFile>,
}

fn default_plan_version() -> u32 {
    PLAN_BUNDLE_VERSION
}

#[derive(Debug, Serialize, Deserialize)]
struct PlanFile {
    path: String,
    plan: MinifyPlan,
}

fn minify_file(
    file_path: &PathBuf,
    in_place: bool,
    dry_run: bool,
    backup_ext: Option<&str>,
    show_stats: bool,
    json_output: bool,
    quiet: bool,
    output_json: Option<&Path>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    force_stdout: bool,
) -> anyhow::Result<(DirStats, Option<Vec<u8>>)> {
    minify_file_impl(
        file_path,
        in_place,
        dry_run,
        backup_ext,
        show_stats,
        json_output,
        quiet,
        output_json,
        fail_on_bailout,
        fail_on_error,
        fail_on_change,
        diff,
        diff_context,
        force_stdout,
        false, // remove_dead_code defaults to false
    )
}

fn minify_file_impl(
    file_path: &PathBuf,
    in_place: bool,
    dry_run: bool,
    backup_ext: Option<&str>,
    show_stats: bool,
    json_output: bool,
    quiet: bool,
    output_json: Option<&Path>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    force_stdout: bool,
    remove_dead_code: bool,
) -> anyhow::Result<(DirStats, Option<Vec<u8>>)> {
    if json_output && !show_stats {
        anyhow::bail!("--json requires --stats");
    }

    let (source, metadata) = read_python(file_path)?;
    let module_name = file_path
        .file_stem()
        .and_then(|stem| stem.to_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| file_path.to_string_lossy().to_string());

    let mut plan = Minifier::plan_from_source(&module_name, &source)?;

    // Filter plan if --remove-dead-code is requested
    if remove_dead_code {
        let dead_code = detect_dead_code(&source, &module_name, quiet)?;
        plan = filter_plan_for_dead_code(plan, &dead_code);
    }

    apply_plan_to_file(
        file_path,
        &source,
        &metadata,
        &plan,
        in_place,
        dry_run,
        backup_ext,
        show_stats,
        json_output,
        quiet,
        output_json,
        fail_on_bailout,
        fail_on_error,
        fail_on_change,
        diff,
        diff_context,
        force_stdout,
    )
}

fn apply_plan_to_file(
    file_path: &PathBuf,
    source: &str,
    metadata: &TextMetadata,
    plan: &MinifyPlan,
    in_place: bool,
    dry_run: bool,
    backup_ext: Option<&str>,
    show_stats: bool,
    json_output: bool,
    quiet: bool,
    output_json: Option<&Path>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    force_stdout: bool,
) -> anyhow::Result<(DirStats, Option<Vec<u8>>)> {
    if json_output && !show_stats {
        anyhow::bail!("--json requires --stats");
    }

    if backup_ext.is_some() && !in_place {
        anyhow::bail!("--backup-ext requires --in-place");
    }

    let rename_total: usize = plan.functions.iter().map(|f| f.renames.len()).sum();

    let mut status;
    let mut final_content: Cow<'_, str> = Cow::Borrowed(source);

    if rename_total == 0 {
        status = "skipped (no renames)".to_string();
    } else {
        let rewritten = Minifier::rewrite_with_plan(&plan.module, source, plan)?;
        if rewritten == source {
            status = "skipped (rewrite aborted)".to_string();
        } else {
            status = "minified".to_string();
            final_content = Cow::Owned(rewritten);
        }
    }

    let display_path = file_path.display().to_string();

    if in_place && !dry_run {
        if let Some(ext) = backup_ext {
            let mut backup_os = file_path.as_os_str().to_os_string();
            backup_os.push(ext);
            let backup_path = PathBuf::from(backup_os);
            if backup_path.exists() {
                status = "skipped (backup exists)".to_string();
                final_content = Cow::Borrowed(source);
            } else {
                fs::copy(file_path, &backup_path).with_context(|| {
                    format!("failed to create backup {}", backup_path.display())
                })?;
            }
        }

        if let Cow::Owned(ref content) = final_content {
            write_python(file_path, content, metadata)?;
        }
    }

    let applied_renames = if matches!(status.as_str(), "minified") {
        rename_total
    } else {
        0
    };

    if !force_stdout {
        if show_stats {
            print_file_status(&display_path, &status, applied_renames, true, quiet);
        } else if in_place {
            print_file_status(&display_path, &status, applied_renames, false, quiet);
        }
    }

    if diff && matches!(status.as_str(), "minified") && !quiet && !force_stdout {
        let diff_str =
            make_unified_diff(&display_path, source, final_content.as_ref(), diff_context);
        println!("{}", diff_str);
    }

    let mut stdout_bytes = None;
    if force_stdout {
        let bytes = encode_python(final_content.as_ref(), metadata, &display_path)?;
        stdout_bytes = Some(bytes);
    } else if !in_place && !show_stats && !quiet {
        println!("{}", final_content);
    }

    let mut stats = DirStats::default();
    stats.processed = 1;
    stats.total_renames = applied_renames;
    match status.as_str() {
        "minified" => {
            stats.rewritten = 1;
            bump_reason(&mut stats, "minified");
        }
        "skipped (no renames)" => {
            stats.skipped_no_change = 1;
            bump_reason(&mut stats, "no_renames");
        }
        "skipped (rewrite aborted)" => {
            stats.bailouts = 1;
            bump_reason(&mut stats, "rewrite_aborted");
        }
        "skipped (backup exists)" => {
            stats.bailouts = 1;
            bump_reason(&mut stats, "backup_exists");
        }
        _ => {
            stats.bailouts = 1;
        }
    }
    stats.files.push(FileStats {
        path: display_path.clone(),
        renames: applied_renames,
        status: status.clone(),
    });

    let summary_needed =
        show_stats || fail_on_bailout || fail_on_error || fail_on_change || output_json.is_some();
    if summary_needed && !force_stdout {
        let output_target = if in_place {
            display_path.clone()
        } else {
            "stdout".to_string()
        };
        print_summary(
            &stats,
            show_stats,
            json_output,
            dry_run,
            &output_target,
            output_json,
        )?;
    }

    Ok((stats, stdout_bytes))
}

#[allow(dead_code)]
fn minify_plan_dir(
    input_dir: &PathBuf,
    out_path: &PathBuf,
    includes: &[String],
    include_file: Option<&PathBuf>,
    excludes: &[String],
    exclude_file: Option<&PathBuf>,
    jobs: Option<usize>,
    include_hidden: bool,
    follow_symlinks: bool,
    glob_case_insensitive: Option<bool>,
    quiet: bool,
) -> anyhow::Result<()> {
    minify_plan_dir_with_depth(
        input_dir,
        out_path,
        includes,
        include_file,
        excludes,
        exclude_file,
        jobs,
        include_hidden,
        follow_symlinks,
        glob_case_insensitive,
        None,
        false,
        quiet,
    )
}

fn minify_plan_dir_with_depth(
    input_dir: &PathBuf,
    out_path: &PathBuf,
    includes: &[String],
    include_file: Option<&PathBuf>,
    excludes: &[String],
    exclude_file: Option<&PathBuf>,
    jobs: Option<usize>,
    include_hidden: bool,
    follow_symlinks: bool,
    glob_case_insensitive: Option<bool>,
    max_depth: Option<usize>,
    respect_gitignore: bool,
    quiet: bool,
) -> anyhow::Result<()> {
    let input_dir = canonicalize_directory(input_dir.as_path())?;
    if !input_dir.is_dir() {
        anyhow::bail!("Input '{}' is not a directory", input_dir.display());
    }

    let mut include_patterns = if includes.is_empty() {
        vec!["**/*.py".to_string()]
    } else {
        includes.to_vec()
    };
    if let Some(path) = include_file {
        include_patterns.extend(read_pattern_file(path.as_path())?);
    }
    let glob_case_insensitive = glob_case_insensitive.unwrap_or(cfg!(windows));
    let include_glob = build_globset(&include_patterns, glob_case_insensitive)?;
    let mut exclude_patterns = merged_exclude_patterns(excludes);
    if let Some(path) = exclude_file {
        exclude_patterns.extend(read_pattern_file(path.as_path())?);
    }
    let exclude_glob = build_globset(&exclude_patterns, glob_case_insensitive)?;

    let mut errors = 0usize;
    let mut candidates: Vec<Candidate> = Vec::new();

    let walker = build_walker(
        &input_dir,
        include_hidden,
        follow_symlinks,
        max_depth,
        respect_gitignore,
    );

    for entry in walker {
        let entry = match entry {
            Ok(entry) => entry,
            Err(err) => {
                errors += 1;
                warn!("walk error: {}", err);
                continue;
            }
        };

        let file_type = match entry.file_type() {
            Some(ft) => ft,
            None => continue,
        };

        if file_type.is_dir() {
            continue;
        }

        if !follow_symlinks && entry.path_is_symlink() {
            continue;
        }

        let path = entry.path();
        let rel_path = match path.strip_prefix(&input_dir) {
            Ok(rel) => rel,
            Err(_) => continue,
        };

        let rel_norm = normalize_rel_path(rel_path);

        if !include_hidden
            && rel_path.components().any(|comp| {
                matches!(comp, std::path::Component::Normal(os) if os.to_string_lossy().starts_with('.'))
            })
        {
            debug!("• {} → skipped (hidden path)", rel_norm);
            continue;
        }

        if !include_glob.is_match(rel_norm.as_str()) {
            debug!("• {} → skipped (not included)", rel_norm);
            continue;
        }
        if exclude_glob.is_match(rel_norm.as_str()) {
            debug!("• {} → skipped (excluded)", rel_norm);
            continue;
        }

        if path
            .extension()
            .and_then(|ext| ext.to_str())
            .map(|ext| ext.eq_ignore_ascii_case("py"))
            != Some(true)
        {
            debug!("• {} → skipped (non-Python)", rel_norm);
            continue;
        }

        candidates.push(Candidate {
            abs_path: path.to_path_buf(),
            rel_path: rel_path.to_path_buf(),
            rel_norm,
        });
    }

    let jobs = resolve_jobs(jobs)?;

    #[derive(Debug)]
    enum PlanOutcome {
        Success { plan: MinifyPlan, renames: usize },
        ReadError(String),
        PlanError(String),
    }

    candidates.sort_by(|a, b| a.rel_norm.cmp(&b.rel_norm));

    let plan_results: Vec<(Candidate, PlanOutcome)> = if candidates.is_empty() {
        Vec::new()
    } else if jobs <= 1 {
        candidates
            .iter()
            .map(|candidate| (candidate.clone(), compute_plan(candidate)))
            .collect()
    } else {
        let pool = ThreadPoolBuilder::new().num_threads(jobs).build()?;
        pool.install(|| {
            candidates
                .par_iter()
                .map(|candidate| (candidate.clone(), compute_plan(candidate)))
                .collect()
        })
    };

    fn compute_plan(candidate: &Candidate) -> PlanOutcome {
        let source = match read_python(&candidate.abs_path) {
            Ok((content, _)) => content,
            Err(err) => return PlanOutcome::ReadError(err.to_string()),
        };

        let module_name = derive_module_name(&candidate.rel_path);
        let plan = match Minifier::plan_from_source(&module_name, &source) {
            Ok(plan) => plan,
            Err(err) => return PlanOutcome::PlanError(err.to_string()),
        };

        let renames = plan.functions.iter().map(|f| f.renames.len()).sum();
        PlanOutcome::Success { plan, renames }
    }

    let mut plans: Vec<PlanFile> = Vec::new();

    for (candidate, outcome) in plan_results {
        match outcome {
            PlanOutcome::Success { plan, renames } => {
                print_file_status(&candidate.rel_norm, "planned", renames, true, quiet);
                plans.push(PlanFile {
                    path: candidate.rel_norm,
                    plan,
                });
            }
            PlanOutcome::ReadError(message) => {
                errors += 1;
                error!(
                    "failed to read {}: {}",
                    candidate.abs_path.display(),
                    message
                );
            }
            PlanOutcome::PlanError(message) => {
                errors += 1;
                error!(
                    "failed to plan {}: {}",
                    candidate.abs_path.display(),
                    message
                );
            }
        }
    }

    plans.sort_by(|a, b| a.path.cmp(&b.path));
    let planned_count = plans.len();

    if planned_count == 0 {
        warn!("no files matched the provided filters; writing empty plan bundle");
    }

    if let Some(parent) = out_path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)?;
        }
    }

    let bundle = PlanBundle {
        version: PLAN_BUNDLE_VERSION,
        files: plans,
    };
    fs::write(out_path, serde_json::to_string_pretty(&bundle)?)?;

    println!(
        "Planned {} files ({} errors). Output: {}",
        planned_count,
        errors,
        out_path.display()
    );

    Ok(())
}

#[allow(dead_code)]
fn apply_plan_dir(
    input_dir: &PathBuf,
    plan_path: &PathBuf,
    out_dir: Option<PathBuf>,
    includes: &[String],
    include_file: Option<&PathBuf>,
    excludes: &[String],
    exclude_file: Option<&PathBuf>,
    backup_ext: Option<&str>,
    in_place: bool,
    dry_run: bool,
    show_stats: bool,
    json_output: bool,
    include_hidden: bool,
    follow_symlinks: bool,
    glob_case_insensitive: Option<bool>,
    quiet: bool,
    output_json: Option<&Path>,
    jobs: Option<usize>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
) -> anyhow::Result<DirStats> {
    apply_plan_dir_with_depth(
        input_dir,
        plan_path,
        out_dir,
        includes,
        include_file,
        excludes,
        exclude_file,
        backup_ext,
        in_place,
        dry_run,
        show_stats,
        json_output,
        include_hidden,
        follow_symlinks,
        glob_case_insensitive,
        quiet,
        output_json,
        jobs,
        fail_on_bailout,
        fail_on_error,
        fail_on_change,
        diff,
        diff_context,
        false,
        None,
    )
}

fn apply_plan_dir_with_depth(
    input_dir: &PathBuf,
    plan_path: &PathBuf,
    out_dir: Option<PathBuf>,
    includes: &[String],
    include_file: Option<&PathBuf>,
    excludes: &[String],
    exclude_file: Option<&PathBuf>,
    backup_ext: Option<&str>,
    in_place: bool,
    dry_run: bool,
    show_stats: bool,
    json_output: bool,
    include_hidden: bool,
    follow_symlinks: bool,
    glob_case_insensitive: Option<bool>,
    quiet: bool,
    output_json: Option<&Path>,
    jobs: Option<usize>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    respect_gitignore: bool,
    max_depth: Option<usize>,
) -> anyhow::Result<DirStats> {
    if json_output && !show_stats {
        anyhow::bail!("--json requires --stats");
    }

    let input_dir = canonicalize_directory(input_dir.as_path())?;
    if !input_dir.is_dir() {
        anyhow::bail!("Input '{}' is not a directory", input_dir.display());
    }

    if backup_ext.is_some() && !in_place {
        anyhow::bail!("--backup-ext requires --in-place");
    }

    if in_place && out_dir.is_some() {
        anyhow::bail!("Cannot use --out-dir with --in-place");
    }

    let plan_contents = fs::read_to_string(plan_path)?;
    let bundle: PlanBundle = serde_json::from_str(&plan_contents)?;
    if bundle.version > PLAN_BUNDLE_VERSION {
        anyhow::bail!(
            "unsupported plan bundle version: {} (supported: {})",
            bundle.version,
            PLAN_BUNDLE_VERSION
        );
    }
    let mut plan_map: HashMap<String, MinifyPlan> = HashMap::new();
    for file_plan in bundle.files {
        plan_map.insert(file_plan.path, file_plan.plan);
    }

    if plan_map.is_empty() {
        anyhow::bail!("Plan bundle contains no files");
    }

    let plan_map = Arc::new(plan_map);

    let resolved_out_dir = if in_place {
        input_dir.clone()
    } else {
        out_dir.unwrap_or_else(|| default_output_dir(&input_dir))
    };

    if !in_place {
        let out_norm = normalize_output_path_guard(&resolved_out_dir)?;

        if out_norm.starts_with(&input_dir) {
            anyhow::bail!("--out-dir cannot be inside the input directory");
        }

        if resolved_out_dir.exists() {
            if !resolved_out_dir.is_dir() {
                anyhow::bail!(
                    "Output '{}' exists and is not a directory",
                    resolved_out_dir.display()
                );
            }
            if !dry_run && resolved_out_dir.read_dir()?.next().is_some() {
                anyhow::bail!(
                    "Output directory '{}' already exists and is not empty",
                    resolved_out_dir.display()
                );
            }
        } else if !dry_run {
            fs::create_dir_all(&resolved_out_dir)?;
        }
    }

    let mut include_patterns = if includes.is_empty() {
        vec!["**/*.py".to_string()]
    } else {
        includes.to_vec()
    };
    if let Some(path) = include_file {
        include_patterns.extend(read_pattern_file(path.as_path())?);
    }
    let glob_case_insensitive = glob_case_insensitive.unwrap_or(cfg!(windows));
    let include_glob = build_globset(&include_patterns, glob_case_insensitive)?;
    let mut exclude_patterns = merged_exclude_patterns(excludes);
    if let Some(path) = exclude_file {
        exclude_patterns.extend(read_pattern_file(path.as_path())?);
    }
    let exclude_glob = build_globset(&exclude_patterns, glob_case_insensitive)?;

    let jobs = resolve_jobs(jobs)?;

    let mut stats = DirStats::default();
    let mut candidates: Vec<Candidate> = Vec::new();

    let walker = build_walker(
        &input_dir,
        include_hidden,
        follow_symlinks,
        max_depth,
        respect_gitignore,
    );

    for entry in walker {
        let entry = match entry {
            Ok(entry) => entry,
            Err(err) => {
                stats.errors += 1;
                warn!("walk error: {}", err);
                continue;
            }
        };

        let file_type = match entry.file_type() {
            Some(ft) => ft,
            None => continue,
        };

        if file_type.is_dir() {
            continue;
        }

        if !follow_symlinks && entry.path_is_symlink() {
            continue;
        }

        let path = entry.path();
        let rel_path = match path.strip_prefix(&input_dir) {
            Ok(rel) => rel,
            Err(_) => continue,
        };

        let rel_norm = normalize_rel_path(rel_path);

        if !include_hidden
            && rel_path.components().any(|comp| {
                matches!(comp, std::path::Component::Normal(os) if os.to_string_lossy().starts_with('.'))
            })
        {
            debug!("• {} → skipped (hidden path)", rel_norm);
            continue;
        }

        if !include_glob.is_match(rel_norm.as_str()) {
            debug!("• {} → skipped (not included)", rel_norm);
            continue;
        }
        if exclude_glob.is_match(rel_norm.as_str()) {
            debug!("• {} → skipped (excluded)", rel_norm);
            continue;
        }

        if path
            .extension()
            .and_then(|ext| ext.to_str())
            .map(|ext| ext.eq_ignore_ascii_case("py"))
            != Some(true)
        {
            debug!("• {} → skipped (non-Python)", rel_norm);
            continue;
        }

        if !plan_map.contains_key(&rel_norm) {
            debug!("• {} → skipped (no plan)", rel_norm);
            continue;
        }

        candidates.push(Candidate {
            abs_path: path.to_path_buf(),
            rel_path: rel_path.to_path_buf(),
            rel_norm,
        });
    }

    candidates.sort_by(|a, b| a.rel_norm.cmp(&b.rel_norm));

    stats.processed = candidates.len();

    let processor = {
        let plan_map = Arc::clone(&plan_map);
        move |candidate: &Candidate| -> FileResult {
            let candidate_clone = candidate.clone();
            let (source, metadata) = match read_python(&candidate.abs_path) {
                Ok(result) => result,
                Err(err) => {
                    return FileResult {
                        candidate: candidate_clone,
                        outcome: FileOutcome::ReadError {
                            message: err.to_string(),
                        },
                    }
                }
            };

            let plan = match plan_map.get(&candidate.rel_norm) {
                Some(plan) => plan,
                None => {
                    return FileResult {
                        candidate: candidate_clone,
                        outcome: FileOutcome::PlanError {
                            message: "plan missing".to_string(),
                        },
                    }
                }
            };

            let rename_total: usize = plan.functions.iter().map(|f| f.renames.len()).sum();
            let has_nested = plan.functions.iter().any(|f| f.has_nested_functions);

            if has_nested {
                return FileResult {
                    candidate: candidate_clone,
                    outcome: FileOutcome::SkippedNested {
                        original: source,
                        metadata,
                    },
                };
            }

            if rename_total == 0 {
                return FileResult {
                    candidate: candidate_clone,
                    outcome: FileOutcome::SkippedNoRenames {
                        original: source,
                        metadata,
                    },
                };
            }

            match Minifier::rewrite_with_plan(&plan.module, &source, plan) {
                Ok(rewritten) => {
                    if rewritten == source {
                        FileResult {
                            candidate: candidate_clone,
                            outcome: FileOutcome::SkippedRewriteAborted {
                                original: source,
                                metadata,
                            },
                        }
                    } else {
                        FileResult {
                            candidate: candidate_clone,
                            outcome: FileOutcome::Minified {
                                original: source,
                                rewritten,
                                renames: rename_total,
                                metadata,
                            },
                        }
                    }
                }
                Err(err) => FileResult {
                    candidate: candidate_clone,
                    outcome: FileOutcome::RewriteError {
                        message: err.to_string(),
                    },
                },
            }
        }
    };

    let results = execute_parallel_processing(&candidates, jobs, processor)?;

    finalize_file_results(
        results,
        &mut stats,
        &input_dir,
        &resolved_out_dir,
        in_place,
        dry_run,
        backup_ext,
        quiet,
        show_stats,
        diff,
        diff_context,
    )?;

    let summary_needed =
        show_stats || fail_on_bailout || fail_on_error || fail_on_change || output_json.is_some();
    if summary_needed {
        let output_label = if in_place {
            input_dir.display().to_string()
        } else {
            resolved_out_dir.display().to_string()
        };
        print_summary(
            &stats,
            show_stats,
            json_output,
            dry_run,
            &output_label,
            output_json,
        )?;
    }

    Ok(stats)
}

#[allow(dead_code)]
fn minify_dir(
    input_dir: &PathBuf,
    out_dir: Option<PathBuf>,
    includes: &[String],
    include_file: Option<&PathBuf>,
    excludes: &[String],
    exclude_file: Option<&PathBuf>,
    backup_ext: Option<&str>,
    in_place: bool,
    dry_run: bool,
    show_stats: bool,
    json_output: bool,
    include_hidden: bool,
    follow_symlinks: bool,
    glob_case_insensitive: Option<bool>,
    quiet: bool,
    output_json: Option<&Path>,
    jobs: Option<usize>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    remove_dead_code: bool,
) -> anyhow::Result<DirStats> {
    minify_dir_with_depth(
        input_dir,
        out_dir,
        includes,
        include_file,
        excludes,
        exclude_file,
        backup_ext,
        in_place,
        dry_run,
        show_stats,
        json_output,
        include_hidden,
        follow_symlinks,
        glob_case_insensitive,
        quiet,
        output_json,
        jobs,
        fail_on_bailout,
        fail_on_error,
        fail_on_change,
        diff,
        diff_context,
        false,
        None,
        remove_dead_code,
    )
}

fn minify_dir_with_depth(
    input_dir: &PathBuf,
    out_dir: Option<PathBuf>,
    includes: &[String],
    include_file: Option<&PathBuf>,
    excludes: &[String],
    exclude_file: Option<&PathBuf>,
    backup_ext: Option<&str>,
    in_place: bool,
    dry_run: bool,
    show_stats: bool,
    json_output: bool,
    include_hidden: bool,
    follow_symlinks: bool,
    glob_case_insensitive: Option<bool>,
    quiet: bool,
    output_json: Option<&Path>,
    jobs: Option<usize>,
    fail_on_bailout: bool,
    fail_on_error: bool,
    fail_on_change: bool,
    diff: bool,
    diff_context: usize,
    respect_gitignore: bool,
    max_depth: Option<usize>,
    remove_dead_code: bool,
) -> anyhow::Result<DirStats> {
    let input_dir = canonicalize_directory(input_dir.as_path())?;
    if !input_dir.is_dir() {
        anyhow::bail!("Input '{}' is not a directory", input_dir.display());
    }

    if json_output && !show_stats {
        anyhow::bail!("--json requires --stats");
    }

    if in_place && out_dir.is_some() {
        anyhow::bail!("Cannot use --out-dir with --in-place");
    }

    if backup_ext.is_some() && !in_place {
        anyhow::bail!("--backup-ext requires --in-place");
    }

    let resolved_out_dir = if in_place {
        input_dir.clone()
    } else {
        out_dir.unwrap_or_else(|| default_output_dir(&input_dir))
    };

    if !in_place {
        let out_norm = normalize_output_path_guard(&resolved_out_dir)?;

        if out_norm.starts_with(&input_dir) {
            anyhow::bail!("--out-dir cannot be inside the input directory");
        }

        if resolved_out_dir.exists() {
            if !resolved_out_dir.is_dir() {
                anyhow::bail!(
                    "Output '{}' exists and is not a directory",
                    resolved_out_dir.display()
                );
            }
            if !dry_run && resolved_out_dir.read_dir()?.next().is_some() {
                anyhow::bail!(
                    "Output directory '{}' already exists and is not empty",
                    resolved_out_dir.display()
                );
            }
        } else if !dry_run {
            fs::create_dir_all(&resolved_out_dir)?;
        }
    }

    let jobs = resolve_jobs(jobs)?;

    let mut stats = DirStats::default();

    let mut include_patterns = if includes.is_empty() {
        vec!["**/*.py".to_string()]
    } else {
        includes.to_vec()
    };
    if let Some(path) = include_file {
        include_patterns.extend(read_pattern_file(path.as_path())?);
    }
    let glob_case_insensitive = glob_case_insensitive.unwrap_or(cfg!(windows));
    let include_glob = build_globset(&include_patterns, glob_case_insensitive)?;
    let mut exclude_patterns = merged_exclude_patterns(excludes);
    if let Some(path) = exclude_file {
        exclude_patterns.extend(read_pattern_file(path.as_path())?);
    }
    let exclude_glob = build_globset(&exclude_patterns, glob_case_insensitive)?;

    let mut candidates: Vec<Candidate> = Vec::new();

    let walker = build_walker(
        &input_dir,
        include_hidden,
        follow_symlinks,
        max_depth,
        respect_gitignore,
    );

    for entry in walker {
        let entry = match entry {
            Ok(entry) => entry,
            Err(err) => {
                stats.errors += 1;
                warn!("walk error: {}", err);
                continue;
            }
        };

        let file_type = match entry.file_type() {
            Some(ft) => ft,
            None => continue,
        };

        if file_type.is_dir() {
            continue;
        }

        if !follow_symlinks && entry.path_is_symlink() {
            continue;
        }

        let path = entry.path();
        let rel_path = match path.strip_prefix(&input_dir) {
            Ok(rel) => rel,
            Err(_) => continue,
        };

        let rel_norm = normalize_rel_path(rel_path);

        if !include_hidden
            && rel_path.components().any(|comp| {
                matches!(comp, std::path::Component::Normal(os) if os.to_string_lossy().starts_with('.'))
            })
        {
            debug!("• {} → skipped (hidden path)", rel_norm);
            continue;
        }

        if !include_glob.is_match(rel_norm.as_str()) {
            debug!("• {} → skipped (not included)", rel_norm);
            continue;
        }
        if exclude_glob.is_match(rel_norm.as_str()) {
            debug!("• {} → skipped (excluded)", rel_norm);
            continue;
        }

        if path
            .extension()
            .and_then(|ext| ext.to_str())
            .map(|ext| ext.eq_ignore_ascii_case("py"))
            != Some(true)
        {
            debug!("• {} → skipped (non-Python)", rel_norm);
            continue;
        }

        candidates.push(Candidate {
            abs_path: path.to_path_buf(),
            rel_path: rel_path.to_path_buf(),
            rel_norm,
        });
    }

    candidates.sort_by(|a, b| a.rel_norm.cmp(&b.rel_norm));

    stats.processed = candidates.len();

    let processor = |candidate: &Candidate| -> FileResult {
        let candidate_clone = candidate.clone();
        let (source, metadata) = match read_python(&candidate.abs_path) {
            Ok(result) => result,
            Err(err) => {
                return FileResult {
                    candidate: candidate_clone,
                    outcome: FileOutcome::ReadError {
                        message: err.to_string(),
                    },
                }
            }
        };

        let module_name = derive_module_name(&candidate.rel_path);
        let mut plan = match Minifier::plan_from_source(&module_name, &source) {
            Ok(plan) => plan,
            Err(err) => {
                return FileResult {
                    candidate: candidate_clone,
                    outcome: FileOutcome::PlanError {
                        message: err.to_string(),
                    },
                }
            }
        };

        // Filter plan if --remove-dead-code is requested
        if remove_dead_code {
            let dead_code = match detect_dead_code(&source, &module_name, quiet) {
                Ok(dead_code) => dead_code,
                Err(_err) => {
                    // If dead code detection fails, just continue with unfiltered plan
                    Vec::new()
                }
            };
            plan = filter_plan_for_dead_code(plan, &dead_code);
        }

        let rename_total: usize = plan.functions.iter().map(|f| f.renames.len()).sum();
        let has_nested = plan.functions.iter().any(|f| f.has_nested_functions);

        if has_nested {
            return FileResult {
                candidate: candidate_clone,
                outcome: FileOutcome::SkippedNested {
                    original: source,
                    metadata,
                },
            };
        }

        if rename_total == 0 {
            return FileResult {
                candidate: candidate_clone,
                outcome: FileOutcome::SkippedNoRenames {
                    original: source,
                    metadata,
                },
            };
        }

        match Minifier::rewrite_with_plan(&module_name, &source, &plan) {
            Ok(rewritten) => {
                if rewritten == source {
                    FileResult {
                        candidate: candidate_clone,
                        outcome: FileOutcome::SkippedRewriteAborted {
                            original: source,
                            metadata,
                        },
                    }
                } else {
                    FileResult {
                        candidate: candidate_clone,
                        outcome: FileOutcome::Minified {
                            original: source,
                            rewritten,
                            renames: rename_total,
                            metadata,
                        },
                    }
                }
            }
            Err(err) => FileResult {
                candidate: candidate_clone,
                outcome: FileOutcome::RewriteError {
                    message: err.to_string(),
                },
            },
        }
    };

    let results = execute_parallel_processing(&candidates, jobs, processor)?;

    finalize_file_results(
        results,
        &mut stats,
        &input_dir,
        &resolved_out_dir,
        in_place,
        dry_run,
        backup_ext,
        quiet,
        show_stats,
        diff,
        diff_context,
    )?;

    let summary_needed =
        show_stats || fail_on_bailout || fail_on_error || fail_on_change || output_json.is_some();
    if summary_needed {
        let output_label = if in_place {
            input_dir.display().to_string()
        } else {
            resolved_out_dir.display().to_string()
        };
        print_summary(
            &stats,
            show_stats,
            json_output,
            dry_run,
            &output_label,
            output_json,
        )?;
    }

    Ok(stats)
}

fn default_output_dir(input_dir: &Path) -> PathBuf {
    let parent = input_dir
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."));

    let name = input_dir
        .file_name()
        .map(|os| os.to_string_lossy().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "minified".to_string());

    parent.join(format!("{}-min", name))
}

fn derive_module_name(rel_path: &Path) -> String {
    let without_ext = rel_path.with_extension("");
    let mut parts: Vec<String> = without_ext
        .iter()
        .map(|component| component.to_string_lossy().replace('-', "_"))
        .collect();

    if parts.last().map(|part| part == "__init__").unwrap_or(false) {
        parts.pop();
    }

    if parts.is_empty() {
        rel_path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .map(|s| s.to_string())
            .unwrap_or_else(|| "module".to_string())
    } else {
        parts.join(".")
    }
}

fn merged_exclude_patterns(extras: &[String]) -> Vec<String> {
    let mut patterns: Vec<String> = DEFAULT_EXCLUDES
        .iter()
        .map(|pattern| pattern.to_string())
        .collect();
    patterns.extend(extras.iter().cloned());
    patterns
}

fn build_globset(patterns: &[String], case_insensitive: bool) -> anyhow::Result<GlobSet> {
    let mut builder = GlobSetBuilder::new();
    for pattern in patterns {
        let mut glob_builder = GlobBuilder::new(pattern);
        glob_builder.case_insensitive(case_insensitive);
        builder.add(glob_builder.build()?);
    }
    Ok(builder.build()?)
}

fn normalize_rel_path(rel_path: &Path) -> String {
    let mut parts = Vec::new();
    for component in rel_path.iter() {
        parts.push(component.to_string_lossy());
    }
    parts.join("/")
}

#[derive(Clone)]
struct Candidate {
    abs_path: PathBuf,
    rel_path: PathBuf,
    rel_norm: String,
}

struct FileResult {
    candidate: Candidate,
    outcome: FileOutcome,
}

enum FileOutcome {
    Minified {
        original: String,
        rewritten: String,
        renames: usize,
        metadata: TextMetadata,
    },
    SkippedNoRenames {
        original: String,
        metadata: TextMetadata,
    },
    SkippedNested {
        original: String,
        metadata: TextMetadata,
    },
    SkippedRewriteAborted {
        original: String,
        metadata: TextMetadata,
    },
    ReadError {
        message: String,
    },
    PlanError {
        message: String,
    },
    RewriteError {
        message: String,
    },
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum FinalStatusKind {
    Minified,
    SkippedNoRenames,
    SkippedNested,
    SkippedRewriteAborted,
    SkippedBackupExists,
}

impl FinalStatusKind {
    fn label(self) -> &'static str {
        match self {
            FinalStatusKind::Minified => "minified",
            FinalStatusKind::SkippedNoRenames => "skipped (no renames)",
            FinalStatusKind::SkippedNested => "skipped (nested scopes)",
            FinalStatusKind::SkippedRewriteAborted => "skipped (rewrite aborted)",
            FinalStatusKind::SkippedBackupExists => "skipped (backup exists)",
        }
    }

    fn is_bailout(self) -> bool {
        matches!(
            self,
            FinalStatusKind::SkippedNested
                | FinalStatusKind::SkippedRewriteAborted
                | FinalStatusKind::SkippedBackupExists
        )
    }
}

fn resolve_jobs(jobs: Option<usize>) -> anyhow::Result<usize> {
    match jobs {
        Some(0) => anyhow::bail!("--jobs must be at least 1"),
        Some(value) => Ok(value),
        None => Ok(std::cmp::max(1, num_cpus::get())),
    }
}

fn execute_parallel_processing<F>(
    candidates: &[Candidate],
    jobs: usize,
    processor: F,
) -> anyhow::Result<Vec<FileResult>>
where
    F: Fn(&Candidate) -> FileResult + Sync,
{
    if candidates.is_empty() {
        return Ok(Vec::new());
    }

    if jobs <= 1 {
        Ok(candidates
            .iter()
            .map(|candidate| processor(candidate))
            .collect())
    } else {
        let pool = ThreadPoolBuilder::new().num_threads(jobs).build()?;
        Ok(pool.install(|| {
            candidates
                .par_iter()
                .map(|candidate| processor(candidate))
                .collect()
        }))
    }
}

fn finalize_file_results(
    results: Vec<FileResult>,
    stats: &mut DirStats,
    input_dir: &Path,
    resolved_out_dir: &Path,
    in_place: bool,
    dry_run: bool,
    backup_ext: Option<&str>,
    quiet: bool,
    show_stats: bool,
    diff: bool,
    diff_context: usize,
) -> anyhow::Result<()> {
    for result in results {
        let candidate = result.candidate;
        match result.outcome {
            FileOutcome::ReadError { message } => {
                stats.errors += 1;
                error!(
                    "failed to read {}: {}",
                    candidate.abs_path.display(),
                    message
                );
                bump_reason(stats, "read_error");
            }
            FileOutcome::PlanError { message } => {
                stats.errors += 1;
                error!(
                    "failed to plan {}: {}",
                    candidate.abs_path.display(),
                    message
                );
                bump_reason(stats, "plan_error");
            }
            FileOutcome::RewriteError { message } => {
                stats.errors += 1;
                error!(
                    "failed to rewrite {}: {}",
                    candidate.abs_path.display(),
                    message
                );
                debug!("• {} → skipped (rewrite error)", candidate.rel_norm);
                bump_reason(stats, "rewrite_error");
            }
            FileOutcome::Minified {
                original,
                rewritten,
                renames,
                metadata,
            } => {
                process_ready_file(
                    candidate,
                    original,
                    Some(rewritten),
                    renames,
                    FinalStatusKind::Minified,
                    stats,
                    input_dir,
                    resolved_out_dir,
                    in_place,
                    dry_run,
                    backup_ext,
                    metadata,
                    quiet,
                    show_stats,
                    diff,
                    diff_context,
                )?;
            }
            FileOutcome::SkippedNoRenames { original, metadata } => {
                process_ready_file(
                    candidate,
                    original,
                    None,
                    0,
                    FinalStatusKind::SkippedNoRenames,
                    stats,
                    input_dir,
                    resolved_out_dir,
                    in_place,
                    dry_run,
                    backup_ext,
                    metadata,
                    quiet,
                    show_stats,
                    diff,
                    diff_context,
                )?;
            }
            FileOutcome::SkippedNested { original, metadata } => {
                process_ready_file(
                    candidate,
                    original,
                    None,
                    0,
                    FinalStatusKind::SkippedNested,
                    stats,
                    input_dir,
                    resolved_out_dir,
                    in_place,
                    dry_run,
                    backup_ext,
                    metadata,
                    quiet,
                    show_stats,
                    diff,
                    diff_context,
                )?;
            }
            FileOutcome::SkippedRewriteAborted { original, metadata } => {
                process_ready_file(
                    candidate,
                    original,
                    None,
                    0,
                    FinalStatusKind::SkippedRewriteAborted,
                    stats,
                    input_dir,
                    resolved_out_dir,
                    in_place,
                    dry_run,
                    backup_ext,
                    metadata,
                    quiet,
                    show_stats,
                    diff,
                    diff_context,
                )?;
            }
        }
    }

    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn process_ready_file(
    candidate: Candidate,
    original: String,
    rewritten: Option<String>,
    renames: usize,
    mut status_kind: FinalStatusKind,
    stats: &mut DirStats,
    input_dir: &Path,
    resolved_out_dir: &Path,
    in_place: bool,
    dry_run: bool,
    backup_ext: Option<&str>,
    metadata: TextMetadata,
    quiet: bool,
    show_stats: bool,
    diff: bool,
    diff_context: usize,
) -> anyhow::Result<()> {
    let mut applied_renames = renames;
    let target_path = if in_place {
        input_dir.join(&candidate.rel_path)
    } else {
        resolved_out_dir.join(&candidate.rel_path)
    };

    if !dry_run {
        if in_place {
            if status_kind == FinalStatusKind::Minified {
                if let Some(ext) = backup_ext {
                    let mut backup_os: OsString = target_path.as_os_str().to_os_string();
                    backup_os.push(ext);
                    let backup_path = PathBuf::from(backup_os);
                    if backup_path.exists() {
                        status_kind = FinalStatusKind::SkippedBackupExists;
                        applied_renames = 0;
                        debug!("• {} → skipped (backup exists)", candidate.rel_norm);
                    } else if let Err(err) = fs::copy(&target_path, &backup_path) {
                        stats.errors += 1;
                        error!("failed to write backup {}: {}", backup_path.display(), err);
                        debug!("• {} → skipped (backup failed)", candidate.rel_norm);
                        bump_reason(stats, "backup_failed");
                        return Ok(());
                    }
                }

                if status_kind == FinalStatusKind::Minified {
                    if let Some(ref content) = rewritten {
                        if let Err(err) = write_python(&target_path, content, &metadata) {
                            stats.errors += 1;
                            error!("failed to write {}: {}", target_path.display(), err);
                            debug!("• {} → skipped (write failed)", candidate.rel_norm);
                            bump_reason(stats, "write_failed");
                            return Ok(());
                        }
                    }
                }
            }
        } else {
            if let Some(parent) = target_path.parent() {
                if let Err(err) = fs::create_dir_all(parent) {
                    stats.errors += 1;
                    error!("failed to create directory {}: {}", parent.display(), err);
                    debug!("• {} → skipped (mkdir failed)", candidate.rel_norm);
                    bump_reason(stats, "mkdir_failed");
                    return Ok(());
                }
            }

            let content = if status_kind == FinalStatusKind::Minified {
                rewritten
                    .as_ref()
                    .map(|s| s.as_str())
                    .unwrap_or_else(|| original.as_str())
            } else {
                original.as_str()
            };

            if let Err(err) = write_python(&target_path, content, &metadata) {
                stats.errors += 1;
                error!("failed to write {}: {}", target_path.display(), err);
                debug!("• {} → skipped (write failed)", candidate.rel_norm);
                bump_reason(stats, "write_failed");
                return Ok(());
            }
        }
    }

    match status_kind {
        FinalStatusKind::Minified => {
            stats.rewritten += 1;
            stats.total_renames += applied_renames;
            bump_reason(stats, "minified");
        }
        FinalStatusKind::SkippedNoRenames => {
            stats.skipped_no_change += 1;
            bump_reason(stats, "no_renames");
        }
        _ => {
            if status_kind.is_bailout() {
                stats.bailouts += 1;
            }
            let reason = match status_kind {
                FinalStatusKind::SkippedNested => "nested_scopes",
                FinalStatusKind::SkippedRewriteAborted => "rewrite_aborted",
                FinalStatusKind::SkippedBackupExists => "backup_exists",
                _ => "unknown",
            };
            if reason != "unknown" {
                bump_reason(stats, reason);
            }
        }
    }

    if show_stats {
        stats.files.push(FileStats {
            path: candidate.rel_norm.clone(),
            renames: applied_renames,
            status: status_kind.label().to_string(),
        });
    }

    if diff && status_kind == FinalStatusKind::Minified && !quiet {
        if let Some(ref new_content) = rewritten {
            let diff_str =
                make_unified_diff(&candidate.rel_norm, &original, new_content, diff_context);
            println!("{}", diff_str);
        }
    }

    print_file_status(
        &candidate.rel_norm,
        status_kind.label(),
        applied_renames,
        show_stats,
        quiet,
    );

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Result as AnyResult;
    use assert_cmd::Command;
    use encoding_rs::Encoding;
    use serde_json;
    #[cfg(unix)]
    use std::os::unix::fs::{symlink, PermissionsExt};
    use std::path::PathBuf;
    use std::process::Command as StdCommand;
    use tempfile::tempdir;

    #[derive(Clone)]
    struct MinifyDirTestCfg {
        in_place: bool,
        dry_run: bool,
        show_stats: bool,
        json_output: bool,
        include_file: Option<PathBuf>,
        include_hidden: bool,
        follow_symlinks: bool,
        glob_case_insensitive: Option<bool>,
        quiet: bool,
        output_json: Option<PathBuf>,
        jobs: Option<usize>,
        fail_on_bailout: bool,
        fail_on_error: bool,
        fail_on_change: bool,
        diff: bool,
        diff_context: usize,
        max_depth: Option<usize>,
        exclude_file: Option<PathBuf>,
        respect_gitignore: bool,
    }

    impl Default for MinifyDirTestCfg {
        fn default() -> Self {
            Self {
                in_place: false,
                dry_run: false,
                show_stats: false,
                json_output: false,
                include_file: None,
                include_hidden: false,
                follow_symlinks: false,
                glob_case_insensitive: None,
                quiet: false,
                output_json: None,
                jobs: None,
                fail_on_bailout: false,
                fail_on_error: false,
                fail_on_change: false,
                diff: false,
                diff_context: 3,
                max_depth: None,
                exclude_file: None,
                respect_gitignore: false,
            }
        }
    }

    #[derive(Clone)]
    struct ApplyPlanDirTestCfg {
        in_place: bool,
        dry_run: bool,
        show_stats: bool,
        json_output: bool,
        include_file: Option<PathBuf>,
        include_hidden: bool,
        follow_symlinks: bool,
        glob_case_insensitive: Option<bool>,
        quiet: bool,
        output_json: Option<PathBuf>,
        jobs: Option<usize>,
        fail_on_bailout: bool,
        fail_on_error: bool,
        fail_on_change: bool,
        diff: bool,
        diff_context: usize,
        max_depth: Option<usize>,
        exclude_file: Option<PathBuf>,
        respect_gitignore: bool,
    }

    impl Default for ApplyPlanDirTestCfg {
        fn default() -> Self {
            Self {
                in_place: false,
                dry_run: false,
                show_stats: false,
                json_output: false,
                include_file: None,
                include_hidden: false,
                follow_symlinks: false,
                glob_case_insensitive: None,
                quiet: false,
                output_json: None,
                jobs: None,
                fail_on_bailout: false,
                fail_on_error: false,
                fail_on_change: false,
                diff: false,
                diff_context: 3,
                max_depth: None,
                exclude_file: None,
                respect_gitignore: false,
            }
        }
    }

    fn run_minify_dir(
        input_dir: &Path,
        out_dir: Option<PathBuf>,
        includes: &[String],
        excludes: &[String],
        backup_ext: Option<&str>,
        cfg: MinifyDirTestCfg,
    ) -> AnyResult<DirStats> {
        minify_dir_with_depth(
            &input_dir.to_path_buf(),
            out_dir,
            includes,
            cfg.include_file.as_ref(),
            excludes,
            cfg.exclude_file.as_ref(),
            backup_ext,
            cfg.in_place,
            cfg.dry_run,
            cfg.show_stats,
            cfg.json_output,
            cfg.include_hidden,
            cfg.follow_symlinks,
            cfg.glob_case_insensitive,
            cfg.quiet,
            cfg.output_json.as_deref(),
            cfg.jobs,
            cfg.fail_on_bailout,
            cfg.fail_on_error,
            cfg.fail_on_change,
            cfg.diff,
            cfg.diff_context,
            cfg.respect_gitignore,
            cfg.max_depth,
            false,
        )
    }

    fn run_apply_plan_dir(
        input_dir: &Path,
        plan_path: &Path,
        out_dir: Option<PathBuf>,
        includes: &[String],
        excludes: &[String],
        backup_ext: Option<&str>,
        cfg: ApplyPlanDirTestCfg,
    ) -> AnyResult<DirStats> {
        apply_plan_dir_with_depth(
            &input_dir.to_path_buf(),
            &plan_path.to_path_buf(),
            out_dir,
            includes,
            cfg.include_file.as_ref(),
            excludes,
            cfg.exclude_file.as_ref(),
            backup_ext,
            cfg.in_place,
            cfg.dry_run,
            cfg.show_stats,
            cfg.json_output,
            cfg.include_hidden,
            cfg.follow_symlinks,
            cfg.glob_case_insensitive,
            cfg.quiet,
            cfg.output_json.as_deref(),
            cfg.jobs,
            cfg.fail_on_bailout,
            cfg.fail_on_error,
            cfg.fail_on_change,
            cfg.diff,
            cfg.diff_context,
            cfg.respect_gitignore,
            cfg.max_depth,
        )
    }

    fn create_nested_fixture(base: &Path) -> AnyResult<()> {
        fs::create_dir_all(base)?;
        fs::write(base.join("root.py"), "def root():\n    return 1\n")?;
        let level1 = base.join("level1");
        fs::create_dir_all(&level1)?;
        fs::write(level1.join("inner.py"), "def inner():\n    return 2\n")?;
        let level2 = level1.join("level2");
        fs::create_dir_all(&level2)?;
        fs::write(level2.join("deep.py"), "def deep():\n    return 3\n")?;
        Ok(())
    }

    fn cli_cmd() -> AnyResult<Command> {
        Ok(Command::from_std(StdCommand::new(cli_binary_path())))
    }

    fn cli_binary_path() -> PathBuf {
        if let Some(path) = std::env::var_os("CARGO_BIN_EXE_tsrs-cli") {
            return PathBuf::from(path);
        }

        let mut target_dir = std::env::var_os("CARGO_TARGET_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target"));

        let profile = std::env::var("PROFILE").unwrap_or_else(|_| "debug".to_string());
        target_dir.push(profile);
        let binary = if cfg!(windows) {
            "tsrs-cli.exe"
        } else {
            "tsrs-cli"
        };
        target_dir.push(binary);
        target_dir
    }

    #[test]
    fn unified_diff_smoke() {
        let diff = make_unified_diff("example.py", "a = 1\n", "a = 2\n", 3);
        assert!(diff.contains("a/example.py"));
        assert!(diff.contains("b/example.py"));
        assert!(diff.contains("-a = 1"));
        assert!(diff.contains("+a = 2"));
    }

    #[test]
    fn unified_diff_context_zero() {
        let diff = make_unified_diff("example.py", "a = 1\nprint(a)\n", "a = 2\nprint(a)\n", 0);
        assert!(diff.contains("@@"));
        let context_lines = diff.lines().filter(|line| line.starts_with(' ')).count();
        assert_eq!(context_lines, 0, "unexpected context lines: {diff}");
    }

    #[test]
    fn minify_dir_diff_context_one_outputs_expected() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\nprint(\"done\")\n",
        )?;

        let out_dir = tmp.path().join("out");

        let output = cli_cmd()?
            .arg("minify-dir")
            .arg(input_dir.to_str().unwrap())
            .arg("--out-dir")
            .arg(out_dir.to_str().unwrap())
            .arg("--diff")
            .arg("--diff-context")
            .arg("1")
            .arg("--dry-run")
            .output()?;

        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        let context_lines = stdout.lines().filter(|line| line.starts_with(' ')).count();
        assert_eq!(context_lines, 1, "unexpected context lines: {stdout}");
        Ok(())
    }

    #[test]
    fn glob_case_insensitive_matches_uppercase() -> AnyResult<()> {
        let set = build_globset(&["a*.py".to_string()], true)?;
        assert!(set.is_match("A.py"));
        Ok(())
    }

    #[cfg(windows)]
    #[test]
    fn default_glob_matching_is_case_insensitive_on_windows() -> AnyResult<()> {
        let set = build_globset(&["a*.py".to_string()], cfg!(windows))?;
        assert!(set.is_match("A.py"));
        Ok(())
    }

    #[cfg(not(windows))]
    #[test]
    fn glob_matching_requires_opt_in_for_case_insensitivity_on_unix() -> AnyResult<()> {
        let set = build_globset(&["a*.py".to_string()], false)?;
        assert!(!set.is_match("A.py"));

        let insensitive = build_globset(&["a*.py".to_string()], true)?;
        assert!(insensitive.is_match("A.py"));
        Ok(())
    }

    #[test]
    fn minify_dir_preserves_structure() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("input");
        let nested = input_dir.join("pkg");
        fs::create_dir_all(&nested)?;

        let module_source = "\
def sample(value):
    temp = value + 1
    return temp
";
        fs::write(input_dir.join("module.py"), module_source)?;
        fs::write(nested.join("__init__.py"), "")?;

        let output_dir = tmp.path().join("output");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(
            &input_dir,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        let rewritten = fs::read_to_string(output_dir.join("module.py"))?;
        assert!(rewritten.contains("def sample(a):"));
        assert!(output_dir.join("pkg/__init__.py").exists());
        Ok(())
    }

    #[test]
    fn minify_dir_respects_include_exclude() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        let pkg_a = input_dir.join("pkg_a");
        let pkg_b = input_dir.join("pkg_b");
        fs::create_dir_all(&pkg_a)?;
        fs::create_dir_all(&pkg_b)?;

        fs::write(
            pkg_a.join("mod.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;
        fs::write(
            pkg_b.join("mod.py"),
            "def bar(y):\n    z = y - 1\n    return z\n",
        )?;

        let output_dir = tmp.path().join("out");
        let includes = vec!["pkg_a/**".to_string()];
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(
            &input_dir,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        assert!(output_dir.join("pkg_a/mod.py").exists());
        assert!(!output_dir.join("pkg_b/mod.py").exists());
        Ok(())
    }

    #[test]
    fn minify_dir_dry_run_creates_no_output() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            dry_run: true,
            show_stats: true,
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(
            &input_dir,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        assert!(!output_dir.exists());
        Ok(())
    }

    #[test]
    fn minify_dir_in_place_updates_files() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        let file_path = input_dir.join("example.py");
        fs::write(
            &file_path,
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            in_place: true,
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(&input_dir, None, &includes, &excludes, None, cfg)?;

        let rewritten = fs::read_to_string(&file_path)?;
        assert!(rewritten.contains("def foo(a):"));
        Ok(())
    }

    #[test]
    fn minify_dir_in_place_writes_backup() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        let file_path = input_dir.join("example.py");
        let original = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, original)?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            in_place: true,
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(&input_dir, None, &includes, &excludes, Some(".bak"), cfg)?;

        let rewritten = fs::read_to_string(&file_path)?;
        assert!(rewritten.contains("def foo(a):"));

        let backup_path = input_dir.join("example.py.bak");
        assert!(backup_path.exists());
        let backup_contents = fs::read_to_string(backup_path)?;
        assert_eq!(backup_contents, original);

        Ok(())
    }

    #[test]
    fn minify_dir_stats_json_runs() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            dry_run: true,
            show_stats: true,
            json_output: true,
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(
            &input_dir,
            Some(output_dir),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        Ok(())
    }

    #[test]
    fn minify_dir_skips_hidden_by_default() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join(".hidden.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(
            &input_dir,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        assert!(!output_dir.join(".hidden.py").exists());
        Ok(())
    }

    #[test]
    fn minify_dir_includes_hidden_when_requested() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join(".hidden.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            include_hidden: true,
            quiet: true,
            ..Default::default()
        };
        let _stats = run_minify_dir(
            &input_dir,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        assert!(output_dir.join(".hidden.py").exists());
        Ok(())
    }

    #[test]
    fn minify_dir_respects_max_depth() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        create_nested_fixture(&input_dir)?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();

        let cfg_depth1 = MinifyDirTestCfg {
            quiet: true,
            max_depth: Some(1),
            ..Default::default()
        };
        let stats_depth1 = run_minify_dir(
            &input_dir,
            Some(tmp.path().join("min-out-depth1")),
            &includes,
            &excludes,
            None,
            cfg_depth1,
        )?;
        assert_eq!(stats_depth1.processed, 1);

        let cfg_depth2 = MinifyDirTestCfg {
            quiet: true,
            max_depth: Some(2),
            ..Default::default()
        };
        let stats_depth2 = run_minify_dir(
            &input_dir,
            Some(tmp.path().join("min-out-depth2")),
            &includes,
            &excludes,
            None,
            cfg_depth2,
        )?;
        assert_eq!(stats_depth2.processed, 2);

        Ok(())
    }

    #[test]
    fn minify_dir_respects_gitignore() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join(".gitignore"), "alpha.py\n")?;
        fs::write(
            input_dir.join("alpha.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;
        fs::write(
            input_dir.join("beta.py"),
            "def bar(value):\n    temp = value + 2\n    return temp\n",
        )?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();

        let cfg_all = MinifyDirTestCfg {
            in_place: true,
            dry_run: true,
            quiet: true,
            ..Default::default()
        };
        let stats_all = run_minify_dir(&input_dir, None, &includes, &excludes, None, cfg_all)?;
        assert_eq!(stats_all.processed, 2);

        let cfg_respect = MinifyDirTestCfg {
            in_place: true,
            dry_run: true,
            quiet: true,
            respect_gitignore: true,
            ..Default::default()
        };
        let stats_respected =
            run_minify_dir(&input_dir, None, &includes, &excludes, None, cfg_respect)?;
        assert_eq!(stats_respected.processed, 1);
        assert_eq!(stats_respected.rewritten, 1);
        Ok(())
    }

    #[test]
    fn minify_dir_include_exclude_precedence_exclude_wins() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join("alpha.py"), "def foo():\n    return 1\n")?;
        fs::write(input_dir.join("beta.py"), "def bar():\n    return 2\n")?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &["*.py".to_string()],
            None,
            &["alpha*.py".to_string()],
            None,
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;

        let bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        let paths: Vec<String> = bundle.files.into_iter().map(|f| f.path).collect();
        assert_eq!(paths, vec!["beta.py".to_string()]);
        Ok(())
    }

    #[test]
    fn minify_dir_pattern_files_respected() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("alpha.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;
        fs::write(
            input_dir.join("beta.py"),
            "def bar(value):\n    temp = value + 2\n    return temp\n",
        )?;

        let include_file = tmp.path().join("includes.txt");
        fs::write(&include_file, "*.py\n")?;
        let exclude_file = tmp.path().join("excludes.txt");
        fs::write(&exclude_file, "alpha*.py\n")?;

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            include_file: Some(include_file.clone()),
            exclude_file: Some(exclude_file.clone()),
            quiet: true,
            ..Default::default()
        };

        let stats = run_minify_dir(
            &input_dir,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        assert_eq!(stats.processed, 1);
        assert!(output_dir.join("beta.py").exists());
        assert!(!output_dir.join("alpha.py").exists());
        Ok(())
    }

    #[test]
    fn minify_file_output_json_writes_file() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(
            &file_path,
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let json_path = tmp.path().join("file.json");
        let (stats, _) = minify_file(
            &file_path,
            false,
            false,
            None,
            false,
            false,
            true,
            Some(json_path.as_path()),
            false,
            false,
            false,
            false,
            3,
            false,
        )?;

        let written: DirStats = serde_json::from_str(&fs::read_to_string(&json_path)?)?;
        assert_eq!(written.processed, stats.processed);
        assert_eq!(written.rewritten, stats.rewritten);
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn minify_file_output_json_unwritable_parent_fails() -> AnyResult<()> {
        use std::os::unix::fs::PermissionsExt;

        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(
            &file_path,
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let reports_dir = tmp.path().join("reports");
        fs::create_dir(&reports_dir)?;
        let mut perms = fs::metadata(&reports_dir)?.permissions();
        perms.set_mode(0o500);
        fs::set_permissions(&reports_dir, perms.clone())?;

        let output = cli_cmd()?
            .arg("minify")
            .arg(file_path.to_str().unwrap())
            .arg("--stats")
            .arg("--output-json")
            .arg(reports_dir.join("minify.json").to_str().unwrap())
            .output()?;

        perms.set_mode(0o700);
        fs::set_permissions(&reports_dir, perms)?;

        assert!(!output.status.success());
        assert!(!reports_dir.join("minify.json").exists());
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn minify_dir_output_json_unwritable_parent_fails() -> AnyResult<()> {
        use std::os::unix::fs::PermissionsExt;

        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let reports_dir = tmp.path().join("reports");
        fs::create_dir(&reports_dir)?;
        let mut perms = fs::metadata(&reports_dir)?.permissions();
        perms.set_mode(0o555);
        fs::set_permissions(&reports_dir, perms.clone())?;

        let out_dir = tmp.path().join("out");
        let output = cli_cmd()?
            .arg("minify-dir")
            .arg(input_dir.to_str().unwrap())
            .arg("--out-dir")
            .arg(out_dir.to_str().unwrap())
            .arg("--stats")
            .arg("--output-json")
            .arg(reports_dir.join("minify-dir.json").to_str().unwrap())
            .output()?;

        perms.set_mode(0o755);
        fs::set_permissions(&reports_dir, perms)?;

        assert!(!output.status.success());
        assert!(!reports_dir.join("minify-dir.json").exists());
        Ok(())
    }

    #[test]
    fn minify_cli_output_json_writes_file() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(
            &file_path,
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let json_path = tmp.path().join("cli.json");
        let (stats, _) = minify(
            &file_path,
            false,
            false,
            None,
            false,
            false,
            true,
            Some(json_path.as_path()),
            false,
            false,
            false,
            false,
            3,
            false,
        )?;

        let written: DirStats = serde_json::from_str(&fs::read_to_string(&json_path)?)?;
        assert_eq!(written.processed, stats.processed);
        assert_eq!(written.rewritten, stats.rewritten);
        Ok(())
    }

    #[test]
    fn minify_cli_dry_run_no_write() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let original = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, original)?;

        let output = cli_cmd()?
            .arg("minify")
            .arg(file_path.to_str().unwrap())
            .arg("--in-place")
            .arg("--dry-run")
            .output()?;
        assert!(output.status.success());

        let after = fs::read_to_string(&file_path)?;
        assert_eq!(after, original);
        Ok(())
    }

    #[test]
    fn minify_file_fail_on_change_exits_nonzero() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(
            &file_path,
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let output = cli_cmd()?
            .arg("minify")
            .arg(file_path.to_str().unwrap())
            .arg("--fail-on-change")
            .output()?;
        assert!(!output.status.success());
        assert_eq!(output.status.code(), Some(4));
        Ok(())
    }

    #[test]
    fn minify_file_fail_on_bailout_exits_nonzero() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(
            &file_path,
            "def foo(values):\n    squared = [v * v for v in values]\n    return squared\n",
        )?;

        let output = cli_cmd()?
            .arg("minify")
            .arg(file_path.to_str().unwrap())
            .arg("--fail-on-bailout")
            .output()?;

        assert!(!output.status.success());
        assert_eq!(output.status.code(), Some(2));
        Ok(())
    }

    #[test]
    #[cfg(unix)]
    fn minify_file_fail_on_error_exits_nonzero() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(
            &file_path,
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;
        let mut perms = fs::metadata(&file_path)?.permissions();
        let mut readonly = perms.clone();
        readonly.set_mode(0o444);
        fs::set_permissions(&file_path, readonly)?;

        let output = cli_cmd()?
            .arg("minify")
            .arg(file_path.to_str().unwrap())
            .arg("--in-place")
            .arg("--fail-on-error")
            .output()?;

        perms.set_mode(0o644);
        fs::set_permissions(&file_path, perms)?;

        assert!(!output.status.success());
        assert_eq!(output.status.code(), Some(1));
        Ok(())
    }

    #[test]
    fn minify_stdin_stdout_rewrites() -> AnyResult<()> {
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";

        let output = cli_cmd()?
            .arg("minify")
            .arg("stdin.py")
            .arg("--stdin")
            .arg("--stdout")
            .write_stdin(source)
            .output()?;

        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        assert!(stdout.contains("def foo(a):"));
        assert!(!stdout.contains("value"));
        assert!(!stdout.contains("Processed"));
        Ok(())
    }

    #[test]
    fn minify_file_reasons_noop() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(&file_path, "def foo():\n    return 42\n")?;

        let json_path = tmp.path().join("reasons.json");
        let (stats, _) = minify_file(
            &file_path,
            false,
            false,
            None,
            false,
            false,
            true,
            Some(json_path.as_path()),
            false,
            false,
            false,
            false,
            3,
            false,
        )?;

        assert_eq!(stats.reasons.get("no_renames"), Some(&1));

        let written: DirStats = serde_json::from_str(&fs::read_to_string(&json_path)?)?;
        assert_eq!(written.reasons.get("no_renames"), Some(&1));

        Ok(())
    }

    #[test]
    fn minify_file_preserves_encoding_cookie() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("latin.py");
        let source = "# -*- coding: latin-1 -*-\n\nmsg = \"café\"\n\ndef foo(value):\n    temp = value + 1\n    return msg\n";
        let encoding = Encoding::for_label(b"iso-8859-1").expect("latin-1 encoding");
        let (encoded, output_enc, had_errors) = encoding.encode(source);
        assert!(!had_errors);
        assert!(std::ptr::eq(output_enc, encoding));
        match encoded {
            Cow::Borrowed(bytes) => fs::write(&file_path, bytes)?,
            Cow::Owned(buffer) => fs::write(&file_path, buffer)?,
        }

        let (stats, _) = minify_file(
            &file_path, true, false, None, false, false, true, None, false, false, false, false, 3,
            false,
        )?;
        assert_eq!(stats.rewritten, 1);

        let bytes_after = fs::read(&file_path)?;
        let (decoded, had_decode_errors) = encoding.decode_without_bom_handling(&bytes_after);
        assert!(!had_decode_errors);
        let text = decoded.into_owned();
        assert!(text.lines().next().unwrap().contains("coding: latin-1"));
        assert!(text.contains("café"));

        Ok(())
    }

    #[test]
    fn minify_file_preserves_utf8_bom() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("bom.py");
        let source = b"\xEF\xBB\xBFdef foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let (_stats, _) = minify_file(
            &file_path, true, false, None, false, false, true, None, false, false, false, false, 3,
            false,
        )?;

        let bytes_after = fs::read(&file_path)?;
        assert!(bytes_after.starts_with(b"\xEF\xBB\xBF"));

        let text = String::from_utf8(bytes_after[3..].to_vec())?;
        assert!(text.contains("def foo(a):"));

        Ok(())
    }

    #[test]
    fn minify_file_preserves_utf16le_bom() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("bom_le.py");
        let utf16: Vec<u8> = {
            let mut bytes = vec![0xFF, 0xFE];
            let content = "def foo(value):\r\n    temp = value + 1\r\n    return temp\r\n";
            for unit in content.encode_utf16() {
                bytes.extend_from_slice(&unit.to_le_bytes());
            }
            bytes
        };
        fs::write(&file_path, &utf16)?;

        let (_stats, _) = minify_file(
            &file_path, true, false, None, false, false, true, None, false, false, false, false, 3,
            false,
        )?;

        let bytes_after = fs::read(&file_path)?;
        assert!(bytes_after.starts_with(&[0xFF, 0xFE]));
        let decoded = UTF_16LE
            .decode_without_bom_handling(&bytes_after)
            .0
            .into_owned();
        assert!(decoded.contains("def foo(a):"));

        Ok(())
    }

    #[test]
    fn minify_file_preserves_utf16be_bom() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("bom_be.py");
        let utf16: Vec<u8> = {
            let mut bytes = vec![0xFE, 0xFF];
            let content = "def foo(value):\n    temp = value + 1\n    return temp\n";
            for unit in content.encode_utf16() {
                let be = unit.to_be_bytes();
                bytes.extend_from_slice(&be);
            }
            bytes
        };
        fs::write(&file_path, &utf16)?;

        let (_stats, _) = minify_file(
            &file_path, true, false, None, false, false, true, None, false, false, false, false, 3,
            false,
        )?;

        let bytes_after = fs::read(&file_path)?;
        assert!(bytes_after.starts_with(&[0xFE, 0xFF]));
        let decoded = UTF_16BE
            .decode_without_bom_handling(&bytes_after)
            .0
            .into_owned();
        assert!(decoded.contains("def foo(a):"));

        Ok(())
    }

    #[test]
    fn minify_dir_preserves_utf8_bom_and_crlf() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;

        let mut bytes = b"\xEF\xBB\xBF".to_vec();
        bytes.extend_from_slice(b"def foo(value):\r\n    temp = value + 1\r\n    return temp\r\n");
        fs::write(input_dir.join("example.py"), bytes)?;

        let out_dir = tmp.path().join("out");
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let stats = run_minify_dir(&input_dir, Some(out_dir.clone()), &[], &[], None, cfg)?;
        assert_eq!(stats.rewritten, 1);

        let output_bytes = fs::read(out_dir.join("example.py"))?;
        assert!(output_bytes.starts_with(b"\xEF\xBB\xBF"));
        assert!(output_bytes.windows(2).any(|w| w == b"\r\n"));
        let decoded = String::from_utf8(output_bytes[3..].to_vec())?;
        assert!(decoded.contains("def foo(a):"));
        Ok(())
    }

    #[test]
    fn minify_dir_preserves_utf16le_bom_and_crlf() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;

        let mut bytes = vec![0xFF, 0xFE];
        let content = "def foo(value):\r\n    temp = value + 1\r\n    return temp\r\n";
        for unit in content.encode_utf16() {
            bytes.extend_from_slice(&unit.to_le_bytes());
        }
        fs::write(input_dir.join("example.py"), &bytes)?;

        let out_dir = tmp.path().join("out");
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let stats = run_minify_dir(&input_dir, Some(out_dir.clone()), &[], &[], None, cfg)?;
        assert_eq!(stats.rewritten, 1);

        let output_bytes = fs::read(out_dir.join("example.py"))?;
        assert!(output_bytes.starts_with(&[0xFF, 0xFE]));
        assert!(output_bytes
            .windows(4)
            .any(|w| w == [0x0D, 0x00, 0x0A, 0x00]));
        let decoded = UTF_16LE
            .decode_without_bom_handling(&output_bytes)
            .0
            .into_owned();
        assert!(decoded.contains("def foo(a):"));
        Ok(())
    }

    #[test]
    fn apply_plan_dir_preserves_bom_and_crlf() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;

        let mut utf8_bom = b"\xEF\xBB\xBF".to_vec();
        utf8_bom
            .extend_from_slice(b"def foo(value):\r\n    temp = value + 1\r\n    return temp\r\n");
        fs::write(input_dir.join("utf8.py"), utf8_bom)?;

        let mut utf16le_bom = vec![0xFF, 0xFE];
        let utf16_content = "def bar(value):\r\n    temp = value + 2\r\n    return temp\r\n";
        for unit in utf16_content.encode_utf16() {
            utf16le_bom.extend_from_slice(&unit.to_le_bytes());
        }
        fs::write(input_dir.join("utf16.py"), &utf16le_bom)?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;

        let out_dir = tmp.path().join("out");
        let cfg = ApplyPlanDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let stats = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(out_dir.clone()),
            &[],
            &[],
            None,
            cfg,
        )?;
        assert_eq!(stats.rewritten, 2);

        let utf8_bytes = fs::read(out_dir.join("utf8.py"))?;
        assert!(utf8_bytes.starts_with(b"\xEF\xBB\xBF"));
        assert!(utf8_bytes.windows(2).any(|w| w == b"\r\n"));
        let utf8_decoded = String::from_utf8(utf8_bytes[3..].to_vec())?;
        assert!(utf8_decoded.contains("def foo(a):"));

        let utf16_bytes = fs::read(out_dir.join("utf16.py"))?;
        assert!(utf16_bytes.starts_with(&[0xFF, 0xFE]));
        assert!(utf16_bytes
            .windows(4)
            .any(|w| w == [0x0D, 0x00, 0x0A, 0x00]));
        let utf16_decoded = UTF_16LE
            .decode_without_bom_handling(&utf16_bytes)
            .0
            .into_owned();
        assert!(utf16_decoded.contains("def bar(a):"));
        Ok(())
    }

    #[test]
    fn preserves_crlf_after_rewrite() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("crlf.py");
        let source = "def foo(value):\r\n    temp = value + 1\r\n    return temp\r\n";
        fs::write(&file_path, source)?;

        let _ = minify_file(
            &file_path, true, false, None, false, false, true, None, false, false, false, false, 3,
            false,
        )?;

        let bytes_after = fs::read(&file_path)?;
        for (idx, byte) in bytes_after.iter().enumerate() {
            if *byte == b'\n' {
                assert!(idx > 0 && bytes_after[idx - 1] == b'\r');
            }
        }

        Ok(())
    }

    #[test]
    fn preserves_missing_final_newline() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("no_newline.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp";
        fs::write(&file_path, source)?;

        let _ = minify_file(
            &file_path, true, false, None, false, false, true, None, false, false, false, false, 3,
            false,
        )?;

        let bytes_after = fs::read(&file_path)?;
        if let Some(last) = bytes_after.last() {
            assert!(*last != b'\n' && *last != b'\r');
        }

        Ok(())
    }

    #[test]
    fn minify_dir_output_json_writes_file() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let output_dir = tmp.path().join("out");
        let json_path = tmp.path().join("dir.json");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            quiet: true,
            output_json: Some(json_path.clone()),
            ..Default::default()
        };
        let stats = run_minify_dir(
            &input_dir,
            Some(output_dir),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        let written: DirStats = serde_json::from_str(&fs::read_to_string(&json_path)?)?;
        assert_eq!(written.processed, stats.processed);
        assert_eq!(written.rewritten, stats.rewritten);
        Ok(())
    }

    #[test]
    fn apply_plan_file_output_json_writes_file() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let module_name = "example";
        let plan = Minifier::plan_from_source(module_name, source)?;
        let plan_path = tmp.path().join("plan.json");
        fs::write(&plan_path, serde_json::to_string(&plan)?)?;

        let json_path = tmp.path().join("apply.json");
        let (stats, _) = apply_plan(
            &file_path,
            &plan_path,
            false,
            false,
            None,
            false,
            false,
            true,
            Some(json_path.as_path()),
            false,
            false,
            false,
            false,
            3,
            false,
        )?;

        let written: DirStats = serde_json::from_str(&fs::read_to_string(&json_path)?)?;
        assert_eq!(written.processed, stats.processed);
        assert_eq!(written.rewritten, stats.rewritten);
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn apply_plan_file_output_json_unwritable_parent_fails() -> AnyResult<()> {
        use std::os::unix::fs::PermissionsExt;

        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let plan = Minifier::plan_from_source("example", source)?;
        let plan_path = tmp.path().join("plan.json");
        fs::write(&plan_path, serde_json::to_string(&plan)?)?;

        let reports_dir = tmp.path().join("reports");
        fs::create_dir(&reports_dir)?;
        let mut perms = fs::metadata(&reports_dir)?.permissions();
        perms.set_mode(0o500);
        fs::set_permissions(&reports_dir, perms.clone())?;

        let output = cli_cmd()?
            .arg("apply-plan")
            .arg(file_path.to_str().unwrap())
            .arg("--plan")
            .arg(plan_path.to_str().unwrap())
            .arg("--stats")
            .arg("--output-json")
            .arg(reports_dir.join("apply.json").to_str().unwrap())
            .output()?;

        perms.set_mode(0o700);
        fs::set_permissions(&reports_dir, perms)?;

        assert!(!output.status.success());
        assert!(!reports_dir.join("apply.json").exists());
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn apply_plan_dir_output_json_unwritable_parent_fails() -> AnyResult<()> {
        use std::os::unix::fs::PermissionsExt;

        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;

        let reports_dir = tmp.path().join("reports");
        fs::create_dir(&reports_dir)?;
        let mut perms = fs::metadata(&reports_dir)?.permissions();
        perms.set_mode(0o555);
        fs::set_permissions(&reports_dir, perms.clone())?;

        let out_dir = tmp.path().join("out");
        let output = cli_cmd()?
            .arg("apply-plan-dir")
            .arg(input_dir.to_str().unwrap())
            .arg("--plan")
            .arg(plan_path.to_str().unwrap())
            .arg("--out-dir")
            .arg(out_dir.to_str().unwrap())
            .arg("--stats")
            .arg("--output-json")
            .arg(reports_dir.join("apply-dir.json").to_str().unwrap())
            .output()?;

        perms.set_mode(0o755);
        fs::set_permissions(&reports_dir, perms)?;

        assert!(!output.status.success());
        assert!(!reports_dir.join("apply-dir.json").exists());
        Ok(())
    }

    #[test]
    fn apply_plan_stdin_and_plan_stdin_pipe() -> AnyResult<()> {
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        let plan = Minifier::plan_from_source("stdin", source)?;
        let plan_json = serde_json::to_string(&plan)?;
        let combined = format!("{source}\n{plan_json}");

        let output = cli_cmd()?
            .arg("apply-plan")
            .arg("stdin.py")
            .arg("--stdin")
            .arg("--plan-stdin")
            .write_stdin(combined)
            .output()?;

        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        assert!(stdout.contains("def foo(a):"));
        Ok(())
    }

    #[test]
    fn apply_plan_file_reads_plan_from_dash() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let plan = Minifier::plan_from_source("example", source)?;
        let plan_json = serde_json::to_string(&plan)?;

        let output = cli_cmd()?
            .arg("apply-plan")
            .arg(file_path.to_str().unwrap())
            .arg("--plan")
            .arg("-")
            .write_stdin(plan_json)
            .output()?;

        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        assert!(stdout.contains("def foo(a):"));
        Ok(())
    }

    #[test]
    fn apply_plan_file_fail_on_change_exits_nonzero() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let plan = Minifier::plan_from_source("module", source)?;
        let plan_path = tmp.path().join("plan.json");
        fs::write(&plan_path, serde_json::to_string(&plan)?)?;

        let output = cli_cmd()?
            .arg("apply-plan")
            .arg(file_path.to_str().unwrap())
            .arg("--plan")
            .arg(plan_path.to_str().unwrap())
            .arg("--fail-on-change")
            .output()?;

        assert!(!output.status.success());
        assert_eq!(output.status.code(), Some(4));
        Ok(())
    }

    #[test]
    fn apply_plan_cli_dry_run_no_write() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let plan = Minifier::plan_from_source("module", source)?;
        let plan_path = tmp.path().join("plan.json");
        fs::write(&plan_path, serde_json::to_string(&plan)?)?;

        let output = cli_cmd()?
            .arg("apply-plan")
            .arg(file_path.to_str().unwrap())
            .arg("--plan")
            .arg(plan_path.to_str().unwrap())
            .arg("--in-place")
            .arg("--dry-run")
            .output()?;
        assert!(output.status.success());

        let after = fs::read_to_string(&file_path)?;
        assert_eq!(after, source);
        Ok(())
    }

    #[test]
    fn apply_plan_stdin_stdout_rewrites() -> AnyResult<()> {
        let tmp = tempdir()?;
        let plan_path = tmp.path().join("plan.json");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        let plan = Minifier::plan_from_source("module", source)?;
        fs::write(&plan_path, serde_json::to_string(&plan)?)?;

        let output = cli_cmd()?
            .arg("apply-plan")
            .arg("stdin.py")
            .arg("--plan")
            .arg(plan_path.to_str().unwrap())
            .arg("--stdin")
            .arg("--stdout")
            .write_stdin(source)
            .output()?;

        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        assert!(stdout.contains("def foo(a):"));
        assert!(!stdout.contains("value"));
        assert!(!stdout.contains("Processed"));
        Ok(())
    }

    #[test]
    fn minify_dir_rejects_output_inside_input() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let out_dir = input_dir.join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let err = run_minify_dir(&input_dir, Some(out_dir), &includes, &excludes, None, cfg)
            .expect_err("out dir under input should error");
        let message = err.to_string();
        assert!(
            message.contains("--out-dir cannot be inside the input directory"),
            "unexpected error: {}",
            message
        );
        Ok(())
    }

    #[test]
    fn minify_dir_rejects_output_inside_input_with_parent_segments() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let out_dir = input_dir.join("..").join("src").join("nested");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let err = run_minify_dir(&input_dir, Some(out_dir), &includes, &excludes, None, cfg)
            .expect_err("out dir with parent segments should error");
        assert!(err
            .to_string()
            .contains("--out-dir cannot be inside the input directory"));
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn minify_dir_rejects_output_inside_input_via_symlink() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        let nested = input_dir.join("nested");
        fs::create_dir_all(&nested)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let alias = tmp.path().join("alias");
        symlink(&nested, &alias)?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = MinifyDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let err = run_minify_dir(&input_dir, Some(alias), &includes, &excludes, None, cfg)
            .expect_err("symlinked out dir should error");
        assert!(err
            .to_string()
            .contains("--out-dir cannot be inside the input directory"));
        Ok(())
    }

    #[test]
    fn apply_plan_dir_output_json_writes_file() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;
        assert!(plan_path.exists());

        let output_dir = tmp.path().join("out");
        let json_path = tmp.path().join("apply-dir.json");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = ApplyPlanDirTestCfg {
            quiet: true,
            output_json: Some(json_path.clone()),
            ..Default::default()
        };
        let stats = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(output_dir),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        let written: DirStats = serde_json::from_str(&fs::read_to_string(&json_path)?)?;
        assert_eq!(written.processed, stats.processed);
        assert_eq!(written.rewritten, stats.rewritten);
        Ok(())
    }

    #[test]
    fn minify_plan_dir_respects_max_depth() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        create_nested_fixture(&input_dir)?;

        let plan_depth1 = tmp.path().join("plan-depth1.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_depth1,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            Some(1),
            false,
            true,
        )?;
        let bundle1: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_depth1)?)?;
        let paths1: Vec<String> = bundle1.files.iter().map(|f| f.path.clone()).collect();
        assert_eq!(paths1, vec!["root.py".to_string()]);

        let plan_depth2 = tmp.path().join("plan-depth2.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_depth2,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            Some(2),
            false,
            true,
        )?;
        let mut paths2: Vec<String> =
            serde_json::from_str::<PlanBundle>(&fs::read_to_string(&plan_depth2)?)?
                .files
                .into_iter()
                .map(|f| f.path)
                .collect();
        paths2.sort();
        assert_eq!(
            paths2,
            vec!["level1/inner.py".to_string(), "root.py".to_string()]
        );
        Ok(())
    }

    #[test]
    fn apply_plan_dir_rejects_output_inside_input() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let out_dir = input_dir.join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = ApplyPlanDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let err = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(out_dir),
            &includes,
            &excludes,
            None,
            cfg,
        )
        .expect_err("out dir under input should error");
        let message = err.to_string();
        assert!(
            message.contains("--out-dir cannot be inside the input directory"),
            "unexpected error: {}",
            message
        );
        Ok(())
    }

    #[test]
    fn apply_plan_dir_rejects_output_inside_input_with_parent_segments() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let out_dir = input_dir.join("..").join("src").join("mirror");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = ApplyPlanDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let err = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(out_dir),
            &includes,
            &excludes,
            None,
            cfg,
        )
        .expect_err("out dir with parent segments should error");
        assert!(err
            .to_string()
            .contains("--out-dir cannot be inside the input directory"));
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn apply_plan_dir_rejects_output_inside_input_via_symlink() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        let nested = input_dir.join("nested");
        fs::create_dir_all(&nested)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let alias = tmp.path().join("alias");
        symlink(&nested, &alias)?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = ApplyPlanDirTestCfg {
            quiet: true,
            ..Default::default()
        };
        let err = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(alias),
            &includes,
            &excludes,
            None,
            cfg,
        )
        .expect_err("symlinked out dir should error");
        assert!(err
            .to_string()
            .contains("--out-dir cannot be inside the input directory"));
        Ok(())
    }

    #[test]
    fn apply_plan_dir_pattern_files_respected() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("alpha.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;
        fs::write(
            input_dir.join("beta.py"),
            "def bar(value):\n    temp = value + 2\n    return temp\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;

        let include_file = tmp.path().join("includes.txt");
        fs::write(&include_file, "*.py\n")?;
        let exclude_file = tmp.path().join("excludes.txt");
        fs::write(&exclude_file, "alpha*.py\n")?;

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = ApplyPlanDirTestCfg {
            include_file: Some(include_file.clone()),
            exclude_file: Some(exclude_file.clone()),
            quiet: true,
            ..Default::default()
        };

        let stats = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        assert_eq!(stats.processed, 1);
        assert!(output_dir.join("beta.py").exists());
        assert!(!output_dir.join("alpha.py").exists());
        Ok(())
    }

    #[test]
    fn apply_plan_dir_respects_max_depth() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        create_nested_fixture(&input_dir)?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();

        let cfg_depth1 = ApplyPlanDirTestCfg {
            quiet: true,
            max_depth: Some(1),
            ..Default::default()
        };
        let stats_depth1 = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(tmp.path().join("apply-out-depth1")),
            &includes,
            &excludes,
            None,
            cfg_depth1,
        )?;
        assert_eq!(stats_depth1.processed, 1);

        let cfg_depth2 = ApplyPlanDirTestCfg {
            quiet: true,
            max_depth: Some(2),
            ..Default::default()
        };
        let stats_depth2 = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(tmp.path().join("apply-out-depth2")),
            &includes,
            &excludes,
            None,
            cfg_depth2,
        )?;
        assert_eq!(stats_depth2.processed, 2);

        Ok(())
    }

    #[test]
    fn apply_plan_dir_respects_gitignore() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join(".gitignore"), "alpha.py\n")?;
        fs::write(
            input_dir.join("alpha.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;
        fs::write(
            input_dir.join("beta.py"),
            "def bar(value):\n    temp = value + 2\n    return temp\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;

        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();

        let cfg_all = ApplyPlanDirTestCfg {
            in_place: true,
            dry_run: true,
            quiet: true,
            ..Default::default()
        };
        let stats_all = run_apply_plan_dir(
            &input_dir, &plan_path, None, &includes, &excludes, None, cfg_all,
        )?;
        assert_eq!(stats_all.processed, 2);

        let cfg_respect = ApplyPlanDirTestCfg {
            in_place: true,
            dry_run: true,
            quiet: true,
            respect_gitignore: true,
            ..Default::default()
        };
        let stats_respected = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            None,
            &includes,
            &excludes,
            None,
            cfg_respect,
        )?;
        assert_eq!(stats_respected.processed, 1);
        assert_eq!(stats_respected.rewritten, 1);
        Ok(())
    }

    #[test]
    fn minify_dir_quiet_suppresses_diff() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(
            input_dir.join("example.py"),
            "def foo(x):\n    y = x + 1\n    return y\n",
        )?;

        let out_dir = tmp.path().join("out");
        let output = cli_cmd()?
            .arg("minify-dir")
            .arg(input_dir.to_str().unwrap())
            .arg("--out-dir")
            .arg(out_dir.to_str().unwrap())
            .arg("--diff")
            .arg("--diff-context")
            .arg("1")
            .arg("--quiet")
            .arg("--dry-run")
            .output()?;
        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        assert!(!stdout.contains("@@"));
        assert!(!stdout.contains("a/example.py"));
        assert!(!stdout.contains("b/example.py"));
        Ok(())
    }

    #[test]
    fn minify_dir_debug_logs_emitted_on_stderr() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join("keep.py"), "def foo():\n    return 1\n")?;
        fs::write(
            input_dir.join(".hidden.py"),
            "def hidden():\n    return 0\n",
        )?;

        let out_dir = tmp.path().join("out");
        let output = cli_cmd()?
            .arg("minify-dir")
            .arg(input_dir.to_str().unwrap())
            .arg("--out-dir")
            .arg(out_dir.to_str().unwrap())
            .arg("--dry-run")
            .arg("--include-hidden")
            .arg("--exclude")
            .arg(".hidden.py")
            .arg("-vv")
            .output()?;

        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        assert!(!stdout.contains("skipped (excluded)"));
        let stderr = String::from_utf8(output.stderr)?;
        assert!(stderr.contains("skipped (excluded)"));
        Ok(())
    }

    #[test]
    fn minify_cli_quiet_suppresses_content() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let body = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, body)?;

        let output = cli_cmd()?
            .arg("minify")
            .arg(file_path.to_str().unwrap())
            .arg("--quiet")
            .output()?;
        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout)?;
        assert!(stdout.trim().is_empty());
        assert!(!stdout.contains("@@"));
        assert!(!stdout.contains("a/"));
        assert!(!stdout.contains("b/"));
        assert!(!stdout.contains(body));
        Ok(())
    }

    #[test]
    fn minify_file_in_place_writes_backup() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let original = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, original)?;

        let (_stats, _) = minify_file(
            &file_path,
            true,
            false,
            Some(".bak"),
            false,
            false,
            true,
            None,
            false,
            false,
            false,
            false,
            3,
            false,
        )?;

        let rewritten = fs::read_to_string(&file_path)?;
        assert!(rewritten.contains("def foo(a):"));

        let backup_path = tmp.path().join("example.py.bak");
        assert!(backup_path.exists());
        let backup_contents = fs::read_to_string(backup_path)?;
        assert_eq!(backup_contents, original);

        Ok(())
    }

    #[test]
    fn minify_file_stats_json_runs() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        fs::write(
            &file_path,
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;

        let (_stats, _) = minify_file(
            &file_path, false, false, None, true, true, true, None, false, false, false, false, 3,
            false,
        )?;

        Ok(())
    }

    #[test]
    fn apply_plan_in_place_writes_backup() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let plan = Minifier::plan_from_source("module", source)?;
        let plan_path = tmp.path().join("plan.json");
        fs::write(&plan_path, serde_json::to_string(&plan)?)?;

        let (_stats, _) = apply_plan(
            &file_path,
            &plan_path,
            true,
            false,
            Some(".bak"),
            false,
            false,
            true,
            None,
            false,
            false,
            false,
            false,
            3,
            false,
        )?;

        let rewritten = fs::read_to_string(&file_path)?;
        assert!(rewritten.contains("def foo(a):"));

        let backup_path = tmp.path().join("example.py.bak");
        assert!(backup_path.exists());
        let backup_contents = fs::read_to_string(backup_path)?;
        assert_eq!(backup_contents, source);

        Ok(())
    }

    #[test]
    fn apply_plan_stats_json_runs() -> AnyResult<()> {
        let tmp = tempdir()?;
        let file_path = tmp.path().join("example.py");
        let source = "def foo(value):\n    temp = value + 1\n    return temp\n";
        fs::write(&file_path, source)?;

        let plan = Minifier::plan_from_source("module", source)?;
        let plan_path = tmp.path().join("plan.json");
        fs::write(&plan_path, serde_json::to_string(&plan)?)?;

        let (_stats, _) = apply_plan(
            &file_path, &plan_path, false, false, None, true, true, true, None, false, false,
            false, false, 3, false,
        )?;

        Ok(())
    }

    #[test]
    fn compute_exit_code_flags() {
        let mut stats = DirStats::default();
        assert_eq!(compute_exit_code(&stats, false, false, false), 0);

        stats.errors = 1;
        assert_eq!(compute_exit_code(&stats, false, true, false), 1);

        stats.errors = 0;
        stats.bailouts = 2;
        assert_eq!(compute_exit_code(&stats, true, false, false), 2);

        stats.bailouts = 0;
        stats.rewritten = 3;
        assert_eq!(compute_exit_code(&stats, false, false, true), 4);

        stats.errors = 1;
        stats.bailouts = 1;
        stats.rewritten = 1;
        assert_eq!(compute_exit_code(&stats, true, true, true), 7);
    }

    #[test]
    fn minify_plan_dir_round_trip() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        let nested = input_dir.join("pkg");
        fs::create_dir_all(&nested)?;

        fs::write(
            input_dir.join("module.py"),
            "def foo(value):\n    temp = value + 1\n    return temp\n",
        )?;
        fs::write(
            nested.join("helpers.py"),
            "def helper(value):\n    result = value * 2\n    return result\n",
        )?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;
        assert!(plan_path.exists());

        let plan_bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        assert_eq!(plan_bundle.files.len(), 2);

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = ApplyPlanDirTestCfg {
            show_stats: false,
            quiet: true,
            ..Default::default()
        };
        let _stats = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(output_dir.clone()),
            &includes,
            &excludes,
            None,
            cfg,
        )?;

        let rewritten_module = fs::read_to_string(output_dir.join("module.py"))?;
        assert!(rewritten_module.contains("def foo(a):"));

        let rewritten_helper = fs::read_to_string(output_dir.join("pkg/helpers.py"))?;
        assert!(rewritten_helper.contains("def helper(a):"));

        Ok(())
    }

    #[test]
    fn minify_plan_dir_includes_version() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join("example.py"), "def foo(x):\n    return x\n")?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let plan_bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        assert_eq!(plan_bundle.version, PLAN_BUNDLE_VERSION);

        Ok(())
    }

    #[test]
    fn minify_plan_dir_skips_hidden_by_default() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join(".hidden.py"), "def foo(x):\n    return x\n")?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let plan_bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        assert!(plan_bundle.files.is_empty());

        Ok(())
    }

    #[test]
    fn minify_plan_dir_includes_hidden_when_requested() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join(".hidden.py"), "def foo(x):\n    return x\n")?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            true,
            false,
            None,
            true,
        )?;

        let plan_bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        assert_eq!(plan_bundle.files.len(), 1);
        assert_eq!(plan_bundle.files[0].path, ".hidden.py");

        Ok(())
    }

    #[test]
    fn minify_plan_dir_pattern_files_respected() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join("alpha.py"), "def foo(x):\n    return x\n")?;
        fs::write(input_dir.join("beta.py"), "def bar(x):\n    return x + 1\n")?;

        let include_file = tmp.path().join("patterns.txt");
        fs::write(&include_file, "*.py\n")?;
        let exclude_file = tmp.path().join("exclude.txt");
        fs::write(&exclude_file, "alpha*.py\n")?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir_with_depth(
            &input_dir,
            &plan_path,
            &[],
            Some(&include_file),
            &[],
            Some(&exclude_file),
            None,
            false,
            false,
            None,
            None,
            false,
            true,
        )?;

        let bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        let paths: Vec<String> = bundle.files.into_iter().map(|f| f.path).collect();
        assert_eq!(paths, vec!["beta.py".to_string()]);
        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn minify_plan_dir_skips_symlink_by_default() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        let real_dir = input_dir.join("real");
        fs::create_dir_all(&real_dir)?;
        fs::write(real_dir.join("a.py"), "def foo(x):\n    return x\n")?;

        let link_path = input_dir.join("link");
        symlink(&real_dir, &link_path)?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let plan_bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        assert_eq!(plan_bundle.files.len(), 1);
        assert_eq!(plan_bundle.files[0].path, "real/a.py");

        Ok(())
    }

    #[cfg(unix)]
    #[test]
    fn minify_plan_dir_follows_symlink_when_requested() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        let real_dir = input_dir.join("real");
        fs::create_dir_all(&real_dir)?;
        fs::write(real_dir.join("a.py"), "def foo(x):\n    return x\n")?;

        let link_path = input_dir.join("link");
        symlink(&real_dir, &link_path)?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            true,
            None,
            true,
        )?;

        let plan_bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        assert_eq!(plan_bundle.files.len(), 2);
        let paths: Vec<_> = plan_bundle
            .files
            .into_iter()
            .map(|entry| entry.path)
            .collect();
        assert_eq!(
            paths,
            vec!["link/a.py".to_string(), "real/a.py".to_string()]
        );

        Ok(())
    }

    #[cfg(windows)]
    #[test]
    fn minify_plan_dir_default_case_insensitive_on_windows() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join("A.py"), "def foo(x):\n    return x\n")?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &["a*.py".to_string()],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let bundle: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        let paths: Vec<_> = bundle.files.into_iter().map(|f| f.path).collect();
        assert_eq!(paths, vec!["A.py".to_string()]);

        Ok(())
    }

    #[cfg(not(windows))]
    #[test]
    fn minify_plan_dir_case_insensitive_flag_controls_matching() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join("A.py"), "def foo(x):\n    return x\n")?;

        let plan_default = tmp.path().join("plan_default.json");
        minify_plan_dir(
            &input_dir,
            &plan_default,
            &["a*.py".to_string()],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;
        let bundle_default: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_default)?)?;
        assert!(bundle_default.files.is_empty());

        let plan_ci = tmp.path().join("plan_ci.json");
        minify_plan_dir(
            &input_dir,
            &plan_ci,
            &["a*.py".to_string()],
            None,
            &[],
            None,
            None,
            false,
            false,
            Some(true),
            true,
        )?;
        let bundle_ci: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_ci)?)?;
        let ci_paths: Vec<_> = bundle_ci.files.into_iter().map(|f| f.path).collect();
        assert_eq!(ci_paths, vec!["A.py".to_string()]);

        let plan_cs = tmp.path().join("plan_cs.json");
        minify_plan_dir(
            &input_dir,
            &plan_cs,
            &["a*.py".to_string()],
            None,
            &[],
            None,
            None,
            false,
            false,
            Some(false),
            true,
        )?;
        let bundle_cs: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_cs)?)?;
        assert!(bundle_cs.files.is_empty());

        Ok(())
    }

    #[test]
    fn apply_plan_dir_rejects_future_version() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;
        fs::write(input_dir.join("example.py"), "def foo(x):\n    return x\n")?;

        let plan_path = tmp.path().join("plan.json");
        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;

        let mut bundle_value: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&plan_path)?)?;
        if let serde_json::Value::Object(ref mut obj) = bundle_value {
            obj.insert(
                "version".to_string(),
                serde_json::Value::Number(serde_json::Number::from(
                    (PLAN_BUNDLE_VERSION + 1) as u64,
                )),
            );
        }
        fs::write(&plan_path, serde_json::to_string_pretty(&bundle_value)?)?;

        let output_dir = tmp.path().join("out");
        let includes: Vec<String> = Vec::new();
        let excludes: Vec<String> = Vec::new();
        let cfg = ApplyPlanDirTestCfg {
            quiet: true,
            fail_on_bailout: false,
            ..Default::default()
        };
        let err = run_apply_plan_dir(
            &input_dir,
            &plan_path,
            Some(output_dir),
            &includes,
            &excludes,
            None,
            cfg,
        )
        .expect_err("future plan version should be rejected");

        let message = err.to_string();
        assert!(
            message.contains("unsupported plan bundle version"),
            "unexpected error: {}",
            message
        );

        Ok(())
    }

    #[test]
    fn minify_plan_dir_deterministic_order() -> AnyResult<()> {
        let tmp = tempdir()?;
        let input_dir = tmp.path().join("src");
        fs::create_dir_all(&input_dir)?;

        fs::write(input_dir.join("b.py"), "def foo(x):\n    return x\n")?;
        fs::write(input_dir.join("a.py"), "def bar(y):\n    return y\n")?;

        let plan_path = tmp.path().join("plan.json");

        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;
        let bundle_one: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;

        minify_plan_dir(
            &input_dir,
            &plan_path,
            &[],
            None,
            &[],
            None,
            None,
            false,
            false,
            None,
            true,
        )?;
        let bundle_two: PlanBundle = serde_json::from_str(&fs::read_to_string(&plan_path)?)?;

        let expected = vec!["a.py", "b.py"];
        let paths_one: Vec<_> = bundle_one.files.iter().map(|f| f.path.as_str()).collect();
        let paths_two: Vec<_> = bundle_two.files.iter().map(|f| f.path.as_str()).collect();

        assert_eq!(paths_one, expected);
        assert_eq!(paths_two, expected);

        Ok(())
    }
}
