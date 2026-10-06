# AGENTS.md

**Purpose**: This file provides comprehensive guidance to Claude Code and AI agents when working on code improvements in the tsrs repository. It includes architectural details, known limitations, test coverage maps, and patterns to follow.

## Quick Links

- **Project Overview**: See section "Project Overview" below
- **Architecture**: See "Code Architecture & Module Responsibilities"
- **Website Structure**: See "Website & Documentation Structure"
- **Testing**: See "Testing Strategy & Coverage Map"
- **Making Changes**: See "Development Workflow" and "Common Patterns"
- **File Organization**: See "File Organization & Where to Find Things"
- **Known Issues**: See "Current State & Known Limitations"

---

## Project Overview

**tsrs** (Tree-Shaking in Rust for Python) is a high-performance Rust implementation that analyzes Python code to identify and remove unused exports from modules and packages. It can create minimal virtual environments based on actual code usage, optimizing deployment sizes (typically 30-70% reduction).

### Current Version
- **Cargo Version**: 0.2.0
- **Edition**: 2021
- **Python Support**: 3.7+
- **Latest Release**: 2025-11-01

### Core Philosophy

The project prioritizes **high precision over aggressive optimization**:
- Never remove code unless absolutely certain it's unused
- Keep module-level exports and public APIs to avoid breaking indirect usage patterns
- Conservative with dynamic features and reflection
- Correctness over comprehensiveness

---

## Code Architecture & Module Responsibilities

### File-to-Responsibility Map

| File | Primary Responsibility | Key Types | Dependencies |
|------|------------------------|-----------|--------------|
| `src/lib.rs` | Library root, public API, PyO3 extension | `MinifyPlan`, `FunctionPlan` | All modules |
| `src/bin/cli.rs` | CLI argument parsing and command dispatch | `Cli`, `Commands` enum | All core modules |
| `src/venv.rs` | Virtual env discovery, package metadata | `VenvAnalyzer`, `PackageInfo` | walkdir, serde |
| `src/imports.rs` | Extract import statements from AST | `ImportCollector`, `Import` struct | rustpython-parser |
| `src/callgraph.rs` | Build function call graphs, detect dead code | `CallGraphAnalyzer`, `CallGraph` | rustpython-parser, HashMap |
| `src/slim.rs` | Create minimal venvs from imports | `VenvSlimmer` | venv, imports, walkdir |
| `src/minify.rs` | Local variable renaming, plan generation | `Minifier`, `ShortNameGen`, `MinifyPlan` | rustpython-parser, regex |
| `src/error.rs` | Custom error types | `TsrsError` enum | thiserror |

### Data Flow Pipeline

```
Source Code
    ↓
[ImportCollector] → Extract all import/from-import statements
    ↓
[VenvAnalyzer] → Map imports to actual packages in venv
    ↓
├─→ [VenvSlimmer] → Copy only necessary packages to .venv-slim
└─→ [CallGraphAnalyzer] → Build function call graph
         ↓
    [Minifier] → Generate rename plans for local variables
         ↓
    [Plan Writer] → Serialize MinifyPlan to JSON
         ↓
    [Plan Applier] → Rewrite source code with minified names
```

### Core Data Structures

**MinifyPlan** (serializable, v1 format):
```rust
{
  "format_version": "1",
  "python_version": "3.7+",
  "functions": [
    {
      "name": "func_name",
      "lineno": 10,
      "local_names": ["var1", "var2", ...],
      "rename_map": {"var1": "a", "var2": "b", ...},
      "excluded_names": ["global_x", "nonlocal_y", ...]
    }
  ],
  "python_keywords": [...],
  "builtins": [...]
}
```

**FunctionPlan**:
- `name`: Function identifier for debugging
- `local_names`: All names bound in function scope (sorted for stability)
- `rename_map`: Original name → minified name (a, b, c, ..., z, aa, ab, ..., zz, aaa, ...)
- `excluded_names`: Names that cannot be renamed (globals, nonlocals, builtins, keywords)

---

## Dependencies Overview

### Production Dependencies

