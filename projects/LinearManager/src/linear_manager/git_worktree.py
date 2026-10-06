"""Git worktree helpers adapted from par."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Tuple

from . import config


class GitWorktreeError(RuntimeError):
    """Raised when Git worktree operations fail."""


def _run_git(
    command: list[str],
    cwd: Path | None = None,
    *,
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            check=check,
            capture_output=capture_output,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - error path
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = stderr or stdout or f"exit code {exc.returncode}"
        raise GitWorktreeError(f"{' '.join(command)} failed: {details}") from exc
    except FileNotFoundError as exc:  # pragma: no cover - missing git binary
        raise GitWorktreeError(f"{command[0]} not found in PATH") from exc


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    if not slug:
        slug = "ticket"
    return slug[:63] or "ticket"


def _repo_identifier(repo_root: Path) -> str:
    digest = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()
    return digest[:8]


def _worktrees_dir(repo_root: Path) -> Path:
    base = config.get_worktrees_base_directory()
    repo_dir = base / _repo_identifier(repo_root)
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir


def _branch_exists(branch: str, repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=str(repo_root),
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _worktree_path_for(repo_root: Path, candidate: str) -> Path:
    return _worktrees_dir(repo_root) / candidate


def _pick_unique_branch_and_path(label: str, repo_root: Path) -> Tuple[str, Path]:
    base = _slugify(label)
    attempt = 0
    while True:
        suffix = "" if attempt == 0 else f"-{attempt}"
        branch_name = f"{base}{suffix}"
        worktree_path = _worktree_path_for(repo_root, branch_name.replace("/", "-"))
        if _branch_exists(branch_name, repo_root):
            attempt += 1
            continue
        if worktree_path.exists():
            attempt += 1
            continue
        return branch_name, worktree_path


def get_git_repo_root(start_path: Path | None = None) -> Path:
    cwd = start_path or Path.cwd()
    result = _run_git(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
    )
    text = (result.stdout or "").strip()
    if not text:
        raise GitWorktreeError("Unable to determine git repo root")
    return Path(text)


def create_branch_and_worktree(
    label: str,
    *,
    base_branch: str | None = None,
    start_path: Path | None = None,
) -> tuple[str, Path]:
    repo_root = get_git_repo_root(start_path)
    branch_name, worktree_path = _pick_unique_branch_and_path(label, repo_root)
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    branch_source = base_branch or config.get_default_base_branch()
    command = ["git", "worktree", "add", "-b", branch_name, str(worktree_path)]
    if branch_source:
        command.append(branch_source)
    _run_git(command, cwd=repo_root, capture_output=True)

    return branch_name, worktree_path
