"""Unit tests for Jira API client.

Tests JiraClient with:
- Authentication (Basic Auth base64 encoding)
- Token-based pagination for issues (nextPageToken/isLast)
- Offset-based pagination for comments (startAt/maxResults/total)
- Bounded JQL requirement (project = KEY)
- Error handling (HTTP errors, timeouts, malformed responses)
- Context manager support
"""

import base64
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.memory.connectors.jira.client import JiraClient, JiraClientError

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def jira_client():
    """Create JiraClient instance for testing."""
    return JiraClient(
        instance_url="https://test.atlassian.net",
        email="test@example.com",
        api_token="test-token-123",
        delay_ms=0,  # No delay for tests
    )


# =============================================================================
# Authentication Tests
# =============================================================================


class TestAuthentication:
    """Test Basic Auth implementation."""

    def test_basic_auth_header_format(self, jira_client):
        """Basic Auth header is properly formatted."""
        # Should be "Basic <base64>"
        assert jira_client.auth_header.startswith("Basic ")

    def test_credentials_encoding(self):
        """Credentials encoded as base64(email:token)."""
        client = JiraClient(
            instance_url="https://test.atlassian.net",
            email="user@example.com",
            api_token="secret123",
        )

        # Decode and verify
        auth_part = client.auth_header.replace("Basic ", "")
        decoded = base64.b64decode(auth_part).decode()
        assert decoded == "user@example.com:secret123"

    def test_authorization_header_in_client(self, jira_client):
        """Authorization header present in httpx client."""
        headers = jira_client.client.headers
        assert "Authorization" in headers
        assert headers["Authorization"] == jira_client.auth_header

    def test_accept_header(self, jira_client):
        """Accept header set to application/json."""
        headers = jira_client.client.headers
        assert headers["Accept"] == "application/json"

    def test_content_type_header(self, jira_client):
        """Content-Type header set to application/json."""
        headers = jira_client.client.headers
        assert headers["Content-Type"] == "application/json"


class TestClientConfiguration:
    """Test client initialization and configuration."""

    def test_base_url_stripped(self):
        """Base URL trailing slash stripped."""
        client = JiraClient(
            instance_url="https://test.atlassian.net/",
            email="test@example.com",
            api_token="token",
        )
        assert client.base_url == "https://test.atlassian.net"

    def test_delay_ms_configured(self):
        """Delay_ms stored correctly."""
        client = JiraClient(
            instance_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token",
            delay_ms=250,
        )
        assert client.delay_ms == 250

    def test_timeout_configuration(self, jira_client):
        """Timeout configuration set on httpx client."""
        timeout = jira_client.client.timeout
        assert timeout.connect == 3.0
        assert timeout.read == 15.0
        assert timeout.write == 5.0
        assert timeout.pool == 3.0


# =============================================================================
# Test Connection Tests
# =============================================================================


class TestTestConnection:
    """Test test_connection method."""

    @pytest.mark.asyncio
    async def test_successful_connection(self, jira_client):
        """Successful connection returns user email."""
        mock_response = Mock()
        mock_response.json.return_value = {"emailAddress": "test@example.com"}
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "get", new=AsyncMock(return_value=mock_response)
        ):
            result = await jira_client.test_connection()

        assert result["success"] is True
        assert result["user_email"] == "test@example.com"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_connection_timeout(self, jira_client):
        """Connection timeout handled gracefully."""
        with patch.object(
            jira_client.client,
            "get",
            new=AsyncMock(side_effect=httpx.TimeoutException("Timeout")),
        ):
            result = await jira_client.test_connection()

        assert result["success"] is False
        assert result["user_email"] is None
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connection_http_401(self, jira_client):
        """HTTP 401 Unauthorized handled."""
        mock_response = Mock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError(
            "Unauthorized", request=Mock(), response=mock_response
        )

        with patch.object(
            jira_client.client,
            "get",
            new=AsyncMock(side_effect=error),
        ):
            result = await jira_client.test_connection()

        assert result["success"] is False
        assert "401" in result["error"]

    @pytest.mark.asyncio
    async def test_connection_http_404(self, jira_client):
        """HTTP 404 Not Found handled."""
        mock_response = Mock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=mock_response
        )

        with patch.object(
            jira_client.client,
            "get",
            new=AsyncMock(side_effect=error),
        ):
            result = await jira_client.test_connection()

        assert result["success"] is False
        assert "404" in result["error"]

    @pytest.mark.asyncio
    async def test_connection_generic_http_error(self, jira_client):
        """Generic HTTP error handled."""
        with patch.object(
            jira_client.client,
            "get",
            new=AsyncMock(side_effect=httpx.ConnectError("Connection failed")),
        ):
            result = await jira_client.test_connection()

        assert result["success"] is False
        assert result["error"] is not None


