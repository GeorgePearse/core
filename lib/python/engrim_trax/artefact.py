"""Build the dark-mode HTML report for the engrim -> trackinizer import from the run's JSON summaries."""

import base64
import html
import json
import sys
from pathlib import Path

SCRATCH = Path("/var/tmp/engrim-trax")
KINDS = ("Issue", "Belief", "Experiment", "WebResult", "Paper", "CodeChange")
ENGRIM_TYPES = ("state", "fact", "decision", "feedback", "reference", "user")

CSS = """
:root { --bg:#ffffff; --fg:#1b1f24; --muted:#5c6470; --line:#d9dee5; --card:#f5f7fa; --accent:#2f6fed;
  --ok:#1f8a4c; --warn:#b7791f; --bad:#c0392b; --bar:#2f6fed; --bar2:#8a63d2; --bar3:#2aa58a; --bar4:#c9a227; }
@media (prefers-color-scheme: dark) { :root { --bg:#0f1115; --fg:#e6e9ee; --muted:#9aa4b2; --line:#2a2f3a; --card:#171a21;
  --accent:#6ea0ff; --ok:#4cc38a; --warn:#e2b04a; --bad:#ff7b72; --bar:#6ea0ff; --bar2:#b393f5; --bar3:#5fd2b4; --bar4:#e5c45a; } }
html { color-scheme: light dark; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
main { max-width:1040px; margin:0 auto; padding:32px 20px 64px; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:19px; margin:36px 0 10px; border-bottom:1px solid var(--line); padding-bottom:6px; }
h3 { font-size:15px; margin:18px 0 6px; color:var(--muted); font-weight:600; }
p, li { max-width:78ch; } .muted { color:var(--muted); } code { background:var(--card); padding:1px 5px; border-radius:4px; font-size:13px; }
table { border-collapse:collapse; width:100%; margin:10px 0 18px; font-size:14px; } th, td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; } td.n, th.n { text-align:right; font-variant-numeric:tabular-nums; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:14px 0; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; } .tile b { display:block; font-size:22px; } .tile span { color:var(--muted); font-size:13px; }
.bars { margin:8px 0 16px; } .bar { display:grid; grid-template-columns:130px 1fr 70px; gap:10px; align-items:center; margin:4px 0; font-size:14px; }
.bar i { display:block; height:14px; border-radius:3px; background:var(--bar); } .bar .n { text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }
.stack { display:flex; height:16px; border-radius:3px; overflow:hidden; } .stack i { display:block; height:100%; }
.legend { display:flex; gap:14px; flex-wrap:wrap; font-size:13px; color:var(--muted); margin:6px 0 14px; } .legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:middle; }
figure { margin:14px 0 24px; } figure img { width:100%; border:1px solid var(--line); border-radius:8px; } figcaption { color:var(--muted); font-size:13px; margin-top:6px; }
.verdict { background:var(--card); border-left:4px solid var(--accent); padding:12px 16px; border-radius:6px; margin:14px 0; }
.ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); }
blockquote { margin:6px 0 10px; padding:6px 12px; border-left:3px solid var(--line); color:var(--muted); font-size:14px; }
"""


