"""The engrim `log` table as trackinizer AgentSessions with IR session records (content only, never `raw`)."""

import sqlite3
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engrim_trax.importer import NAMESPACE, IdMap
from engrim_trax.records import parse_ts

BATCH = 1000


@dataclass(frozen=True)
class SessionInfo:
    project: str
    session: str
    rows: int
    first_ts: str
    last_ts: str
    first_user: str
    multi_project: bool

    @property
    def project_name(self) -> str:
        return "global" if self.project == "__global__" else (Path(self.project).name or self.project)

    @property
    def key(self) -> str:
        return f"{self.project}|{self.session}"

    @property
    def cli_session_id(self) -> str:
        return self.session if not self.multi_project else f"{self.session}@{self.project_name}"

    @property
    def title(self) -> str:
        head = " ".join(self.first_user.split())[:100]
        return f"claude session {self.session[:8]} in {self.project_name}: {head or '(no user message)'}"


def ensure_index(db_path: str | Path) -> None:
    """A covering index on the COPY: `raw` is 2.5 GB inline, so any per-session query without it scans the file."""
    conn = sqlite3.connect(Path(db_path))
    conn.execute("CREATE INDEX IF NOT EXISTS log_cover ON log(project, session, ts, id, role, content, msg_uuid)")
    conn.commit()
    conn.close()


def list_sessions(db_path: str | Path) -> list[SessionInfo]:
    ensure_index(db_path)
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    multi = {
        s for (s,) in conn.execute("SELECT session FROM log GROUP BY session HAVING count(DISTINCT project) > 1")
    }
    rows = conn.execute(
        "SELECT project, session, count(*), min(ts), max(ts) FROM log GROUP BY project, session ORDER BY min(ts)"
    ).fetchall()
    out = []
    for project, session, n, t0, t1 in rows:
        first = conn.execute(
            "SELECT content FROM log WHERE project=? AND session=? AND role='user' "
            "AND content NOT LIKE '<%' ORDER BY ts, id LIMIT 1",
            (project, session),
        ).fetchone()
        out.append(SessionInfo(project, session, n, t0, t1, first[0] if first else "", session in multi))
    conn.close()
    return out


def iter_rows(db_path: str | Path, info: SessionInfo) -> Iterator[tuple[int, str, str, str, str | None]]:
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    cur = conn.execute(
        "SELECT id, ts, role, content, msg_uuid FROM log WHERE project=? AND session=? ORDER BY ts, id",
        (info.project, info.session),
    )
    yield from cur
    conn.close()


def session_key(info: SessionInfo) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"engrim-trax:session:{info.key}")


def ir_id(info: SessionInfo) -> uuid.UUID:
    try:
        return uuid.UUID(info.session)
    except ValueError:
        return uuid.uuid5(NAMESPACE, f"engrim-trax:ir:{info.session}")


def import_sessions(
    db_path: str | Path, client: Any, idmap: IdMap, actor: str = "george", limit: int | None = None
) -> dict[str, int]:
    """Start, fill and end one AgentSession per (project, session); skips what the id map says is done."""
    from trackinizer.client.errors import ClientError
    from trackinizer.lib.agent.types.sessions import AssistantMessage, UserMessage
    from trackinizer.types.session_records import SessionRecordRow
    from trackinizer.wire.wire_session_ir import ManifestBody, RecordBody
    from trackinizer.wire.wire_sessions import SessionEnd, SessionStart

    stats = {"sessions": 0, "sessions_skipped": 0, "records_written": 0, "records_skipped": 0}
    infos = list_sessions(db_path)
    if limit is not None:
        infos = infos[:limit]
    state: dict[str, Any] = idmap.data["sessions"]
    for info in infos:
        st = state.setdefault(info.key, {})
        if st.get("ended"):
            stats["sessions_skipped"] += 1
            continue
        if "id" not in st:
            resp = client.session_start(
                SessionStart(
                    cli="claude",
                    cli_session_id=info.cli_session_id,
                    title=info.title,
                    started=parse_ts(info.first_ts),
                    actor=actor,
                    idempotency_key=session_key(info),
                )
            )
            st["id"] = str(resp.id)
            for label in ("engrim", "engrim:log", f"project:{info.project_name}"):
                client.add_label(resp.id, label, actor=actor)
            idmap.save()
        sid = uuid.UUID(st["id"])
        name = f"{info.session}.jsonl"
        manifest = ManifestBody(
            name=name,
            metadata={"source": "engrim log", "project": info.project, "rows": info.rows, "raw": "left in SQLite"},
            ir_id=ir_id(info),
            format="",
            records=info.rows,
        )
        batch: list[RecordBody] = []
        idx = 0
        for log_id, ts, role, content, msg_uuid in iter_rows(db_path, info):
            cls = UserMessage if role == "user" else AssistantMessage
            rec = cls(timestamp=ts, content=content, extra={"engrim_log_id": log_id, "msg_uuid": msg_uuid, "role": role})
            batch.append(RecordBody.of(SessionRecordRow.of(session_id=sid, part=0, idx=idx, record=rec)))
            idx += 1
            if len(batch) >= BATCH:
                r = client.append_records(sid, name=name, manifest=manifest, records=batch)
                stats["records_written"] += r.written
                stats["records_skipped"] += r.skipped
                batch = []
        if batch:
            r = client.append_records(sid, name=name, manifest=manifest, records=batch)
            stats["records_written"] += r.written
            stats["records_skipped"] += r.skipped
        try:
            client.session_end(sid, SessionEnd(ended=parse_ts(info.last_ts), actor=actor))
        except ClientError as err:
            if "already ended" not in str(err):
                raise
        st["ended"] = True
        st["rows"] = idx
        stats["sessions"] += 1
        idmap.save()
    idmap.save()
    return stats
