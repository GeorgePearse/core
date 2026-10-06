"""memtype structure|conflicts|show|eval over a COPY of an engrim database."""

import argparse
import asyncio
import json
from pathlib import Path

from memtype.corpus import Corpus
from memtype.jev import Jev
from memtype.schema import Schema
from memtype.store import Sidecar
from memtype.structure import Structurer

LIVE = Path.home() / ".engrim" / "memory.db"


def _copy(db: str) -> Path:
    path = Path(db).resolve()
    if path == LIVE.resolve():
        raise SystemExit(
            f"refusing to read the live engrim db; copy it first: sqlite3 {LIVE} '.backup /path/copy.db'"
        )
    return path


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="memtype")
    p.add_argument(
        "--db", required=True, help="copy of ~/.engrim/memory.db (never the live file)"
    )
    p.add_argument("--sidecar", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("structure")
    s.add_argument("--ids", type=int, nargs="*")
    s.add_argument("--active-only", action="store_true")
    s.add_argument("--no-relate", action="store_true")
    s.add_argument("--budget", type=float, default=5.0)
    c = sub.add_parser("conflicts")
    c.add_argument("--method", choices=["key", "jev", "compose"])
    sh = sub.add_parser("show")
    sh.add_argument("id", type=int)
    e = sub.add_parser("eval")
    e.add_argument("--gold", required=True)
    e.add_argument("--supersede", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--baseline", action="store_true")
    e.add_argument("--budget", type=float, default=3.0)
    a = p.parse_args(argv)

    db = _copy(a.db)
    sidecar = Sidecar(a.sidecar)
    if a.cmd == "conflicts":
        for row in sidecar.conflicts():
            if a.method in (None, row["method"]):
                print(json.dumps(row))
        return
    if a.cmd == "show":
        corpus = Corpus.load(db)
        print(corpus.text(a.id))
        print(json.dumps(sidecar.record(a.id), indent=1, default=str))
        return
    corpus = Corpus.load(db)
    schema = Schema.load()
    if a.cmd == "structure":
        jev = Jev(budget_usd=a.budget)
        ids = a.ids
        if a.active_only and ids is None:
            ids = [
                int(i) for i in corpus.df.filter(corpus.df["status"] == "active")["id"]
            ]
        stats = asyncio.run(
            _structure(Structurer(corpus, schema, jev, sidecar), ids, not a.no_relate)
        )
        print(json.dumps(stats))
        return
    from memtype.evaluate import run_eval

    report = asyncio.run(
        run_eval(
            corpus, schema, Jev(budget_usd=a.budget), a.gold, a.supersede, a.baseline
        )
    )
    Path(a.out).write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report["headline"], indent=1))


async def _structure(
    structurer: Structurer, ids: list[int] | None, relate: bool
) -> dict:
    try:
        return await structurer.run(ids, relate=relate)
    finally:
        await structurer.jev.aclose()


if __name__ == "__main__":
    main()
