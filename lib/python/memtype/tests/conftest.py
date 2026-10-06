import sqlite3

import numpy as np
import pytest

RECORDS = [
    (
        1,
        "2026-09-01T10:00:00",
        "/home/u/core-worktrees/main",
        "fact",
        "active",
        "Laser on the Acme line uses `score_threshold` 0.5 for cam 409",
        '["acme", "laser"]',
    ),
    (
        2,
        "2026-09-02T10:00:00",
        "/home/u/core-worktrees/main",
        "fact",
        "active",
        "Laser on the Acme line uses `score_threshold` 0.7 for cam 409",
        '["acme", "laser"]',
    ),
    (
        3,
        "2026-09-03T10:00:00",
        "__global__",
        "feedback",
        "active",
        "George prefers `uv` over pip for every Python install",
        '["uv"]',
    ),
    (
        4,
        "2026-09-04T10:00:00",
        "/home/u/core-worktrees/vlm-chat",
        "state",
        "superseded",
        "PR #17325 ready to integrate on branch feat/rust-cp",
        '["pr"]',
    ),
    (
        5,
        "2026-09-05T10:00:00",
        "/home/u/core-worktrees/vlm-chat",
        "state",
        "active",
        "SUPERSEDES #4: PR #17325 merged to main 2026-09-05",
        '["pr"]',
    ),
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
        CREATE VIRTUAL TABLE memories_fts USING fts5(summary, detail, tags, content='memories', content_rowid='id');
        CREATE TRIGGER mem_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, summary, detail, tags) VALUES (new.id, new.summary, new.detail, new.tags);
        END;
    """)
    rng = np.random.default_rng(0)
    base = rng.normal(size=8).astype(np.float32)
    for mid, ts, project, kind, status, summary, tags in RECORDS:
        conn.execute(
            "INSERT INTO memories (id, ts, project, type, summary, detail, status, tags) VALUES (?,?,?,?,?,?,?,?)",
            (mid, ts, project, kind, summary, None, status, tags),
        )
        v = base + 0.1 * mid * rng.normal(size=8).astype(np.float32)
        conn.execute(
            "INSERT INTO embedding VALUES (?, 'test', 8, ?)",
            (mid, (v / np.linalg.norm(v)).astype(np.float32).tobytes()),
        )
    conn.commit()
    conn.close()
    return path
