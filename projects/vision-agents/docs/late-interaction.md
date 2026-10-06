# Late Interaction

Late interaction is a retrieval architecture that delays the comparison between query and document representations until after both have been independently encoded.

## The Core Idea

Traditional retrieval has two extremes:

1. **Bi-encoder** — encode query and document separately into single vectors, compare with dot product. Fast but loses fine-grained matching.
2. **Cross-encoder** — feed query + document together through a transformer. Accurate but expensive (must re-run for every document at query time).

Late interaction sits in between.

## The Three Librarians (Analogy)

Imagine you're searching a library for books about "brave dogs":

1. **Bi-encoder librarian**: Before opening day, she wrote ONE sticky note per book summarizing the whole thing — "This book is about: brave animals, adventure, friendship." When you ask for "brave dogs", she quickly compares your request against her book summaries. Fast, but she might miss a book where "brave" appears in chapter 3 and "dogs" in chapter 7.

2. **Cross-encoder librarian**: No prep at all. When you ask for "brave dogs", she reads every book cover-to-cover with your query in mind. Most accurate, but you're waiting all day.

3. **Late interaction librarian**: Before opening day, she wrote sticky notes for every *page* of every book. When you ask for "brave dogs", she scans her page-notes looking for where "brave" matches strongly AND where "dogs" matches strongly — even if they're on different pages. Best of both worlds.

The key insight: **everyone pre-computes something** (except cross-encoder). The question is *how granular*?

| Approach | Pre-computes | Granularity |
|----------|--------------|-------------|
| Bi-encoder | One summary per book | Coarse |
| Late interaction | Notes per page | Fine |
| Cross-encoder | Nothing | N/A (all live) |

The "late" in late interaction: the *matching* between your query and the pages happens late (at query time), but the page representations were built early.

## Technical View

**Pre-compute token-level embeddings for each document**, then at query time compute token-level embeddings for the query and do fine-grained matching across the grid.

```
Document tokens:  [d1] [d2] [d3] [d4] [d5]
                   ↓    ↓    ↓    ↓    ↓
                  (pre-computed embeddings)

Query tokens:     [q1] [q2] [q3]
                   ↓    ↓    ↓
                  (computed at query time)

Matching:         q1·d1  q1·d2  q1·d3  q1·d4  q1·d5
                  q2·d1  q2·d2  q2·d3  q2·d4  q2·d5
                  q3·d1  q3·d2  q3·d3  q3·d4  q3·d5

Score = sum of max similarities per query token (MaxSim)
```

## Why This Works

- **Pre-built grid**: Document representations are computed once at index time. You're essentially pre-building half of the interaction matrix.
- **Fine-grained matching**: Unlike single-vector bi-encoders, you preserve token-level semantics. A query about "red car" can match strongly on "red" in one part of the doc and "vehicle" in another.
- **Scalable**: The expensive document encoding happens offline. Query-time cost grows with document length but not with corpus size (after retrieval candidates are selected).

## ColBERT

ColBERT (Contextualized Late Interaction over BERT) is the canonical implementation:

1. **Encode documents** into per-token embeddings (typically 128-dim after projection)
2. **Store all token embeddings** in an index
3. **At query time**, encode query tokens, then compute MaxSim against retrieved document tokens

The MaxSim operator:
```
score(q, d) = Σᵢ maxⱼ (qᵢ · dⱼ)
```

For each query token, find the most similar document token, then sum.

## Trade-offs

| Aspect | Bi-encoder | Late Interaction | Cross-encoder |
|--------|-----------|------------------|---------------|
| Index size | Small (1 vec/doc) | Large (N vecs/doc) | N/A |
| Query latency | Fast | Medium | Slow |
| Accuracy | Lower | Higher | Highest |
| Offline cost | Low | Medium | N/A |

## Connection to Vision

The same principle applies to image retrieval and VQA:

- **Pre-compute patch-level embeddings** for images (like ViT patch tokens)
- **Query with text tokens** and do late interaction across the patch grid
- Models like ColPali apply this to document images, treating each image patch as a "token"

This is why late interaction matters for vision-language retrieval: you can pre-index visual representations at patch granularity and match against arbitrary text queries without re-encoding images.

## Key Insight

> Late interaction is about **pre-computing low-level representations** of your documents — almost like pre-building a grid with respect to different queries. The document side of the interaction matrix is frozen at index time; only the query side is computed live.

This lets you get cross-encoder-like matching quality with bi-encoder-like scalability.

## References

- [ColBERT paper](https://arxiv.org/abs/2004.12832) — Khattab & Zaharia, 2020
- [ColBERTv2](https://arxiv.org/abs/2112.01488) — improved training and compression
- [Late Interaction Overview (Weaviate)](https://weaviate.io/blog/late-interaction-overview)
- [ColPali](https://arxiv.org/abs/2407.01449) — late interaction for document images
