import sqlite3
import uuid
from types import SimpleNamespace

import numpy as np
import pytest

# (id, ts, project, type, status, summary, detail, tags, links)
RECORDS = [
    (1, "2026-09-01T10:00:00+00:00", "/home/u/core-worktrees/main", "fact", "superseded",
     "Laser on the Acme line uses `score_threshold` 0.5 for cam 409", "", '["acme", "laser"]', "[]"),
    (2, "2026-09-02T10:00:00+00:00", "/home/u/core-worktrees/main", "fact", "active",
     "Correction to #1: laser on the Acme line uses `score_threshold` 0.7 for cam 409", "", '["acme", "laser"]', "[]"),
    (3, "2026-09-03T10:00:00+00:00", "__global__", "feedback", "active",
     "George prefers `uv` over pip for every Python install", "", '["uv"]', "[]"),
    (4, "2026-09-04T10:00:00+00:00", "/home/u/core-worktrees/vlm-chat", "state", "active",
     "PR #17325 ready to integrate on branch feat/rust-cp", "", '["pr"]', "[]"),
    (5, "2026-09-05T10:00:00+00:00", "/home/u/core-worktrees/vlm-chat", "state", "active",
     "PR #17325 merged to main 2026-09-05", "", '["pr"]', "[]"),
    (6, "2026-09-06T10:00:00+00:00", "/home/u/core-worktrees/main", "fact", "active",
     "Measured cam 409 at threshold 0.7 vs 0.5 on 200 frames: precision=0.91 recall=0.84; method = held-out frames",
     "", '["acme", "laser"]', "[]"),
    (7, "2026-09-07T10:00:00+00:00", "/home/u/core-worktrees/main", "reference", "active",
     "Trackinizer docs https://github.com/rekursiv-ai/trackinizer", "", '[]', '["https://github.com/rekursiv-ai/trackinizer"]'),
    (8, "2026-09-08T10:00:00+00:00", "/home/u/core-worktrees/main", "reference", "active",
     "Paper on typed decisions arXiv:2405.16391 is the basis for Jev", "", '["jev"]', "[]"),
    (9, "2026-09-09T10:00:00+00:00", "/home/u/core-worktrees/main", "decision", "active",
     "Decided: " + "x" * 300, "long detail here", '["long"]', "[]"),
]

LOG = [
    (1, "2026-09-07T07:30:39.711Z", "/home/u/core-worktrees/main", "a5c58653-6edd-431d-90b8-a684ad6a13d5", "user", "hello there", "{}", "m1"),
    (2, "2026-09-07T07:30:45.000Z", "/home/u/core-worktrees/main", "a5c58653-6edd-431d-90b8-a684ad6a13d5", "assistant", "hi", "{}", "m2"),
    (3, "2026-09-07T07:31:00.000Z", "/home/u/core-worktrees/main", "a5c58653-6edd-431d-90b8-a684ad6a13d5", "user", "<local-command>x</local-command>", "{}", "m3"),
    (4, "2026-09-08T07:30:00.000Z", "/home/u/core-worktrees/vlm-chat", "11111111-2222-3333-4444-555555555555", "user", "second session", "{}", "m4"),
]


