# tsrs - Tree-Shaking in Rust for Python

A high-performance tree-shaking implementation in Rust for Python modules and packages.

## Manifesto

> "Ever had someone say, 'just copy the function, we don't need the whole package'? What if that didn't have to be true?"

Tree-shaking enables developers to depend on large, well-designed libraries while only deploying the code they actually use. No more choosing between monolithic packages or duplicating code. Get the best of both worlds: leverage battle-tested libraries while keeping your deployments lean and efficient.

Also makes it much cheaper and simpler to in-house your use of an upstream package, giving you much more freedom to look behind the curtains and upgrade the foundations to your stack.

## Overview

Tree-shaking is the process of analyzing code to identify and remove unused exports from Python modules. This project provides a Rust-based implementation that can be used from Python to detect dead code and optimize module sizes.

## Usage

### CLI
```bash
# Analyze a virtual environment
./target/debug/tsrs-cli analyze /path/to/venv

# Create a slim venv from Python code and venv
./target/debug/tsrs-cli slim <python-directory> <venv-location>

# Create slim venv with custom output path
./target/debug/tsrs-cli slim <python-directory> <venv-location> -o /path/to/output/.venv-slim
```

### Minify Plan Preview

```bash
# Inspect planned local renames without rewriting code
./target/debug/tsrs-cli minify-plan path/to/module.py

# Apply a curated plan to a file (prints to stdout by default)
./target/debug/tsrs-cli apply-plan path/to/module.py --plan plan.json

# Apply in place with a backup and stats
./target/debug/tsrs-cli apply-plan path/to/module.py --plan plan.json --in-place --backup-ext .bak --stats --json

# Feed plan JSON from stdin
./target/debug/tsrs-cli apply-plan path/to/module.py --plan - < plan.json

# Dry run an in-place apply without modifying the file
./target/debug/tsrs-cli apply-plan path/to/module.py --plan plan.json --in-place --dry-run

# Preview the planned changes without touching the file
./target/debug/tsrs-cli apply-plan path/to/module.py --plan plan.json --diff

# Persist plan application stats for later inspection
./target/debug/tsrs-cli apply-plan path/to/module.py --plan plan.json --stats --output-json reports/apply-plan.json

# Pipe source through stdin and capture rewritten output
cat path/to/module.py \\ 
  | ./target/debug/tsrs-cli apply-plan path/to/module.py --plan plan.json --stdin --stdout \\ 
  > path/to/module.min.py

# Pipe source followed by plan JSON through stdin (source first, plan second)
{ cat path/to/module.py; cat plan.json; } \\ 
  | ./target/debug/tsrs-cli apply-plan stdin.py --stdin --plan-stdin
```

### Safe Local Rename Rewrite

```bash
# Emit rewritten source when safe (no nested scopes/imports)
./target/debug/tsrs-cli minify path/to/module.py

# Rewrite in place (updates the file on disk)
./target/debug/tsrs-cli minify path/to/module.py --in-place

# Preview the in-place rewrite without touching the file
./target/debug/tsrs-cli minify path/to/module.py --in-place --dry-run

# Keep a .bak backup before rewriting in place
./target/debug/tsrs-cli minify path/to/module.py --in-place --backup-ext .bak

# Inspect rename counts (optionally emit JSON)
./target/debug/tsrs-cli minify path/to/module.py --stats
./target/debug/tsrs-cli minify path/to/module.py --stats --json

# Preview a unified diff alongside rewritten output
./target/debug/tsrs-cli minify path/to/module.py --diff
# Adjust diff context lines (default: 3)
./target/debug/tsrs-cli minify path/to/module.py --diff --diff-context 5
# Persist stats to disk for later analysis
./target/debug/tsrs-cli minify path/to/module.py --stats --output-json reports/minify.json

# Stream via stdin/stdout for editor integrations
cat path/to/module.py \\
  | ./target/debug/tsrs-cli minify path/to/module.py --stdin --stdout \\
  > path/to/module.min.py
```

Docstrings at the module, class, and function level are stripped automatically during these rewrites so the rewritten files shed non-executable documentation without changing runtime behaviour. Ordinary string literals inside executable code remain intact.

### Directory Rewrite

