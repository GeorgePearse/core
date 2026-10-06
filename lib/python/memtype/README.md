# memtype

A sidecar that gives [engrim](https://github.com/timgordontg/engrim) memory records typed structure using Jev
(`typesafe-ai/jev`), a typed decision model that answers boolean and choice questions with probabilities and never
writes text. engrim itself is never modified: memtype reads a **copy** of `~/.engrim/memory.db` and writes its own
SQLite sidecar, keyed by engrim memory id.

Per record:

1. One Jev call with five questions: is it durable, which of 27 record types (`schema.json`), context level
   (global > repo > component > worktree > session), context anchor, and time window.
2. One Jev call that fills every role of the chosen type. Entity roles pick from an entity shortlist (tag
   gazetteer + regex mentions, `new:` for unseen ones). Value roles pick from regex spans and clauses.
3. Relations to the top-4 older neighbours (model2vec vectors ⊕ FTS5 BM25, RRF), one call per pair. Each call asks
   a 5-way `same / supersedes / refines / contradicts / independent` choice, gated by two booleans: same subject,
   and older one stale.

Over the whole store:
- a deterministic key check: same type, key roles and context, but a different value
- Jev `contradicts` relations
- transitive path composition over `relation` facts

Every field keeps its probability. The band policy is: ≥0.8 accept, 0.5–0.8 review, <0.5 empty (raw kept).

```bash
sqlite3 ~/.engrim/memory.db ".backup /tmp/engrim-copy.db"
export AI_GATEWAY_API_KEY=...
python -m memtype.cli --db /tmp/engrim-copy.db --sidecar side.db structure      # incremental
python -m memtype.cli --db /tmp/engrim-copy.db --sidecar side.db conflicts --method key
python -m memtype.cli --db /tmp/engrim-copy.db --sidecar side.db show 1502
python -m memtype.cli --db /tmp/engrim-copy.db --sidecar side.db eval --gold gold.jsonl \
    --supersede supersede_labels.jsonl --out report.json --baseline             # needs GEMINI_API_KEY too
python -m memtype.report report.json /tmp/engrim-copy.db side.db report.html [--public]
```

Tests use `FakeJev`. Set `MEMTYPE_LIVE=1` to also run one live smoke call. Results: `docs/engrim_jev_structurer.html`.
