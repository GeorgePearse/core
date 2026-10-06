"""Tests for TeamContext and related functionality."""

from __future__ import annotations

import pytest

from linear_manager.operations import TeamContext, _normalize_key


class TestTeamContext:
    """Test TeamContext resolution methods."""

    @pytest.fixture
    def team_context(self) -> TeamContext:
        """Create a sample TeamContext for testing."""
        return TeamContext(
            key="ENG",
            id="team-123",
            states={"backlog": "state-1", "todo": "state-2", "done": "state-3"},
            available_states=["Backlog", "Todo", "Done"],
            done_state_id="state-3",
            labels={"bug": "label-1", "feature": "label-2", "frontend": "label-3"},
            available_labels=["Bug", "Feature", "Frontend"],
            members={
                "dev1@example.com": "user-1",
                "dev2@example.com": "user-2",
            },
        )

    def test_resolve_state_id(self, team_context: TeamContext) -> None:
        """Test resolving state names to IDs."""
        assert team_context.resolve_state_id("Backlog") == "state-1"
        assert team_context.resolve_state_id("backlog") == "state-1"
        assert team_context.resolve_state_id("Todo") == "state-2"

    def test_resolve_state_id_invalid(self, team_context: TeamContext) -> None:
        """Test resolving invalid state name."""
        with pytest.raises(RuntimeError, match="State 'Invalid' is not valid"):
            team_context.resolve_state_id("Invalid")

    def test_resolve_label_ids_single(self, team_context: TeamContext) -> None:
        """Test resolving single label to ID."""
        result = team_context.resolve_label_ids(["Bug"])
        assert result == ["label-1"]

    def test_resolve_label_ids_multiple(self, team_context: TeamContext) -> None:
        """Test resolving multiple labels to IDs."""
        result = team_context.resolve_label_ids(["Bug", "Feature"])
        assert result == ["label-1", "label-2"]

    def test_resolve_label_ids_case_insensitive(
        self, team_context: TeamContext
    ) -> None:
        """Test label resolution is case-insensitive."""
        result = team_context.resolve_label_ids(["bug", "FEATURE"])
        assert result == ["label-1", "label-2"]

    def test_resolve_label_ids_missing(self, team_context: TeamContext) -> None:
        """Test resolving with missing label."""
        with pytest.raises(RuntimeError, match="Label\\(s\\) Invalid not found"):
            team_context.resolve_label_ids(["Bug", "Invalid"])

    def test_resolve_member_id(self, team_context: TeamContext) -> None:
        """Test resolving member email to ID."""
        assert team_context.resolve_member_id("dev1@example.com") == "user-1"
        assert team_context.resolve_member_id("DEV2@EXAMPLE.COM") == "user-2"

    def test_resolve_member_id_invalid(self, team_context: TeamContext) -> None:
        """Test resolving invalid member email."""
        with pytest.raises(RuntimeError, match="No Linear member with email"):
            team_context.resolve_member_id("invalid@example.com")

    def test_done_state_id(self, team_context: TeamContext) -> None:
        """Test that done_state_id is accessible."""
        assert team_context.done_state_id == "state-3"


class TestNormalizeKey:
    """Test key normalization function."""

    def test_normalize_lowercase(self) -> None:
        """Test normalizing to lowercase."""
        assert _normalize_key("Test") == "test"
        assert _normalize_key("TEST") == "test"

    def test_normalize_strips_whitespace(self) -> None:
        """Test stripping whitespace."""
        assert _normalize_key("  test  ") == "test"
        assert _normalize_key("\ttest\n") == "test"

    def test_normalize_complex(self) -> None:
        """Test normalizing complex strings."""
        assert _normalize_key("  Test String  ") == "test string"
