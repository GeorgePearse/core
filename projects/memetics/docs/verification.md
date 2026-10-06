# Implementation verification

## Rust rewrite (2026-10-06)

The Rust binary replaces the Python package. Evidence from this branch:

- `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` and `cargo test` pass. The suite has 49 tests, plus one ignored live Jev test: all 24 Python scenarios ported (boundaries, engine, server), plus anchors, manifest, drift-policy, trigger and agent tests.
- **State compatibility.** Registering `examples/deepseek-harness-listener.json` with the Rust and the Python implementations gives the same source id (`17ce9147…`) and config hash (`4b26997a…`). The Rust CLI also reads a Python-created state directory.
- **CLI.** `register`, `status`, `pause`/`resume`, re-register (pause stays sticky), `search`, `show-job` and `retry` (refused for a non-blocked job, exit 2) were run against a temporary state directory.
- **Dashboard.** `serve --port 8786` (8776 was in use by the Python service) answered `/health` 200, `/` with the dashboard, and `/api/status`. Writes without a token got 401 and an unknown job got 404. Ctrl-C shut it down cleanly.
- **Real upstream, `run --once --force-poll`.** Three throwaway listeners watched `deepseek-ai/deepseek-harness:master`, sharing one watch, with the private `GeorgePearse/memetics-demo` as the read-only destination:
  - The watch made one GitHub poll for all three listeners and stored the ETag; a second run made a conditional poll and enqueued nothing new.
  - The baseline at the current head created no job.
  - A merge-commit baseline mirrored the real repository (partial clone) and finished `irrelevant` (tree unchanged).
  - A release baseline (300 changed files) was `blocked` at the 100-file context bound after indexing 92 blobs, which `search` then returned.
  - No model calls were made and no PR was created; the run stopped before PR creation by design.
- **Symbol trigger.** `memetics cite` computed `ToolResultPruner.pruneContent` at five upstream commits that edited its file (`f4a32db`, `ec3560c`, `b5e7fca`, `37abcb7`, `27bf103`) and their parents. Its normalised hash stayed `0e5c1a2e86d5cd0e` throughout, so none of those edits would trigger an adaptation.
- **Live Jev drift checks.** These are three hand-made commits against a binary-search idea (`cargo test --test live_jev -- --ignored`):

  | Commit | Jev (`typesafe-ai/jev`, Vercel AI Gateway) | Chat judge (`typesafe/jev-router`, OpenRouter) |
  |---|---|---|
  | Pure rename of locals | `same_idea`, 1.00 | `same_idea`, 1.00 |
  | Overflow-safe midpoint + `match` | `refines_idea`, 0.53 (p=0.65) | `refines_idea`, 0.99 |
  | Linear scan replaces binary search | `different_idea`, 0.89 | `different_idea`, 0.95 |

  Each verdict cited anchor `a1` and its hunk(s). Jev cost about $0.0001 in total and OpenRouter under $0.10.

## Python implementation (PR #1)

Verified on 2026-10-06 using a private, controlled repository owned by George Pearse. No production implementation was changed or merged.

## Real upstream → real model → real draft PRs

Two enabled listeners share `GeorgePearse/memetics-demo:upstream` and independently adapt two destination modules on `demo-base`:

- Baseline: `295d1299e5f965a0025b6dccf22691d0e1d53cc0`.
- Upstream change: `b2daf586171b5c7041ec583cb36661975187c0aa` changes linear retry delays to capped exponential delays.
- [Primary adaptation PR #1](https://github.com/GeorgePearse/memetics-demo/pull/1): `src/backoff.py` and its tests; generated head `ad202c9f3a0e46eae6e83478beb6212643602d09`.
- [Secondary adaptation PR #2](https://github.com/GeorgePearse/memetics-demo/pull/2): `src/secondary_backoff.py` and its tests; generated head `d2ac677ec87e44c013977b18f8f8d9e0514a45bb`.

The worker used the real GitHub API, real Git fetch/push, and two xAI `grok-4.7` calls. Both PRs are drafts. Each changes the formula through the existing local function name and adds regression cases. Validation passed inside `python:3.13-slim` with network disabled. The image available during verification had digest `sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c`.

Independent negative-control checks restored the old implementation in disposable copies while retaining the generated tests. Both test suites failed on the old behavior. Thus the added tests distinguish the intended behavioral change, rather than merely passing on either version.

After publication, persisted state contained **two jobs, two model calls, one shared change record and two indexed blobs**. Service restart and subsequent polling retained the same two jobs and proposals without another model call. DeepSeek's disabled example performed zero upstream polls.

## Runtime and interface

A user systemd service runs on the development host at `http://127.0.0.1:8776`. Credentials are outside the checkout, and state is under `~/.local/share/memetics`. This is a local service, not a public deployment.

Browser verification covered dashboard loading, real listener/job/PR data, reload, a narrow viewport, and console errors. `/health` returned HTTP 200. The dashboard displays observed revisions and the two draft PR links; adopted revisions remain empty because neither PR has merged.

## Automated checks

`python -m unittest discover -s tests -v` passes 24 tests covering real local Git operations plus controlled external boundaries: shared indexing, conditional polling and late registration, pause behavior, interrupted work, lost PR-create responses, append-only updates, human edits, decline and merge reconciliation, destination-base movement, private/public separation, write scope, budgets, upstream history divergence, API auth, signed webhook deduplication, GitHub App JWT creation/token caching, rate-limit reset handling, and incomplete model output.

The source distribution and wheel build successfully with `uv build`. CI runs the suite and package/CLI installation on Python 3.11 and 3.13. This repository has no pre-commit configuration, so `prek run --from-ref origin/main --to-ref HEAD` is unavailable here.

The DeepSeek listener remains disabled until its illustrative destination is replaced by a real repository, authorized paths and runnable checks. GitHub App signing/token caching is unit-tested; this live run used the owner's existing GitHub CLI authentication.
