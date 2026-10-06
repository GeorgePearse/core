# Selected project copies

Ten substantial public GeorgePearse repositories, copied on **6 October 2026**.
These are actual tracked files under `projects/<repository>/`, not submodules or
links that require the original repositories to remain checked out.

Selection considered implemented content, sustained personal development, tests,
documentation, benchmarks, and coverage across useful project areas. The commit
counts below are commits GitHub attributes to GeorgePearse on the pinned branch;
they are evidence of activity, not a quality score. Upstream histories were not
counted as personal effort. Memetics replaces LinearManager at the owner's request and was made public before
import. Its account-attributed commit count was not assessed; the other counts
are retained from the original inventory.

| Project | Purpose | Account-attributed commits | Tracked files | Pinned source |
| --- | --- | ---: | ---: | --- |
| [Genesis](Genesis/) | Program evolution platform | 97 | 343 | [0f17748a](https://github.com/GeorgePearse/Genesis/tree/0f17748a4c8c6dbd53de8bdbd7e13d92da8f1a0c) |
| [squeeze](squeeze/) | Dimensionality reduction | 83 | 564 | [2397360d](https://github.com/GeorgePearse/squeeze/tree/2397360df5833fcfc5a575b9188379e38681103f) |
| [bayesian_filters](bayesian_filters/) | Bayesian filtering library | 79 | 135 | [9cef532e](https://github.com/GeorgePearse/bayesian_filters/tree/9cef532e6df9d05a23a440e76a311e6730950b89) |
| [mcp-tui-test](mcp-tui-test/) | Terminal UI testing over MCP | 16 | 32 | [bbdd9003](https://github.com/GeorgePearse/mcp-tui-test/tree/bbdd9003eaefd0609d86707abdb5d32d1540b25c) |
| [rust-copy-paste](rust-copy-paste/) | Computer-vision augmentation | 83 | 218 | [01cdbbe8](https://github.com/GeorgePearse/rust-copy-paste/tree/01cdbbe877fa9946a02fd6e0b230878ef001b2df) |
| [vision-agents](vision-agents/) | Vision experiments and tooling | 118 | 69 | [d6bbc028](https://github.com/GeorgePearse/vision-agents/tree/d6bbc028e44f9d811e886217fb21d70718b00621) |
| [tsrs](tsrs/) | Python analysis and slimming in Rust | 50 | 224 | [6ecb112f](https://github.com/GeorgePearse/tsrs/tree/6ecb112f4f7ba8868804ed9d5cb9e71ca8002de0) |
| [optillm-rs](optillm-rs/) | LLM inference strategies in Rust | 47 | 373 | [78e540f3](https://github.com/GeorgePearse/optillm-rs/tree/78e540f3c4a909a39eaf3fe2e2a2fa99350c54f6) |
| [memetics](memetics/) | Upstream implementation listeners and idea provenance | Not assessed | 32 | [269e3085](https://github.com/GeorgePearse/memetics/tree/269e30854d1b056b6990d5ff8f538e7f85f4f938) |
| [evaluator](evaluator/) | Coding-agent evaluation | 37 | 61 | [f9d2e816](https://github.com/GeorgePearse/evaluator/tree/f9d2e8166f2b33b94104fc330c79ffd3302f0c39) |

## What was already in core

Before this import, core contained the Genesis Python/Rust platform and web UI,
Squeeze code under `lib/python/squeeze` and `lib/rust/squeeze`, a reference library
of 16 algorithms in Python/Rust/TypeScript/Go with an MCP server, and supporting
configuration, tests, examples, documentation, SQL migrations, and infrastructure.
The new `projects/Genesis` and `projects/squeeze` directories are complete standalone
source snapshots. They do not overwrite or replace those existing integrations.

## Why these ten

- **Genesis**: 97 account-attributed commits; Python orchestration, Rust backend, frontend, tests, deployment tooling, and documentation.
- **squeeze**: 83 account-attributed commits; Python/Rust algorithms, benchmark material, tests, and extensive documentation.
- **bayesian_filters**: 79 account-attributed commits; broad filtering APIs, reference tests, examples, and documentation.
- **mcp-tui-test**: 16 account-attributed commits; Python and Go implementations, tests, examples, and the recently merged Material documentation.
- **rust-copy-paste**: 83 account-attributed commits; Rust implementation, Python packaging, benchmark material, and test fixtures.
- **vision-agents**: 118 account-attributed commits; active-learning runner, agent tooling, frontend, tests, and presentation material.
- **tsrs**: 50 account-attributed commits; CLI/library code, Python integration, substantial test fixtures, and design documentation.
- **optillm-rs**: 47 account-attributed commits; multi-crate implementation, CLI, tests, benchmarks, and integration guides.
- **memetics**: Selected by George to replace LinearManager; Rust listeners, shared update processing, draft adaptation PRs, idea manifests, drift detection, and tests.
- **evaluator**: 37 account-attributed commits; evaluation code, sandbox integration, tests, and documentation for agent and diff evaluation.

## Working with the copies

Each project retains its own README, dependency files, source, tests, configuration,
license notices, and agent instructions. Follow that project's documented commands
from its own directory and use an isolated environment. These projects have not
been combined into the root Python package or Rust workspace.

The root pre-commit configuration excludes copied project trees so that its hooks
do not silently reformat imported source. Select that configuration explicitly:

```bash
prek run --config .pre-commit-config.yaml --from-ref origin/main --to-ref HEAD
```

Without `--config`, newer prek versions can discover and run the copied projects'
nested configurations. Run those intentionally only when developing that project.
Project workflows are retained under their nested `.github/` directories; GitHub
Actions only discovers the root workflow directory, so those workflows are not
automatically installed as monorepo jobs.

The [manifest](manifest.json) records the source repository, branch, exact commit,
Git tree ID, file count, license paths, and any LFS pointers or symlinks. Existing
license notices remain authoritative for their respective projects; the root
license does not relicense the imported work. A null detected license means GitHub
did not identify a repository license, not that unrestricted reuse is granted.

Nine snapshots use **default branches**. Memetics uses the unmerged Rust
implementation from [PR #2](https://github.com/GeorgePearse/memetics/pull/2),
branch `feat/rust-rewrite`, pinned at `269e3085`; its default branch contains
only a README. Importing this snapshot does not merge that source PR.
For example, the optional Rust backend and uv refresh in bayesian_filters PRs
[#141](https://github.com/GeorgePearse/bayesian_filters/pull/141) and
[#140](https://github.com/GeorgePearse/bayesian_filters/pull/140) were still unmerged
at capture time and are not part of its imported default-branch tree.
Original commit histories, issues, releases, secrets, and untracked local files
are not copied. Any Git LFS pointer remains a pointer; external payloads are not
silently downloaded or claimed as included. See each manifest entry for details.

## Verify the imported content

After committing, run this from the monorepo root. A matching Git tree ID verifies
all tracked filenames, file contents, executable modes, and symlink targets against
the source snapshot without requiring network access or executing project code.

```bash
python - <<'PYVERIFY'
import json
import subprocess
from pathlib import Path

manifest = json.loads(Path("projects/manifest.json").read_text())
for project in manifest["projects"]:
    actual = subprocess.check_output(
        ["git", "rev-parse", f"HEAD:{project['path']}"], text=True
    ).strip()
    assert actual == project["source_tree"], project["name"]
    print(f"Verified {project['name']}: {actual}")
PYVERIFY
```

This verifies the committed snapshot, not uncommitted working-tree changes and not
the runtime correctness of every copied application. Use `git status` to inspect
local edits. Before a future refresh, inspect changes against the pinned source,
preserve local work, and update provenance in the manifest. Do not assume copies
will automatically stay in sync with their standalone repositories.
