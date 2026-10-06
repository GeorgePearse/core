"""Type, role-fill, scope and relate engrim records with Jev; deterministic key and path checks on top."""

import asyncio
import hashlib
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from memtype.corpus import Corpus, canon, repo_and_worktree
from memtype.jev import Jev, boolean, choice
from memtype.schema import Schema
from memtype.store import REVIEW, Sidecar, band

RELATIONS = {
    "same": "A restates the same information as B",
    "supersedes": "A makes B stale or outdated: an update, a correction or a newer status of the same thing",
    "refines": "A adds detail to or narrows B, and B stays true",
    "contradicts": "A and B cannot both be true in the same context, and A is not an explicit update of B",
    "independent": "A and B are about different things, or are compatible facts on another topic",
}
VALIDITY = {
    "timeless": "holds until explicitly changed: a rule, mechanism, preference or pointer",
    "snapshot": "a state as of the save time that will soon change: a status, what is live, ready to integrate",
    "event": "something that happened at a point in time: measured, dispatched, broke, merged",
}
TRANSITIVE = {
    "part_of",
    "belongs_to",
    "stacked_on",
    "located_at",
    "sub_component_of",
    "depends_on",
    "registered_in",
}
NEIGHBOURS = 4


def _hash(row: dict[str, Any]) -> str:
    return hashlib.sha1(
        f"{row['engrim_type']}\x00{row['summary']}\x00{row['detail']}".encode()
    ).hexdigest()[:16]


def _state(corpus: Corpus, memory_id: int) -> str:
    r = corpus.row(memory_id)
    repo = repo_and_worktree(r["project"])[0]
    return f"Memory record #{memory_id} (saved {r['ts'][:16]}, engrim type {r['engrim_type']}, repo {repo}):\n{corpus.text(memory_id)}"


def _pair_state(corpus: Corpus, a: int, b: int) -> str:
    ra, rb = corpus.row(a), corpus.row(b)
    return (
        f"Record A (newer, saved {ra['ts'][:16]}, project {ra['project']}):\n{corpus.text(a)}\n\n"
        f"Record B (older, saved {rb['ts'][:16]}, project {rb['project']}):\n{corpus.text(b)}"
    )


