"""One engrim memory row, read from a SQLite copy, plus the regex helpers that pre-fill Jev questions.

Nothing here classifies: the regexes only find candidate spans (URLs, SHAs, clauses, `name=value` pairs,
`#1234` citations) that a Jev question then confirms or chooses between.
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

MAX_DETAIL = 2400
MAX_CLAUSES = 60
CLAUSE_MIN, CLAUSE_MAX = 12, 160

_URL = re.compile(r"https?://[^\s<>()\[\]'\"`]+")
_ARXIV = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arXiv:\s?)(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)
_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
_CITE = re.compile(r"(?<![\w#/.$])#(\d{1,4})\b")
_CITE_NOT = re.compile(r"(?:PR|pr|Pr|pull|issue|Issue|ISSUE|gh|GH|MR|mr)\s*$")
_PR = re.compile(r"\bPR\s?#?(\d{2,6})\b|/pull/(\d{1,6})\b")
_ARTEFACT = re.compile(r"artefact\s+(?:id\s+)?([0-9a-f]{8})\b", re.I)
_METRIC = re.compile(
    r"\b([A-Za-z][\w./@-]{1,40}?)\s*(?:=|:)\s*(-?\d+(?:\.\d+)?)\s*(%|ms|s|GB|MB|k|x)?(?![\w.])"
)
_CLAUSE_SPLIT = re.compile(r"(?<=[.;!?])\s+|\n+|\s[-–—]\s|:\s(?=[A-Z])")
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Record:
    """One `memories` row."""

    id: int
    ts: str
    project: str
    type: str
    status: str
    summary: str
    detail: str
    tags: tuple[str, ...]
    links: tuple[str, ...]
    source: str
    origin_agent: str

    @property
    def when(self) -> datetime:
        return parse_ts(self.ts)

    @property
    def project_name(self) -> str:
        if self.project == "__global__":
            return "global"
        return Path(self.project).name or self.project

    @property
    def text(self) -> str:
        body = self.summary
        if self.detail:
            body += "\n" + self.detail[:MAX_DETAIL]
        return body

    def content_hash(self) -> str:
        h = hashlib.sha1()
        for part in (self.type, self.status, self.summary, self.detail, json.dumps(self.tags)):
            h.update(part.encode())
        return h.hexdigest()[:16]


def parse_ts(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _json_list(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        v = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    return tuple(str(x) for x in v) if isinstance(v, list) else ()


def load_records(db_path: str | Path) -> list[Record]:
    """Every memory row, oldest first (ties by id), from a read-only connection."""
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT id, ts, project, type, status, summary, coalesce(detail,''), tags, links, "
        "coalesce(source,''), coalesce(origin_agent,'') FROM memories ORDER BY ts, id"
    ).fetchall()
    conn.close()
    return [
        Record(r[0], r[1], r[2], r[3], r[4], r[5], r[6], _json_list(r[7]), _json_list(r[8]), r[9], r[10])
        for r in rows
    ]


def load_vectors(db_path: str | Path) -> dict[int, np.ndarray]:
    """Unit-norm embedding per memory id, when the store has one."""
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT memory_id, vec FROM embedding WHERE vec IS NOT NULL").fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    out: dict[int, np.ndarray] = {}
    for mid, blob in rows:
        v = np.frombuffer(blob, dtype=np.float32)
        n = float(np.linalg.norm(v))
        if n > 0:
            out[int(mid)] = v / n
    return out


def urls(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0).rstrip(".,;:") for m in _URL.finditer(text)))


def arxiv_id(text: str) -> str | None:
    m = _ARXIV.search(text)
    return m.group(1) if m else None


def shas(text: str) -> list[str]:
    return [s for s in dict.fromkeys(_SHA.findall(text)) if not s.isdigit()]


def cited_ids(text: str) -> list[int]:
    """`#1234` references that are not PR / issue numbers (by their preceding word)."""
    out: list[int] = []
    for m in _CITE.finditer(text):
        if _CITE_NOT.search(text[max(0, m.start() - 8) : m.start()]):
            continue
        out.append(int(m.group(1)))
    return list(dict.fromkeys(out))


def pr_numbers(text: str) -> list[str]:
    return list(dict.fromkeys(a or b for a, b in _PR.findall(text)))


def artefact_ids(text: str) -> list[str]:
    return list(dict.fromkeys(_ARTEFACT.findall(text)))


def metric_pairs(text: str) -> list[tuple[str, float]]:
    """Explicit `name=value` / `name: value` numeric pairs, in order, deduped by name."""
    seen: dict[str, float] = {}
    for name, value, _unit in _METRIC.findall(text):
        if _DATE_LIKE.match(name) or name.lower() in {"id", "pr", "ts", "port", "pid"}:
            continue
        if name not in seen and len(seen) < 20:
            try:
                seen[name] = float(value)
            except ValueError:
                continue
    return list(seen.items())


def clauses(text: str, max_len: int = CLAUSE_MAX) -> list[str]:
    """Sentence-ish spans between CLAUSE_MIN and max_len chars, deduped, in order."""
    out: list[str] = []
    for c in _CLAUSE_SPLIT.split(text):
        c = c.strip(" -–—,;:()[]`'\"")
        if len(c) < CLAUSE_MIN:
            continue
        if len(c) > max_len:
            c = c[: max_len - 1].rsplit(" ", 1)[0] + "…"
        if c not in out:
            out.append(c)
        if len(out) >= MAX_CLAUSES:
            break
    return out


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
