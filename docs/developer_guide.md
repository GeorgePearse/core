# Repository Guidelines

**Important: All pull requests should be opened against this repository: https://github.com/GeorgePearse/Genesis**

## Project Structure & Module Organization
- `genesis/`: core Python package for evolution runners, job configs, and database utilities.
- `configs/`: Hydra configuration presets; start new experiments by extending an existing YAML here.
- `tests/`: pytest suite covering edit strategies and evaluation tooling; mirror source layout when adding modules.
- `examples/`: runnable task templates, including notebooks, to demonstrate common workflows.
- `webui-react/` and `website/`: front-end clients; keep UI changes isolated from the core engine.

## Build, Test, and Development Commands
- `uv venv --python 3.12 && source .venv/bin/activate`: create and activate the recommended environment.
- `uv pip install -e .[dev]`: install the package with developer tooling.
- `genesis_launch variant=circle_packing_example`: run a reference experiment via the CLI entrypoint.
- `pytest`: execute the full unit test suite; use `pytest tests/test_edit_circle.py -k "smoke"` while iterating.
- `black genesis tests && isort genesis tests && flake8 genesis tests`: format and lint before submitting.

## Coding Style & Naming Conventions
- Python 3.12+, 4-space indentation, and type hints for new public APIs.
- Modules, files, and functions use `snake_case`; classes follow `PascalCase`.
- Keep experiment configs declarative; prefer Hydra overrides (`genesis_launch +foo=bar`) over ad-hoc scripts.
- Document non-obvious behaviors with concise docstrings referencing evaluation assumptions.
- For creating new tasks, see the [Creating Custom Tasks](creating_tasks.md) guide.

## Testing Guidelines
- Favor pytest parameterization to cover candidate mutation edge cases.
- Place new tests alongside related modules under `tests/` using the `test_<feature>.py` pattern.
- Ensure evolution runs include deterministic seeds when feasible; capture fixtures for expensive evaluators.
- Add regression tests whenever logic affects scoring, database migrations, or patch synthesis.

## Commit & Pull Request Guidelines
- Follow Conventional Commit prefixes observed in history (`feat:`, `fix:`, `docs:`); keep the subject under 72 chars.
- Squash noise commits locally; PRs should include a one-paragraph summary plus CLI or screenshot evidence for UI changes.
- Link tracking issues and note required credentials or configs in the PR body.
- Request review once CI (formatting + pytest) is green; highlight remaining risks or TODOs inline.

## Configuration & Secrets
- Store API keys in `.env` (see `docs/getting_started.md`); never commit secrets or experiment artifacts.
- For multi-node or E2B runs, duplicate configs into `configs/custom/` and document cluster dependencies in the PR.

## Merging Upstream Updates (Syncing with SakanaAI/ShinkaEvolve)

The Genesis repository is a fork/derivative of [SakanaAI/ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve). We maintain a different package name (`genesis` instead of `shinka`) and custom features (E2B integration, etc.), which requires care when merging upstream updates.

See [E2B Integration](e2b_integration.md) for details on our cloud sandbox features.

**Workflow:**

1.  **Configure Remote:** Ensure you have the upstream remote configured:
    ```bash
    git remote add upstream https://github.com/SakanaAI/ShinkaEvolve.git
    ```

2.  **Commit Local State:** **Crucial:** Ensure all your local changes are committed before merging. Git's rename detection relies on comparing the file content. If you have uncommitted changes (especially import renames), git might treat files as deleted/added instead of renamed, causing massive conflicts.

3.  **Fetch and Merge:**
    ```bash
    git fetch upstream
    git merge upstream/main
    ```
    *   Git usually detects the `shinka/` -> `genesis/` folder rename automatically if the file contents are similar enough.
    *   If you see `CONFLICT (file location)`, git likely detected the rename but needs confirmation for new files.

4.  **Resolve Conflicts:**
    *   **New Upstream Files:** If upstream added a file in `shinka/new_file.py`, git might place it there. Move it to `genesis/new_file.py` using `git mv`.
    *   **Imports:** Upstream changes will re-introduce `from shinka...` imports. You must revert these to `from genesis...` in conflict resolution.
    *   **Config Defaults:** Be careful with `pyproject.toml` and `dbase.py`. Preserve our dependencies (e.g. `e2b`, `google-generativeai`) and config defaults (e.g. `db_path` optionality).

5.  **Update Dependencies:**
    ```bash
    python3 -m pip install .
    ```

6.  **Verify:** Run a quick evolution task (e.g., `mask_to_seg_example`) to ensure the system works with the updates.

## Language Support

Genesis primarily orchestrates the evolution process in Python, but it can optimize code in any language (e.g., Rust, C++, CUDA) provided you supply a suitable evaluator.

### Optimizing Rust, C++, or Other Compiled Languages

To optimize a compiled language like Rust:

1.  **Initial Program:** Create your `initial.rs` file.
2.  **Evaluator Script:** Create a Python script (e.g., `evaluate.py`) that:
    *   Accepts the path to the candidate code (e.g., `main.rs`).
    *   Compiles the code (e.g., using `rustc` or `cargo build`).
    *   Runs the binary against test cases.
    *   Returns metrics (score, correctness) to Genesis via JSON or `run_genesis_eval`.
3.  **Configuration:** Set `language: rust` in your task config. This ensures the LLM uses correct syntax highlighting and comments when generating patches.

Example structure:
```
examples/rust_task/
  initial.rs
  evaluate.py  # Wraps rustc and execution
```
