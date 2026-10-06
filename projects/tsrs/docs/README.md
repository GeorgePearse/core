# tsrs - Tree-Shaking in Rust for Python

A high-performance tree-shaking implementation in Rust for Python modules and packages.

## Manifesto

> "Ever had someone say, 'just copy the function, we don't need the whole package'? What if that didn't have to be true?"

Tree-shaking enables developers to depend on large, well-designed libraries while only deploying the code they actually use. No more choosing between monolithic packages or duplicating code. Get the best of both worlds: leverage battle-tested libraries while keeping your deployments lean and efficient.

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
```

### Safe Local Rename Rewrite

```bash
# Emit rewritten source when safe (no nested scopes/imports)
./target/debug/tsrs-cli minify path/to/module.py

# Rewrite in place (updates the file on disk)
./target/debug/tsrs-cli minify path/to/module.py --in-place

# Keep a .bak backup before rewriting in place
./target/debug/tsrs-cli minify path/to/module.py --in-place --backup-ext .bak

# Inspect rename counts (optionally emit JSON)
./target/debug/tsrs-cli minify path/to/module.py --stats
./target/debug/tsrs-cli minify path/to/module.py --stats --json
```

### Directory Rewrite

```bash
# Mirror ./src into ./src-min with minified modules
./target/debug/tsrs-cli minify-dir ./src

# Write into a custom output directory
./target/debug/tsrs-cli minify-dir ./src --out-dir ./dist/min

# Only minify application code, skip tests
./target/debug/tsrs-cli minify-dir ./project \
  --include "project/**" \
  --exclude "project/tests/**"

# Preview changes without writing files
./target/debug/tsrs-cli minify-dir ./src --dry-run

# Rewrite files in place (no mirror directory)
./target/debug/tsrs-cli minify-dir ./src --in-place

# Rewrite in place and keep .bak backups of originals
./target/debug/tsrs-cli minify-dir ./src --in-place --backup-ext .bak
```

Each run prints per-file status lines (minified, skipped, bailouts) and summarises the total work. Bailouts copy the original file verbatim so you never lose working code—re-run with `--debug` to inspect why a file could not be safely renamed.

Add `--stats` to include per-file rename counts in the output, and combine it with `--json` for a machine-readable summary of the same data.

### Plan Bundles

```bash
# Create a directory-wide plan bundle
./target/debug/tsrs-cli minify-plan-dir ./src --out plan.json

# Apply the bundle to a mirrored output tree
./target/debug/tsrs-cli apply-plan-dir ./src --plan plan.json --out-dir ./src-min

# Apply in place with backups and detailed stats
./target/debug/tsrs-cli apply-plan-dir ./src --plan plan.json --in-place --backup-ext .bak --stats --json

# CI: fail if a rewrite would change files or introduce bailouts
./target/debug/tsrs-cli minify-dir ./src --dry-run --fail-on-change --fail-on-bailout
```

## Application Guides

**New to tsrs?** Start with one of these guides to understand what you can do:

- **[Minification Guide](MINIFICATION_GUIDE.md)** - Reduce code size by renaming local variables. Perfect for Lambda, Docker, and size-constrained deployments.
- **[Test Selection Guide](TEST_SELECTION_GUIDE.md)** - Run only tests affected by code changes. Speed up CI/CD pipelines by 30-80%.
- **[Applications Overview](APPLICATIONS.md)** - Explore all possible uses of the analysis framework (dead code detection, package slimming, and more).

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