| Crate | Version | Purpose | Notes |
|-------|---------|---------|-------|
| `rustpython-parser` | 0.3 | Python AST parsing | Fast, handles modern syntax |
| `walkdir` | 2 | Directory traversal | Used by venv, slim, minify-dir |
| `serde` + `serde_json` | 1 | Serialization | For plan format and CLI output |
| `anyhow` | 1 | Error context | General error handling |
| `thiserror` | 1 | Error definitions | Custom TsrsError enum |
| `clap` | 4 | CLI parsing | Derives, matches our command structure |
| `regex` | 1 | Pattern matching | Import analysis, name validation |
| `rayon` | 1 | Parallelization | `--jobs N` support in minify-dir |
| `num_cpus` | 1 | CPU detection | Default parallelization level |
| `encoding_rs` | 0.8 | Charset detection | Preserve file encodings |
| `similar` | 2 | Diff generation | `--diff` output |
| `ignore` | 0.4 | `.gitignore` support | `--respect-gitignore` flag |
| `dunce` | 1 | Path normalization | Windows/POSIX compatibility |
| `tracing` + `tracing-subscriber` | 0.1 / 0.3 | Structured logging | Debug logging via `RUST_LOG` |

### Optional Features

- **`python-extension`**: Enables PyO3 extension (requires pyo3 0.22)
- **Default**: No features enabled

### Dev Dependencies

- `assert_cmd` (2): CLI testing
- `tempfile` (3): Temporary directories for tests
- `serde_json` (1): JSON manipulation in tests

---

## Current State & Known Limitations

### What Works Well ✅

1. **Basic minification**: Simple functions with parameters, locals, assignments
2. **Import analysis**: Accurately extracts import statements (including from/import, aliases)
3. **Package mapping**: Correctly maps imports to venv packages
4. **Encoding preservation**: Maintains UTF-8, BOMs, line endings, trailing newlines
5. **Plan stability**: Plans are reproducible (sorted, deterministic)
6. **Nested function handling**: Can minify inside closures and class bodies
7. **Parallel processing**: Multi-core support via rayon
8. **Diff output**: Clear `--diff` with configurable context

### Known Limitations ⚠️

1. **Bailout on nested scopes**: Functions containing inner functions/classes skip minification
   - Reason: Scope tracking complexity with closures
   - File: `src/minify.rs` lines ~400-450
   - Example: Function with nested `def` won't be minified

2. **Global/nonlocal declarations**: Any function with `global x` or `nonlocal y` is skipped
   - Reason: Can't safely rename variables that reference outer scope
   - File: `src/minify.rs` - `GlobalCollector` struct

3. **No comprehension variable minification**: List/dict/set comprehensions preserve variable names
   - Reason: Complex scope rules, variables leak in Python 2 style
   - File: `src/minify.rs` - `is_comprehension` check

4. **Dynamic imports not tracked**: `importlib.import_module()` or string-based imports ignored
   - Reason: Requires dataflow analysis
   - File: `src/imports.rs` - only handles static import statements

5. **Call graph is per-package, not cross-package**: Dead code detection doesn't follow imports
   - Reason: Would require whole-program analysis
   - File: `src/callgraph.rs` - `CallGraphAnalyzer` builds per-package graphs

6. **Class/dunder names not minified**: `__init__`, `_private`, class-scoped names excluded
   - Reason: Preserve reflection/introspection compatibility
   - File: `src/minify.rs` - exclusion lists

### Edge Cases Being Handled ✅

1. **Multiline strings & docstrings**: Stripped during minification (preserves other literals)
2. **Decorators with side effects**: Preserved (conservative approach)
3. **Walrus operator (`:=`)**: Handled in assignment collection
4. **Match statements (Python 3.10+)**: Entire function bails out if match found
5. **Async functions**: Minified same as regular functions
6. **With/except variable binding**: Captured in assignment targets
7. **For-loop variables**: Tracked as local bindings

### Missing/Incomplete Features ⚠️

1. **Call graph analysis**:
   - No interprocedural analysis (function A calls function B not tracked)
   - No type inference for dead code detection
   - Task: Consider SSA form or simpler PDG approach

2. **Import analysis**:
   - Relative imports within packages not fully resolved
   - No `__all__` export list analysis
   - Task: Integrate `__all__` detection

3. **Python 3.12+ support**:
   - No testing against Python 3.12 type hints (PEP 695)
   - No support for type parameter syntax
   - Task: Update rustpython-parser version + add tests

