"""Gold-set evaluation: per-step accuracy, calibration, review-band share, supersede recall/precision, cost, baseline."""

import asyncio
import json
import os
import random
import re
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

from memtype.corpus import Corpus, canon
from memtype.jev import Jev
from memtype.schema import Schema
from memtype.store import band
from memtype.structure import RELATIONS, VALIDITY, Structurer

BASELINE_MODEL = os.environ.get("MEMTYPE_BASELINE_MODEL", "gemini-3.8-flash")
BASELINE_PRICE = (
    float(os.environ.get("MEMTYPE_BASELINE_IN", "1.50")),
    float(os.environ.get("MEMTYPE_BASELINE_OUT", "7.50")),
)


def lenient(gold: Any, pred: Any) -> bool:
    if gold is None or pred is None:
        return gold is None and pred is None
    g, p = canon(str(gold)), canon(str(pred))
    if not (g and p):
        return False
    if g == p or g in p or p in g:
        return True
    tg, tp = set(re.findall(r"\w+", g)), set(re.findall(r"\w+", p))
    return len(tg & tp) / max(min(len(tg), len(tp)), 1) >= 0.8


def strict(gold: Any, pred: Any) -> bool:
    if gold is None or pred is None:
        return gold is None and pred is None
    g, p = (
        set(re.findall(r"\w+", str(gold).lower())),
        set(re.findall(r"\w+", str(pred).lower())),
    )
    return bool(g | p) and len(g & p) / len(g | p) >= 0.5


def ece(
    items: list[tuple[float, bool]], bins: int = 10
) -> tuple[float, list[dict[str, float]]]:
    out, total, n = [], 0.0, len(items)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(p, c) for p, c in items if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if sel:
            conf, acc = (
                statistics.fmean(p for p, _ in sel),
                statistics.fmean(float(c) for _, c in sel),
            )
            total += len(sel) / n * abs(conf - acc)
            out.append({"lo": lo, "hi": hi, "n": len(sel), "conf": conf, "acc": acc})
    return total, out


