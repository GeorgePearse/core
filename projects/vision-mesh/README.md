# vision-mesh

A lightweight, fast vision model that identifies objects and their parts and
directly predicts the structured representation used by vision-harness, including
`part_of` relationships.

This is a dedicated project in George Pearse's personal core. **Status: project
definition with a tested offline contract scaffold.** A dependency-free decoder
converts supplied query and parent scores to the located harness input. There is
no trained model, image inference implementation, or measured latency yet.

## Intended behavior

Given an image, predict the visible object instances, their component parts, and
which instance each part belongs to. Structure is a learned output of the model:
it must distinguish the wheels of two adjacent bicycles, for example, rather than
attach every detected wheel to the nearest bicycle after detection.

The initial scope is a single image with potentially multiple objects and nested
parts. Here, “mesh” means connected visual entities and relationships; 3D surface
reconstruction is outside this initial scope.

## Contract with vision-harness

vision-harness is the authority for the output schema. Reuse its entity identity,
geometry, labels, relation direction, uncertainty, and serialization conventions.
Do not introduce a competing public scene-graph format in this project.

The located API is `visia_vision_agent_mcp.part_graph`, pinned to VisiaAI/core
`fcb664472e2313be15a7f42b659997809a9a55df`. It accepts call-local `PartObject`
records with boxes, existing class names/IDs and optional single-parent `part_of`
links; it rejects self-links and cycles. Its consumer uses stable annotation IDs
and recomputed dotted display numbers. The exact name “vision-harness” remains
unconfirmed; the synthetic harnesses contain this API but concern generation and
scoring. See [the contract evidence and commands](CONTRACT.md) for source paths,
field semantics, fixtures, provenance and verification limits.

Original upstream fixtures and a separate authored repeated-object/nested-part
case exercise the offline decoder and actual pure consumer functions. They are
test fixtures, not reviewed training data. The harness has no explicit uncertain
parent field and omits absent parents from the read graph.
The following is a semantic illustration, **not a JSON/API contract**:

```text
bicycle A
  front wheel A  --part_of--> bicycle A
    tyre A      --part_of--> front wheel A
  rear wheel A   --part_of--> bicycle A
bicycle B
  front wheel B  --part_of--> bicycle B
```

## Proposed model

Start with one compact image encoder and a bounded set of learned instance
queries. Share image features between objects and parts. Each query predicts
presence, class, geometry, and an embedding used by a relationship head.

The relationship head scores candidate links between instance queries, including
`part_of`. The located contract permits one parent, so use a parent-pointer head
with an explicit no-parent outcome. The scaffold already decodes this head's
supplied scores; the head itself still needs implementation and training.
With Q instance queries, all-pairs edge scoring costs O(Q²); measure its latency
and memory contribution and keep Q explicit in every benchmark.

Use fixed-size tensor predictions followed by a small deterministic decoder that
assigns IDs, filters predictions, and serializes the harness structure. Parent
selection must come from learned scores. Do not infer membership solely from box
containment, proximity, or an LLM call after detection.

The located contract requires boxes and permits optional polygons. The scaffold
emits normalized boxes and rejects self-links, cycles and links to filtered
parents, preserving structural failures for inspection. Polygons, captions and
learned uncertainty are future outputs if the selected application needs them.

## Training data and objectives

Keep images, object/part instance annotations, and explicit relationship labels
together. Preserve annotation provenance and distinguish reviewed labels from
teacher-generated proposals. Missing relationship annotations are unknown, not
automatically negative examples.

Proposed training objectives combine instance presence/classification, geometry,
and supervised relationships. Remap relationship endpoints through the same
prediction-to-target assignment used for instance supervision; query indices are
not stable entity identities. Mask unknown edges out of the relationship loss.
Include crowded scenes, repeated objects, occluded parts, nested components, and
objects with no annotated parts.

Split by source scene or capture sequence before sampling frames, so near-duplicate
frames and components of the same object cannot leak into evaluation. Freeze the
evaluation manifest before selecting model configurations.

## Evaluation and acceptance

| Dimension | Evidence to retain |
| --- | --- |
| Objects and parts | Detection/segmentation precision and recall, split by whole objects and parts |
| Relationships | Labeled edge precision/recall after matching predicted instances to ground truth |
| Structure | Correct-parent rate, nested-chain accuracy, dangling edges, self-links, and invalid cycles where prohibited |
| Compatibility | Predictions accepted by the pinned vision-harness parser and exercised by its actual consumer |
| Speed | Batch-one p50/p95 latency including preprocessing, forward pass, decoding, and serialization |
| Footprint | Parameters, checkpoint size, peak runtime memory, precision, input resolution, and query count |

Record hardware, software versions, warmup, sample count, and separate cold-start
cost for every speed result. “Lightweight” and “fast” are goals until the target
device, latency budget, and quality floor are selected and measured.

Compare the learned relationships with a detector plus a containment/proximity
baseline on the same frozen examples. A useful first milestone is a compact model
that predicts a small, explicitly documented object/part vocabulary and improves
parent assignment over that baseline while satisfying the selected speed budget.
Keep raw outputs and a browsable report showing both successes and failures.

## Implementation sequence

1. **Complete offline:** pin the located part-graph contract, replay its original
   fixtures, decode supplied parent scores, and exercise its pure consumer helpers.
2. Implement the dataset reader and review a small object/part/relationship set.
3. Build the compact shared encoder, instance heads, and learned relationship head.
4. Train a bounded baseline and evaluate quality, structural validity, and speed.
5. Export the model and verify the complete image-to-harness path on the target device.

Milestones 2–5 remain planned. A database round-trip and live surface rendering
have not been exercised. Backbone selection,
training runs, accelerator allocation, and deployment are separate implementation
decisions once the harness contract and benchmark target are available.