@pytest.fixture()
def engrim_copy(tmp_path):
    path = tmp_path / "memory.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE memories (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, project TEXT NOT NULL, type TEXT NOT NULL,
            summary TEXT NOT NULL, detail TEXT, status TEXT NOT NULL DEFAULT 'active', tags TEXT, links TEXT,
            source TEXT, origin_agent TEXT);
        CREATE TABLE embedding (memory_id INTEGER PRIMARY KEY, model TEXT, dim INTEGER, vec BLOB);
        CREATE TABLE log (id INTEGER PRIMARY KEY, ts TEXT, project TEXT, session TEXT, role TEXT, content TEXT, raw TEXT, msg_uuid TEXT);
    """)
    rng = np.random.default_rng(0)
    base = rng.normal(size=8).astype(np.float32)
    for mid, ts, project, kind, status, summary, detail, tags, links in RECORDS:
        conn.execute(
            "INSERT INTO memories (id, ts, project, type, summary, detail, status, tags, links, source, origin_agent) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (mid, ts, project, kind, summary, detail, status, tags, links, "cli", "claude-code"),
        )
        v = base + 0.05 * rng.normal(size=8).astype(np.float32)
        conn.execute("INSERT INTO embedding VALUES (?, 'test', 8, ?)", (mid, (v / np.linalg.norm(v)).astype(np.float32).tobytes()))
    conn.executemany("INSERT INTO log VALUES (?,?,?,?,?,?,?,?)", LOG)
    conn.commit()
    conn.close()
    return path


def rule(state: str, name: str, q: dict):
    """Deterministic stand-in for Jev over the fixture records."""
    low = state.lower()
    if name == "kind":
        if "arxiv" in low:
            return "Paper", 0.95
        if "https://" in low and "engrim type: reference" in low:
            return "WebResult", 0.9
        if "measured" in low and "method" in low:
            return "Experiment", 0.85
        if "engrim type: state" in low:
            return "Issue", 0.9
        if "engrim type: decision" in low:
            return "Belief", 0.4  # fallback band
        if "prefers" in low:
            return "Belief", 0.7  # review band
        return "Belief", 0.95
    if name == "finished":
        return ("merged" in low), 0.9 if "merged" in low else 0.1
    if name == "abandoned":
        return False, 0.05
    if name == "issue_kind":
        return "task", 0.8
    if name == "priority":
        return "p1", 0.6
    if name == "judgement":
        return "proven", 0.85
    if name == "true_now":
        return ("superseded" not in low), 0.2 if "engrim status: superseded" in low else 0.9
    if name == "measured":
        return ("measured" in low), 0.9 if "measured" in low else 0.1
    if name == "title":
        return next(iter(q["criteria"])), 0.9
    if name == "outcome":
        return next((k for k in q["criteria"] if "precision" in k), "none"), 0.9
    if name == "config":
        return next((k for k in q["criteria"] if "threshold" in k), "none"), 0.85
    if name == "metrics_ok":
        return True, 0.9
    if name == "corrected":
        return ("correction to #1" in low), 0.95 if "correction to #1" in low else 0.1
    if name == "bears":
        return True, 0.9
    if name == "supports":
        return True, 0.8
    return next(iter(q.get("criteria", {"x": None}))), 0.6


class FakeClient:
    """Records every call the importer makes; mints ids like the server."""

    def __init__(self):
        self.submits: list[tuple[str, dict]] = []
        self.by_key: dict[str, uuid.UUID] = {}
        self.edges: list[tuple[uuid.UUID, uuid.UUID, str, dict]] = []
        self.metrics: list[tuple[uuid.UUID, list]] = []
        self.sessions: dict[uuid.UUID, dict] = {}
        self.labels: list[tuple[uuid.UUID, str]] = []
        self.appends: list[tuple[uuid.UUID, int]] = []
        self.records: dict[tuple[uuid.UUID, int], object] = {}

    def submit(self, kind, body):
        key = body["idempotency_key"]
        if key in self.by_key:
            return self.by_key[key]
        new = uuid.uuid4()
        self.by_key[key] = new
        self.submits.append((kind, dict(body)))
        return new

    def add_edge(self, from_id, to_id, edge_kind, *, actor, **kw):
        created = (from_id, to_id, edge_kind) not in {(a, b, k) for a, b, k, _ in self.edges}
        self.edges.append((from_id, to_id, edge_kind, kw))
        return SimpleNamespace(created=created, changed=created)

    def log_metrics(self, experiment_id, points):
        self.metrics.append((experiment_id, list(points)))
        return SimpleNamespace(logged=len(points), skipped=0)

    def session_start(self, body):
        key = str(body.idempotency_key)
        for sid, s in self.sessions.items():
            if s["key"] == key:
                return SimpleNamespace(id=sid, seq=0, cli_session_id=body.cli_session_id, actor=body.actor)
        sid = uuid.uuid4()
        self.sessions[sid] = {"key": key, "body": body, "ended": None}
        return SimpleNamespace(id=sid, seq=0, cli_session_id=body.cli_session_id, actor=body.actor)

    def add_label(self, target_id, label, *, actor):
        self.labels.append((target_id, label))

    def append_records(self, session_id, *, name, manifest, records, restart=False, slash_commands=()):
        written = skipped = 0
        for r in records:
            if (session_id, r.idx) in self.records:
                skipped += 1
            else:
                self.records[(session_id, r.idx)] = r
                written += 1
        self.appends.append((session_id, len(records)))
        return SimpleNamespace(part=0, written=written, skipped=skipped, slash_commands=0)

    def session_end(self, session_id, body=None):
        from trackinizer.client.errors import ClientError

        if self.sessions[session_id]["ended"]:
            raise ClientError("409: session has already ended; cannot end again", status_code=409)
        self.sessions[session_id]["ended"] = body.ended
        return SimpleNamespace(id=session_id, ended=body.ended)