4. **Multi-version handling**:
   - Single minify plan per file (can't generate version-specific plans)
   - Task: Add plan versioning for different Python versions

---

## Testing Strategy & Coverage Map

### Unit Test Coverage (34 tests passing)

**imports.rs** (3 tests):
- ✅ Skips relative imports
- ✅ Collects top-level modules
- ✅ Ignores duplicates and handles aliases

**minify.rs - Planning** (8 tests):
- ✅ Records globals and nonlocals correctly
- ✅ Plans comprehension detection (sets bailout flag)
- ✅ Collects parameters and locals
- ✅ Preserves closure variables
- ✅ Handles from-import aliases

**minify.rs - Rewriting** (19 tests):
- ✅ Simple plan application
- ✅ Import alias handling (multiple variants)
- ✅ Comprehension bailout behavior
- ✅ Dotted import handling (skips without alias)
- ✅ Star import behavior (skipped)
- ✅ Name replacement stability
- ✅ Docstring stripping (module, function, async, class, nested)
- ✅ Decorator preservation
- ✅ Multiline docstring preservation
- ✅ Global/nonlocal respect
- ✅ Match statement bailout
- ✅ Nested function bailout
- ✅ Annotation preservation (not renamed)

**Gap Analysis - What Needs Testing**:
- ❌ Call graph dead code detection (no unit tests)
- ❌ Venv analysis edge cases (mixed packages, namespaces)
- ❌ Large directory traversal (performance tests)
- ❌ Error recovery paths
- ⚠️ Plan format versioning (only v1 tested)

### Integration Test Packages

**test_unused_function/package_one** (2 tests):
```
├── test_add_one_and_one ✅
└── test_hello_world_greet ✅
```
Status: Both pass with full venv and .venv-slim

**test_slim_packages/** (16 manual test scenarios):
```
├── project/ → Basic import pattern
├── project_alias_function/ → Function aliases
├── project_alias_import/ → Module aliases
├── project_backslash_import/ → Line continuation
├── project_from_import/ → from X import Y
├── project_function_scope_import/ → Imports in functions
├── project_if_block_import/ → Conditional imports
├── project_multi_import/ → Multiple imports per line
├── project_multiline_import/ → Parenthesized imports
├── project_submodule_alias/ → Submodule with alias
├── project_submodule_alias_item/ → Import specific submodule item
├── project_submodule_import/ → Direct submodule import
├── project_submodule_wildcard/ → from X import *
├── project_try_except_import/ → Try/except imports
├── project_wildcard_import/ → Wildcard imports
└── unused_pkg/ + used_pkg/ → Dependency packages
```

**How to Run**:
```bash
# Unit tests
cargo test

# Integration tests (manually)
cd test_packages/test_unused_function/package_one
uv sync --all-extras && uv run pytest -v

# Manual slim verification (example)
cd test_packages/test_slim_packages/project
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python main.py  # Baseline
../../../../../../target/release/tsrs-cli slim . .venv-slim
VIRTUAL_ENV=.venv-slim .venv-slim/bin/python main.py  # Slimmed
```

### What Tests Are Missing

1. **Parallel processing edge cases**: Race conditions in rayon traversal
2. **File encoding edge cases**: UTF-16, Latin-1, mixed encodings
3. **Large codebases**: Performance testing on 10K+ file projects
4. **Plan application with errors**: Corrupted plans, missing files
5. **Circular imports**: Package import cycles
6. **Dynamic `__all__` modification**: Runtime export list changes

---

## Common Patterns & Code Style

### Rust Code Patterns

1. **Error handling**: Use `Result<T>` with `?` operator + `thiserror` for custom errors
   ```rust
   fn analyze_imports(path: &Path) -> Result<Vec<Import>> {
       let content = std::fs::read_to_string(path)?;
       // ...
       Ok(imports)
   }
   ```

2. **AST traversal**: `rustpython-parser` uses recursive visitor pattern
   ```rust
   for stmt in &mod_ast.body {
       match stmt {
           StmtKind::Import { names, .. } => { /* handle */ },
           StmtKind::ImportFrom { module, names, .. } => { /* handle */ },
           _ => {}
       }
   }
   ```

3. **Collection stability**: Always sort results before serialization
   ```rust
   let mut names = vec![...];
   names.sort();  // Ensures reproducible plans
   ```

4. **Logging**: Use `tracing::debug!`, `tracing::info!` (configurable via `RUST_LOG`)
   ```rust
   debug!("Processing file: {:?}", path);
   ```

5. **Parallel processing**: Use rayon for directory operations
   ```rust
   files.par_iter().map(|f| minify_file(f)).collect()
   ```

### Python AST Handling

**Supported Import Patterns** (from `src/imports.rs`):
- ✅ `import module`
- ✅ `import module as alias`
- ✅ `import m1, m2, m3`
- ✅ `from module import name`
- ✅ `from module import name as alias`
- ✅ `from module import name1, name2`
- ✅ `from module import *`
- ✅ `from . import relative` (skipped, preserved)
- ✅ `from .. import relative` (skipped, preserved)

**Unsupported**:
- ❌ `importlib.import_module("name")` (dynamic)
- ❌ `__import__("name")` (dynamic)
- ❌ Late `__all__` definitions: `__all__ = ['a', 'b'] + other_list`

### Minification Scope Rules

**Renamed** (function-local only):
- Function parameters: `def f(x, y, *args, **kwargs)`
- Assignment targets: `x = 1`
- Loop variables: `for x in list:`
- Exception handlers: `except Error as e:`
- With statement: `with open() as f:`
- Comprehension targets: `[x for x in list]` (but entire function bails)
- Import aliases: `from X import Y as name` → `name` renamed, not `Y`

**Not Renamed** (preserved):
- Global names: `x` with `global x` in function
- Nonlocal names: `x` with `nonlocal x` in function
- Class scope names: Names defined in `class Foo: x = 1`
- Dunder names: `__init__`, `__call__`, `__all__`, etc.
- Single underscore: `_`
- Python keywords: 35 reserved words
- Builtin names: `print`, `len`, `str`, `dict`, etc.

### Name Generation Algorithm

Sequential generator (stable, deterministic):
```
a, b, c, ..., z,          (1-letter, 26 names)
aa, ab, ac, ..., az, ba, ..., zz,  (2-letter, 676 names)
aaa, aab, ...             (3-letter, 17,576 names)
```

**Never uses**: Keywords, builtins, single `_`, leading `__`

---

## Development Workflow

### Building & Running

```bash
# Debug build
cargo build

