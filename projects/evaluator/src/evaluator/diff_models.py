"""Data models for git diff representation and analysis."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DiffLineType(str, Enum):
    """Type of line in a diff."""

    CONTEXT = "context"  # Unchanged line (starts with space)
    ADDITION = "addition"  # Added line (starts with +)
    DELETION = "deletion"  # Deleted line (starts with -)
    HEADER = "header"  # Diff header line
    HUNK_HEADER = "hunk_header"  # @@ line


class DiffLine(BaseModel):
    """A single line in a diff."""

    type: DiffLineType
    content: str
    old_line_no: Optional[int] = None  # Line number in original file
    new_line_no: Optional[int] = None  # Line number in new file


class DiffHunk(BaseModel):
    """A hunk within a diff (section starting with @@)."""

    old_start: int  # Starting line in original file
    old_count: int  # Number of lines from original
    new_start: int  # Starting line in new file
    new_count: int  # Number of lines in new
    header: str  # The full @@ line
    lines: list[DiffLine] = Field(default_factory=list)

    @property
    def additions(self) -> list[DiffLine]:
        """Get all added lines in this hunk."""
        return [l for l in self.lines if l.type == DiffLineType.ADDITION]

    @property
    def deletions(self) -> list[DiffLine]:
        """Get all deleted lines in this hunk."""
        return [l for l in self.lines if l.type == DiffLineType.DELETION]

    @property
    def context_lines(self) -> list[DiffLine]:
        """Get all context (unchanged) lines."""
        return [l for l in self.lines if l.type == DiffLineType.CONTEXT]


class FileDiff(BaseModel):
    """Diff for a single file."""

    old_path: Optional[str] = None  # Path in --- line (None for new files)
    new_path: Optional[str] = None  # Path in +++ line (None for deleted files)
    hunks: list[DiffHunk] = Field(default_factory=list)
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_renamed: bool = False
    is_binary: bool = False
    old_mode: Optional[str] = None
    new_mode: Optional[str] = None

    @property
    def path(self) -> str:
        """Get the most relevant path for this diff."""
        return self.new_path or self.old_path or "unknown"

    @property
    def total_additions(self) -> int:
        """Total number of added lines."""
        return sum(len(h.additions) for h in self.hunks)

    @property
    def total_deletions(self) -> int:
        """Total number of deleted lines."""
        return sum(len(h.deletions) for h in self.hunks)


class GitDiff(BaseModel):
    """Complete parsed git diff, potentially containing multiple files."""

    raw_diff: str  # Original diff string
    files: list[FileDiff] = Field(default_factory=list)
    commit_hash: Optional[str] = None
    author: Optional[str] = None
    message: Optional[str] = None

    @property
    def total_files_changed(self) -> int:
        """Number of files changed."""
        return len(self.files)

    @property
    def total_additions(self) -> int:
        """Total additions across all files."""
        return sum(f.total_additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        """Total deletions across all files."""
        return sum(f.total_deletions for f in self.files)

    @property
    def files_added(self) -> list[FileDiff]:
        """Get all newly created files."""
        return [f for f in self.files if f.is_new_file]

    @property
    def files_deleted(self) -> list[FileDiff]:
        """Get all deleted files."""
        return [f for f in self.files if f.is_deleted_file]

    @property
    def files_modified(self) -> list[FileDiff]:
        """Get all modified (not new/deleted) files."""
        return [f for f in self.files if not f.is_new_file and not f.is_deleted_file]

    def get_file(self, path: str) -> Optional[FileDiff]:
        """Get diff for a specific file path."""
        for f in self.files:
            if f.path == path or f.old_path == path or f.new_path == path:
                return f
        return None

    def summary(self) -> str:
        """Generate a human-readable summary of the diff."""
        lines = [
            f"Files changed: {self.total_files_changed}",
            f"Additions: +{self.total_additions}",
            f"Deletions: -{self.total_deletions}",
        ]
        if self.files_added:
            lines.append(f"New files: {', '.join(f.path for f in self.files_added)}")
        if self.files_deleted:
            lines.append(f"Deleted files: {', '.join(f.path for f in self.files_deleted)}")
        return "\n".join(lines)


@dataclass
class DiffValidationResult:
    """Result of validating a diff."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        """Add an error message."""
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        """Add a warning message."""
        self.warnings.append(msg)


@dataclass
class DiffApplicationResult:
    """Result of attempting to apply a diff."""

    success: bool
    applied_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
