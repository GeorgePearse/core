"""Render eval_report.json (+ a structured sidecar) into a self-contained HTML explainer."""

import html
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from memtype.evaluate import lenient

STEPS = [
    ("gate", "Gate: durable?"),
    ("type", "Type (27 options)"),
    ("context_level", "Context level"),
    ("context_anchor", "Context anchor"),
    ("validity", "Time window"),
    ("role", "Roles (given right type)"),
    ("role_end_to_end", "Roles end-to-end"),
    ("relation", "Relation to neighbour"),
]

CSS = """
:root{--surface:#ffffff;--surface-2:#f4f3ef;--text:#0b0b0b;--text-2:#52514e;--muted:#8a8984;--rule:#e2e1dc;
--s1:#2a78d6;--s2:#eb6834;--good:#008300;--bad:#e34948;--code:#f0efea}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--surface:#1a1a19;--surface-2:#242422;--text:#ffffff;
--text-2:#c3c2b7;--muted:#8f8e86;--rule:#3a3a37;--s1:#3987e5;--s2:#d95926;--good:#3fa33f;--bad:#e66767;--code:#2a2a28}}
:root[data-theme="dark"]{--surface:#1a1a19;--surface-2:#242422;--text:#ffffff;--text-2:#c3c2b7;--muted:#8f8e86;
--rule:#3a3a37;--s1:#3987e5;--s2:#d95926;--good:#3fa33f;--bad:#e66767;--code:#2a2a28}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--text);
font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:36px 0 8px;border-bottom:1px solid var(--rule);padding-bottom:4px}
p,li{color:var(--text-2)}b,strong{color:var(--text)}.sub{color:var(--muted);margin:0 0 20px}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}th,td{text-align:left;padding:6px 8px;
border-bottom:1px solid var(--rule);vertical-align:top}th{color:var(--text-2);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}.wrap{overflow-x:auto}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--surface-2);border-radius:8px;padding:12px}.tile .v{font-size:24px;font-weight:650;color:var(--text)}
.tile .l{font-size:13px;color:var(--text-2)}code{background:var(--code);padding:1px 4px;border-radius:4px;font-size:13px}
.ok{color:var(--good)}.no{color:var(--bad)}.key{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
svg text{fill:var(--text-2);font-size:11px}.ex{background:var(--surface-2);border-radius:8px;padding:10px 12px;margin:8px 0}
.ex .t{color:var(--text);font-size:13px}pre{background:var(--code);padding:10px;border-radius:6px;overflow-x:auto;font-size:12.5px}
"""


def pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def esc(s: Any) -> str:
    return html.escape(str(s))


def bars(rows: list[tuple[str, float | None, float | None]]) -> str:
    w, rh, left = 640, 26, 190
    h = rh * len(rows) + 30
    out = [
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="accuracy, Jev vs baseline">'
    ]
    for x in (0, 0.25, 0.5, 0.75, 1.0):
        gx = left + x * (w - left - 40)
        out.append(
            f'<line x1="{gx}" x2="{gx}" y1="0" y2="{h - 20}" stroke="var(--rule)"/>'
            f'<text x="{gx}" y="{h - 6}" text-anchor="middle">{x:.0%}</text>'
        )
    for i, (label, a, b) in enumerate(rows):
        y = i * rh + 4
        out.append(
            f'<text x="{left - 8}" y="{y + 14}" text-anchor="end">{esc(label)}</text>'
        )
        for j, (v, col) in enumerate(((a, "var(--s1)"), (b, "var(--s2)"))):
            if v is not None:
                bw = v * (w - left - 40)
                out.append(
                    f'<rect x="{left}" y="{y + j * 10}" width="{bw:.1f}" height="8" rx="2" fill="{col}">'
                    f'<title>{esc(label)}: {"Jev" if j == 0 else "Gemini"} {v:.1%}</title></rect>'
                )
    out.append("</svg>")
    return "".join(out)