# =============================================================================
# List Projects Tests
# =============================================================================


class TestListProjects:
    """Test list_projects method."""

    @pytest.mark.asyncio
    async def test_successful_list(self, jira_client):
        """Successful project list retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"key": "PROJ", "name": "Project 1"},
            {"key": "TEST", "name": "Test Project"},
        ]
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "get", new=AsyncMock(return_value=mock_response)
        ):
            result = await jira_client.list_projects()

        assert len(result) == 2
        assert result[0]["key"] == "PROJ"
        assert result[1]["key"] == "TEST"

    @pytest.mark.asyncio
    async def test_list_projects_timeout(self, jira_client):
        """List projects timeout raises JiraClientError."""
        with (
            patch.object(
                jira_client.client,
                "get",
                new=AsyncMock(side_effect=httpx.TimeoutException("Timeout")),
            ),
            pytest.raises(JiraClientError, match="TIMEOUT"),
        ):
            await jira_client.list_projects()

    @pytest.mark.asyncio
    async def test_list_projects_http_error(self, jira_client):
        """List projects HTTP error raises JiraClientError."""
        with (
            patch.object(
                jira_client.client,
                "get",
                new=AsyncMock(side_effect=httpx.ConnectError("Connection failed")),
            ),
            pytest.raises(JiraClientError),
        ):
            await jira_client.list_projects()


# =============================================================================
# Token-Based Pagination (Issues)
# =============================================================================


class TestIssueSearchPagination:
    """Test search_issues with token-based pagination."""

    @pytest.mark.asyncio
    async def test_first_page_no_token(self, jira_client):
        """First page request has no nextPageToken."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "issues": [{"key": "PROJ-1"}],
            "isLast": True,
        }
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "post", new=AsyncMock(return_value=mock_response)
        ) as mock_post:
            await jira_client.search_issues("PROJ")

        # Verify payload has no nextPageToken on first request
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert "nextPageToken" not in payload
        assert payload["jql"] == "project = PROJ"
        assert payload["maxResults"] == 50

    @pytest.mark.asyncio
    async def test_middle_page_with_token(self, jira_client):
        """Middle page includes nextPageToken and isLast=false."""
        responses = [
            # First page
            {
                "issues": [{"key": "PROJ-1"}],
                "isLast": False,
                "nextPageToken": "token-abc-123",
            },
            # Second page
            {
                "issues": [{"key": "PROJ-2"}],
                "isLast": True,
            },
        ]

        mock_response_objs = []
        for response_data in responses:
            mock_resp = Mock()
            mock_resp.json.return_value = response_data
            mock_resp.raise_for_status = Mock()
            mock_response_objs.append(mock_resp)

        with patch.object(
            jira_client.client,
            "post",
            new=AsyncMock(side_effect=mock_response_objs),
        ) as mock_post:
            result = await jira_client.search_issues("PROJ")

        # Verify two calls made
        assert mock_post.call_count == 2

        # Second call should include nextPageToken
        second_call = mock_post.call_args_list[1]
        payload = second_call.kwargs["json"]
        assert payload["nextPageToken"] == "token-abc-123"

        # All issues returned
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_last_page_terminates(self, jira_client):
        """Last page (isLast=true) terminates pagination."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "issues": [{"key": "PROJ-1"}],
            "isLast": True,
        }
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client,
            "post",
            new=AsyncMock(return_value=mock_response),
        ) as mock_post:
            result = await jira_client.search_issues("PROJ")

        # Only one call (isLast=true stops pagination)
        assert mock_post.call_count == 1
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty_result_set(self, jira_client):
        """Empty result set handled gracefully."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "issues": [],
            "isLast": True,
        }
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "post", new=AsyncMock(return_value=mock_response)
        ):
            result = await jira_client.search_issues("PROJ")

        assert result == []


# =============================================================================
# Offset-Based Pagination (Comments)
# =============================================================================