class Structurer:
    def __init__(
        self, corpus: Corpus, schema: Schema, jev: Jev, sidecar: Sidecar | None = None
    ) -> None:
        self.corpus, self.schema, self.jev, self.sidecar = corpus, schema, jev, sidecar

    def frame_questions(self, memory_id: int) -> dict[str, dict[str, Any]]:
        repo, worktree = repo_and_worktree(self.corpus.row(memory_id)["project"])
        anchors = self.corpus.entity_options(memory_id)
        if worktree:
            anchors = {
                **dict(list(anchors.items())[:-1]),
                f"worktree:{worktree}": None,
                "none": anchors["none"],
            }
        levels = {
            "global": "about the user, how they work, or tools/APIs/services in general, independent of any code repository",
            "repo": f"a {repo}-wide fact: CI, build, conventions, credentials or infra that every part of the repo shares",
            "component": "about one named subsystem, app, service, model, dataset, site or customer",
            "worktree": "about work in progress on one branch or PR that is not merged: what that branch contains or does",
            "session": "about one agent session or moment only: a dispatch, a running job, a progress snapshot",
        }
        return {
            "durable": boolean(
                "Is this worth keeping in long-term memory for future sessions?",
                "a reusable fact, decision, rule, pointer or state that future work will need",
                "transient progress chatter or noise with nothing reusable",
            ),
            "type": choice(
                "Which record type best describes what this memory states?",
                self.schema.options(),
            ),
            "context_level": choice(
                "What is the most specific scope in which this fact holds?", levels
            ),
            "context_anchor": choice(
                "If the fact is scoped to one component or worktree, which one is it? "
                "Choose 'none' if it is global or repo-wide.",
                anchors,
            ),
            "validity": choice("Over what time window does this hold?", VALIDITY),
        }

    def role_questions(
        self, memory_id: int, type_name: str
    ) -> dict[str, dict[str, Any]]:
        t = self.schema.types[type_name]
        ents, vals = (
            self.corpus.entity_options(memory_id),
            self.corpus.value_options(memory_id),
        )
        return {
            role.name: choice(
                f"This record is a '{t.name}': {t.description} Which option fills the role '{role.name}' "
                f"({role.description})? Choose 'none' if the record does not state it.",
                ents if role.kind == "entity" else vals,
            )
            for role in t.roles
        }

    async def structure(self, memory_id: int) -> dict[str, Any]:
        state = _state(self.corpus, memory_id)
        frame = await self.jev.ask(state, self.frame_questions(memory_id))
        type_name = frame["type"]["choice"]
        roles_raw = await self.jev.ask(state, self.role_questions(memory_id, type_name))
        anchor = frame["context_anchor"]
        rec = {
            "memory_id": memory_id,
            "content_hash": _hash(self.corpus.row(memory_id)),
            "durable_p": frame["durable"]["p"],
            "type": type_name,
            "type_p": frame["type"]["p"],
            "type_probs": frame["type"]["probabilities"],
            "context_level": frame["context_level"]["choice"],
            "context_level_p": frame["context_level"]["p"],
            "context_anchor": None
            if anchor["choice"] == "none"
            else str(anchor["choice"]).removeprefix("new:"),
            "context_anchor_p": anchor["p"],
            "validity": frame["validity"]["choice"],
            "validity_p": frame["validity"]["p"],
        }
        kinds = {r.name: r.kind for r in self.schema.types[type_name].roles}
        roles = []
        for name, a in roles_raw.items():
            raw = (
                None if a["choice"] == "none" else str(a["choice"]).removeprefix("new:")
            )
            b = band(a["p"])
            roles.append(
                {
                    "memory_id": memory_id,
                    "role": name,
                    "kind": kinds[name],
                    "value": raw if b != "empty" else None,
                    "raw": raw,
                    "p": a["p"],
                    "band": b,
                }
            )
        return {**rec, "roles": roles}

    async def relate_pair(self, a: int, b: int) -> dict[str, Any]:
        ans = await self.jev.ask(
            _pair_state(self.corpus, a, b),
            {
                "relation": choice(
                    "How does record A relate to the older record B?", RELATIONS
                ),
                "same_subject": boolean(
                    "Are A and B about the same specific thing (same system, setting, PR, job or question)?"
                ),
                "b_stale": boolean(
                    "After reading A, is something B states now outdated or wrong?"
                ),
            },
        )
        r, same, stale = ans["relation"], ans["same_subject"]["p"], ans["b_stale"]["p"]
        probs = dict(r["probabilities"])
        if same < REVIEW:
            probs["independent"] = probs.get("independent", 0.0) + sum(
                probs.pop(k, 0.0)
                for k in ("same", "supersedes", "refines", "contradicts")
            )
            probs.update(
                {k: 0.0 for k in ("same", "supersedes", "refines", "contradicts")}
            )
        elif stale < REVIEW and probs.get("supersedes", 0.0) > 0:
            probs["refines"] = probs.get("refines", 0.0) + probs["supersedes"]
            probs["supersedes"] = 0.0
        kind = max(probs, key=probs.get)
        return {
            "src": a,
            "dst": b,
            "kind": kind,
            "p": probs[kind],
            "band": band(probs[kind]),
            "method": "jev",
            "probs": {
                **probs,
                "raw_choice": r["choice"],
                "same_subject": same,
                "b_stale": stale,
            },
        }

    def shortlist(self, memory_id: int) -> list[int]:
        me = self.sidecar.record(memory_id) if self.sidecar else None
        mine = {
            canon(r["value"])
            for r in (me or {}).get("roles", [])
            if r["value"] and r["kind"] == "entity"
        }
        picked = []
        for n, sim in self.corpus.neighbours(memory_id, 3 * NEIGHBOURS):
            other = self.sidecar.record(n) if self.sidecar else None
            theirs = {
                canon(r["value"])
                for r in (other or {}).get("roles", [])
                if r["value"] and r["kind"] == "entity"
            }
            if (
                other is None
                or other["type"] == (me or {}).get("type")
                or mine & theirs
                or sim >= 0.8
            ):
                picked.append(n)
        return picked[:NEIGHBOURS]

    async def relate(self, memory_id: int) -> list[dict[str, Any]]:
        return list(
            await asyncio.gather(
                *(self.relate_pair(memory_id, n) for n in self.shortlist(memory_id))
            )
        )

    async def run(
        self, ids: list[int] | None = None, relate: bool = True, batch: int = 64
    ) -> dict[str, Any]:
        assert self.sidecar is not None
        started, t0, calls0, usd0 = (
            datetime.now(timezone.utc).isoformat(),
            time.perf_counter(),
            self.jev.calls,
            self.jev.usd,
        )
        ids = ids if ids is not None else [int(i) for i in self.corpus.df["id"]]
        todo = [
            i for i in ids if self.sidecar.content_hash(i) != _hash(self.corpus.row(i))
        ]
        for k in range(0, len(todo), batch):
            for rec in await asyncio.gather(
                *(self.structure(i) for i in todo[k : k + batch])
            ):
                self.sidecar.put_record(
                    {k2: v for k2, v in rec.items() if k2 != "roles"}, rec["roles"]
                )
        if relate:
            pending = [i for i in self.sidecar.unrelated() if i in set(ids)]
            for k in range(0, len(pending), batch):
                chunk = pending[k : k + batch]
                for i, rels in zip(
                    chunk, await asyncio.gather(*(self.relate(i) for i in chunk))
                ):
                    self.sidecar.put_relations(i, rels)
        key = key_conflicts(self.sidecar, self.schema)
        self.sidecar.put_conflicts("key", key)
        self.sidecar.put_conflicts("jev", jev_conflicts(self.sidecar))
        self.sidecar.put_conflicts("compose", compose_conflicts(self.sidecar))
        stats = {
            "structured": len(todo),
            "calls": self.jev.calls - calls0,
            "usd": self.jev.usd - usd0,
            "seconds": time.perf_counter() - t0,
        }
        self.sidecar.log_run(
            started,
            datetime.now(timezone.utc).isoformat(),
            len(todo),
            stats["calls"],
            stats["usd"],
            stats["seconds"],
        )
        return stats