def reliability(bins: list[dict[str, float]], title: str) -> str:
    s, pad = 240, 30
    out = [
        f'<svg viewBox="0 0 {s + pad + 10} {s + pad + 10}" width="280" role="img" aria-label="{esc(title)}">',
        f'<line x1="{pad}" y1="{s}" x2="{pad + s}" y2="0" stroke="var(--muted)" stroke-dasharray="4 4"/>',
        f'<line x1="{pad}" y1="{s}" x2="{pad + s}" y2="{s}" stroke="var(--rule)"/>'
        f'<line x1="{pad}" y1="0" x2="{pad}" y2="{s}" stroke="var(--rule)"/>',
    ]
    for t in (0, 0.5, 1):
        out.append(
            f'<text x="{pad + t * s}" y="{s + 14}" text-anchor="middle">{t:g}</text>'
            f'<text x="{pad - 4}" y="{s - t * s + 4}" text-anchor="end">{t:g}</text>'
        )
    pts = [(pad + b["conf"] * s, s - b["acc"] * s, b) for b in bins]
    out.append(
        '<polyline fill="none" stroke="var(--s1)" stroke-width="2" points="'
        + " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        + '"/>'
    )
    for x, y, b in pts:
        r = 3 + min(6, b["n"] ** 0.5 / 3)
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="var(--s1)" stroke="var(--surface)" stroke-width="2">'
            f'<title>p≈{b["conf"]:.2f}: accuracy {b["acc"]:.0%} (n={b["n"]})</title></circle>'
        )
    out.append(
        f'<text x="{pad + s / 2}" y="{s + 28}" text-anchor="middle">stated probability</text></svg>'
    )
    return f'<figure style="margin:0;display:inline-block"><figcaption class="t">{esc(title)}</figcaption>{"".join(out)}</figure>'


def by_band(report: dict[str, Any]) -> dict[str, dict[str, list[bool]]]:
    out: dict[str, dict[str, list[bool]]] = {}

    def add(step: str, p: float, ok: bool) -> None:
        b = (
            "accept ≥0.8"
            if p >= 0.8
            else "review 0.5–0.8"
            if p >= 0.5
            else "empty <0.5"
        )
        out.setdefault(step, {}).setdefault(b, []).append(ok)

    for r in report["rows"]:
        g, p = r["gold"], r["pred"]
        add("type", p["type_p"], p["type"] == g["type"])
        add(
            "context_level",
            p["context_level_p"],
            p["context_level"] == g["context_level"],
        )
        add("validity", p["validity_p"], p["validity"] == g["validity"])
        if p["type"] == g["type"]:
            for o in p["roles"]:
                add("role", o["p"], lenient(g["roles"].get(o["role"]), o["raw"]))
    for x in report["relation_rows"]:
        add("relation", x["p"], x["gold"] == x["pred"])
    return out


def sidecar_stats(path: Path, db: Path) -> dict[str, Any]:
    side = sqlite3.connect(f"file:{path}", uri=True)
    side.execute(f"ATTACH DATABASE 'file:{db}?mode=ro' AS e")
    q = lambda sql: side.execute(sql).fetchall()  # noqa: E731
    stats = {
        "records": q("SELECT count(*) FROM mt_record")[0][0],
        "types": q(
            "SELECT type, count(*) c FROM mt_record GROUP BY type ORDER BY c DESC"
        ),
        "conflicts": dict(
            q("SELECT method, count(*) FROM mt_conflict GROUP BY method")
        ),
        "relations": q(
            "SELECT kind, band, count(*) FROM mt_relation GROUP BY kind, band ORDER BY kind, band"
        ),
        "stale_active": q(
            "SELECT r.src, r.dst, r.p, substr(a.summary,1,140), substr(b.summary,1,140) FROM mt_relation r "
            "JOIN e.memories a ON a.id=r.src JOIN e.memories b ON b.id=r.dst "
            "WHERE r.kind='supersedes' AND r.p>=0.8 AND b.status='active' ORDER BY r.p DESC, r.src DESC"
        ),
        "key_examples": q(
            "SELECT c.a, c.b, c.detail, substr(a.summary,1,140), substr(b.summary,1,140) FROM mt_conflict c "
            "JOIN e.memories a ON a.id=c.a JOIN e.memories b ON b.id=c.b WHERE c.method='key' LIMIT 6"
        ),
        "jev_examples": q(
            "SELECT c.a, c.b, c.detail, substr(a.summary,1,140), substr(b.summary,1,140) FROM mt_conflict c "
            "JOIN e.memories a ON a.id=c.a JOIN e.memories b ON b.id=c.b WHERE c.method='jev' LIMIT 4"
        ),
        "run": q("SELECT records, calls, usd, seconds FROM mt_run"),
        "superseded_engrim": q(
            "SELECT count(*) FROM e.memories WHERE status='superseded'"
        )[0][0],
    }
    side.close()
    return stats


