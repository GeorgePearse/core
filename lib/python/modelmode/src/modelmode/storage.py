"""Atomic files and a short-lived workspace lock; training never holds the lock."""

import fcntl
import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from modelmode.data import canonical


def identifier(value: str) -> str:
    """Restrict all identifiers that become path components."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value):
        raise ValueError(
            "Use 1–100 letters, digits, underscores or hyphens for identifiers"
        )
    return value


def read(path: Path) -> Any:
    """Read a complete atomic JSON artifact."""
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    """Replace metadata atomically so interrupted writers cannot leave partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256(path: Path) -> str:
    """Hash persisted estimator bytes before deserialization."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def locked(root: Path) -> Iterator[None]:
    """Serialize metadata transitions across MCP/CLI and worker processes."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def implementation_hash() -> str:
    """Identify the exact installed Python implementation sent to a remote worker."""
    return hashlib.sha256(
        b"".join(
            p.name.encode() + p.read_bytes()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        )
    ).hexdigest()
