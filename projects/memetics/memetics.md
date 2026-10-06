# Memetics

The ideas this repository implements, where each one lives, and where it came from. The Python sources
below are the first implementation (PR #1) that this Rust code was ported from. Check the anchors with
`memetics ideas --check`; the format is described in the README.

## shared-watch
- idea: One conditional poll (ETag) per upstream repository and ref is shared by every listener that watches it; webhooks only wake that same check, and new listeners catch up without a fresh fetch.
- source: code swh:1:rev:77bb8cc88cb3be16ebb3a0c9f36626672b451094;origin=https://github.com/GeorgePearse/memetics;path=/memetics/engine.py;lines=56-84 repo=https://github.com/GeorgePearse/memetics symbol=Engine.poll hash=5adb9f6a2561e3df
- source: code swh:1:rev:77bb8cc88cb3be16ebb3a0c9f36626672b451094;origin=https://github.com/GeorgePearse/memetics;path=/memetics/db.py;lines=150-183 repo=https://github.com/GeorgePearse/memetics symbol=Store.enqueue hash=55dfa80b2d8959a2
- code: src/engine.rs symbol=Engine::poll hash=4f6ef89bedb1c5f5 lines=247-286
- code: src/db.rs symbol=Store::enqueue hash=f3e9c78b60175b03 lines=235-285

## shared-change-index
- idea: Each upstream before/after change and each changed blob is fetched and indexed once per repository and content SHA, then reused by every listener (SQLite FTS over changed UTF-8 blobs).
- source: code swh:1:rev:77bb8cc88cb3be16ebb3a0c9f36626672b451094;origin=https://github.com/GeorgePearse/memetics;path=/memetics/git.py;lines=92-152 repo=https://github.com/GeorgePearse/memetics symbol=Git.change hash=03faade4022bee87
- code: src/git.rs symbol=Git::change hash=b4f1c25ebe97ddcb lines=248-318
- code: src/db.rs symbol=Store::cache_blob hash=ee6c2548a292ea6d lines=331-346

## write-boundary
- idea: Model edits may only touch the listener's destination paths and test paths; a trailing slash authorises a directory recursively, anything else exactly one file, and symlinks or .git are never written.
- source: code swh:1:rev:77bb8cc88cb3be16ebb3a0c9f36626672b451094;origin=https://github.com/GeorgePearse/memetics;path=/memetics/config.py;lines=44-48 repo=https://github.com/GeorgePearse/memetics symbol=in_scope hash=6ba4c52b3c02bbb5
- code: src/config.rs symbol=in_scope hash=da19afe69d0873e7 lines=88-93
- code: src/git.rs symbol=Git::apply hash=36263cbdfb1d4681 lines=406-465

## adaptation-prs
- idea: An adaptation is delivered as a draft PR that is created or updated append-only, persists its delivery intent before any external write, preserves human-written PR prose and branches, revalidates when the base moves, and never merges.
- source: code swh:1:rev:77bb8cc88cb3be16ebb3a0c9f36626672b451094;origin=https://github.com/GeorgePearse/memetics;path=/memetics/engine.py;lines=344-425 repo=https://github.com/GeorgePearse/memetics symbol=Engine.deliver hash=e2d05b92681bb5f6
- code: src/engine.rs symbol=Engine::deliver hash=042e0a11377fbd28 lines=686-813
- code: src/git.rs symbol=Git::publish hash=4c94eb83f29bcf6e lines=484-521

## sandboxed-validation
- idea: Trusted validation commands from the manifest run on a disposable copy in Docker with no network, no credentials, a read-only root, dropped capabilities and resource limits.
- source: code swh:1:rev:77bb8cc88cb3be16ebb3a0c9f36626672b451094;origin=https://github.com/GeorgePearse/memetics;path=/memetics/validation.py;lines=13-96 repo=https://github.com/GeorgePearse/memetics symbol=DockerValidator.run hash=1608b9479324c926
- code: src/validation.rs symbol=DockerValidator::command hash=6734b6bddf0c2dde lines=44-120

## signed-wakeups
- idea: GitHub push webhooks are accepted only with a valid HMAC signature and a fresh delivery id, and only reset the shared watch's poll timer; their payload SHA is never trusted.
- source: code swh:1:rev:77bb8cc88cb3be16ebb3a0c9f36626672b451094;origin=https://github.com/GeorgePearse/memetics;path=/memetics/server.py;lines=25-137 repo=https://github.com/GeorgePearse/memetics symbol=make_server hash=cfe0f370f394671d
- code: src/server.rs symbol=App::post hash=44c6237cbb436156 lines=96-179

## symbol-anchors
- idea: Code is anchored by tree-sitter symbol plus a blake3 hash of its comment- and whitespace-normalised text with its own name masked, so anchors re-resolve as same place, moved or renamed, edited, or lost.
- source: article https://swhid.org/specification
- source: article https://docs.swimm.io/features/keep-docs-updated-with-auto-sync/
- code: src/anchors.rs symbol=symbols hash=72144d932948fbe2 lines=202-222
- code: src/anchors.rs symbol=resolve hash=32cf0201521556a2 lines=263-319

## idea-drift-gate
- idea: A commit touching idea code is classified same, refines, different or removes; a structural check settles unchanged or moved code without a model, the judge must cite its evidence, and only a confident different or removes verdict without a memetics.md amendment fails.
- source: article https://github.com/Wilfred/difftastic
- source: article https://foremerge.com/blog/31-questions-coordinating-parallel-coding-agents/
- code: src/judge.rs symbol=check_commit hash=f559076c029acb81 lines=557-840
- code: src/judge.rs symbol=decide hash=3f42e03689a77c3f lines=496-524
- code: src/judge.rs symbol=validate_verdict hash=1803e3c8b149402a lines=121-162

## symbol-triggered-adaptation
- idea: An adaptation is triggered only when the normalised hash of an anchored upstream symbol changes, and a bounded agent with code lookup in both repositories and validation feedback decides relevance and writes the port.
- source: paper arXiv:2510.22396 section="PortGPT agent"
- source: article https://cohere.com/blog/automating-fork-maintenance-with-ai-agents
- code: src/engine.rs symbol=changed_symbols hash=6562f4ababb52654 lines=50-84
- code: src/model.rs symbol=Model::adapt hash=c72d5e42b29b65b2 lines=189-270