def examples(report: dict[str, Any], db: Path) -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

    def summary(i):
        return conn.execute(
            "SELECT substr(summary,1,170) FROM memories WHERE id=?", (i,)
        ).fetchone()[0]  # noqa: E731

    rows = report["rows"]
    out = []
    good_type = [
        r
        for r in rows
        if r["pred"]["type"] == r["gold"]["type"] and r["pred"]["type_p"] >= 0.95
    ]
    for r in good_type[:3]:
        roles = ", ".join(
            f"{o['role']}={o['raw']!r} ({o['p']:.2f})"
            for o in r["pred"]["roles"]
            if o["raw"]
        )[:260]
        out.append(
            (
                "good",
                summary(r["id"]),
                f"#{r['id']} typed <b>{r['pred']['type']}</b> p={r['pred']['type_p']:.2f}; {esc(roles)}",
            )
        )
    over = sorted(
        (r for r in rows if r["pred"]["type"] != r["gold"]["type"]),
        key=lambda r: -r["pred"]["type_p"],
    )
    for r in over[:2]:
        out.append(
            (
                "bad",
                summary(r["id"]),
                f"#{r['id']} typed <b>{r['pred']['type']}</b> p={r['pred']['type_p']:.2f}, gold <b>{r['gold']['type']}</b> (overconfident)",
            )
        )
    sup = report["supersede_rows"]
    for x in [
        x for x in sup if x["source"] == "explicit" and x["pred"] == "supersedes"
    ][:2]:
        out.append(
            (
                "good",
                summary(x["a"]),
                f"#{x['a']} → #{x['b']}: <b>supersedes</b> p={x['p']:.2f} (explicit pair) — older: {esc(summary(x['b']))}",
            )
        )
    for x in [
        x for x in sup if x["source"] == "explicit" and x["pred"] != "supersedes"
    ][:1]:
        out.append(
            (
                "bad",
                summary(x["a"]),
                f"#{x['a']} → #{x['b']}: predicted <b>{x['pred']}</b> p={x['p']:.2f}, but the text says it supersedes — older: {esc(summary(x['b']))}",
            )
        )
    for x in [
        x for x in sup if x["source"] == "hard-negative" and x["pred"] == "supersedes"
    ][:1]:
        out.append(
            (
                "bad",
                summary(x["a"]),
                f"#{x['a']} → #{x['b']}: false <b>supersedes</b> p={x['p']:.2f} on a hard negative — older: {esc(summary(x['b']))}",
            )
        )
    roles_wrong = [
        (r, o)
        for r in rows
        if r["pred"]["type"] == r["gold"]["type"]
        for o in r["pred"]["roles"]
        if o["band"] == "accept"
        and not lenient(r["gold"]["roles"].get(o["role"]), o["raw"])
    ]
    for r, o in roles_wrong[:1]:
        out.append(
            (
                "bad",
                summary(r["id"]),
                f"#{r['id']} role <b>{o['role']}</b> = {esc(o['raw'])!s} accepted at p={o['p']:.2f}; gold = {esc(r['gold']['roles'].get(o['role']))}",
            )
        )
    conn.close()
    return out[:10]