```bash
# Mirror ./src into ./src-min with minified modules
./target/debug/tsrs-cli minify-dir ./src

# Write into a custom output directory
./target/debug/tsrs-cli minify-dir ./src --out-dir ./dist/min

> The output path must reside outside the input tree after resolving `..` segments
> and symlinks; otherwise the command aborts to avoid clobbering sources.

# Only minify application code, skip tests
./target/debug/tsrs-cli minify-dir ./project \
  --include "project/**" \
  --exclude "project/tests/**"

# Load include/exclude globs from files
./target/debug/tsrs-cli minify-dir ./src --include-file includes.txt --exclude-file excludes.txt

# Preview changes without writing files
./target/debug/tsrs-cli minify-dir ./src --dry-run

# Rewrite files in place (no mirror directory)
./target/debug/tsrs-cli minify-dir ./src --in-place

# Rewrite in place and keep .bak backups of originals
./target/debug/tsrs-cli minify-dir ./src --in-place --backup-ext .bak

# Customize diff context for previews (default: 3)
./target/debug/tsrs-cli minify-dir ./src --diff --diff-context 1 --dry-run

# Limit traversal depth (root depth = 1)
./target/debug/tsrs-cli minify-dir ./src --max-depth 2 --dry-run

# Limit the worker pool (defaults to CPU count)
./target/debug/tsrs-cli minify-dir ./src --jobs 4

# Process hidden files and directories as well
./target/debug/tsrs-cli minify-dir ./src --include-hidden

# Layer repository ignore rules on top of custom globs
./target/debug/tsrs-cli minify-dir ./src --respect-gitignore --exclude "scripts/**"

# Traverse symlinked directories too
./target/debug/tsrs-cli minify-dir ./src --follow-symlinks

# Force case-insensitive glob matching on non-Windows hosts
./target/debug/tsrs-cli minify-dir ./src --glob-case-insensitive

# Show diffs for every rewritten file
./target/debug/tsrs-cli minify-dir ./src --diff

# Write stats to a JSON file for dashboards
./target/debug/tsrs-cli minify-dir ./src --stats --output-json reports/minify-dir.json

# Plan a directory but ignore deeply nested modules
./target/debug/tsrs-cli minify-plan-dir ./src --max-depth 2 --jobs 4 > plans.json

> When `--respect-gitignore` is set, `.gitignore`, global git excludes, and `.ignore`
> files run first; explicit `--include`/`--exclude` (or pattern files) are then applied
> on top, so excludes still win over includes.
```

Each run prints per-file status lines (minified, skipped, bailouts) and summarises the total work. Bailouts copy the original file verbatim so you never lose working code—re-run with `--debug` to inspect why a file could not be safely renamed.

Add `--stats` to include per-file rename counts in the output, and combine it with `--json` for a machine-readable summary of the same data.

Pass `--quiet` when you only want the final summary/JSON; it suppresses per-file status lines, diff output, and non-in-place rewritten content (unless you opt into `--stdout`).

Use `--dry-run` to preview the work (including stats and diffs) without writing any files—available for both single-file and directory commands.

For CI flows, combine `--fail-on-change`, `--fail-on-bailout`, or `--fail-on-error` with dry runs to turn safe previews into enforcement checks.

All directory commands accept `--jobs <N>` to control the number of Rayon worker threads. When omitted the tool uses the machine's CPU count. They also ignore `.git`, `__pycache__`, and `.venv` directories by default—add `--follow-symlinks` if you need to traverse symlinked trees, and `--glob-case-insensitive` if you want case-insensitive glob matching on platforms where the default is case-sensitive (Windows already matches case-insensitively).
Pattern files (`--include-file`, `--exclude-file`) accept newline-delimited globs; blank lines and `#` comments are ignored.

Key directory flags at a glance:

- `--diff` / `--diff-context <N>` preview unified diffs with adjustable context (default 3 lines).
- `--max-depth <N>` limits recursion depth (the root input directory counts as depth 1).
- `--include-hidden` enables processing of dot-prefixed files and directories.
- Exclude globs always take precedence over include globs.
- `--follow-symlinks` traverses symlinked directories.
- `--glob-case-insensitive` forces case-insensitive glob matching on every platform.

### Plan Bundles

```bash
# Create a directory-wide plan bundle
./target/debug/tsrs-cli minify-plan-dir ./src --out plan.json

# Include hidden files while planning
./target/debug/tsrs-cli minify-plan-dir ./src --out plan.json --include-hidden

# Apply the bundle to a mirrored output tree
./target/debug/tsrs-cli apply-plan-dir ./src --plan plan.json --out-dir ./src-min

# Apply in place with backups and detailed stats
./target/debug/tsrs-cli apply-plan-dir ./src --plan plan.json --in-place --backup-ext .bak --stats --json

# Include unified diffs while applying a plan bundle
./target/debug/tsrs-cli apply-plan-dir ./src --plan plan.json --diff

# Apply to hidden files too
./target/debug/tsrs-cli apply-plan-dir ./src --plan plan.json --include-hidden

# Capture directory stats to a JSON report while applying a bundle
./target/debug/tsrs-cli apply-plan-dir ./src --plan plan.json --stats --output-json reports/apply-plan-dir.json

# CI: fail if a rewrite would change files or introduce bailouts
./target/debug/tsrs-cli minify-dir ./src --dry-run --fail-on-change --fail-on-bailout

Plan bundles include a `version` field (currently `1`) so future releases can evolve the schema without breaking old plans; tools should validate this field when consuming stored bundles, and the CLI refuses to apply plans whose version exceeds the supported value.
```

