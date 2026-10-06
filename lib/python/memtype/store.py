"""Sidecar SQLite keyed by engrim memory id; engrim's own database is only ever read."""

import json
import sqlite3
from pathlib import Path
from typing import Any

ACCEPT = 0.8
REVIEW = 0.5

DDL = """
CREATE TABLE IF NOT EXISTS mt_record (
    memory_id INTEGER PRIMARY KEY, content_hash TEXT NOT NULL,
    durable_p REAL, type TEXT, type_p REAL, type_probs TEXT,
    context_level TEXT, context_level_p REAL, context_anchor TEXT, context_anchor_p REAL,
    validity TEXT, validity_p REAL, structured_at TEXT, related_at TEXT
);
CREATE TABLE IF NOT EXISTS mt_role (
    memory_id INTEGER NOT NULL, role TEXT NOT NULL, kind TEXT NOT NULL,
    value TEXT, raw TEXT, p REAL NOT NULL, band TEXT NOT NULL,
    PRIMARY KEY (memory_id, role)
);
CREATE TABLE IF NOT EXISTS mt_relation (
    src INTEGER NOT NULL, dst INTEGER NOT NULL, kind TEXT NOT NULL, p REAL NOT NULL,
    band TEXT NOT NULL, method TEXT NOT NULL, probs TEXT,
    PRIMARY KEY (src, dst, method)
);
CREATE TABLE IF NOT EXISTS mt_conflict (
    a INTEGER NOT NULL, b INTEGER NOT NULL, method TEXT NOT NULL, detail TEXT,
    PRIMARY KEY (a, b, method)
);
CREATE TABLE IF NOT EXISTS mt_run (
    started_at TEXT, finished_at TEXT, records INTEGER, calls INTEGER, usd REAL, seconds REAL
);
"""


def band(p: float) -> str:
    return "accept" if p >= ACCEPT else "review" if p >= REVIEW else "empty"


class Sidecar:
    def __init__(self, path: str | Path) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(DDL)

    def content_hash(self, memory_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM mt_record WHERE memory_id=?", (memory_id,)
        ).fetchone()
        return row[0] if row else None

    def unrelated(self) -> list[int]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT memory_id FROM mt_record WHERE related_at IS NULL ORDER BY memory_id"
            )
        ]

    def put_record(self, rec: dict[str, Any], roles: list[dict[str, Any]]) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM mt_role WHERE memory_id=?", (rec["memory_id"],)
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO mt_record VALUES (:memory_id, :content_hash, :durable_p, :type, :type_p, :type_probs,"
                " :context_level, :context_level_p, :context_anchor, :context_anchor_p, :validity, :validity_p,"
                " datetime('now'), NULL)",
                {**rec, "type_probs": json.dumps(rec["type_probs"])},
            )
            self.conn.executemany(
                "INSERT INTO mt_role VALUES (:memory_id, :role, :kind, :value, :raw, :p, :band)",
                roles,
            )

    def put_relations(self, memory_id: int, relations: list[dict[str, Any]]) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM mt_relation WHERE src=? AND method='jev'", (memory_id,)
            )
            self.conn.executemany(
                "INSERT OR REPLACE INTO mt_relation VALUES (:src, :dst, :kind, :p, :band, :method, :probs)",
                [{**r, "probs": json.dumps(r.get("probs"))} for r in relations],
            )
            self.conn.execute(
                "UPDATE mt_record SET related_at=datetime('now') WHERE memory_id=?",
                (memory_id,),
            )

    def put_conflicts(self, method: str, conflicts: list[dict[str, Any]]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM mt_conflict WHERE method=?", (method,))
            self.conn.executemany(
                "INSERT OR REPLACE INTO mt_conflict VALUES (?, ?, ?, ?)",
                [(c["a"], c["b"], method, json.dumps(c["detail"])) for c in conflicts],
            )

    def log_run(
        self,
        started: str,
        finished: str,
        records: int,
        calls: int,
        usd: float,
        seconds: float,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO mt_run VALUES (?, ?, ?, ?, ?, ?)",
                (started, finished, records, calls, usd, seconds),
            )

    def record(self, memory_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM mt_record WHERE memory_id=?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        roles = self.conn.execute(
            "SELECT role, kind, value, raw, p, band FROM mt_role WHERE memory_id=?",
            (memory_id,),
        )
        rels = self.conn.execute(
            "SELECT src, dst, kind, p, band, method FROM mt_relation WHERE src=? OR dst=? ORDER BY p DESC",
            (memory_id, memory_id),
        )
        return {
            **dict(row),
            "type_probs": json.loads(row["type_probs"] or "{}"),
            "roles": [dict(r) for r in roles],
            "relations": [dict(r) for r in rels],
        }

    def roles_frame(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT r.memory_id, r.type, r.context_level, r.context_anchor, r.context_anchor_p, r.context_level_p,"
                " o.role, o.kind, o.value, o.raw, o.p, o.band FROM mt_record r JOIN mt_role o USING (memory_id)"
            )
        ]

    def conflicts(self) -> list[dict[str, Any]]:
        return [
            {**dict(r), "detail": json.loads(r["detail"])}
            for r in self.conn.execute(
                "SELECT a, b, method, detail FROM mt_conflict ORDER BY method, a"
            )
        ]
