"""engrim -> trackinizer importer.

    python -m engrim_trax.cli import --db COPY.db --server http://127.0.0.1:8766 [--limit 50] [--sessions]
    python -m engrim_trax.cli report --db COPY.db --server ...
    python -m engrim_trax.cli spotcheck --db COPY.db --n 40 --seed 7
    python -m engrim_trax.cli wipe --datadir /var/tmp/engrim-trax/pgdata --tmux engrim-trax:server
"""

import argparse
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from memtype.jev import Jev

from engrim_trax.classify import Classifier
from engrim_trax.edges import citation_edges, drop_newer, evidence_edges, supersession_edges
from engrim_trax.importer import IdMap, Importer
from engrim_trax.records import load_records, load_vectors
from engrim_trax.sessions import import_sessions

SCRATCH = Path("/var/tmp/engrim-trax")


def _client(url: str):
    from trackinizer.client.client import Client

    return Client(url, author="george")


async def _classify(a, records):
    jev = Jev(concurrency=a.concurrency, budget_usd=a.budget)
    clf = Classifier(jev, a.answers, concurrency_batch=a.concurrency * 4)
    t0 = time.perf_counter()
    mappings = await clf.classify(records)
    return jev, clf, mappings, time.perf_counter() - t0


def cmd_import(a) -> int:
    records = load_records(a.db)
    if a.limit:
        records = records[: a.limit]
    by_id = {r.id: r for r in records}
    t_all = time.perf_counter()

    async def run():
        jev, clf, mappings, t_cls = await _classify(a, records)
        edges = citation_edges(records)
        sup, sup_pairs = await supersession_edges(clf, records)
        ev, ev_pairs = await evidence_edges(clf, records, mappings, load_vectors(a.db))
        sup_pairs_set = {(e.src, e.dst) for e in sup}
        edges = [e for e in edges if (e.src, e.dst) not in sup_pairs_set] + sup + ev
        kept, dropped = drop_newer(edges, by_id)
        await jev.aclose()
        return jev, clf, mappings, kept, dropped, t_cls, sup_pairs, ev_pairs, sup, ev

    jev, clf, mappings, edges, dropped, t_cls, sup_pairs, ev_pairs, sup, ev = asyncio.run(run())
    idmap = IdMap(a.idmap)
    idmap.data["dropped_edges"] = dropped
    imp = Importer(_client(a.server), idmap)
    t0 = time.perf_counter()
    imp.submit_records(records, mappings)
    imp.submit_metrics(mappings)
    imp.submit_edges(edges)
    t_submit = time.perf_counter() - t0
    sess = None
    if a.sessions:
        t1 = time.perf_counter()
        sess = import_sessions(a.db, _client(a.server), idmap, limit=a.session_limit)
        sess["seconds"] = round(time.perf_counter() - t1, 1)
    kinds = Counter(m.kind for m in mappings.values())
    bands = Counter(m.band for m in mappings.values())
    by_type = Counter((by_id[i].type, m.kind) for i, m in mappings.items())
    out = {
        "records": len(records),
        "kinds": dict(kinds),
        "bands": dict(bands),
        "type_to_kind": {f"{t}->{k}": n for (t, k), n in sorted(by_type.items())},
        "edges": dict(Counter(e.kind for e in edges)),
        "edges_dropped_newer_parent": dropped,
        "supersede_pairs_asked": sup_pairs,
        "supersede_edges": len(sup),
        "evidence_pairs_asked": ev_pairs,
        "evidence_edges": len(ev),
        "jev": {
            "calls": jev.calls,
            "usd": round(jev.usd, 4),
            "retries": jev.retries,
            "cache_hits": clf.cache_hits,
            "classify_seconds": round(t_cls, 1),
            "p50_latency_s": round(sorted(jev.latencies)[len(jev.latencies) // 2], 2) if jev.latencies else None,
        },
        "import": {**imp.stats, "submit_seconds": round(t_submit, 1)},
        "sessions": sess,
        "wall_seconds": round(time.perf_counter() - t_all, 1),
    }
    print(json.dumps(out, indent=1))
    if a.summary_out:
        Path(a.summary_out).write_text(json.dumps(out, indent=1))
    return 0


def cmd_report(a) -> int:
    client = _client(a.server)
    records = load_records(a.db)
    eng = Counter(r.type for r in records)
    trax: dict[str, int] = {}
    for kind in ("Issue", "Belief", "Experiment", "WebResult", "Paper", "CodeChange", "AgentSession", "WebSearch", "Artifact"):
        rows = client.list_kind_all(kind)
        trax[kind] = sum(1 for r in rows if "engrim" in (r.get("labels") or []))
        trax[f"{kind}:all"] = len(rows)
    print(json.dumps({"engrim_by_type": dict(eng), "engrim_total": len(records), "trackinizer_by_kind": trax}, indent=1))
    return 0


def cmd_spotcheck(a) -> int:
    records = load_records(a.db)
    answers = Classifier(Jev(), a.answers).cache
    rng = random.Random(a.seed)
    sample = rng.sample(records, a.n)
    rows = []
    for r in sample:
        key = next((k for k in answers if k.startswith(f"v1:kind:{r.id}:")), None)
        ans = answers.get(key) if key else None
        rows.append(
            {
                "id": r.id,
                "type": r.type,
                "status": r.status,
                "jev_kind": ans["kind"]["choice"] if ans else None,
                "jev_p": round(ans["kind"]["p"], 2) if ans else None,
                "text": r.text[:400],
            }
        )
    Path(a.out).write_text(json.dumps(rows, indent=1))
    print(f"wrote {len(rows)} records to {a.out}")
    return 0


def cmd_wipe(a) -> int:
    """Stop the server (tmux), delete the PGlite data dir and the id map, restart, wait until ready."""
    datadir = Path(a.datadir)
    if not str(datadir).startswith(str(SCRATCH)):
        print(f"refusing to wipe {datadir}: not under {SCRATCH}", file=sys.stderr)
        return 2
    subprocess.run(["tmux", "send-keys", "-t", a.tmux, "C-c", ""], check=True)
    time.sleep(3)
    if datadir.exists():
        shutil.rmtree(datadir)
    datadir.mkdir(parents=True)
    for p in (Path(a.idmap),):
        if p.exists():
            p.unlink()
    cmd = (
        f"trackinizer --no-auth --host 127.0.0.1 --port {a.port} --datadir {datadir} 2>&1 | tee -a {SCRATCH}/server.log"
    )
    subprocess.run(["tmux", "send-keys", "-t", a.tmux, cmd, "Enter"], check=True)
    _client(f"http://127.0.0.1:{a.port}").wait_until_ready(timeout_sec=120)
    print("server restarted on a fresh data dir")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="engrim_trax")
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=str(SCRATCH / "memory.db"))
    common.add_argument("--server", default="http://127.0.0.1:8766")
    common.add_argument("--idmap", default=str(SCRATCH / "idmap.json"))
    common.add_argument("--answers", default=str(SCRATCH / "jev_answers.jsonl"))

    i = sub.add_parser("import", parents=[common])
    i.add_argument("--limit", type=int, default=0)
    i.add_argument("--sessions", action="store_true")
    i.add_argument("--session-limit", type=int, default=None)
    i.add_argument("--concurrency", type=int, default=12)
    i.add_argument("--budget", type=float, default=5.0)
    i.add_argument("--summary-out", default=None)
    i.set_defaults(fn=cmd_import)

    r = sub.add_parser("report", parents=[common])
    r.set_defaults(fn=cmd_report)

    s = sub.add_parser("spotcheck", parents=[common])
    s.add_argument("--n", type=int, default=40)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--out", default=str(SCRATCH / "spotcheck.json"))
    s.set_defaults(fn=cmd_spotcheck)

    w = sub.add_parser("wipe", parents=[common])
    w.add_argument("--datadir", default=str(SCRATCH / "pgdata"))
    w.add_argument("--tmux", default="engrim-trax:server")
    w.add_argument("--port", type=int, default=8766)
    w.set_defaults(fn=cmd_wipe)

    a = p.parse_args(argv)
    if a.cmd in ("import",) and not os.environ.get("AI_GATEWAY_API_KEY"):
        print("AI_GATEWAY_API_KEY is not set", file=sys.stderr)
        return 2
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
