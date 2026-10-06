"""Tests for the `manager list` CLI command."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from linear_manager.cli import main, _strip_ansi


def _write_manifest(path: Path, content: str) -> None:
    path.write_text(dedent(content).strip() + "\n", encoding="utf-8")


def test_list_outputs_table_for_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "issues.yaml"
    _write_manifest(
        manifest,
        """
        team_key: ENG
        title: Refactor login flow
        description: Improve login sequence for oauth integrations
        branch: feature/login-flow
        state: In Progress
        """,
    )

    result = main(["list", str(manifest)])

    assert result == 0
    out = capsys.readouterr().out
    # Remove ANSI color codes for easier testing
    clean_out = _strip_ansi(out)
    assert "Title" in clean_out
    # Title may be wrapped across lines, so check for key parts
    assert "Refactor" in clean_out
    assert "login" in clean_out and "flow" in clean_out
    # Check for branch (should be present by default)
    assert "feature" in clean_out and "flow" in clean_out
    # Description should NOT be present without --verbose
    assert "Improve" not in clean_out or "Improve login" not in clean_out
    assert "Progress" in clean_out


def test_list_uses_defaults_and_marks_complete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "one.yaml",
        """
        team_key: ENG
        title: Common refactor
        description: Update shared helpers
        branch: feature/common
        state: Done
        """,
    )
    _write_manifest(
        manifest_dir / "two.yaml",
        """
        team_key: ENG
        title: API polish
        description: Improve API messaging
        state: Review
        """,
    )

    result = main(["list", str(manifest_dir), "--include-done"])

    assert result == 0
    out = capsys.readouterr().out
    # Remove ANSI color codes for easier testing
    clean_out = _strip_ansi(out)
    # Title may be wrapped across lines, so check for key parts
    assert "Common" in clean_out and "refactor" in clean_out
    # Check for branch (should be present by default)
    assert "feature/common" in clean_out or "common" in clean_out
    # Description should NOT be present without --verbose
    assert "Update shared helpers" not in clean_out
    assert "Improve API messaging" not in clean_out
    # Done state should show with checkmark
    assert "[x]" in clean_out or "Done" in clean_out
    assert "Review" in clean_out


def test_list_verbose_shows_descriptions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "issues.yaml"
    _write_manifest(
        manifest,
        """
        team_key: ENG
        title: Refactor login flow
        description: Improve login sequence for oauth integrations
        branch: feature/login-flow
        state: In Progress
        """,
    )

    result = main(["list", str(manifest), "--verbose"])

    assert result == 0
    out = capsys.readouterr().out
    # Remove ANSI color codes for easier testing
    clean_out = "".join(char for char in out if char.isprintable() or char in "\n\r")
    assert "Title" in clean_out
    # Title may be wrapped across lines, so check for key parts
    assert "Refactor" in clean_out and "login" in clean_out and "flow" in clean_out
    # Check for branch and description (should both be present with --verbose)
    assert "feature" in clean_out and "flow" in clean_out
    assert "Improve" in clean_out
    assert "Progress" in clean_out


def test_list_errors_for_missing_path() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["list", "does-not-exist.yaml"])
    assert excinfo.value.code == 2


def test_list_by_block_shows_blocking_relationships(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --by-block shows blocking relationships in box format."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Create a blocker ticket
    _write_manifest(
        manifest_dir / "blocker.yaml",
        """
        team_key: ENG
        title: Deploy infrastructure
        description: Set up the infrastructure
        priority: 3
        labels:
          - Infrastructure
          - Deployment
        """,
    )

    # Create a blocked ticket
    _write_manifest(
        manifest_dir / "blocked.yaml",
        """
        team_key: ENG
        title: Implement feature X
        description: Feature that depends on infrastructure
        priority: 2
        state: Todo
        blocked_by:
          - "Deploy infrastructure"
        """,
    )

    result = main(["list", str(manifest_dir), "--by-block"])

    assert result == 0
    out = capsys.readouterr().out
    clean_out = _strip_ansi(out)

    # Check for blocking relationship header
    assert "Blocking Relationships" in clean_out

    # Check for blocker box
    assert "Deploy infrastructure" in clean_out
    assert "Infrastructure" in clean_out
    assert "Priority: High" in clean_out or "High" in clean_out

    # Check for blocks indicator
    assert "blocks" in clean_out

    # Check for blocked box
    assert "Implement feature X" in clean_out
    assert "Priority: Medium" in clean_out or "Medium" in clean_out
    assert "State: Todo" in clean_out or "Todo" in clean_out


def test_list_by_block_shows_external_dependencies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --by-block shows external dependencies correctly."""
    manifest = tmp_path / "issues.yaml"
    _write_manifest(
        manifest,
        """
        team_key: ENG
        title: Implement feature Y
        description: Feature blocked by external dependency
        blocked_by:
          - "Third-party API availability"
        """,
    )

    result = main(["list", str(manifest), "--by-block"])

    assert result == 0
    out = capsys.readouterr().out
    clean_out = _strip_ansi(out)

    # Check for external dependency marker
    assert "Third-party API availability" in clean_out
    assert "External dependency" in clean_out

    # Check for blocked issue
    assert "Implement feature Y" in clean_out


def test_list_by_block_no_relationships(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that --by-block handles tickets with no blocking relationships."""
    manifest = tmp_path / "issues.yaml"
    _write_manifest(
        manifest,
        """
        team_key: ENG
        title: Standalone feature
        description: Feature with no blockers
        """,
    )

    result = main(["list", str(manifest), "--by-block"])

    assert result == 0
    out = capsys.readouterr().out
    clean_out = _strip_ansi(out)

    # Should show message about no blocking relationships
    assert "No blocking relationships found" in clean_out
