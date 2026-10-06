# Changelog

All notable changes to this project will be documented in this file.

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