class TestCommentPagination:
    """Test get_comments with offset-based pagination."""

    @pytest.mark.asyncio
    async def test_first_page_start_at_zero(self, jira_client):
        """First page request has startAt=0."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "comments": [{"id": "10001"}],
            "total": 1,
        }
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "get", new=AsyncMock(return_value=mock_response)
        ) as mock_get:
            await jira_client.get_comments("PROJ-123")

        # Verify startAt=0 on first request
        call_args = mock_get.call_args
        params = call_args.kwargs["params"]
        assert params["startAt"] == 0
        assert params["maxResults"] == 50

    @pytest.mark.asyncio
    async def test_middle_page_increments_start_at(self, jira_client):
        """Middle page increments startAt correctly."""
        responses = [
            # First page: startAt=0, returns 50 comments
            {"comments": [{"id": f"1000{i}"} for i in range(50)], "total": 100},
            # Second page: startAt=50, returns remaining 50
            {"comments": [{"id": f"1050{i}"} for i in range(50)], "total": 100},
        ]

        mock_response_objs = []
        for response_data in responses:
            mock_resp = Mock()
            mock_resp.json.return_value = response_data
            mock_resp.raise_for_status = Mock()
            mock_response_objs.append(mock_resp)

        with patch.object(
            jira_client.client,
            "get",
            new=AsyncMock(side_effect=mock_response_objs),
        ) as mock_get:
            result = await jira_client.get_comments("PROJ-123")

        # Verify two calls
        assert mock_get.call_count == 2

        # Second call should have startAt=50
        second_call = mock_get.call_args_list[1]
        params = second_call.kwargs["params"]
        assert params["startAt"] == 50

        # All comments returned
        assert len(result) == 100

    @pytest.mark.asyncio
    async def test_last_page_termination(self, jira_client):
        """Last page (startAt >= total) terminates pagination."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "comments": [{"id": "10001"}, {"id": "10002"}],
            "total": 2,
        }
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client,
            "get",
            new=AsyncMock(return_value=mock_response),
        ) as mock_get:
            result = await jira_client.get_comments("PROJ-123")

        # Only one call (startAt=0 + 2 comments = 2, which equals total)
        assert mock_get.call_count == 1
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_comment_list(self, jira_client):
        """Empty comment list handled gracefully."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "comments": [],
            "total": 0,
        }
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "get", new=AsyncMock(return_value=mock_response)
        ):
            result = await jira_client.get_comments("PROJ-123")

        assert result == []


# =============================================================================
# Bounded JQL Requirement
# =============================================================================


class TestBoundedJQL:
    """Test JQL bounded by project key."""

    @pytest.mark.asyncio
    async def test_project_key_in_jql(self, jira_client):
        """Project key always present in JQL."""
        mock_response = Mock()
        mock_response.json.return_value = {"issues": [], "isLast": True}
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "post", new=AsyncMock(return_value=mock_response)
        ) as mock_post:
            await jira_client.search_issues("MYPROJ")

        # Verify JQL contains project key
        payload = mock_post.call_args.kwargs["json"]
        assert "project = MYPROJ" in payload["jql"]

    @pytest.mark.asyncio
    async def test_updated_since_filter_added(self, jira_client):
        """updated_since adds AND filter to JQL."""
        mock_response = Mock()
        mock_response.json.return_value = {"issues": [], "isLast": True}
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "post", new=AsyncMock(return_value=mock_response)
        ) as mock_post:
            await jira_client.search_issues(
                "PROJ", updated_since="2026-01-01T00:00:00Z"
            )

        # Verify JQL has both project and updated filter
        payload = mock_post.call_args.kwargs["json"]
        jql = payload["jql"]
        assert "project = PROJ" in jql
        assert "updated >= '2026-01-01T00:00:00Z'" in jql
        assert " AND " in jql

    @pytest.mark.asyncio
    async def test_jql_without_updated_filter(self, jira_client):
        """JQL without updated_since has only project filter."""
        mock_response = Mock()
        mock_response.json.return_value = {"issues": [], "isLast": True}
        mock_response.raise_for_status = Mock()

        with patch.object(
            jira_client.client, "post", new=AsyncMock(return_value=mock_response)
        ) as mock_post:
            await jira_client.search_issues("PROJ")

        # Verify JQL has only project filter
        payload = mock_post.call_args.kwargs["json"]
        assert payload["jql"] == "project = PROJ"


# =============================================================================
# Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling for API calls."""

    @pytest.mark.asyncio
    async def test_search_issues_timeout(self, jira_client):
        """Search issues timeout raises JiraClientError."""
        with (
            patch.object(
                jira_client.client,
                "post",
                new=AsyncMock(side_effect=httpx.TimeoutException("Timeout")),
            ),
            pytest.raises(JiraClientError, match="TIMEOUT"),
        ):
            await jira_client.search_issues("PROJ")

    @pytest.mark.asyncio
    async def test_search_issues_http_error(self, jira_client):
        """Search issues HTTP error raises JiraClientError."""
        with (
            patch.object(
                jira_client.client,
                "post",
                new=AsyncMock(side_effect=httpx.ConnectError("Connection failed")),
            ),
            pytest.raises(JiraClientError),
        ):
            await jira_client.search_issues("PROJ")

    @pytest.mark.asyncio
    async def test_get_comments_timeout(self, jira_client):
        """Get comments timeout raises JiraClientError."""
        with (
            patch.object(
                jira_client.client,
                "get",
                new=AsyncMock(side_effect=httpx.TimeoutException("Timeout")),
            ),
            pytest.raises(JiraClientError, match="TIMEOUT"),
        ):
            await jira_client.get_comments("PROJ-123")

    @pytest.mark.asyncio
    async def test_get_comments_http_error(self, jira_client):
        """Get comments HTTP error raises JiraClientError."""
        mock_response = Mock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "Server Error", request=Mock(), response=mock_response
        )

        with (
            patch.object(
                jira_client.client,
                "get",
                new=AsyncMock(side_effect=error),
            ),
            pytest.raises(JiraClientError),
        ):
            await jira_client.get_comments("PROJ-123")

    @pytest.mark.asyncio
    async def test_malformed_json_response(self, jira_client):
        """Malformed JSON response handled gracefully."""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock()

        with (
            patch.object(
                jira_client.client, "post", new=AsyncMock(return_value=mock_response)
            ),
            pytest.raises(ValueError),
        ):
            await jira_client.search_issues("PROJ")


