# Research: storing the algorithms library in a typed code database

*Written 2026-08-04. Context: the algorithms library currently stores
implementations as plain source files under `algorithms/<category>/<name>/`,
indexed by a generated `index.json` and served over MCP. The goal explored
here is storing algorithms in an actual database designed for code, with
typed boundaries between the stored logic and its consumers.*

## The candidates

### Legend / PURE (Goldman Sachs → FINOS)

The "Goldman one". Goldman Sachs open-sourced their internal Alloy/PURE
platform through FINOS as [Legend](https://github.com/finos/legend), a data
modeling and governance platform. Its
[PURE language](https://www.finos.org/press/goldman-sachs-open-sources-its-data-modeling-platform-through-finos)
is an immutable, typed functional modeling language (UML-based, OCL-inspired),
and models are stored and versioned centrally via Legend SDLC
([Linux Foundation announcement](https://www.linuxfoundation.org/press/press-release/goldman-sachs-open-sources-its-data-modeling-platform-through-finos),
[GS engineering blog](https://developer.gs.com/blog/posts/how-legend-has-empowered-global-markets-engineering)).

**Fit:** weak. Legend targets *data models* — trades, derivatives, schemas,
mappings to stores — not general-purpose algorithms. Its typed discipline is
inspiring, but it is not a home for quicksort in four languages.

### Morphir (Morgan Stanley → FINOS)

Easy to conflate with the Goldman project because it is also a FINOS bank
donation, but [Morphir](https://morphir.finos.org/) came from Morgan Stanley.
It "captures business logic as data": logic is authored in a typed frontend
(Elm-based) and stored as a
[strongly-typed intermediate representation](https://morphir.finos.org//docs/morphir-ir/)
serialized to JSON, with explicit
[typed boundary metadata](https://morphir.finos.org/docs/design/draft/ir/attributes/)
for functions that cross component boundaries. Code generators project the IR
out to multiple target languages ([repo](https://github.com/finos/morphir)).

**Fit:** conceptually the closest to "a database of algorithms in different
languages" — the IR record *is* the algorithm and languages are projections.
The trade-offs:

- Generated code is not the idiomatic, reference-quality code this library
  hand-writes and verifies; a reference library's value is largely that the
  code reads like a human expert wrote it for that language.
- Backend coverage is uneven (Scala and TypeScript are the mature paths;
  others vary), so Python/Rust/Go projections would be a gamble.

### Unison

[Unison](https://www.unison-lang.org/) is the purest realization of "code
actually lives in a database." Every definition is stored as its typed AST in
a [SQLite codebase](https://x.com/unisonweb/status/1491823684742434824),
identified by a 512-bit content hash of its implementation and its
dependencies' hashes; names are just metadata pointing at immutable typed
definitions ([the big idea](https://www.unison-lang.org/docs/the-big-idea/),
[LWN writeup](https://lwn.net/Articles/978955/)).

**Fit:** architectural inspiration, not a host. The Unison codebase format
stores *Unison* code only — it cannot hold the existing Python, Rust,
TypeScript, and Go implementations. Adding Unison as a fifth implementation
language would be a fun complement, though.

## Options for this library

1. **Morphir-style, write once / generate many.** Author each algorithm once
   in a typed frontend, store the typed IR as the database record, generate
   per-language code. Truest to the "database of algorithms" vision, but
   sacrifices idiomatic reference quality and depends on backend maturity.

2. **Typed catalogue (recommended).** Keep the handwritten implementations as
   the source of truth. Add a language-neutral **typed signature** to each
   algorithm's metadata — parameters, returns, generic constraints: the typed
   boundary — and compile the whole library into a SQLite database
   (`algorithms`, `signatures`, `implementations` tables) that the MCP server
   queries instead of walking files. Same shape as Unison's design
   (files → typed records in SQLite), but multi-language, and nothing already
   merged is thrown away. Morphir's IR is a good reference when designing the
   signature schema.

3. **Unison as-is.** Only viable if the library *is* Unison code; treat as a
   possible extra language rather than the architecture.

## Recommendation

Option 2. Concretely:

- Extend `meta.yaml` with a `signature` block (typed inputs/outputs in a
  small language-neutral type vocabulary, per-language type mappings where
  they diverge).
- Replace/augment `index.json` with a generated `algorithms.db` (SQLite):
  full-text search over descriptions and tags, typed signature columns,
  implementation source stored as rows.
- Point the MCP server at the database; keep `build_index.py`-style
  generation so git remains the review surface and the DB stays reproducible.

## All sources

- https://www.finos.org/press/goldman-sachs-open-sources-its-data-modeling-platform-through-finos
- https://www.linuxfoundation.org/press/press-release/goldman-sachs-open-sources-its-data-modeling-platform-through-finos
- https://a-teaminsight.com/blog/finos-and-goldman-sachs-release-legend-open-source-data-management-platform/
- https://developer.gs.com/blog/posts/how-legend-has-empowered-global-markets-engineering
- https://github.com/finos/legend
- https://morphir.finos.org/docs/concepts/introduction-to-morphir/
- https://morphir.finos.org//docs/morphir-ir/
- https://morphir.finos.org/docs/design/draft/ir/attributes/
- https://github.com/finos/morphir
- https://www.unison-lang.org/
- https://www.unison-lang.org/docs/the-big-idea/
- https://x.com/unisonweb/status/1491823684742434824
- https://lwn.net/Articles/978955/
- https://github.com/unisonweb/unison
