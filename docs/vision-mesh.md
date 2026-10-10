# vision-mesh

vision-mesh is a dedicated project in personal core for a lightweight, fast model
that identifies objects and their parts and directly predicts vision-harness
structure, including `part_of` relationships.

The proposed architecture shares a compact image encoder between instance and
relationship heads. Learned relationships connect parts to the correct object
instances, including repeated objects and nested components.

The project currently contains its design and evaluation requirements. The exact
harness schema still needs to be located and pinned; there is no trained model or
speed result yet.

See the [project specification](https://github.com/GeorgePearse/core/blob/v2-vision-mesh/projects/vision-mesh/README.md)
for the output-contract boundary, proposed architecture, training objectives,
evaluation criteria, and implementation milestones.