def img(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def esc(s: object) -> str:
    return html.escape(str(s))


def bars(items: list[tuple[str, int]], colors: tuple[str, ...] = ("var(--bar)",)) -> str:
    top = max((n for _, n in items), default=1) or 1
    out = ['<div class="bars">']
    for i, (label, n) in enumerate(items):
        c = colors[i % len(colors)]
        out.append(
            f'<div class="bar"><span>{esc(label)}</span><i style="width:{100 * n / top:.1f}%;background:{c}"></i><span class="n">{n:,}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def build(out_path: Path) -> None:
    full = json.load((SCRATCH / "summary-full.json").open())
    first = json.load((SCRATCH / "summary-50.json").open())
    idem = json.load((SCRATCH / "idempotency.json").open())
    review = json.load((SCRATCH / "spotcheck_review.json").open())
    sample = {r["id"]: r for r in json.load((SCRATCH / "spotcheck.json").open())}
    sess_path = SCRATCH / "summary-sessions.json"
    sess = json.load(sess_path.open())["sessions"] if sess_path.exists() else None
    log = json.load((SCRATCH / "log-size.json").open()) if (SCRATCH / "log-size.json").exists() else {}
    eng = {"state": 2229, "fact": 774, "decision": 149, "feedback": 105, "reference": 58, "user": 2}
    t2k = full["type_to_kind"]
    kinds = full["kinds"]
    bands = full["bands"]
    jev_calls = first["jev"]["calls"] + full["jev"]["calls"]
    jev_usd = first["jev"]["usd"] + full["jev"]["usd"]
    wall = first["wall_seconds"] + full["wall_seconds"] + (sess["seconds"] if sess else 0)

    rows = []
    for t in ENGRIM_TYPES:
        cells = "".join(f'<td class="n">{t2k.get(f"{t}->{k}", 0) or "·"}</td>' for k in KINDS)
        rows.append(f"<tr><td><code>{t}</code></td><td class=\"n\">{eng[t]:,}</td>{cells}</tr>")
    total_cells = "".join(f'<td class="n"><b>{kinds.get(k, 0):,}</b></td>' for k in KINDS)
    rows.append(f'<tr><td><b>total</b></td><td class="n"><b>3,317</b></td>{total_cells}</tr>')
    count_table = (
        "<table><thead><tr><th>engrim type</th><th class=\"n\">rows</th>"
        + "".join(f'<th class="n">{k}</th>' for k in KINDS)
        + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    band_total = sum(bands.values())
    band_stack = (
        '<div class="stack">'
        f'<i style="width:{100 * bands["accept"] / band_total:.1f}%;background:var(--ok)"></i>'
        f'<i style="width:{100 * bands["review"] / band_total:.1f}%;background:var(--warn)"></i>'
        f'<i style="width:{100 * bands["fallback"] / band_total:.1f}%;background:var(--bad)"></i></div>'
        f'<div class="legend"><span><i style="background:var(--ok)"></i>accept p ≥ 0.8: {bands["accept"]:,}</span>'
        f'<span><i style="background:var(--warn)"></i>0.5–0.8, labelled jev:low-confidence: {bands["review"]:,}</span>'
        f'<span><i style="background:var(--bad)"></i>&lt; 0.5, engrim default kind, labelled jev:fallback: {bands["fallback"]:,}</span></div>'
    )

    dis_rows = "".join(
        f"<tr><td>#{d['id']}</td><td><code>{d['engrim']}</code></td><td>{d['jev']} <span class=\"muted\">p={d['jev_p']}</span></td>"
        f"<td>{d['mine']}</td><td>{esc(d['text'])}</td></tr>"
        for d in review["disagreements"]
    )
    agree_rows = "".join(
        f"<tr><td>#{i}</td><td><code>{sample[i]['type']}</code></td><td>{sample[i]['jev_kind']} <span class=\"muted\">p={sample[i]['jev_p']}</span></td>"
        f"<td>{esc(sample[i]['text'][:140])}…</td></tr>"
        for i in sorted(int(k) for k in review["my_kind"]) if sample[i]["jev_kind"] == review["my_kind"][str(i)]
    )

    edges = full["edges"]
    edge_bars = bars(
        [("produced_by", edges["produced_by"]), ("proves", edges["proves"]), ("supersedes", edges["supersedes"]), ("favors", edges["favors"])],
        ("var(--bar)", "var(--bar3)", "var(--bar2)", "var(--bar4)"),
    )

    shots = []
    for name, cap in (
        ("graph-final.png", "The graph view after the import (1,000-node default window; the legend counts the kinds in view)."),
        ("belief-465-evidence.png", "Belief#465 (engrim decision #1932): 13 proved_by edges from Experiments, valence +0.5 (green) and one against (red), judgement proven, author confidence 0.76 from Jev's true_now probability."),
        ("issue-502.png", "Issue#502 (engrim state, VLM Chat one-instance rule): produced_by edges from the three consolidation records that share its PR, and Jev-confirmed supersedes edges to the superseded ones."),
        ("agentsession.png", "One AgentSession from the engrim log: the Claude session envelope with its records (UserMessage / AssistantMessage) readable in the console view."),
    ):
        p = SCRATCH / "shots" / name
        if p.exists():
            shots.append(f'<figure><img src="{img(p)}" alt="{esc(cap)}"><figcaption>{esc(cap)}</figcaption></figure>')

    sess_html = ""
    if sess:
        sess_html = (
            f"<p>{sess['sessions']:,} AgentSessions (one per engrim <code>(project, session)</code>), "
            f"{sess['records_written']:,} IR records written ({sess['records_skipped']:,} already present on re-append), "
            f"in {sess['seconds']:,} s. Each engrim log row became a <code>UserMessage</code> or "
            f"<code>AssistantMessage</code> (timestamp, content, extra = engrim log id, msg uuid, role) through "
            f"<code>trackinizer.types.session_records.SessionRecordRow</code> and <code>append_records</code>; "
            f"<code>cli</code> = claude (every raw line is Claude Code JSONL), <code>started</code>/<code>ended</code> = min/max ts, "
            f"<code>cli_session_id</code> = the Claude session id.</p>"
        )
    else:
        sess_html = "<p class=\"warn\">Session import had not finished when this report was built.</p>"

    left_out = f"""
<ul>
<li><b>The <code>raw</code> column of the log</b> ({log.get('raw_bytes', 2532000757) / 1e9:.2f} GB of the 2.92 GB store, the native Claude Code JSONL line per message):
left in SQLite. Only <code>content</code> ({log.get('content_bytes', 19555325) / 1e6:.1f} MB) was imported, so tool calls, thinking blocks and token usage that live inside the raw
line are not in trackinizer. PGlite is not meant for gigabytes.</li>
<li><b>Record <code>created</code> timestamps</b>: the create API has no <code>created</code> field, so every inquiry is stamped with import time (in engrim <code>ts</code> order) and the real ts
lives in the description's provenance block. Trackinizer's "newest first" views therefore show import order, not memory order.</li>
<li><b>32 of 80 superseded records</b> got no <code>supersedes</code> edge: no candidate in the same project within 60 days with tag/link overlap reached Jev p ≥ 0.8. They carry the label <code>engrim:superseded</code> instead.</li>
<li><b>engrim <code>embedding</code> and FTS tables</b>: not imported (derived data; trackinizer has its own stub embedder and search).</li>
<li><b>engrim_meta</b> (per-project key/value): not imported.</li>
</ul>"""

    verdict = """
<div class="verdict">
<p><b>Verdict: trackinizer is a usable graph <i>view</i> of this memory, not yet a replacement for engrim's SQLite.</b></p>
<p>What works: the whole store (3,317 records, 530 edges, the session log) imports in under five minutes and under a dollar of Jev,
the import is idempotent by construction (client-minted keys, byte-identical re-export), the typed model gives real structure
(Issues with status, Beliefs with judgement + confidence, Experiments with outcome + metrics) and the UI's neighbourhood graph
makes the evidence around a Belief visible in a way <code>engrim recall</code> cannot.</p>
<p>What does not: (1) no <code>created</code> on create, so time order is lost from the UI's sort; (2) Jev's kind decision leans to Issue /
Experiment for engrim <code>state</code> rows that are really diagnoses or rules (7 of 40 in the spot-check, 82% agreement), so
~700 records carry <code>jev:low-confidence</code> and need a review pass before the kinds are trusted; (3) engrim's write path is
one CLI line from any session and a hook mirrors it; trackinizer needs the server up and the agent to pick a kind and fields,
which is more friction per memory; (4) the raw session log (2.5 GB) has no sensible home in PGlite.</p>
<p>Recommended use: keep engrim as the write-side store and re-run this importer (incremental, cached) to publish the graph into
trackinizer for browsing and for the Belief/evidence structure; revisit a switch if trackinizer gains a <code>created</code> override
and a one-line capture CLI.</p>
</div>"""

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>engrim store imported into trackinizer via Jev typing</title><style>{CSS}</style></head><body><main>
<h1>engrim store imported into trackinizer via Jev typing</h1>
<p class="muted">2026-10-07 · tool trial · George's ask: "copy everything from engrim into trackinizer and boot it up; if there's any need to change format use Jev as the classifier".
Server: trackinizer 0.1.5, PGlite, <code>--no-auth</code>, 127.0.0.1:8090 (tailnet http://100.66.62.91:8090/app/). Importer: <code>lib/python/engrim_trax</code>.</p>

<div class="tiles">
<div class="tile"><b>3,317</b><span>engrim records imported</span></div>
<div class="tile"><b>{sum(edges.values()):,}</b><span>edges written (+48 inferred by the server)</span></div>
<div class="tile"><b>{(sess or {}).get('sessions', 0):,}</b><span>agent sessions from the raw log</span></div>
<div class="tile"><b>{(sess or {}).get('records_written', 0):,}</b><span>session records</span></div>
<div class="tile"><b>{jev_calls:,}</b><span>Jev calls</span></div>
<div class="tile"><b>${jev_usd:.2f}</b><span>Jev cost</span></div>
<div class="tile"><b>{wall / 60:.1f} min</b><span>wall-clock, all passes</span></div>
<div class="tile"><b>{review['agree']}/40</b><span>kind agreement, my read vs Jev</span></div>
</div>

<h2>Counts: engrim type → trackinizer kind</h2>
<p>Rows are engrim's <code>type</code>, columns the kind Jev chose. Every record landed as exactly one inquiry; the trackinizer API count by kind
(<code>list_kind_all</code>, label <code>engrim</code>) equals the column totals.</p>
{count_table}
<h3>Kind distribution</h3>
{bars([(k, kinds.get(k, 0)) for k in KINDS])}
<h3>Confidence bands of the kind choice</h3>
{band_stack}
<p>Reading the table: <code>state</code> is 84% Issue, 11% Experiment, 5% Belief; <code>fact</code> is 61% Belief / 39% Experiment; <code>decision</code> 60% Belief / 40% Issue;
<code>feedback</code> and <code>user</code> are all Beliefs (labelled <code>feedback</code> / <code>user</code>); <code>reference</code> is one third WebResult and half Belief
(references without a URL). The Experiment share is the surprise: Jev reads numbers in a record (percentages, version strings, counts) as a measurement.</p>

<h2>Edges</h2>
{edge_bars}
<p><code>produced_by</code>: {edges['produced_by']} (48 citations by engrim id, the rest the most recent older record in the same project sharing a PR number or artefact id;
the server inferred 48 more from the supersedes edges). <code>supersedes</code>: {edges['supersedes']} of 80 superseded records, from {full['supersede_pairs_asked']} candidate pairs
Jev judged ("is B the corrected version of A", p ≥ 0.8). <code>proves</code> {edges['proves']} (from Experiments) and <code>favors</code> {edges['favors']} (from measured facts) into the
3 nearest older Beliefs by engrim's model2vec vectors, from {full['evidence_pairs_asked']:,} pairs asked ("does A bear on B" p ≥ 0.8; sign from "does A support B").
Edges dropped for a newer parent: {full['edges_dropped_newer_parent']}. {full['import']['metrics_logged']} metric points logged on Experiments from Jev-confirmed <code>name=value</code> pairs.</p>

<h2>Idempotency</h2>
<p>Export before, re-run the importer, export after:</p>
<table><thead><tr><th>table</th><th class="n">before</th><th class="n">after</th></tr></thead><tbody>
{''.join(f'<tr><td>{t}</td><td class="n">{idem["before"].get(t, 0):,}</td><td class="n">{idem["after"].get(t, 0):,}</td></tr>' for t in ("inquiries", "edges", "change_log", "experiment_metrics"))}
</tbody></table>
<p>New change_log rows: <b class="ok">0</b>. Re-export byte-identical: <b class="ok">{idem['byte_identical']}</b>. The re-run made 0 Jev calls ({idem['rerun']['jev']['cache_hits']:,} answer-cache hits),
0 submits (3,317 skipped via the id map) and 0 edge calls, in {idem['rerun']['wall_seconds']} s. A lost id map still replays: every submit carries a deterministic
<code>idempotency_key</code> (uuid5 of the engrim id) and trackinizer dedups on it as the <code>change_log.id</code>.</p>

<h2>Jev agreement spot-check</h2>
<p>40 random records (seed 7); I read each one and chose a kind before looking at Jev's. Agreement {review['agree']}/40 = {100 * review['agree'] / 40:.0f}%.</p>
<h3>Disagreements, verbatim</h3>
<table><thead><tr><th>id</th><th>engrim</th><th>Jev</th><th>mine</th><th>record</th></tr></thead><tbody>{dis_rows}</tbody></table>
<blockquote>{esc(review['pattern'])}</blockquote>
<h3>Agreements</h3>
<table><thead><tr><th>id</th><th>engrim</th><th>Jev = mine</th><th>record</th></tr></thead><tbody>{agree_rows}</tbody></table>

<h2>The raw session log</h2>
{sess_html}

<h2>Screenshots</h2>
{''.join(shots)}

<h2>Cost and time</h2>
<table><thead><tr><th>pass</th><th class="n">Jev calls</th><th class="n">USD</th><th class="n">wall s</th></tr></thead><tbody>
<tr><td>first 50 records</td><td class="n">{first['jev']['calls']}</td><td class="n">{first['jev']['usd']:.4f}</td><td class="n">{first['wall_seconds']}</td></tr>
<tr><td>full corpus (3,267 more records, pairs, edges)</td><td class="n">{full['jev']['calls']:,}</td><td class="n">{full['jev']['usd']:.4f}</td><td class="n">{full['wall_seconds']}</td></tr>
<tr><td>idempotent re-run</td><td class="n">0</td><td class="n">0</td><td class="n">{idem['rerun']['wall_seconds']}</td></tr>
<tr><td>session log</td><td class="n">0</td><td class="n">0</td><td class="n">{(sess or {}).get('seconds', '-')}</td></tr>
</tbody></table>
<p>USD {jev_usd / jev_calls * 1000:.3f} per 1,000 Jev calls (about USD 0.00006 per call with a whole record as state), p50 latency {full['jev']['p50_latency_s']} s at concurrency 12, 0 retries.</p>

<h2>What was left out, and why</h2>
{left_out}

<h2>Verdict</h2>
{verdict}
<p class="muted">Sources: <code>/var/tmp/engrim-trax/STATUS.md</code>, <code>summary-*.json</code>, <code>idempotency.json</code>, <code>spotcheck*.json</code>, <code>graph-after.jsonl</code> (trax export).</p>
</main></body></html>"""
    out_path.write_text(doc)
    print(f"wrote {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
