# Located harness contract

The concrete structure API is `visia_vision_agent_mcp.part_graph`, registered in
the VLM Chat tool catalog. The exact project name “vision-harness” has not been
confirmed. The two synthetic harnesses are generation/scoring loops; they contain
the part-graph API but do not define a separate object/part schema.

## Source and discovery

Contract pin: [VisiaAI/core fcb664472e2313be15a7f42b659997809a9a55df](https://github.com/VisiaAI/core/commit/fcb664472e2313be15a7f42b659997809a9a55df).
This published revision contains all source files and original test fixtures used
here. Private repository access may be required for these links.

Read-only inspection on 2026-10-10 located:

| tmux session | Checkout | Branch | Observed HEAD |
| --- | --- | --- | --- |
| `synthetic-harness-v2` | `/home/georgepearse/core-worktrees/synthetic-harness-v2` | `feat/synthetic-harness-v2` | `30ca7f62153da06eb6abc2305b49cb3d107c444a` |
| `synthetic-harness-gan` | `/home/georgepearse/core-worktrees/synthetic-harness-gan` | `exp/synthetic-harness-gan-compressors` | `ad79e9df209cb915325a09af0e6955fb471226ec` |

Neither session was interrupted. Both have byte-identical `part_graph.py` at the
pin (SHA256 `1c83ccf410a94eed8f6bf42cc920b78dd43eb16f3a535926fa53d21817642ce4`).
The GAN HEAD is local and was unavailable from the GitHub commit API; the
published contract revision above is the reproducible source reference.

Relevant files at the pin:

- `lib/python/vision_agent_mcp/visia_vision_agent_mcp/part_graph.py`: input types,
  link planning, coordinate conversion, graph output and surface construction.
- `lib/python/vision_agent/visia_vision_agent/numbering.py`: shared display numbering.
- `lib/python/vision_agent_mcp/visia_vision_agent_mcp/ui.py`: consumer object/edge parsers.
- `lib/python/vision_agent_mcp/visia_vision_agent_mcp/draw.py`: coordinate tolerance.
- `lib/python/vision_agent_mcp/tests/test_part_graph.py`: original unit-test fixtures.

`fixtures/upstream_contract.json` records full-file hashes and exact, unchanged
source definitions for the pure subset exercised offline. The two upstream JSON
fixtures preserve values from the named tests and carry revision/hash provenance.
They are unit-test fixtures, not reviewed images or training labels. Tests also
author a separate synthetic repeated-object example with hand-supplied logits;
its results establish decoding compatibility only.

## Input and consumer boundaries

`write_part_graph(image_id, dataset_id, objects, coords="normalized", ...)` takes
`PartObject` dictionaries:

| Field | Upstream meaning |
| --- | --- |
| `key` | String or integer identity unique within the call; normalized by stripping its string representation |
| `box` | Required `[x0, y0, x1, y1]`, normalized by default, or pixels with `coords="pixel"` |
| `class_name` / `class_id` | At least one needed by the writer; names resolve to existing classes |
| `part_of` | Optional single parent: another key in this call, or an existing object's display number |
| `caption`, `polygon`, `score` | Optional caption, polygon points in the selected coordinates, and instance score |

`part_of` points from part to whole. Missing, null or empty values plan no link.
Keys must be unique and local self-links/cycles are refused. Local keys take
precedence over display-number parsing. External display numbers require the
actual frame for resolution; persistence also enforces image/dataset membership
and acyclicity. There is no explicit uncertain-parent field: unknown supervision
must remain in training metadata. An out-of-frame parent must not be fabricated.
The read graph omits a parent not in its live rows and numbers that child as a
top-level object.

The writer accepts 1–400 objects and may reuse an existing annotation with the
same class and box IoU ≥ 0.9. Its result is a text/image/surface envelope, rather
than the input dictionaries. Stable annotation IDs are distinct from recomputed
dotted display numbers. `GraphObject` uses integer `id`/`part_of`, normalized
`box`, `label`, `number`, `depth` and `parts`. `GraphEdge` uses `kind`, `source`
and `target`; `part_of` is child ID → parent ID. Other supported surface kinds
are `contains`, `touches`, `occludes` and `overlaps`; the harness computes these
from geometry, and they are not learned/persisted membership labels.

The decoder emits the call-local `PartObject` input subset. It uses supplied
Q×(Q+1) parent logits, with the last column meaning no parent, and keeps query
keys across presence filtering. Invalid retained links raise for inspection.
It deliberately accepts only finite, ordered normalized boxes: this is stricter
than the upstream writer's clamping/sorting. Its `score` is instance presence,
not relationship confidence. Class-name existence requires the external catalog.
Empty output means no retained instances; skip the writer in that case. A caller
must respect the writer's 400-object limit.

## Offline verification

From the personal core root, with Python 3.12+ and no extra dependencies:

```bash
PYTHONPATH=projects/vision-mesh python3.12 -m unittest discover -s projects/vision-mesh/tests -v
python3.12 projects/vision-mesh/verify_contract.py /home/georgepearse/core-worktrees/synthetic-harness-v2
```

The first command uses pinned pure definitions without importing services. It
checks decoder JSON → upstream link planning → simulated persisted rows → actual
graph helpers → consumer object/edge parsers. The second reads the source checkout
and verifies pinned full-file hashes, fixture values and current relevant
definitions, detecting contract drift. It does not import or run the harness.

No database round-trip, live surface rendering, model inference, training,
precision/recall or latency benchmark is claimed. Remaining dependencies are a
reviewed image/relationship dataset, trained encoder/heads, class vocabulary,
target device and quality/latency budgets. Confirm the locator if the user means
a different “vision-harness” contract. Production writes and end-to-end live
consumer verification are outside this scaffold.
