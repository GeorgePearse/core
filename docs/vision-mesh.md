# vision-mesh

vision-mesh is a dedicated project in personal core for a lightweight, fast model
that identifies objects and their parts and directly predicts vision-harness
structure, including `part_of` relationships.

The proposed architecture shares a compact image encoder between instance and
relationship heads. Learned relationships connect parts to the correct object
instances, including repeated objects and nested components.

The project includes its design and a tested offline query-score decoder grounded
in the located `visia_vision_agent_mcp.part_graph` API. The contract and original
fixtures are pinned to VisiaAI/core `fcb664472e2313be15a7f42b659997809a9a55df`.
Tests exercise link planning, nested display numbering and the actual pure
consumer object/edge parsers. There is no trained model or speed result yet.

The exact project name “vision-harness” is unconfirmed. See the
[contract evidence and verification commands](https://github.com/GeorgePearse/core/blob/v2-vision-mesh/projects/vision-mesh/CONTRACT.md)
for discovery evidence, field semantics and the limits of offline verification.

See the [project specification](https://github.com/GeorgePearse/core/blob/v2-vision-mesh/projects/vision-mesh/README.md)
for the output-contract boundary, proposed architecture, training objectives,
evaluation criteria, and implementation milestones.
