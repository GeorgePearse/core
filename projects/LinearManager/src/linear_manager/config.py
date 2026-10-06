"""Configuration helpers for LinearManager."""

from __future__ import annotations

import os
from pathlib import Path


def get_home_directory() -> Path:
    """Base directory for LinearManager data."""
    home = os.environ.get("LINEAR_MANAGER_HOME")
    if home:
        return Path(home)
    return Path.home() / "LinearManager"


def get_tasks_directory() -> Path:
    """Directory where task manifests are stored."""
    return get_home_directory() / "tasks"


def get_worktrees_base_directory() -> Path:
    """Directory where Git worktrees managed by LinearManager live."""
    return get_home_directory() / "worktrees"


def get_default_base_branch() -> str | None:
    """Optional default base branch for new worktrees."""
    branch = os.environ.get("LINEAR_MANAGER_BASE_BRANCH")
    if branch:
        trimmed = branch.strip()
        if trimmed:
            return trimmed
    return None