def render(
    report: dict[str, Any],
    side: dict[str, Any],
    exs: list[tuple[str, str, str]],
    history: list[tuple[str, dict]],
    public: bool = False,
) -> str:
    acc, base = report["accuracy"], report.get("baseline", {}).get("accuracy", {})
    cost, sup, bl = report["cost"], report["supersede"], report.get("baseline", {})
    bb = by_band(report)
    h = []
    h.append(
        f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Engrim Jev Structurer</title><style>{CSS}</style></head><body><main>"
    )
    h.append(
        "<h1>Typing agent memory with Jev: an engrim sidecar trial</h1>"
        "<p class=sub>2026-10-06 · memtype (lib/python/memtype) · engrim v1.3.0 (read-only copy) · Jev typesafe-ai/jev via Vercel AI Gateway</p>"
    )
    h.append(
        "<div class=tiles>"
        f"<div class=tile><div class=v>{pct(acc['type'])}</div><div class=l>type accuracy (Gemini flash {pct(base.get('type'))})</div></div>"
        f"<div class=tile><div class=v>{pct(acc['relation'])}</div><div class=l>relation accuracy on 390 neighbour pairs (Gemini {pct(base.get('relation'))})</div></div>"
        f"<div class=tile><div class=v>{sup['precision']:.2f} / {sup['recall']:.2f}</div><div class=l>supersedes precision / recall ({report['n_supersede_pairs']} pairs)</div></div>"
        f"<div class=tile><div class=v>{report['calibration']['all']['ece']:.3f}</div><div class=l>ECE, all Jev fields</div></div>"
        f"<div class=tile><div class=v>${cost['structure_usd_per_1k']:.2f}</div><div class=l>Jev $ per 1k records (Gemini ${bl.get('usd_per_1k', 0):.2f})</div></div>"
        f"<div class=tile><div class=v>{cost['latency_ms']['p50']:.0f} ms</div><div class=l>Jev call p50 (p95 {cost['latency_ms']['p95']:.0f} ms; Gemini p50 {bl.get('latency_ms_p50', 0):.0f} ms)</div></div>"
        "</div>"
    )
    jev_rec = cost["structure_usd_per_1k"] + 4 * 1000 * cost["relate_usd_per_pair"]
    jev_ms = 3 * cost["latency_ms"]["p50"]
    cheaper, faster = (
        bl.get("usd_per_1k", 0) / jev_rec,
        bl.get("latency_ms_p50", 0) / jev_ms,
    )
    h.append(
        "<h2>Verdict</h2><p><b>Wire in only the parts that win.</b> Per record, including relations to 4 neighbours, Jev costs "
        f"${jev_rec:.2f}/1k against ${bl.get('usd_per_1k', 0):.2f}/1k for one-shot {esc(bl.get('model', ''))}, about {cheaper:.0f}× cheaper. "
        f"It takes about {jev_ms:.0f} ms of critical path (three call rounds) against {bl.get('latency_ms_p50', 0):.0f} ms, about {faster:.0f}× faster. "
        "It matches the LLM on relations, beats it on context scope, and its probabilities carry signal: accepted fields "
        "(p ≥ 0.8) are far more accurate than review-band ones. It is worse at <b>type</b> and at <b>role filling</b>. It can only pick "
        "spans that the extractor offers, while the LLM writes its own. Supersede detection is the strongest result. On engrim's own "
        "superseded records it finds the replacing record with high precision and never fired on random pairs. Recommended engrim "
        "write-path hook: after <code>engrim add</code>, run the relate step against the top-4 older neighbours and suggest "
        "<code>engrim supersede</code> when p(supersedes) ≥ 0.8. Keep typed roles as an offline sidecar until role filling improves.</p>"
    )
    h.append(
        "<h2>Accuracy vs one-shot LLM baseline</h2><p><span class=key style='background:var(--s1)'></span>Jev (typed, calibrated) "
        f"&nbsp; <span class=key style='background:var(--s2)'></span>{esc(bl.get('model', 'baseline'))} one-shot JSON, no probabilities. "
        "100 gold records; roles scored with a lenient span match (same, containment, or ≥80% token overlap).</p>"
    )
    h.append(bars([(lab, acc.get(k), base.get(k)) for k, lab in STEPS]))
    h.append(
        "<div class=wrap><table><tr><th>Step</th><th>n</th><th>Jev</th><th>Gemini flash</th><th>Jev ECE</th></tr>"
    )
    for k, lab in STEPS:
        e = report["calibration"].get(k, {}).get("ece")
        h.append(
            f"<tr><td>{lab}</td><td class=n>{report['counts'].get(k, '')}</td><td class=n>{pct(acc.get(k))}</td>"
            f"<td class=n>{pct(base.get(k))}</td><td class=n>{'' if e is None else f'{e:.3f}'}</td></tr>"
        )
    h.append(
        f"<tr><td>Role strict (token Jaccard ≥ 0.5)</td><td></td><td class=n>{pct(acc.get('role_strict'))}</td><td class=n>{pct(base.get('role_strict'))}</td><td></td></tr>"
    )
    h.append(
        f"<tr><td>Role option coverage (gold span is among offered options)</td><td></td><td class=n>{pct(acc.get('role_option_coverage'))}</td><td></td><td></td></tr></table></div>"
    )
    h.append(
        "<h2>Does the probability mean anything? Accuracy by confidence band</h2><p>Confidence policy: ≥ 0.8 auto-accept, 0.5–0.8 review "
        f"queue, &lt; 0.5 leave the field empty and keep the raw text. Share of all Jev fields: accept {pct(report['bands']['accept'])}, "
        f"review {pct(report['bands']['review'])}, empty {pct(report['bands']['empty'])}.</p><div class=wrap><table><tr><th>Step</th>"
        "<th>accept ≥0.8</th><th>review 0.5–0.8</th><th>empty &lt;0.5</th></tr>"
    )
    for k in ("type", "context_level", "validity", "role", "relation"):
        cells = []
        for b in ("accept ≥0.8", "review 0.5–0.8", "empty <0.5"):
            xs = bb.get(k, {}).get(b, [])
            cells.append(
                f"<td class=n>{pct(sum(xs) / len(xs)) if xs else '–'} <span style='color:var(--muted)'>n={len(xs)}</span></td>"
            )
        h.append(f"<tr><td>{k}</td>{''.join(cells)}</tr>")
    h.append("</table></div>")
    h.append(
        "<p>Reliability diagrams (dashed = perfect calibration; dot size ~ bin count; hover for values):</p><div>"
    )
    for k in ("all", "type", "role", "relation"):
        h.append(
            reliability(
                report["calibration"][k]["bins"],
                f"{k} (ECE {report['calibration'][k]['ece']:.3f})",
            )
        )
    h.append("</div>")
    h.append(
        "<h2>Supersede detection on engrim's real history</h2><p>engrim's <code>supersede</code> stores no pointer to the replacing "
        "record, so the ground truth was rebuilt. 11 pairs come from records whose text says <i>supersedes #N</i>, <i>correction</i> or <i>update to #N</i>. "
        "116 more were matched to engrim's 73 other superseded records by a Claude subagent reading the newer candidates (model-made, high or medium "
        "confidence only). Negatives are 137 hard (retrieved neighbours the labeller rejected) plus 127 random pairs. "
        "Each pair gets one Jev call with a 5-way relation choice and two boolean checks (same subject? older one now stale?).</p>"
        "<div class=wrap><table><tr><th>Pair source</th><th>n</th><th>predicted supersedes</th></tr>"
    )
    for s_, v in sorted(sup["by_source"].items()):
        h.append(
            f"<tr><td>{s_}</td><td class=n>{v['n']}</td><td class=n>{pct(v['pred_supersedes'])}</td></tr>"
        )
    h.append(
        f"</table></div><p>Overall: precision <b>{sup['precision']:.2f}</b>, recall <b>{sup['recall']:.2f}</b> (tp {sup['tp']}, fp {sup['fp']}, fn {sup['fn']}).</p>"
    )
    conf = report["relation_confusion"]
    kinds = ["same", "supersedes", "refines", "contradicts", "independent"]
    h.append(
        "<p>Relation confusion on the 390 gold neighbour pairs (rows = gold, columns = Jev):</p><div class=wrap><table><tr><th></th>"
        + "".join(f"<th>{k}</th>" for k in kinds)
        + "</tr>"
    )
    for g in kinds:
        h.append(
            f"<tr><td>{g}</td>"
            + "".join(f"<td class=n>{conf.get(g, {}).get(p, '')}</td>" for p in kinds)
            + "</tr>"
        )
    h.append("</table></div>")
    if side:
        cf = side["conflicts"]
        h.append(f"<h2>Full corpus run: {side['records']} records</h2>")
        run = side["run"][-1] if side["run"] else (0, 0, 0, 0)
        h.append(
            f"<p>{run[1]} Jev calls, ${run[2]:.2f}, {run[3] / 60:.0f} min wall time. Conflicts found: "
            f"<b>{cf.get('key', 0)}</b> by the deterministic key check (no model call), <b>{cf.get('jev', 0)}</b> by Jev "
            f"<code>contradicts</code> (p ≥ 0.5), and <b>{cf.get('compose', 0)}</b> by path composition. "
            f"<b>{len(side['stale_active'])}</b> engrim records are still <code>active</code> although Jev says a newer record supersedes them "
            "with p ≥ 0.8. These are candidates for <code>engrim supersede</code>.</p>"
        )
        h.append(
            "<div class=wrap><table><tr><th>Type</th><th>records</th></tr>"
            + "".join(
                f"<tr><td>{esc(t)}</td><td class=n>{n}</td></tr>"
                for t, n in side["types"][:12]
            )
            + "</table></div>"
        )
        if public:
            h.append(
                "<p><i>Record-level examples are left out of this public copy. They are in the internal analysis artefact.</i></p>"
            )
    if side and not public:
        h.append(
            "<p><b>Key-check conflicts</b> (same type, same key roles and context, different value):</p>"
        )
        for a, b, d, sa, sb in side["key_examples"]:
            d = json.loads(d)
            h.append(
                f"<div class=ex><div class=t>#{a} vs #{b} · {esc(d['type'])} · key {esc(d['key'])} · values {esc(list(d['values'].values()))}</div>"
                f"<div>{esc(sa)}</div><div style='color:var(--muted)'>{esc(sb)}</div></div>"
            )
        h.append("<p><b>Stale but still active</b> (top suggestions):</p>")
        for a, b, p, sa, sb in side["stale_active"][:6]:
            h.append(
                f"<div class=ex><div class=t>#{a} supersedes #{b} · p={p:.2f}</div><div>{esc(sa)}</div>"
                f"<div style='color:var(--muted)'>{esc(sb)}</div></div>"
            )
    h.append("<h2>Ten concrete examples</h2>" if not public else "")
    for kind, s_, d in [] if public else exs:
        h.append(
            f"<div class=ex><div class=t><span class={'ok' if kind == 'good' else 'no'}>{'✓ good' if kind == 'good' else '✗ bad'}</span> "
            f"· {esc(s_)}</div><div>{d}</div></div>"
        )
    h.append(
        "<h2>Design</h2><pre>engrim memory.db (read-only COPY) ──► Corpus: records, model2vec vectors, FTS5, entity index (tags gazetteer + regex), value spans\n"
        "     per record ──► Jev call 1 (5 questions): durable? · type (27) · context level · context anchor · time window\n"
        "                ──► Jev call 2: one choice per role of the chosen type (entity shortlist or value spans + clauses, ≤255 options)\n"
        "                ──► relate: top-4 older neighbours (embedding ⊕ BM25, RRF), 1 call each: 5-way relation + same_subject + b_stale\n"
        "     whole store ─► key check (type, key roles, context → value differs) · Jev contradicts · transitive path compose\n"
        "sidecar.db: mt_record · mt_role(value, raw, p, band) · mt_relation(kind, p, probs) · mt_conflict · mt_run</pre>"
        "<p>Every field stores its probability and band. CLI: <code>python -m memtype.cli --db COPY --sidecar side.db "
        "structure|conflicts|show ID|eval</code>. Runs are incremental through a content hash, and relations are only computed for newly structured records.</p>"
    )
    h.append(
        "<h2>How the prompts got here (same gold set; read the numbers as optimistic)</h2><div class=wrap><table><tr><th>Version</th>"
        "<th>type</th><th>context</th><th>role</th><th>relation</th><th>sup P / R</th></tr>"
    )
    for name, hd in history:
        h.append(
            f"<tr><td>{esc(name)}</td><td class=n>{pct(hd['type'])}</td><td class=n>{pct(hd['context_level'])}</td>"
            f"<td class=n>{pct(hd['role'])}</td><td class=n>{pct(hd['relation'])}</td><td class=n>{hd['supersede_p']:.2f} / {hd['supersede_r']:.2f}</td></tr>"
        )
    h.append("</table></div>")
    h.append(
        "<h2>Gaps and caveats</h2><ul>"
        "<li><b>Every gold label is model-made.</b> Claude subagents wrote the schema, the 100 gold records and the 116 inferred supersede pairs, and no human has checked them yet. "
        "They are kept off this public repo (memory text is private) at <code>/var/tmp/engrim-jev-structurer-20261006/</code> on george-t4 for spot-checking. Context and role boundaries are subjective: one labeller marked every record in its batch durable.</li>"
        "<li>The prompts were changed twice while looking at this gold set: context wording and relation gating. A held-out set would score lower.</li>"
        "<li>Role filling is capped by the candidate extractor. Jev cannot write a span. Coverage is high, but long free-text roles such as cause and workaround become clause picks.</li>"
        "<li>The baseline sees each record's 4 neighbours in its single call. Its relation score is per-record batched and its roles are free text, so it is a strong baseline.</li>"
        "<li>Compose runs only over <code>relation</code>-typed facts. That type is rare in this corpus, so path checks found little. The value is in key checks and supersede detection.</li>"
        "<li>The open-world extension (an LLM proposes new types and Jev verifies them) is not built.</li></ul>"
    )
    h.append("</main></body></html>")
    return "".join(h)


def main() -> None:
    public = "--public" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--public"]
    report_path, db, sidecar, out = map(Path, args[:4])
    history = [
        (Path(p).stem, json.loads(Path(p).read_text())["headline"]) for p in args[4:]
    ]
    report = json.loads(report_path.read_text())
    side = sidecar_stats(sidecar, db) if sidecar.exists() else {}
    out.write_text(render(report, side, examples(report, db), history, public))


if __name__ == "__main__":
    main()
