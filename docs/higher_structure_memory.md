# Beyond graphs: higher structure in AI memory

Prompted by a post from @NoahChrein (2026-10-06):

> We keep returning to ontology generation and every damn time its just graphs like give me a break, do you know how many combinatorial higher structures there are?

The complaint is that LLM-generated ontologies and knowledge stores almost always end up as entity-relation graphs, meaning nodes plus binary edges. That is the least expressive structure on offer. These notes cover what the richer structures are, and what they would change for AI memory tools such as ai-memory, Mem0, Zep/Graphiti, Cognee, engrim and [memory-residuals](https://github.com/GeorgePearse/memory-residuals).

## What a graph cannot say

| Structure | What it adds | Memory example a graph mangles |
| --- | --- | --- |
| Hypergraph / n-ary relation | One fact joins k things | "Alex calibrated the laser at FPT on 09-30 using offset 12" is one fact with five participants. A graph has to invent an event node and loses the fact that the parts belong together. |
| Category | Arrows compose, and some paths are declared equal | "camera → site → customer" equals "camera → customer". A graph stores both edges and cannot say they must agree, so they drift. |
| 2-category / higher category | Relations between relations | "This decision supersedes that decision", or "mapping A refines mapping B". These are edges about edges. |
| Operad / multicategory | Many inputs → one output, with composition laws | "Plan = fetch ∘ (filter, rank)". Procedures and skills are trees of operations, not edges. |
| Simplicial complex | Higher-order co-occurrence, with a boundary rule (every face of a k-fact is a fact) | Three tools that only work together. Pairwise edges imply a triangle that may not exist. |
| Sheaf | Facts that hold in a context, and gluing rules for when local facts form a global one | "Threshold is 0.5" is true for site A and false for site B. A sheaf records the context and detects contradictions where contexts overlap. |
| Bitemporal / modal structure | When a fact was true vs when it was learnt, and in which world or branch | "Was true until 10-05", "true on branch X". Graphiti stores edge validity intervals, which is a step towards this. |

## How it would change memory tools

**1. Store facts as n-ary records, not triples.** Most memory products extract (subject, predicate, object) triples. Each extracted fact should instead be a typed record with named roles: who, what, where, when, evidence and confidence. A record is a hyperedge, and it keeps the provenance on the fact itself. engrim's typed records (`decision`, `fact`, `state`, with tags) are already closer to this than a triple store.

**2. Make supersession and refinement first-class relations between facts.** Supersession is the real update operation in memory, as in `engrim supersede` and Graphiti edge invalidation. It is a 2-cell: an arrow between two facts, with a type (supersedes, refines, contradicts, merges) and its own evidence. Storing it as data allows history queries ("what did we believe about X on 09-20, and why did it change?") and avoids just overwriting the old fact.

**3. Compose, and check that paths agree.** If memory can say both "site → customer" and "camera → site", it should derive "camera → customer" instead of storing a third copy that can go stale. If two derivation paths give different answers, that is a contradiction to surface, which is the commutative-diagram check. This replaces a lot of LLM-based "deduplicate memories" passes.

**4. Scope facts to contexts and treat retrieval as gluing.** Most memory bugs are scope bugs: a fact true for one project, site or branch leaks into another. The sheaf view says to attach every fact to a context (project path, site, branch, time window) and have retrieval for a query context:
- take the facts from every context that covers it
- check they agree where contexts overlap
- return the glued result or an explicit conflict

engrim's project-path scoping plus a `--global` flag is a two-level version of this. The structure generalises to a lattice of contexts: org > project > worktree > session.

**5. Store procedures as operads, not prose.** "How to restart VLM Chat" or "how to publish an artefact" is a composition of steps with inputs and outputs. Stored as a composable tree, it can be partially reused, checked when one step changes, and run. Skills files are a hand-written version of this.

**6. Surprise-only storage stays compatible.** The memory-residuals idea is to store only what the model got wrong, the residual. Higher structure doesn't conflict with that. A residual is a 2-cell: "the model predicted P, the truth was Q, because R". It is a relation between a prediction and an observation, not a free-floating fact.

## Costs and the practical position

- LLMs extract triples reliably. They extract n-ary records with roles less reliably, and declared path equalities hardly at all. The extraction prompt and a schema-constrained output format become the main engineering work.
- Storage is fine. A Postgres or SQLite table per record type with role columns, a `relations` table for 2-cells (`from_fact`, `to_fact`, `kind`, `evidence`) and a `context` column covers points 1, 2 and 4 without a graph database.
- Composition and gluing checks are where the value is and where the work is. Start with one: contradiction detection across overlapping contexts. Most memory failures come from stale or out-of-scope facts, not from missing edges.
- Don't build an ∞-category engine. The useful subset is n-ary typed facts, typed relations between facts, context scoping with conflict detection, and composable procedures.

## Related

- Memetics (GeorgePearse/memetics) is an instance of this: an idea with N sources and M anchored code locations is a hyperedge, and "this commit refines that idea" is a 2-cell checked in CI.
- [Typed code storage research](../algorithms/docs/typed-code-storage-research.md) covers Unison and Morphir, which use content-addressed, typed structure instead of text.
- Applied category theory starting points: Spivak & Kent, *Ologs* (2012), a categorical alternative to ontologies built for this complaint; Fong & Spivak, *Seven Sketches in Compositionality* (2018); Curry, *Sheaves, Cosheaves and Applications* (2014).