# Release build (optimized)
cargo build --release

# Build CLI
cargo build --release --bin tsrs-cli
./target/release/tsrs-cli --help

# Build Python extension (optional)
pip install maturin
maturin develop  # For dev/testing
maturin build --release  # For wheel distribution
```

### Code Quality Checks

```bash
# Format
cargo fmt

# Lint (enforced in pre-commit)
cargo clippy -- -W clippy::pedantic

# Run all tests
cargo test

# Run specific test
cargo test test_name

# Run with output
cargo test -- --nocapture
```

### Pre-commit Hooks

The project enforces:
1. `cargo fmt` - Code formatting
2. `cargo clippy -- -W clippy::pedantic` - Linting

**These must pass before commit or the commit will fail.** Run them locally first:
```bash
cargo fmt && cargo clippy -- -W clippy::pedantic
```

### Common Development Tasks

#### Adding a New CLI Command

1. **Update clap parsing** (`src/bin/cli.rs`):
   ```rust
   #[derive(Subcommand)]
   enum Commands {
       // ... existing commands ...
       NewCommand {
           #[arg(help = "...")]
           path: PathBuf,
       },
   }
   ```

2. **Implement logic** in appropriate module:
   - If related to minification: `src/minify.rs`
   - If related to venv: `src/venv.rs`
   - If related to imports: `src/imports.rs`

3. **Add tests** in `tests/` or inline `#[cfg(test)]`

4. **Update CLI help** and README

5. **Ensure clippy passes**: `cargo clippy -- -W clippy::pedantic`

#### Modifying Minification Logic

1. **Review scope rules** in MINIFY_DESIGN.md
2. **Update exclusion/collection logic** in `src/minify.rs`:
   - `GlobalCollector` for tracking global names
   - `LocalBindingCollector` for function-local names
   - `NameExcluder` for reserved names
3. **Add unit tests** for new AST node types
4. **Test plan stability**: Plans should be identical on repeated runs
5. **Run** `cargo test` to verify no regressions

#### Extending Call Graph Analysis

1. **Enhance** `CallGraphAnalyzer` in `src/callgraph.rs`
2. **Update tracking** for new statement/expression types
3. **Document** what dead code patterns now detected
4. **Test** on real packages in `test_packages/`
5. **Verify** no false positives (conservative is better)

#### Debugging Issues

**Enable debug logging**:
```bash
RUST_LOG=debug cargo run -- <command>
RUST_LOG=tsrs=trace cargo test -- --nocapture
```

