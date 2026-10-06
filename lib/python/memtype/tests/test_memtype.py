import asyncio
import os
from pathlib import Path

import pytest

from memtype import cli
from memtype.corpus import Corpus
from memtype.evaluate import ece, lenient
from memtype.jev import FakeJev, Jev
from memtype.schema import Schema
from memtype.store import Sidecar, band
from memtype.structure import Structurer, compose_conflicts, key_conflicts


def threshold_rule(state, name, q):
    if q["type"] == "boolean":
        return (False, 0.2) if name == "b_stale" else (True, 0.9)
    pick = {
        "type": "limit_setting",
        "context_level": "component",
        "validity": "timeless",
        "relation": "supersedes",
    }.get(name)
    if pick:
        return pick, 0.95
    if name == "context_anchor":
        return next(k for k in q["criteria"] if "Acme" in k or k == "none"), 0.9
    if name == "system":
        return next(k for k in q["criteria"] if "Acme" in k), 0.92
    if name == "parameter":
        return "score_threshold", 0.85
    if name == "value":
        return next(k for k in q["criteria"] if k in ("0.5", "0.7")), 0.9
    if name == "scope":
        return "none", 0.4
    return next(iter(q["criteria"])), 0.6


def test_corpus_options_and_neighbours(engrim_copy):
    c = Corpus.load(engrim_copy)
    ents, vals = c.entity_options(3), c.value_options(5)
    assert "new:uv" in ents and "new:" not in ents and ents["none"]
    assert "PR #17325" in vals and "2026-09-05" in vals
    assert all(n < 5 for n, _ in c.neighbours(5, 4))
    assert len(c.entity_options(1)) <= 255


def test_structure_writes_bands_and_key_conflict(engrim_copy, tmp_path):
    c, schema, sidecar = (
        Corpus.load(engrim_copy),
        Schema.load(),
        Sidecar(tmp_path / "side.db"),
    )
    st = Structurer(c, schema, FakeJev(threshold_rule), sidecar)
    stats = asyncio.run(st.run([1, 2], relate=True))
    assert stats["structured"] == 2
    rec = sidecar.record(2)
    roles = {r["role"]: r for r in rec["roles"]}
    assert rec["type"] == "limit_setting" and roles["value"]["value"] == "0.7"
    assert roles["scope"]["band"] == "empty" and roles["scope"]["value"] is None
    assert roles["parameter"]["band"] == "accept"
    conflicts = sidecar.conflicts()
    assert [
        (x["a"], x["b"], x["method"]) for x in conflicts if x["method"] == "key"
    ] == [(2, 1, "key")]
    rel = rec["relations"][0]
    assert rel["kind"] == "refines"
    assert asyncio.run(st.run([1, 2]))["structured"] == 0


def test_relate_pair_gates_on_same_subject(engrim_copy):
    c = Corpus.load(engrim_copy)

    def rule(s, n, q):
        return (False, 0.1) if n == "same_subject" else threshold_rule(s, n, q)

    out = asyncio.run(Structurer(c, Schema.load(), FakeJev(rule)).relate_pair(5, 3))
    assert out["kind"] == "independent"


def test_compose_flags_disagreeing_paths(tmp_path):
    side = Sidecar(tmp_path / "s.db")
    facts = [
        (10, "cam-409", "located_at", "acme-line-4"),
        (11, "acme-line-4", "located_at", "acme"),
        (12, "cam-409", "located_at", "globex"),
    ]
    for mid, s, r, o in facts:
        side.put_record(
            {
                "memory_id": mid,
                "content_hash": "x",
                "durable_p": 0.9,
                "type": "relation",
                "type_p": 0.9,
                "type_probs": {},
                "context_level": "component",
                "context_level_p": 0.9,
                "context_anchor": None,
                "context_anchor_p": 0.9,
                "validity": "timeless",
                "validity_p": 0.9,
            },
            [
                {
                    "memory_id": mid,
                    "role": k,
                    "kind": "entity",
                    "value": v,
                    "raw": v,
                    "p": 0.9,
                    "band": "accept",
                }
                for k, v in (("subject", s), ("relation", r), ("object", o))
            ],
        )
    out = compose_conflicts(side)
    assert any(
        x["detail"]["stated"] == "globex" and x["detail"]["derived"] == "acme"
        for x in out
    )
    assert key_conflicts(side, Schema.load())


def test_policy_and_metrics():
    assert [band(p) for p in (0.95, 0.8, 0.79, 0.5, 0.49)] == [
        "accept",
        "accept",
        "review",
        "review",
        "empty",
    ]
    assert (
        lenient("uv", "uv")
        and lenient("use --refresh-package", "use `uv sync --refresh-package`")
        and not lenient("uv", None)
    )
    assert ece([(1.0, True), (1.0, True)])[0] == 0.0
    assert abs(ece([(0.9, False)] * 10)[0] - 0.9) < 1e-9


def test_cli_refuses_live_db():
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--db",
                str(Path.home() / ".engrim" / "memory.db"),
                "--sidecar",
                "/dev/null",
                "conflicts",
            ]
        )


@pytest.mark.skipif(
    os.environ.get("MEMTYPE_LIVE") != "1" or not os.environ.get("AI_GATEWAY_API_KEY"),
    reason="live Jev smoke test: set MEMTYPE_LIVE=1 and AI_GATEWAY_API_KEY",
)
def test_live_jev_smoke(engrim_copy):
    async def go():
        jev = Jev(budget_usd=0.01)
        try:
            rec = await Structurer(
                Corpus.load(engrim_copy), Schema.load(), jev
            ).structure(3)
        finally:
            await jev.aclose()
        return rec, jev

    rec, jev = asyncio.run(go())
    assert (
        rec["type"] in Schema.load().types
        and 0 <= rec["type_p"] <= 1
        and jev.usd < 0.01
    )
