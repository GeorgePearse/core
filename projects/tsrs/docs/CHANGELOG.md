# Changelog

All notable changes to this project will be documented in this file.

## 0.3.0 – 2025-11-01

### Major Features

- **Function call graph analysis with dead code detection** 🆕
  - Interprocedural analysis: properly track calls between functions
  - Entry point detection: identify test functions, main blocks, and `__all__` exports
  - Reachability analysis: compute which functions are reachable from entry points (BFS)
  - Dead code detection: conservatively identify unreachable functions
  - Protects dunder methods, exported functions, and framework-decorated functions
  - New CLI flag: `--remove-dead-code` for both `minify` and `minify-dir` commands

### Testing

- Added 16 comprehensive unit tests for call graph analysis
  - Entry point detection (main blocks, test functions, exports)
  - Call edge extraction and reachability analysis
  - Dead code detection with protective filtering
  - Mutual recursion, nested functions, and decorator handling
- Total test coverage: 61 tests passing (45 existing + 16 new)

### API Changes

- New public module: `tsrs::callgraph`
- New struct: `CallGraphAnalyzer` with methods:
  - `analyze_source(package, source)` - Analyze Python code
  - `analyze_file(path, package)` - Analyze a file
  - `compute_reachable()` - Compute reachable functions from entry points
  - `find_dead_code()` - Find unreachable functions
  - `get_entry_points()`, `get_nodes()`, `get_edges()` - Access graph structure

### Documentation

- Updated AGENTS.md with call graph architecture details
- Updated API.md with comprehensive call graph module documentation
- Added examples for dead code detection workflows

### Notes

- Call graph analysis is per-package only (cross-package analysis deferred)
- Conservative approach: protects dunders, exports, and test functions
- Ready for Phase 4b: integration with minify logic

---

## 0.2.0 – 2025-11-01

- Preserve file encodings, BOMs, line endings, and trailing-newline state when rewriting
  Python sources, ensuring byte-for-byte compatibility where possible.
- Support nested-function planning and rewriting, enabling safe local renames inside
  closures and class bodies.
- Expand CLI glob controls: explicit `--glob-case-insensitive`, default behaviour on
  Windows, pattern include/exclude files, and `--max-depth` traversal limits.
- Add diff UX controls (`--diff` with `--diff-context`), dry-run output, and `--stats`
  JSON reporting (including `--output-json`).
- Introduce directory safety flags: include/exclude hidden files, follow symlinks,
  respect `.gitignore` via `--respect-gitignore`, and protect against writing inside the
  source tree.
- Extend single-file and directory commands with stdin/stdout streaming, fail-fast
  options (`--fail-on-change`, `--fail-on-bailout`, `--fail-on-error`), and unwritable
  output detection.
- Add CLI tests covering encoding preservation, glob behaviour, JSON output failure
  cases, gitignore integration, and parallel traversal reporting helpers.