**Inspect minify plans** (JSON):
```bash
./target/release/tsrs-cli minify-plan path/to/file.py | jq
./target/release/tsrs-cli minify-plan-dir src --out plan.json && cat plan.json | jq
```

**Generate diffs** to see what would change:
```bash
./target/release/tsrs-cli minify path/to/file.py --diff --diff-context 3
```

**Dry-run without writing**:
```bash
./target/release/tsrs-cli minify-dir ./src --dry-run --stats
```

---

## Performance Characteristics

### Expected Performance

- **Import analysis**: ~1-2ms per Python file (linear in file size)
- **Minification planning**: ~5-10ms per file (AST walk + name analysis)
- **Minification rewriting**: ~2-5ms per file (text replacement)
- **Directory traversal**: ~10-100ms for typical project (parallel, configurable threads)

### Bottlenecks & Optimization Opportunities

1. **rustpython-parser** parsing: Can be slow on large files (>50KB)
   - Potential: Incremental parsing or caching ASTs

2. **String replacement in minify**: Linear in file size
   - Potential: Use aho-corasick for multi-pattern matching

3. **Directory traversal**: Single-threaded by default (walkdir)
   - Current: Parallelized with rayon when using `--jobs N`
   - Status: ✅ Implemented in v0.2.0

4. **Plan serialization**: JSON is verbose for large projects
   - Potential: Implement JSONL streaming or binary format

### Profiling

```bash
# Generate flamegraph (install cargo-flamegraph first)
cargo flamegraph --release -- minify-dir ./target/release /tmp/out

# Profile with perf
cargo build --release
perf record -g ./target/release/tsrs-cli minify-dir ./large_project
perf report
```

---

## Python Compatibility Notes

### Version Support

- **Target**: Python 3.7+
- **Tested**: Python 3.9.2 (test environment)
- **Parsing**: rustpython-parser 0.3 (handles up to Python 3.10 syntax)

### Python Syntax Handled

**Python 3.8+**:
- ✅ Walrus operator (`:=` in assignments)
- ✅ Positional-only parameters (`/` in function defs)
- ✅ f-strings (not minified, preserved as literals)

**Python 3.10+**:
- ✅ Match statements (function bails out if match detected)
- ✅ Union type syntax (`X | Y` in type hints)
- ❌ Type parameter syntax (`[T]` in class/function defs) - not yet supported

**Python 3.11+**:
- ⚠️ Exception groups (`ExceptionGroup`) - preserved
- ⚠️ Type hints with `Never` - preserved

**Python 3.12+** (not officially tested):
- ❌ Type parameter syntax (`TypeVar` in function/class)
- ❌ Per-interpreter GIL features
- 🔄 Task: Update rustpython-parser, add tests

### Common Pitfalls

1. **Line number confusion**: AST line numbers are 1-indexed, but string indices are 0-indexed
   - Fix: Account for offset when mapping plan to source

2. **UTF-8 vs byte offsets**: File may have non-ASCII characters
   - Current: Handled via encoding_rs detection
   - Safe: Preserve encoding throughout pipeline

3. **Windows line endings (`\r\n`)**: May differ from Unix (`\n`)
   - Current: Preserved in v0.2.0
   - Safe: Use `dunce` for path normalization

4. **Relative imports in packages**: `from . import sibling` needs careful handling
   - Current: Skipped (conservative)
   - Safe: Keep existing behavior

---

## Known Bugs & Issue Tracker

### Recent Issues (0.2.0)

1. **Encoding preservation**: Fixed in v0.2.0
   - What was broken: BOM and encoding lost during rewriting
   - How fixed: Use `encoding_rs` to preserve charset

2. **Nested function minification**: Added support in v0.2.0
   - What was missing: Closures couldn't be minified
   - How fixed: Enhanced scope tracking for nested scopes

3. **Diff context**: Added `--diff-context` in v0.2.0
   - What was missing: Fixed 3-line context
   - How fixed: Made configurable via CLI flag

### Open/Reported Issues

(None currently reported; check GitHub issues)

---

## Future Work & Roadmap

### High Priority

1. **Call graph dead code detection**
   - Status: ⚠️ Implemented but conservative
   - Improvement: Add interprocedural analysis
   - Effort: Medium (requires PDG or similar)

2. **`__all__` export analysis**
   - Status: ❌ Not implemented
   - Benefit: Better slim venv creation
   - Effort: Low-medium (pattern matching)

