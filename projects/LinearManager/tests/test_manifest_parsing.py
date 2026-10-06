"""Tests for manifest parsing and validation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from linear_manager.operations import (
    load_manifest,
    _parse_issue,
    _optional_str,
    _require_str,
    _optional_int,
    _dedupe,
    _normalize_key,
)


class TestManifestLoading:
    """Test manifest loading from YAML files."""

    def test_load_valid_manifest(self) -> None:
        """Test loading a valid manifest file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
team_key: ENG
title: Test Issue
description: Test description
state: Todo
priority: 2
""")
            f.flush()
            path = Path(f.name)

        try:
            manifest = load_manifest(path)
            assert len(manifest.issues) == 1
            assert manifest.issues[0].title == "Test Issue"
            assert manifest.issues[0].team_key == "ENG"
            assert manifest.issues[0].priority == 2
        finally:
            path.unlink()

    def test_load_manifest_nonexistent_file(self) -> None:
        """Test loading a manifest from a nonexistent path."""
        with pytest.raises(RuntimeError, match="does not exist"):
            load_manifest(Path("/nonexistent/path.yaml"))

    def test_load_manifest_directory(self) -> None:
        """Test loading a manifest from a directory path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(RuntimeError, match="is a directory"):
                load_manifest(Path(tmpdir))

    def test_load_empty_manifest(self) -> None:
        """Test loading an empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            path = Path(f.name)

        try:
            with pytest.raises(RuntimeError, match="is empty"):
                load_manifest(path)
        finally:
            path.unlink()


class TestIssueParsing:
    """Test parsing of individual issues."""

    def test_parse_minimal_issue(self) -> None:
        """Test parsing an issue with minimal fields."""
        data = {"title": "Test Issue", "team_key": "ENG"}
        issue = _parse_issue(data)
        assert issue.title == "Test Issue"
        assert issue.description == ""
        assert issue.team_key == "ENG"
        assert issue.identifier is None
        assert issue.state is None
        assert issue.labels == []
        assert issue.assignee_email is None
        assert issue.priority is None
        assert issue.branch is None
        assert issue.blocked_by == []

    def test_parse_full_issue(self) -> None:
        """Test parsing an issue with all fields."""
        data = {
            "title": "Test Issue",
            "description": "Test description",
            "team_key": "ENG",
            "identifier": "ENG-123",
            "state": "Todo",
            "labels": ["Bug", "Frontend"],
            "assignee_email": "dev@example.com",
            "priority": 2,
            "branch": "feature/test",
            "blocked_by": ["Model performance", "Database migration"],
        }
        issue = _parse_issue(data)
        assert issue.title == "Test Issue"
        assert issue.description == "Test description"
        assert issue.team_key == "ENG"
        assert issue.identifier == "ENG-123"
        assert issue.state == "Todo"
        assert issue.labels == ["Bug", "Frontend"]
        assert issue.assignee_email == "dev@example.com"
        assert issue.priority == 2
        assert issue.branch == "feature/test"
        assert issue.blocked_by == ["Model performance", "Database migration"]

    def test_parse_issue_missing_team_key(self) -> None:
        """Test parsing issue without team_key fails."""
        data = {"title": "Test Issue"}
        with pytest.raises(RuntimeError, match="'team_key' is required"):
            _parse_issue(data)

    def test_parse_issue_missing_title(self) -> None:
        """Test parsing issue without title fails."""
        data: dict[str, str] = {"team_key": "ENG"}
        with pytest.raises(RuntimeError, match="'title' is required"):
            _parse_issue(data)

    def test_parse_issue_labels_dedupe(self) -> None:
        """Test that duplicate labels are removed (case-insensitive)."""
        data = {
            "title": "Test Issue",
            "team_key": "ENG",
            "labels": ["Bug", "bug", "Frontend"],
        }
        issue = _parse_issue(data)
        assert issue.labels == ["Bug", "Frontend"]

    def test_parse_issue_blocked_by_dedupe(self) -> None:
        """Test that duplicate blocked_by items are removed (case-insensitive)."""
        data = {
            "title": "Test Issue",
            "team_key": "ENG",
            "blocked_by": ["Performance", "performance", "API"],
        }
        issue = _parse_issue(data)
        assert issue.blocked_by == ["Performance", "API"]

    def test_parse_issue_invalid_blocked_by_type(self) -> None:
        """Test parsing issue with invalid blocked_by type."""
        data = {
            "title": "Test Issue",
            "team_key": "ENG",
            "blocked_by": "not_a_list",
        }
        with pytest.raises(RuntimeError, match="'blocked_by' must be a list"):
            _parse_issue(data)


class TestHelperFunctions:
    """Test helper functions for parsing."""

    def test_optional_str_none(self) -> None:
        """Test _optional_str with None."""
        assert _optional_str(None) is None

    def test_optional_str_string(self) -> None:
        """Test _optional_str with string."""
        assert _optional_str("test") == "test"

    def test_optional_str_empty(self) -> None:
        """Test _optional_str with empty string."""
        assert _optional_str("") is None
        assert _optional_str("   ") is None

    def test_optional_str_number(self) -> None:
        """Test _optional_str with number."""
        assert _optional_str(123) == "123"

    def test_require_str_valid(self) -> None:
        """Test _require_str with valid string."""
        assert _require_str("test", "context") == "test"

    def test_require_str_none(self) -> None:
        """Test _require_str with None."""
        with pytest.raises(RuntimeError, match="context"):
            _require_str(None, "context")

    def test_require_str_empty(self) -> None:
        """Test _require_str with empty string."""
        with pytest.raises(RuntimeError, match="context"):
            _require_str("", "context")

    def test_optional_int_valid(self) -> None:
        """Test _optional_int with valid values."""
        assert _optional_int(0) == 0
        assert _optional_int(2) == 2
        assert _optional_int(4) == 4

    def test_optional_int_none(self) -> None:
        """Test _optional_int with None."""
        assert _optional_int(None) is None

    def test_optional_int_string(self) -> None:
        """Test _optional_int with string number."""
        assert _optional_int("2") == 2

    def test_optional_int_invalid_range(self) -> None:
        """Test _optional_int with out-of-range values."""
        with pytest.raises(RuntimeError, match="Priority must be between 0"):
            _optional_int(5)
        with pytest.raises(RuntimeError, match="Priority must be between 0"):
            _optional_int(-1)

    def test_optional_int_invalid_type(self) -> None:
        """Test _optional_int with invalid type."""
        with pytest.raises(RuntimeError, match="Priority values must be integers"):
            _optional_int("not_a_number")

    def test_dedupe(self) -> None:
        """Test deduplication of list items (case-insensitive)."""
        result = _dedupe(["Bug", "bug", "Frontend", "FRONTEND", "Backend"])
        assert result == ["Bug", "Frontend", "Backend"]

    def test_dedupe_preserves_first(self) -> None:
        """Test that _dedupe preserves first occurrence."""
        result = _dedupe(["Bug", "BUG", "bug"])
        assert result == ["Bug"]

    def test_normalize_key(self) -> None:
        """Test key normalization."""
        assert _normalize_key("Test") == "test"
        assert _normalize_key("  Test  ") == "test"
        assert _normalize_key("TEST") == "test"