def _acc(xs: list[bool]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def load_gold(path: str) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    gold = [
        json.loads(line)
        for f in sorted(Path(path).parent.glob(Path(path).name))
        for line in f.read_text().splitlines()
        if line.strip()
    ]
    return gold, {g["id"]: g for g in gold}


def supersede_pairs(corpus: Corpus, path: str, seed: int = 0) -> list[dict[str, Any]]:
    """Positives: explicit 'supersedes #N' text pairs + model-labelled pairs; negatives: hard (labelled) + random."""
    base = Path(path)
    explicit = json.loads((base.parent / "supersede_explicit.json").read_text())
    pairs = [{"a": a, "b": b, "label": True, "source": "explicit"} for a, b in explicit]
    seen = {(a, b) for a, b in explicit}
    for line in base.read_text().splitlines():
        r = json.loads(line)
        for n in r["superseded_by"]:
            if (n, r["old"]) not in seen and r["confidence"] != "low":
                pairs.append(
                    {
                        "a": n,
                        "b": r["old"],
                        "label": True,
                        "source": f"labelled-{r['confidence']}",
                    }
                )
        for n in r["not_superseding"][:2]:
            pairs.append(
                {"a": n, "b": r["old"], "label": False, "source": "hard-negative"}
            )
    rng = random.Random(seed)
    ids = [int(i) for i in corpus.df["id"]]
    positives = sum(p["label"] for p in pairs)
    while sum(p["source"] == "random-negative" for p in pairs) < positives:
        a, b = sorted(rng.sample(ids, 2), reverse=True)
        pairs.append({"a": a, "b": b, "label": False, "source": "random-negative"})
    return pairs


async def run_eval(
    corpus: Corpus,
    schema: Schema,
    jev: Jev,
    gold_glob: str,
    supersede_path: str,
    baseline: bool,
) -> dict[str, Any]:
    gold, by_id = load_gold(gold_glob)
    st = Structurer(corpus, schema, jev)
    t0 = time.perf_counter()
    preds = await asyncio.gather(*(st.structure(g["id"]) for g in gold))
    structure_s, structure_usd, structure_calls = (
        time.perf_counter() - t0,
        jev.usd,
        jev.calls,
    )
    pairs = [(g["id"], r["other"], r["kind"]) for g in gold for r in g["relations"]]
    rels = await asyncio.gather(*(st.relate_pair(a, b) for a, b, _ in pairs))
    relate_usd = jev.usd - structure_usd
    sup = supersede_pairs(corpus, supersede_path)
    sup_preds = await asyncio.gather(*(st.relate_pair(p["a"], p["b"]) for p in sup))

    cal: dict[str, list[tuple[float, bool]]] = {}
    acc: dict[str, list[bool]] = {}
    bands: dict[str, int] = {"accept": 0, "review": 0, "empty": 0}
    rows = []

    def add(step: str, p: float, ok: bool) -> None:
        cal.setdefault(step, []).append((p, ok))
        acc.setdefault(step, []).append(ok)
        bands[band(p)] += 1

    for g, pr in zip(gold, preds):
        mid = g["id"]
        add(
            "gate",
            pr["durable_p"] if g["durable"] else 1 - pr["durable_p"],
            (pr["durable_p"] >= 0.5) == g["durable"],
        )
        add("type", pr["type_p"], pr["type"] == g["type"])
        add(
            "context_level",
            pr["context_level_p"],
            pr["context_level"] == g["context_level"],
        )
        add("validity", pr["validity_p"], pr["validity"] == g["validity"])
        if g["context_level"] in ("component", "worktree"):
            anchor = pr["context_anchor"]
            add(
                "context_anchor",
                pr["context_anchor_p"],
                lenient(
                    str(g["context_anchor"]).removeprefix("worktree:"),
                    anchor.removeprefix("worktree:") if anchor else None,
                ),
            )
        role_rows = {r["role"]: r for r in pr["roles"]}
        e2e = []
        for role, gv in g["roles"].items():
            r = role_rows.get(role) if pr["type"] == g["type"] else None
            pv = r["raw"] if r else None
            ok_l, ok_s = (
                lenient(gv, pv) and r is not None,
                strict(gv, pv) and r is not None,
            )
            e2e.append(ok_l)
            if r is not None:
                add("role", r["p"], ok_l)
                acc.setdefault("role_strict", []).append(ok_s)
                acc.setdefault(
                    f"role_{schema.types[g['type']].roles and next((x.kind for x in schema.types[g['type']].roles if x.name == role), 'value')}",
                    [],
                ).append(ok_l)
                if gv is not None:
                    opts = corpus.entity_options(mid) | corpus.value_options(mid)
                    acc.setdefault("role_option_coverage", []).append(
                        any(lenient(gv, o.removeprefix("new:")) for o in opts)
                    )
        acc.setdefault("role_end_to_end", []).extend(e2e)
        rows.append({"id": mid, "gold": g, "pred": pr})

    rel_rows = []
    for (a, b, gk), r in zip(pairs, rels):
        add("relation", r["p"], r["kind"] == gk)
        rel_rows.append({"a": a, "b": b, "gold": gk, "pred": r["kind"], "p": r["p"]})
    rel_conf: dict[str, dict[str, int]] = {}
    for x in rel_rows:
        rel_conf.setdefault(x["gold"], {}).setdefault(x["pred"], 0)
        rel_conf[x["gold"]][x["pred"]] += 1

    sup_rows = [
        {
            **p,
            "pred": r["kind"],
            "p": r["p"],
            "p_sup": r["probs"].get("supersedes", 0.0),
        }
        for p, r in zip(sup, sup_preds)
    ]
    tp = sum(x["label"] and x["pred"] == "supersedes" for x in sup_rows)
    fp = sum((not x["label"]) and x["pred"] == "supersedes" for x in sup_rows)
    fn = sum(x["label"] and x["pred"] != "supersedes" for x in sup_rows)
    by_source: dict[str, dict[str, float]] = {}
    for s in {x["source"] for x in sup_rows}:
        sel = [x for x in sup_rows if x["source"] == s]
        by_source[s] = {
            "n": len(sel),
            "pred_supersedes": sum(x["pred"] == "supersedes" for x in sel) / len(sel),
            "pred_stale_signal": sum(
                x["pred"] in ("supersedes", "contradicts", "same") for x in sel
            )
            / len(sel),
        }

    calib = {k: dict(zip(("ece", "bins"), ece(v))) for k, v in cal.items()}
    allc = [x for v in cal.values() for x in v]
    calib["all"] = dict(zip(("ece", "bins"), ece(allc)))
    lat = sorted(jev.latencies)
    n = len(gold)
    report: dict[str, Any] = {
        "n_gold": n,
        "n_relation_pairs": len(pairs),
        "n_supersede_pairs": len(sup_rows),
        "accuracy": {k: _acc(v) for k, v in acc.items()},
        "counts": {k: len(v) for k, v in acc.items()},
        "calibration": calib,
        "bands": {k: v / max(sum(bands.values()), 1) for k, v in bands.items()},
        "relation_confusion": rel_conf,
        "supersede": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / max(tp + fp, 1),
            "recall": tp / max(tp + fn, 1),
            "by_source": by_source,
        },
        "cost": {
            "structure_usd_per_1k": structure_usd / n * 1000,
            "relate_usd_per_pair": relate_usd / max(len(pairs), 1),
            "jev_usd_total": jev.usd,
            "jev_calls": jev.calls,
            "jev_retries": jev.retries,
            "structure_calls": structure_calls,
            "structure_wall_s": structure_s,
            "latency_ms": {
                "p50": 1000 * lat[len(lat) // 2],
                "p95": 1000 * lat[int(len(lat) * 0.95)],
                "mean": 1000 * statistics.fmean(lat),
            },
        },
        "rows": rows,
        "relation_rows": rel_rows,
        "supersede_rows": sup_rows,
    }
    if baseline:
        report["baseline"] = await run_baseline(corpus, schema, gold)
    report["headline"] = {
        k: report["accuracy"].get(k)
        for k in (
            "gate",
            "type",
            "context_level",
            "context_anchor",
            "validity",
            "role",
            "role_end_to_end",
            "relation",
        )
    }
    report["headline"].update(
        ece_all=calib["all"]["ece"],
        supersede_p=report["supersede"]["precision"],
        supersede_r=report["supersede"]["recall"],
        usd_per_1k=report["cost"]["structure_usd_per_1k"],
        review_share=report["bands"]["review"],
    )
    if baseline:
        report["headline"]["baseline"] = report["baseline"]["accuracy"]
    return report


BASELINE_PROMPT = """You structure one agent-memory record into a typed record. Schema of record types (name, description, roles):
{schema}

Record #{id} (saved {ts}, project {project}, repo {repo}):
{text}

Older neighbour records:
{neighbours}

Return ONLY JSON: {{"durable": bool, "type": "<type name>", "roles": {{"<role>": "<short verbatim span or null>"}},
"context_level": "global|repo|component|worktree|session", "context_anchor": "<verbatim name or null>",
"validity": "timeless|snapshot|event", "relations": [{{"other": <neighbour id>, "kind": "same|supersedes|refines|contradicts|independent"}}]}}
durable = worth keeping in long-term memory. context_level = most specific scope where the fact holds ({levels}). validity: {validity}.
relations = this record relative to each OLDER neighbour: {relations}."""


async def run_baseline(
    corpus: Corpus, schema: Schema, gold: list[dict[str, Any]]
) -> dict[str, Any]:
    from memtype.corpus import repo_and_worktree

    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{BASELINE_MODEL}:generateContent?key={key}"
    sch = "\n".join(
        f"- {t.name}: {t.description} roles: {', '.join(f'{r.name} ({r.kind}: {r.description})' for r in t.roles)}"
        for t in schema.types.values()
    )
    sem = asyncio.Semaphore(16)
    usage = {"in": 0, "out": 0}
    lat: list[float] = []

    async def one(client: httpx.AsyncClient, g: dict[str, Any]) -> dict[str, Any]:
        r = corpus.row(g["id"])
        neigh = "\n\n".join(
            f"#{x['other']} (saved {corpus.row(x['other'])['ts'][:16]}): {corpus.text(x['other'])[:1200]}"
            for x in g["relations"]
        )
        prompt = BASELINE_PROMPT.format(
            schema=sch,
            id=g["id"],
            ts=r["ts"][:16],
            project=r["project"],
            repo=repo_and_worktree(r["project"])[0],
            text=corpus.text(g["id"]),
            neighbours=neigh,
            levels="global, repo, component, worktree, session",
            validity=json.dumps(VALIDITY),
            relations=json.dumps(RELATIONS),
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
        async with sem:
            for attempt in range(4):
                t0 = time.perf_counter()
                resp = await client.post(url, json=body)
                if resp.status_code == 200:
                    break
                await asyncio.sleep(2**attempt)
        lat.append(time.perf_counter() - t0)
        data = resp.json()
        meta = data.get("usageMetadata") or {}
        usage["in"] += meta.get("promptTokenCount", 0)
        usage["out"] += meta.get("candidatesTokenCount", 0) + meta.get(
            "thoughtsTokenCount", 0
        )
        try:
            return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, json.JSONDecodeError):
            return {}

    async with httpx.AsyncClient(timeout=120) as client:
        preds = await asyncio.gather(*(one(client, g) for g in gold))
    acc: dict[str, list[bool]] = {}
    for g, p in zip(gold, preds):
        acc.setdefault("gate", []).append(bool(p.get("durable")) == g["durable"])
        acc.setdefault("type", []).append(p.get("type") == g["type"])
        acc.setdefault("context_level", []).append(
            p.get("context_level") == g["context_level"]
        )
        acc.setdefault("validity", []).append(p.get("validity") == g["validity"])
        if g["context_level"] in ("component", "worktree"):
            acc.setdefault("context_anchor", []).append(
                lenient(
                    str(g["context_anchor"]).removeprefix("worktree:"),
                    (p.get("context_anchor") or None),
                )
            )
        proles = p.get("roles") or {}
        for role, gv in g["roles"].items():
            ok = p.get("type") == g["type"] and lenient(gv, proles.get(role))
            acc.setdefault("role_end_to_end", []).append(ok)
            if p.get("type") == g["type"]:
                acc.setdefault("role", []).append(ok)
                acc.setdefault("role_strict", []).append(strict(gv, proles.get(role)))
        prel = {
            int(x.get("other", -1)): x.get("kind")
            for x in p.get("relations") or []
            if str(x.get("other", "")).lstrip("-").isdigit()
        }
        for x in g["relations"]:
            acc.setdefault("relation", []).append(prel.get(x["other"]) == x["kind"])
    usd = usage["in"] / 1e6 * BASELINE_PRICE[0] + usage["out"] / 1e6 * BASELINE_PRICE[1]
    return {
        "model": BASELINE_MODEL,
        "accuracy": {k: _acc(v) for k, v in acc.items()},
        "usd_per_1k": usd / len(gold) * 1000,
        "tokens": usage,
        "price_per_m": BASELINE_PRICE,
        "latency_ms_p50": 1000 * sorted(lat)[len(lat) // 2],
        "failed": sum(not p for p in preds),
        "preds": preds,
    }
