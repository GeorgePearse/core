# Algorithms Reference Library

A machine-friendly database of classic algorithms implemented in multiple
languages. The goal is to be a fast, trustworthy lookup for humans and AI
models alike — grab a known-good implementation instead of re-deriving it.

## Layout

Every algorithm lives in one directory, keyed by category:

```
algorithms/<category>/<algorithm>/
├── meta.yaml        # name, description, complexity, tags, references
├── python.py
├── rust.rs
├── typescript.ts
└── go.go
```

File names are always `<language>.<ext>` so consumers can address an
implementation as `(algorithm, language)` without globbing.

## meta.yaml schema

```yaml
name: quicksort              # kebab-case, matches the directory name
category: sorting            # matches the parent directory
description: >
  One-line-ish summary of what the algorithm does and when to use it.
complexity:
  time_best: O(n log n)
  time_average: O(n log n)
  time_worst: O(n^2)
  space: O(log n)
tags: [sorting, divide-and-conquer, in-place]
references:
  - https://en.wikipedia.org/wiki/Quicksort
```

## Index

`index.json` at this level is generated — do not edit by hand:

```bash
python algorithms/tools/build_index.py
```

It maps every algorithm to its metadata and available languages, which is what
the MCP server (and any other consumer) reads.

## MCP server

`algorithms/mcp/server.py` exposes the library over the Model Context
Protocol:

- `list_algorithms(category?, tag?)` — browse the catalogue
- `get_algorithm(name, language?)` — fetch metadata + source
- `search_algorithms(query)` — substring search over names, tags, descriptions

Run it with:

```bash
uv run --with fastmcp python algorithms/mcp/server.py
```

Register in a client (e.g. Claude Code):

```bash
claude mcp add algorithms -- uv run --with fastmcp python /path/to/core/algorithms/mcp/server.py
```

## Contributing a new algorithm

1. Create `algorithms/<category>/<name>/` with a `meta.yaml` following the
   schema above.
2. Add at least a `python.py` implementation; other languages are welcome.
   Each file should be self-contained (no imports from elsewhere in the repo)
   and include a tiny `main`/`__main__` smoke test where idiomatic.
3. Regenerate the index: `python algorithms/tools/build_index.py`.

## Design notes

- [Typed code storage research](docs/typed-code-storage-research.md) —
  evaluation of Legend, Morphir, and Unison as storage backends, and the
  plan for moving the library into a typed SQLite catalogue.

## Conventions

- Implementations are reference-quality: clear over clever, standard library
  only, self-contained single files.
- Prefer the canonical textbook formulation; note meaningful variants in
  `meta.yaml` references instead of implementing every twist.