3. **Python 3.12+ support**
   - Status: ⚠️ Partial (no type params)
   - Effort: Low (update rustpython-parser)

### Medium Priority

4. **Call graph visualization**
   - Status: ❌ Not implemented
   - Tool: `dot` / Graphviz output
   - Effort: Medium

5. **Incremental minification**
   - Status: ❌ Not implemented
   - Benefit: Cache plans between runs
   - Effort: High (requires fine-grained tracking)

6. **Multi-version plan generation**
   - Status: ❌ Not implemented
   - Benefit: Support Python 3.7-3.12 simultaneously
   - Effort: Medium-high

### Low Priority / Nice-to-Have

7. **IDE integration**: VS Code extension for minify preview
8. **Web UI**: Browser-based analyzer for large projects
9. **Machine learning optimization**: Learn optimal package reduction ratios
10. **Multi-language support**: Extend to JavaScript, Go, etc.

---

## Integration Points & External APIs

### Command-Line API

```bash
# Analyze venv
tsrs-cli analyze /path/to/venv

# Create slim venv
tsrs-cli slim <python-dir> <venv-path> [-o output]

# Minify single file
tsrs-cli minify path.py [--in-place] [--diff] [--stats]

# Minify directory
tsrs-cli minify-dir ./src [--out-dir ./out] [--jobs N]

# Generate plan (no modification)
tsrs-cli minify-plan path.py > plan.json
tsrs-cli minify-plan-dir src --out plan.json

# Apply pre-generated plan
tsrs-cli apply-plan path.py --plan plan.json [--in-place]
tsrs-cli apply-plan-dir ./src --plan plan.json --out-dir ./out
```

### Library API (Rust)

```rust
use tsrs::{MinifyPlan, VenvAnalyzer, Minifier};

// Analyze venv
let analyzer = VenvAnalyzer::new("/path/to/venv")?;
let packages = analyzer.analyze()?;

// Generate minification plan
let minifier = Minifier::new();
let plan = minifier.plan_file("path/to/file.py")?;

// Serialize plan
let json = serde_json::to_string_pretty(&plan)?;

// Apply plan
let source = std::fs::read_to_string("path/to/file.py")?;
let minified = minifier.apply_plan(&source, &plan)?;
```

### Python Extension (PyO3)

When built with `python-extension` feature:
```python
import tsrs

plan = tsrs.plan_minify("path/to/file.py")
minified_source = tsrs.apply_plan(source_code, plan)
```

(Status: Partially implemented, under active development)

---

## Common Pitfalls & How to Avoid Them

### 1. Renaming Global/Nonlocal Variables

**Problem**: Function has `global x` or `nonlocal y`, and you minify `x`/`y`
**Result**: Code breaks because renamed variable no longer refers to outer scope
**Prevention**: `GlobalCollector` + `NonlocalCollector` explicitly track these
**Check**: Search for `is_excluded_name()` call in minify logic

### 2. Minifying Dunder Names

**Problem**: Rename `__init__` to `a` in a class
**Result**: Reflection and pickle break; class becomes unusable
**Prevention**: Hardcoded exclusion list for dunder names (`__*__`)
**Check**: Test with `def __init__` in test suite

### 3. Creating Plans for Different Python Versions

**Problem**: Generate plan for Python 3.9 code, apply to Python 3.7 interpreter
**Result**: Walrus operators, type hints may not parse in 3.7
**Prevention**: Lock plan format to source Python version
**Future**: Add version compatibility checking in plan applier
**Check**: Validate plan version matches target Python version

### 4. Parallel File Access Conflicts

**Problem**: Two threads try to minify same file with `--jobs N > 1`
**Result**: Corrupted output or panic
**Prevention**: rayon handles independent files; use `--dry-run` first
**Check**: Test directory minification with `--jobs 8` on large tree

### 5. Incorrect Line Number Mapping

**Problem**: Plan has line 100, but source code changed (imports added/removed)
**Result**: Minify rewrites wrong variable
**Prevention**: Always regenerate plans, don't reuse old plans
**Check**: Version plans with source file hash or timestamp
**Current**: No built-in versioning (task to add)

### 6. Encoding Loss During Rewrite

**Problem**: UTF-8 file with BOM or UTF-16 file gets corrupted
**Result**: Character encoding errors, file becomes unreadable
**Prevention**: encoding_rs detects and preserves original encoding
**Status**: ✅ Fixed in v0.2.0
**Check**: Test with non-ASCII filenames and content