# =============================================================================
# Context Manager Tests
# =============================================================================


class TestContextManager:
    """Test async context manager support."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Client can be used as async context manager."""
        async with JiraClient(
            instance_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token",
        ) as client:
            assert client is not None
            assert hasattr(client, "client")

    @pytest.mark.asyncio
    async def test_close_called_on_exit(self):
        """close() called when exiting context manager."""
        client = JiraClient(
            instance_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token",
        )

        with patch.object(client, "close", new=AsyncMock()) as mock_close:
            async with client:
                pass

        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_close(self, jira_client):
        """Manual close() closes httpx client."""
        with patch.object(jira_client.client, "aclose", new=AsyncMock()) as mock_aclose:
            await jira_client.close()

        mock_aclose.assert_called_once()


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Test rate limiting delay between requests."""

    @pytest.mark.asyncio
    async def test_delay_between_pages(self):
        """Delay applied between paginated requests."""
        client = JiraClient(
            instance_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token",
            delay_ms=100,  # 100ms delay
        )

        responses = [
            {"issues": [{"key": "P-1"}], "isLast": False, "nextPageToken": "token1"},
            {"issues": [{"key": "P-2"}], "isLast": True},
        ]

        mock_response_objs = []
        for response_data in responses:
            mock_resp = Mock()
            mock_resp.json.return_value = response_data
            mock_resp.raise_for_status = Mock()
            mock_response_objs.append(mock_resp)

        with (
            patch.object(
                client.client,
                "post",
                new=AsyncMock(side_effect=mock_response_objs),
            ),
            patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await client.search_issues("PROJ")

            # Verify sleep called with correct delay (100ms = 0.1s)
            mock_sleep.assert_called_once_with(0.1)

    @pytest.mark.asyncio
    async def test_no_delay_on_last_page(self, jira_client):
        """No delay applied on last page."""
        mock_response = Mock()
        mock_response.json.return_value = {"issues": [{"key": "P-1"}], "isLast": True}
        mock_response.raise_for_status = Mock()

        with (
            patch.object(
                jira_client.client, "post", new=AsyncMock(return_value=mock_response)
            ),
            patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await jira_client.search_issues("PROJ")

            # No sleep on last page
            mock_sleep.assert_not_called()