### Integration Tests

```bash
# Run CLI slimming scenarios (used vs unused packages)
cargo test --test cli_integration

# Run minify/minify-plan integration coverage
cargo test --test minify_integration

# Run apply-plan / apply-plan-dir integration coverage
cargo test --test apply_integration
```

## References

- [pyminifier (liftoffsoftware)](https://github.com/liftoff/pyminifier)
- [TreeShaker (sclabs)](https://github.com/sclabs/treeshaker)
- [“Build a Python tree-shaker in Rust” (dev.to)](https://dev.to/georgepearse/build-a-python-tree-shaker-in-rust-2n4h)
- [“Crude Python tree-shaking for squeezing into AWS Lambda package size limits” (sam152)](https://dev.to/sam152/crude-python-tree-shaking-for-squeezing-into-aws-lambda-package-size-limits-357a)

### How it Works

1. **Scans the Python code directory** for all import statements
2. **Analyzes the source venv** to discover all installed packages
3. **Maps imports to packages** and copies only the used packages to a new slim venv
4. **Creates `.venv-slim`** with only the minimal dependencies needed

### Example
```bash
# Slim your venv based on actual code usage
tsrs-cli slim ./src ./.venv
# Creates: ./.venv-slim with only the packages your code imports
```

## Building

### CLI Only
```bash
cargo build --release --bin tsrs-cli
./target/release/tsrs-cli --help
```

### With Python Extension
This project can also build as a Python extension module using PyO3.

```bash
# Setup (optional Python feature)
pip install maturin

# Build and develop
maturin develop

# Or build a wheel
maturin build --release
```

## Architecture

### Core Modules

- **`venv`** - Virtual environment discovery and package analysis
- **`imports`** - Import statement extraction and tracking
- **`callgraph`** - Function call graph analysis per package
  - Tracks which functions are defined in each package
  - Maps external dependencies between packages
  - Identifies unused/dead code that is never called
- **`slim`** - Creates minimal venvs based on code analysis

### How Tree-Shaking Works

The tool builds a complete picture of your code's dependencies:

1. **Import Analysis**: Extracts all `import` and `from...import` statements from your code
2. **Call Graph Building**: Analyzes function definitions and calls in your Python code
3. **Package Mapping**: Maps imports to actual packages in your venv
4. **Dead Code Detection**: Identifies functions/classes that are defined but never used
5. **Dependency Reduction**: Creates a slim venv with only the necessary packages

This multi-layered approach ensures you don't accidentally remove code that's used through indirect calls or dynamic imports.

### High Precision, Low Recall Philosophy

**tsrs prioritizes precision over recall in dead code detection:**

- **High Precision**: When we flag something as dead/unused, it almost certainly is
- **Low Recall**: We're happy to miss dead code - better conservative than aggressive

We will keep:

- All **global variables and module-level constants** in any package (these may be used externally or through reflection)
- All **public API surfaces** even if not directly called in your code
- **Packages you explicitly import**, even if only specific functions are used
- Any code that **could potentially be used** (even indirectly)

The philosophy: **It's better to leave in unused code than to accidentally break something that's actually used through indirect calls, dynamic imports, reflection, or a library's public API.**

We're optimizing for **correctness over comprehensiveness** - we'd rather miss some dead code than introduce false positives that break your application.

## Development

```bash
cargo test
cargo fmt
cargo clippy
```

## References & Inspiration

### Related Projects
- **[Ruff](https://github.com/astral-sh/ruff)** - An extremely fast Python linter written in Rust. Uses `ruff_python_parser` for parsing Python code.
- **[Pylyzer](https://github.com/mtshiba/pylyzer)** - A fast, feature-rich static code analyzer & language server for Python. Uses Rust internally with type checking capabilities.
- **[Skylos](https://github.com/duriantaco/skylos)** - A static analysis tool for Python codebases that detects dead code, unused functions, classes, imports, and variables. Also includes security flaw detection.

### Discussion
- [Reddit Discussion: Is there any support in Python for something like tree-shaking?](https://www.reddit.com/r/Python/comments/aqqzjl/is_there_any_support_in_python_for_something/)

## License

TBD