### 7. Symlink Loops in Directory Traversal

**Problem**: Directory tree has symlink cycle (A → B → A)
**Result**: Infinite loop or stack overflow
**Prevention**: `--follow-symlinks` is opt-in, off by default
**Status**: ✅ Configurable in v0.2.0
**Check**: Test on directory with symlink cycle

---

## Quick Command Reference

### Testing

```bash
cargo test                  # All tests
cargo test imports::        # Single module tests
cargo test -- --nocapture  # Show println! output
```

### Building

```bash
cargo build                 # Debug
cargo build --release       # Optimized
cargo fmt && cargo clippy -- -W clippy::pedantic
```

### CLI Usage

```bash
# Minify one file (show what would change)
./target/release/tsrs-cli minify src/main.py --diff

# Minify one file (apply changes)
./target/release/tsrs-cli minify src/main.py --in-place

# Minify directory (dry-run with stats)
./target/release/tsrs-cli minify-dir ./src --dry-run --stats --output-json stats.json

# Create minification plan (for review/versioning)
./target/release/tsrs-cli minify-plan-dir ./src --out plan.json

# Apply pre-made plan
./target/release/tsrs-cli apply-plan-dir ./src --plan plan.json --out-dir ./src-minified

# Create minimal venv
./target/release/tsrs-cli slim . .venv --json
```

### Environment Variables

```bash
RUST_LOG=debug cargo test -- --nocapture  # Debug logging
RUST_LOG=tsrs=trace,rustpython=off        # Selective logging
```

---

## Website & Documentation Structure

### Build System

The project uses **MkDocs** with the **Material theme** to generate static documentation. The build process is configured in `mkdocs.yml` at the root of the repository.

**Key Configuration**:
- **Theme**: Material for MkDocs (provides modern styling and navigation)
- **Site URL**: https://georgepearse.github.io/tsrs/
- **Source Files**: `docs/` directory (markdown files)
- **Output**: `site/` directory (generated HTML, committed to repo for GitHub Pages)
- **Python Extensions**: pymdownx (highlight, superfences, inlinehilite), tables, admonition

### Documentation Source Files

```
docs/
├── README.md                    # Home page (project overview & usage)
├── AGENTS.md                    # AI agent guidance (this file, in docs/ too)
├── ALTERNATIVE_APPROACHES.md    # Design alternatives & rationale
├── API.md                       # Library API reference
├── CHANGELOG.md                 # Release notes & version history
├── CONTRIBUTING.md              # Contribution guidelines
├── MINIFY_DESIGN.md            # Algorithm specification & scope rules
├── TESTING.md                   # Test infrastructure & strategies
└── TEST_REPOS_SUMMARY.md        # Summary of test repositories
```

### Generated Website Structure

```
site/
├── index.html                   # Homepage (built from docs/README.md)
├── AGENTS/index.html            # Architecture guide
├── ALTERNATIVE_APPROACHES/index.html  # Design alternatives
├── API/index.html               # API reference
├── CHANGELOG/index.html         # Release notes
├── CONTRIBUTING/index.html      # Contributing guide
├── MINIFY_DESIGN/index.html     # Minification design
├── TESTING/index.html           # Testing guide
├── TEST_REPOS_SUMMARY/index.html # Test repo summary
├── search/                      # Search index (auto-generated)
├── assets/
│   ├── stylesheets/            # CSS (Material theme)
│   ├── javascripts/             # JS (Material theme + search)
│   └── images/                  # Images and favicon
├── sitemap.xml                  # SEO sitemap
└── 404.html                     # 404 error page
```

### Navigation Structure

The site navigation (from `mkdocs.yml`) is organized as:
- **Home**: README.md (landing page)
- **Getting Started**:
  - Contributing: CONTRIBUTING.md
  - Testing: TESTING.md
- **Documentation**:
  - API Reference: API.md
  - Minification Design: MINIFY_DESIGN.md
  - Test Repositories: TEST_REPOS_SUMMARY.md
- **Architecture & Design**:
  - Architecture Guide: AGENTS.md
  - Alternative Approaches: ALTERNATIVE_APPROACHES.md
- **Release Notes**:
  - Changelog: CHANGELOG.md

### Building & Deploying

**Install dependencies**:
```bash
pip install mkdocs mkdocs-material
```

