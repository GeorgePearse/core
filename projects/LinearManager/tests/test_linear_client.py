"""Tests for LinearClient API interactions."""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from linear_manager.operations import LinearClient, LinearApiError


class TestLinearClient:
    """Test LinearClient API wrapper."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create a mock httpx client."""
        return Mock(spec=httpx.Client)

    @pytest.fixture
    def linear_client(self, mock_client: Mock) -> LinearClient:
        """Create a LinearClient with mock httpx client."""
        with patch("linear_manager.operations.httpx.Client", return_value=mock_client):
            client = LinearClient(token="test-token")
            client._client = mock_client
            return client

    def test_client_initialization(self) -> None:
        """Test client is initialized with correct headers."""
        with patch("linear_manager.operations.httpx.Client") as mock_httpx:
            LinearClient(token="test-token")
            mock_httpx.assert_called_once()
            call_kwargs = mock_httpx.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "test-token"
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

    def test_context_manager(self) -> None:
        """Test client works as context manager."""
        with patch("linear_manager.operations.httpx.Client") as mock_httpx:
            mock_instance = Mock()
            mock_httpx.return_value = mock_instance

            with LinearClient(token="test-token") as client:
                assert client is not None
            mock_instance.close.assert_called_once()

    def test_fetch_team_context_success(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test successful team context fetch."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "teams": {
                    "nodes": [
                        {
                            "id": "team-123",
                            "key": "ENG",
                            "states": {
                                "nodes": [
                                    {
                                        "id": "state-1",
                                        "name": "Backlog",
                                        "type": "backlog",
                                    },
                                    {
                                        "id": "state-2",
                                        "name": "Todo",
                                        "type": "started",
                                    },
                                    {
                                        "id": "state-3",
                                        "name": "Done",
                                        "type": "completed",
                                    },
                                ]
                            },
                            "labels": {
                                "nodes": [
                                    {"id": "label-1", "name": "Bug"},
                                    {"id": "label-2", "name": "Feature"},
                                ]
                            },
                            "members": {
                                "nodes": [
                                    {"id": "user-1", "email": "dev1@example.com"},
                                    {"id": "user-2", "email": "dev2@example.com"},
                                ]
                            },
                        }
                    ]
                }
            }
        }
        mock_client.post.return_value = mock_response

        context = linear_client.fetch_team_context("ENG")
        assert context.key == "ENG"
        assert context.id == "team-123"
        assert context.done_state_id == "state-3"
        assert "backlog" in context.states
        assert "bug" in context.labels
        assert "dev1@example.com" in context.members

    def test_fetch_team_context_not_found(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test team context fetch when team not found."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"teams": {"nodes": []}}}
        mock_client.post.return_value = mock_response

        with pytest.raises(RuntimeError, match="Linear team with key 'ENG' not found"):
            linear_client.fetch_team_context("ENG")

    def test_fetch_team_context_no_completed_state(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test team context fetch when no completed state exists."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "teams": {
                    "nodes": [
                        {
                            "id": "team-123",
                            "key": "ENG",
                            "states": {
                                "nodes": [
                                    {
                                        "id": "state-1",
                                        "name": "Backlog",
                                        "type": "backlog",
                                    },
                                ]
                            },
                            "labels": {"nodes": []},
                            "members": {"nodes": []},
                        }
                    ]
                }
            }
        }
        mock_client.post.return_value = mock_response

        with pytest.raises(
            RuntimeError, match="does not have a 'completed' workflow state"
        ):
            linear_client.fetch_team_context("ENG")

    def test_fetch_issue_by_identifier_found(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test fetching existing issue by identifier."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "issue": {
                    "id": "issue-123",
                    "identifier": "ENG-123",
                    "url": "https://linear.app/issue/ENG-123",
                    "title": "Test Issue",
                }
            }
        }
        mock_client.post.return_value = mock_response

        issue = linear_client.fetch_issue_by_identifier("ENG-123")
        assert issue is not None
        assert issue["id"] == "issue-123"
        assert issue["identifier"] == "ENG-123"

    def test_fetch_issue_by_identifier_not_found(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test fetching non-existent issue."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"issue": None}}
        mock_client.post.return_value = mock_response

        issue = linear_client.fetch_issue_by_identifier("ENG-999")
        assert issue is None

    def test_create_issue_success(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test successful issue creation."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "issue": {
                        "id": "issue-123",
                        "identifier": "ENG-123",
                        "url": "https://linear.app/issue/ENG-123",
                    }
                }
            }
        }
        mock_client.post.return_value = mock_response

        issue_input = {"teamId": "team-123", "title": "Test Issue"}
        result = linear_client.create_issue(issue_input)
        assert result["identifier"] == "ENG-123"

    def test_update_issue_success(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test successful issue update."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "issueUpdate": {
                    "issue": {
                        "id": "issue-123",
                        "identifier": "ENG-123",
                        "url": "https://linear.app/issue/ENG-123",
                    }
                }
            }
        }
        mock_client.post.return_value = mock_response

        update_input = {"title": "Updated Title"}
        result = linear_client.update_issue("issue-123", update_input)
        assert result["identifier"] == "ENG-123"

    def test_request_with_api_error(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test handling of API errors."""
        mock_response = Mock()
        mock_response.json.return_value = {"errors": [{"message": "Invalid API token"}]}
        mock_client.post.return_value = mock_response

        with pytest.raises(LinearApiError, match="Invalid API token"):
            linear_client._request("query { viewer { id } }", {})

    def test_request_http_error(
        self, linear_client: LinearClient, mock_client: Mock
    ) -> None:
        """Test handling of HTTP errors."""
        mock_client.post.side_effect = httpx.HTTPError("Network error")

        with pytest.raises(httpx.HTTPError):
            linear_client._request("query { viewer { id } }", {})
