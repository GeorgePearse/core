# engrim_trax

Imports an [engrim](https://github.com/timgordontg/engrim) memory store into
[trackinizer](https://github.com/rekursiv-ai/trackinizer). Where engrim's flat records have to become
trackinizer's typed Inquiries, Jev (`typesafe-ai/jev`, through `memtype.jev`) decides the kind and the typed
fields. Regexes only pre-fill a question's options (URLs, SHAs, clauses, `name=value` pairs); they never classify.

Three types, deliberately:

- `Record` (`records.py`): one `memories` row from a read-only SQLite **copy** (never the live `~/.engrim/memory.db`).
- `Mapping` (`classify.py`): the Jev-decided trackinizer kind, typed fields, status, title, labels and description.
- `Importer` (`importer.py`): idempotent submit through `trackinizer.client.Client`, with a persisted
  `engrim_id -> inquiry uuid` map so a re-run is a no-op. Each submit also carries a deterministic
  `idempotency_key` (uuid5 of the engrim id), so a re-run against the same server replays even if the map is lost.

## Per record

One Jev call, eight questions over the record text (`summary`, `detail`, type, tags, status, project, ts):

| question | type | used for |
|---|---|---|
| `kind` | choice over Issue, Belief, Experiment, WebResult, Paper, CodeChange, AgentSession | the inquiry kind; engrim-type conventions are given as hints in the instructions, not as rules |
| `finished`, `abandoned` | boolean | Issue `status` (complete / abandoned / active) |
| `issue_kind` | choice feature / bug / task / question | `Issue.issue_kind` |
| `priority` | choice p0..p4 / unknown | `Issue.priority` (0, 10, 20, 30, 40) |
| `judgement` | choice proven / disproven / unproven / undecidable | `Belief.judgement` |
| `true_now` | boolean | `Belief.confidence` = its probability |
| `measured` | boolean | Experiment status; which facts may carry evidence edges |
| `title` | choice over clauses of the summary, only when the summary exceeds 160 chars | the title |

Experiments get a second call: `outcome` and `config` as a choice over the record's clauses, and `metrics_ok`
confirming the regex-found `name=value` pairs, which are then logged as metric points (step 0).

Bands (memtype's numbers): kind p >= 0.8 applied; 0.5-0.8 applied and labelled `jev:low-confidence`; below 0.5
the engrim type's default kind (state -> Issue, fact / decision / feedback / user -> Belief, reference -> WebResult
when it has a URL) and the label `jev:fallback`.

Common fields: `labels` = engrim tags + `engrim` + `engrim:<type>` + `project:<basename>` (+ `engrim:superseded`);
`owner` = george; `description` = summary + detail + a provenance block (engrim id, type, status, ts, project,
source, origin_agent, tags, links, Jev kind and p). The create API has no `created` field, so records are
submitted oldest-first and the engrim `ts` lives in the provenance block.

## Edges

- `produced_by`: a record -> the older records it cites by engrim id (`#1234`, not preceded by PR/issue), and the
  most recent older record in the same project that shares a PR number or artefact id (at most 3).
- `supersedes`: for each engrim-superseded record, candidates in the same project within 60 days with tag/link
  overlap or a citation (cap 5); Jev boolean "is B the corrected version of A"; the best candidate with p >= 0.8.
- `proves` / `favors`: from Experiments (`proves`) and measured facts (`favors`) to the 3 nearest older Beliefs by
  engrim's model2vec vectors; Jev boolean "does A bear on B" (p >= 0.8) and "does A support B" for the sign of
  the valence (+-0.5).

The server only rejects cycles, not a parent newer than its child, so `drop_newer` enforces that invariant here
and counts what it dropped.

## The raw session log

`sessions.py` maps each `(project, session)` of engrim's `log` table to an AgentSession (`cli` claude, `started` /
`ended` from min / max ts, `cli_session_id` = the Claude session id) and each row to a `UserMessage` /
`AssistantMessage` IR record (`timestamp`, `content`, `extra` = engrim log id, msg uuid, role) through
`trackinizer.types.session_records.SessionRecordRow` and `append_records`. Only `content` is imported; `raw`
(the native JSONL line, 2.5 GB of the 2.9 GB store) stays in SQLite.

## Run

```bash
sqlite3 ~/.engrim/memory.db ".backup /var/tmp/engrim-trax/memory.db"
trackinizer --no-auth --host 127.0.0.1 --port 8766 --datadir /var/tmp/engrim-trax/pgdata
export AI_GATEWAY_API_KEY=...
uv run --with trackinizer python -m engrim_trax.cli import --limit 50          # first pass
uv run --with trackinizer python -m engrim_trax.cli import --sessions          # everything
uv run --with trackinizer python -m engrim_trax.cli report                     # counts by kind vs engrim type
uv run --with trackinizer python -m engrim_trax.cli spotcheck --n 40 --seed 7  # sample for a manual read
uv run --with trackinizer python -m engrim_trax.cli wipe                       # fresh PGlite dir + restart (tmux)
uv run --with trackinizer pytest lib/python/engrim_trax/tests
```

Every Jev answer is appended to `/var/tmp/engrim-trax/jev_answers.jsonl` keyed by question set, record id and
content hash, so re-runs ask Jev nothing and the mapping is auditable.