def _facts(sidecar: Sidecar) -> dict[int, dict[str, Any]]:
    facts: dict[int, dict[str, Any]] = defaultdict(lambda: {"roles": {}})
    for r in sidecar.roles_frame():
        f = facts[r["memory_id"]]
        f.update(
            type=r["type"],
            level=r["context_level"],
            anchor=canon(r["context_anchor"])
            if r["context_anchor"]
            and r["context_anchor_p"] >= REVIEW
            and r["context_level"] in ("component", "worktree")
            else None,
        )
        if r["band"] == "accept" and r["value"]:
            f["roles"][r["role"]] = canon(r["value"])
        elif r["raw"] is None:
            f["roles"].setdefault(r["role"], "∅")
    return facts


def key_conflicts(sidecar: Sidecar, schema: Schema) -> list[dict[str, Any]]:
    """Same type, same key roles, same context, different value role: a conflict, no model call."""
    groups: dict[tuple, list[tuple[int, str]]] = defaultdict(list)
    for mid, f in _facts(sidecar).items():
        t = schema.types.get(f["type"])
        if (
            not t
            or not t.value
            or f["roles"].get(t.value, "∅") == "∅"
            or any(k not in f["roles"] for k in t.key)
            or all(f["roles"][k] == "∅" for k in t.key)
        ):
            continue
        groups[
            (t.name, f["level"], f["anchor"], tuple(f["roles"][k] for k in t.key))
        ].append((mid, f["roles"][t.value]))
    out = []
    for key, members in groups.items():
        for i, (a, va) in enumerate(members):
            for b, vb in members[i + 1 :]:
                if va != vb:
                    newer, older = (a, b) if a > b else (b, a)
                    out.append(
                        {
                            "a": newer,
                            "b": older,
                            "detail": {
                                "type": key[0],
                                "context": [key[1], key[2]],
                                "key": list(key[3]),
                                "values": {a: va, b: vb},
                            },
                        }
                    )
    return out


def jev_conflicts(sidecar: Sidecar) -> list[dict[str, Any]]:
    rows = sidecar.conn.execute(
        "SELECT src, dst, kind, p FROM mt_relation WHERE method='jev' AND kind='contradicts' AND p >= ?",
        (REVIEW,),
    )
    return [{"a": r[0], "b": r[1], "detail": {"kind": r[2], "p": r[3]}} for r in rows]


def compose_conflicts(sidecar: Sidecar) -> list[dict[str, Any]]:
    """Follow transitive `relation` facts; a derived path that lands on a different object than a stated one is a conflict."""
    edges: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for mid, f in _facts(sidecar).items():
        r = f["roles"]
        if f["type"] == "relation" and {"subject", "relation", "object"} <= r.keys():
            rel = r["relation"].replace("-", "_")
            if rel in TRANSITIVE:
                edges[(r["subject"], rel)][r["object"]] = mid
    out = []
    for (subj, rel), objs in edges.items():
        for mid_obj, via_mid in list(objs.items()):
            for derived, mid2 in edges.get((mid_obj, rel), {}).items():
                for stated, mid3 in objs.items():
                    if stated not in (mid_obj, derived) and rel in {
                        "part_of",
                        "belongs_to",
                        "located_at",
                        "stacked_on",
                    }:
                        out.append(
                            {
                                "a": mid3,
                                "b": mid2,
                                "detail": {
                                    "subject": subj,
                                    "relation": rel,
                                    "stated": stated,
                                    "derived": derived,
                                    "path": [via_mid, mid2],
                                },
                            }
                        )
    return out
