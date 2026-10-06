"""Read-only view of an engrim SQLite copy: records, neighbour shortlists, entity index and value spans."""

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

MAX_TEXT = 2400
MAX_OPTIONS = 254
KEY_LEN = 160

_ENTITY_PATTERNS = [
    re.compile(r"`([^`\n]{2,60})`"),
    re.compile(r"\b([A-Za-z][\w.]*(?:[-_][\w.]+)+)\b"),
    re.compile(r"\b([A-Z][a-z]*[A-Z0-9][\w.]*)\b"),
    re.compile(r"\b([A-Z]{2,}[\w.]*)\b"),
    re.compile(
        r"(?<![.!?]\s)(?<!^)\b((?:[A-Z][a-z]+)(?:\s(?:[A-Z][a-zA-Z0-9]+)){0,3})\b"
    ),
]
_VALUE_PATTERNS = [
    re.compile(r"https?://\S+[^\s.,;)\]]"),
    re.compile(r"\bgs://\S+[^\s.,;)\]]"),
    re.compile(r"(?:PR\s?)?#\d{2,6}\b"),
    re.compile(r"(?<![\w/])(?:~|\.{0,2})/?[\w.-]+(?:/[\w.-]+)+/?"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?"),
    re.compile(r"\b\d{1,2}:\d{2}Z?\b"),
    re.compile(
        r"[$~]?\d+(?:[.,]\d+)*\s?(?:%|ms|s|px|GB|MB|k|M|x|/mo|/M|\s?boxes|\s?frames)?(?![\w-])"
    ),
    re.compile(r"\b[0-9a-f]{7,40}\b"),
    re.compile(r"\b(?:c|gen|run)_[0-9A-Za-z]{6,}\b"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    re.compile(r":\d{4,5}\b"),
    re.compile(r"'([^'\n]{3,60})'"),
    re.compile(r'"([^"\n]{3,60})"'),
    re.compile(r"`([^`\n]{2,80})`"),
]
_STOP = set(
    """the this that when what then also use not and but for with if it in on no do don see note why how
apply trap ready done decided each all one two only so any its an to as at is are was were be been every pr fix
fixed now new old yes from by of or after before since until while into over under per via vs never always must
should can cannot will would here there they them their our your we you he she his her who which where why how
project dispatch feedback state fact decision reference user integrate integration needs status result results
measured verified live main local broken stale blocked task plan only few shot paste copy data image images run
runs test tests version config experiment env token flow release dev search batch cloud class object store
supersedes superseded correction update merged ready draft open closed pending""".split()
)
GAZETTEER_MIN = 3


def canon(s: str) -> str:
    return re.sub(r"[\s_]+", "-", s.strip().strip("`'\".,:;()").lower())


def repo_and_worktree(project: str) -> tuple[str, str | None]:
    if project == "__global__":
        return "global", None
    if "/core-worktrees/" in project:
        slug = project.rsplit("/core-worktrees/", 1)[1].split("/")[0]
        return "core", None if slug == "main" else slug
    return Path(project).name or project, None


def mentions(text: str) -> list[str]:
    out: list[str] = []
    for pat in _ENTITY_PATTERNS:
        for m in pat.finditer(text):
            s = m.group(1).strip(".-_ ")
            if (
                len(s) >= 2
                and s.lower() not in _STOP
                and not s.isdigit()
                and not re.fullmatch(r"[\d.:%$-]+", s)
            ):
                out.append(s)
    return out


def value_spans(text: str) -> list[str]:
    seen: dict[str, int] = {}
    for pat in _VALUE_PATTERNS:
        for m in pat.finditer(text):
            s = (m.group(1) if m.groups() else m.group(0)).strip(" .,;")
            if s and len(s) <= 120 and s not in seen and not re.fullmatch(r"[\d]", s):
                seen[s] = m.start()
    spans = sorted(seen, key=seen.get)
    clauses = [
        c.strip(" -–—,") for c in re.split(r"(?<=[.;!?])\s+|\n+|\s[-–—]\s|:\s", text)
    ]
    clauses = [c[:160] for c in clauses if 12 <= len(c) and c not in seen]
    return list(dict.fromkeys(clauses[:120] + spans))[:MAX_OPTIONS]


def record_text(row: dict) -> str:
    body = row["summary"] + ("\n" + row["detail"] if row.get("detail") else "")
    return body[:MAX_TEXT]


@dataclass
class Corpus:
    db_path: Path
    df: pl.DataFrame
    vectors: np.ndarray
    index_of: dict[int, int]
    entity_counts: Counter = field(default_factory=Counter)
    surface: dict[str, str] = field(default_factory=dict)
    gazetteer: re.Pattern | None = None

    @classmethod
    def load(cls, db_path: str | Path) -> "Corpus":
        db_path = Path(db_path)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        df = pl.read_database(
            "SELECT m.id, m.ts, m.project, m.type AS engrim_type, m.status, m.summary, m.detail, m.tags, e.vec "
            "FROM memories m LEFT JOIN embedding e ON e.memory_id = m.id ORDER BY m.id",
            conn,
        )
        conn.close()
        dim = next((len(v) // 4 for v in df["vec"] if v is not None), 256)
        vecs = np.stack(
            [
                np.frombuffer(v, dtype=np.float32)
                if v is not None
                else np.zeros(dim, np.float32)
                for v in df["vec"]
            ]
        )
        df = df.drop("vec").with_columns(
            pl.col("detail").fill_null(""), pl.col("tags").fill_null("[]")
        )
        corpus = cls(db_path, df, vecs, {int(i): n for n, i in enumerate(df["id"])})
        corpus._index_entities()
        return corpus

    def _index_entities(self) -> None:
        forms: dict[str, Counter] = {}
        tags: Counter = Counter()
        for row in self.df.iter_rows(named=True):
            found = {canon(m): m for m in mentions(record_text(row))}
            for tag in json.loads(row["tags"] or "[]"):
                found.setdefault(canon(tag), tag)
                tags[canon(tag)] += 1
            for c, m in found.items():
                self.entity_counts[c] += 1
                forms.setdefault(c, Counter())[m] += 1
        self.surface = {c: f.most_common(1)[0][0] for c, f in forms.items()}
        words = sorted(
            (
                c
                for c, n in tags.items()
                if n >= GAZETTEER_MIN
                and len(c) >= 2
                and c not in _STOP
                and not c.isdigit()
            ),
            key=len,
            reverse=True,
        )
        self.gazetteer = (
            re.compile(
                r"(?i)(?<![\w-])("
                + "|".join(re.escape(w) for w in words)
                + r")(?![\w-])"
            )
            if words
            else None
        )

    def mentions(self, text: str) -> list[str]:
        found = (
            [(m.start(), m.group(1)) for m in self.gazetteer.finditer(text)]
            if self.gazetteer
            else []
        )
        pos = {s: text.find(s) for s in mentions(text)}
        return [s for _, s in sorted(found + [(p, s) for s, p in pos.items()])]

    def row(self, memory_id: int) -> dict:
        return self.df.row(self.index_of[memory_id], named=True)

    def text(self, memory_id: int) -> str:
        return record_text(self.row(memory_id))

    def entity_options(self, memory_id: int) -> dict[str, str | None]:
        text = self.text(memory_id)
        opts: dict[str, str | None] = {}
        for m in self.mentions(text):
            c = canon(m)
            key = (m if self.entity_counts[c] > 1 else f"new:{m}")[:KEY_LEN]
            if c not in {canon(k.removeprefix("new:")) for k in opts}:
                opts[key] = None
            if len(opts) >= MAX_OPTIONS - 1:
                break
        opts["none"] = "the record does not state this role"
        return opts

    def value_options(self, memory_id: int) -> dict[str, str | None]:
        opts: dict[str, str | None] = {
            s[:KEY_LEN]: None for s in value_spans(self.text(memory_id))
        }
        opts = dict(list(opts.items())[: MAX_OPTIONS - 1])
        opts["none"] = "the record does not state this role"
        return opts

    def neighbours(
        self, memory_id: int, k: int = 6, older_only: bool = True
    ) -> list[tuple[int, float]]:
        i = self.index_of[memory_id]
        sims = self.vectors @ self.vectors[i]
        sims[i] = -1
        if older_only:
            sims[i:] = -1
        emb = [int(j) for j in np.argsort(-sims)[: 4 * k] if sims[j] > 0]
        fts = self._fts(memory_id, 4 * k, older_only)
        score: dict[int, float] = {}
        for rank_list in (emb, fts):
            for r, j in enumerate(rank_list):
                score[j] = score.get(j, 0.0) + 1 / (60 + r)
        best = sorted(score, key=score.get, reverse=True)[:k]
        return [(int(self.df["id"][j]), float(sims[j])) for j in best]

    def _fts(self, memory_id: int, k: int, older_only: bool) -> list[int]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", self.row(memory_id)["summary"])
        words = list(dict.fromkeys(w.lower() for w in words))[:24]
        if not words:
            return []
        q = " OR ".join(f'"{w}"' for w in words)
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ? AND rowid != ? "
                + ("AND rowid < ? " if older_only else "AND ? > -1 ")
                + "ORDER BY bm25(memories_fts) LIMIT ?",
                (q, memory_id, memory_id, k),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        conn.close()
        return [self.index_of[r[0]] for r in rows if r[0] in self.index_of]