**Build the site locally** (regenerates `site/` directory):
```bash
mkdocs build
```

**Serve locally** (preview at http://localhost:8000):
```bash
mkdocs serve
```

**Deployment**:
The `site/` directory is committed to the repository and served via GitHub Pages. To deploy:
1. Update markdown files in `docs/`
2. Run `mkdocs build` to regenerate `site/`
3. Commit both the source changes and the updated `site/` directory
4. Push to `origin/master` (GitHub Actions or manual deployment)

**GitHub Pages Configuration** (from repo settings):
- Source: `master` branch, `/` root directory (or `/docs` folder depending on setup)
- Custom domain: None (uses `georgepearse.github.io/tsrs/`)

---

## File Organization & Where to Find Things

### Source Code Structure

```
src/
├── lib.rs                 # Library root, public API exports
├── bin/
│   └── cli.rs             # CLI argument parsing and dispatch
├── imports.rs             # Import statement extraction
├── venv.rs                # Virtual environment analysis
├── callgraph.rs           # Function call graph, dead code detection
├── slim.rs                # Minimal venv creation
├── minify.rs              # Local variable minification
└── error.rs               # Error types

tests/                      # Integration tests (if any)

test_packages/
├── test_unused_function/  # Dead code detection test
├── test_minify/           # Minification test samples
└── test_slim_packages/    # 16 import pattern tests

mkdocs.yml                  # Documentation build configuration
docs/                       # Documentation source (markdown)
site/                       # Generated documentation (HTML, published)
```

### Where to Find Specific Things

| What | Where |
|------|-------|
| Minification exclusions (dunder, keywords) | `src/minify.rs` line ~50-150 |
| Python keyword list | `src/minify.rs` line ~100 |
| Builtin name list | `src/minify.rs` line ~120 |
| Name generation algorithm | `src/minify.rs` - `ShortNameGen` struct |
| Import pattern matching | `src/imports.rs` line ~100+ |
| Plan serialization | `src/minify.rs` - `MinifyPlan` struct |
| CLI command definitions | `src/bin/cli.rs` - `#[derive(Subcommand)]` |
| Venv discovery | `src/venv.rs` - `VenvAnalyzer::new()` |
| Call graph building | `src/callgraph.rs` - `CallGraphAnalyzer` |

---

## How to Contribute Effectively

1. **Before starting**: Check current issues and recent PRs (GitHub)
2. **Pick a task**: From "Future Work" section or GitHub issues
3. **Create a branch**: `git checkout -b feature/my-feature`
4. **Implement with tests**: Add unit tests for new logic
5. **Run checks locally**: `cargo fmt && cargo clippy -- -W clippy::pedantic && cargo test`
6. **Commit**: Follow conventional commits (`feat:`, `fix:`, `docs:`, etc.)
7. **Push & create PR**: Link to any relevant issues
8. **Wait for CI**: Ensure all tests pass
9. **Address review feedback**: Make requested changes
10. **Merge**: Maintainer will merge when approved

---

## Version History Quick Reference

### v0.2.0 (2025-11-01) - Current

**Major Features**:
- Encoding preservation (BOM, UTF-8, line endings)
- Nested function minification
- Diff improvements (`--diff-context`)
- Directory safety flags (hidden files, symlinks, `.gitignore`)
- Parallel processing with `--jobs N`
- JSON stats output (`--output-json`)
- Streaming support (stdin/stdout)
- Comprehensive error handling

**File Changes**:
- Enhanced `src/minify.rs` for nested scopes
- Updated `src/bin/cli.rs` with new flags
- Added `encoding_rs` and `ignore` dependencies

### v0.1.0 (Earlier)

**Basic Features**:
- Core minification
- CLI interface
- Basic venv slimming
- Plan generation

**Limitations**:
- Encoding loss during rewriting
- No nested function support
- Limited CLI options

---

## Next Steps for Contributors

**If improving code quality**: Review `MINIFY_DESIGN.md` for detailed algorithm specification

**If adding features**: Check `Future Work` section and GitHub issues

**If fixing bugs**: Use debug logging (`RUST_LOG=debug`) and test on `test_packages/`

**If documenting**: Update relevant `.md` file and ensure consistency with code

**Questions?** Check inline code comments and see `src/minify.rs` for detailed explanations of scope rules.

---

**Last Updated**: 2025-11-01
**Maintainer**: George Pearse
**Repository**: https://github.com/georgepearse/tsrs
