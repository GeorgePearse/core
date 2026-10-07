"""Edges between imported records: citations by id (deterministic), supersession and evidence (Jev-gated)."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from memtype.store import ACCEPT

from engrim_trax.classify import Classifier, Mapping
from engrim_trax.records import Record, artefact_ids, cited_ids, pr_numbers

SUPERSEDE_WINDOW = timedelta(days=60)
SUPERSEDE_CANDIDATES = 5
EVIDENCE_CANDIDATES = 3
EVIDENCE_MIN_COS = 0.4
MAX_SHARED_REF_EDGES = 3
VALENCE = 0.5


@dataclass(frozen=True)
class Edge:
    src: int
    dst: int
    kind: str
    valence: float | None = None
    note: str = ""
    p: float | None = None


def drop_newer(edges: list[Edge], by_id: dict[int, Record]) -> tuple[list[Edge], int]:
    """Keep only edges whose parent (dst) is strictly older than its child (src); count the rest."""
    kept, dropped = [], 0
    for e in edges:
        a, b = by_id.get(e.src), by_id.get(e.dst)
        if a is None or b is None or e.src == e.dst:
            dropped += 1
        elif (b.when, b.id) < (a.when, a.id):
            kept.append(e)
        else:
            dropped += 1
    return kept, dropped


def citation_edges(records: list[Record]) -> list[Edge]:
    """`produced_by` from a record to the older records it cites by engrim id, PR number or artefact id."""
    by_id = {r.id: r for r in records}
    out: list[Edge] = []
    last_by_ref: dict[tuple[str, str], Record] = {}
    for r in records:  # oldest first
        text = r.text
        seen: set[int] = set()
        for cid in cited_ids(text):
            if cid in by_id and cid != r.id and cid not in seen:
                out.append(Edge(r.id, cid, "produced_by", note=f"cites engrim #{cid}"))
                seen.add(cid)
        refs = [("pr", n) for n in pr_numbers(text)] + [("artefact", a) for a in artefact_ids(text)]
        shared = 0
        for ref in refs:
            prev = last_by_ref.get((r.project, *ref))
            if prev is not None and prev.id not in seen and shared < MAX_SHARED_REF_EDGES:
                out.append(Edge(r.id, prev.id, "produced_by", note=f"shares {ref[0]} {ref[1]}"))
                seen.add(prev.id)
                shared += 1
            last_by_ref[(r.project, *ref)] = r
    return out


def supersede_candidates(a: Record, records: list[Record]) -> list[Record]:
    """Newer records in the same project within 60 days, ranked by tag/link overlap and citation, capped."""
    scored = []
    a_tags, a_links = set(a.tags), set(a.links)
    for b in records:
        if b.id == a.id or b.project != a.project or not (a.when < b.when <= a.when + SUPERSEDE_WINDOW):
            continue
        score = len(a_tags & set(b.tags)) + 2 * len(a_links & set(b.links)) + (3 if a.id in cited_ids(b.text) else 0)
        if score > 0:
            scored.append((-score, b.when, b))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in scored[:SUPERSEDE_CANDIDATES]]


async def supersession_edges(classifier: Classifier, records: list[Record]) -> tuple[list[Edge], int]:
    """One `supersedes` edge per superseded record, from the candidate Jev rates highest with p >= ACCEPT."""
    superseded = [r for r in records if r.status == "superseded"]
    out: list[Edge] = []
    pairs = 0

    async def best(a: Record) -> Edge | None:
        cands = supersede_candidates(a, records)
        if not cands:
            return None
        ps = await asyncio.gather(*(classifier.corrected(a, b) for b in cands))
        nonlocal pairs
        pairs += len(cands)
        p, b = max(zip(ps, cands), key=lambda t: t[0])
        return Edge(b.id, a.id, "supersedes", note="jev: corrected version", p=p) if p >= ACCEPT else None

    for k in range(0, len(superseded), 32):
        for e in await asyncio.gather(*(best(a) for a in superseded[k : k + 32])):
            if e:
                out.append(e)
    return out, pairs


def evidence_candidates(
    src: Record, records: list[Record], mappings: dict[int, Mapping], vectors: dict[int, np.ndarray]
) -> list[Record]:
    """Older Beliefs in the same project (or global) nearest to the source by cosine, capped."""
    v = vectors.get(src.id)
    if v is None:
        return []
    scored = []
    for t in records:
        if t.id == src.id or (t.when, t.id) >= (src.when, src.id):
            continue
        if t.project not in (src.project, "__global__") and src.project != "__global__":
            continue
        m = mappings.get(t.id)
        if m is None or m.kind != "Belief":
            continue
        w = vectors.get(t.id)
        if w is None:
            continue
        cos = float(v @ w)
        if cos >= EVIDENCE_MIN_COS:
            scored.append((cos, t))
    scored.sort(key=lambda t: -t[0])
    return [t for _, t in scored[:EVIDENCE_CANDIDATES]]


async def evidence_edges(
    classifier: Classifier,
    records: list[Record],
    mappings: dict[int, Mapping],
    vectors: dict[int, np.ndarray],
) -> tuple[list[Edge], int]:
    """`proves` (from Experiments) or `favors` (from measured facts) into older Beliefs, Jev p >= ACCEPT."""
    sources = [
        r
        for r in records
        if r.id in mappings
        and (mappings[r.id].kind == "Experiment" or (r.type == "fact" and mappings[r.id].measured_p >= 0.5))
    ]
    out: list[Edge] = []
    pairs = 0

    async def one(src: Record) -> list[Edge]:
        cands = evidence_candidates(src, records, mappings, vectors)
        res = await asyncio.gather(*(classifier.evidence(src, t) for t in cands))
        nonlocal pairs
        pairs += len(cands)
        kind = "proves" if mappings[src.id].kind == "Experiment" else "favors"
        return [
            Edge(src.id, t.id, kind, valence=VALENCE if sup >= 0.5 else -VALENCE, note="jev: evidence", p=bears)
            for t, (bears, sup) in zip(cands, res)
            if bears >= ACCEPT
        ]

    for k in range(0, len(sources), 32):
        for es in await asyncio.gather(*(one(s) for s in sources[k : k + 32])):
            out.extend(es)
    return out, pairs
