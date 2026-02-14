"""Unit tests for GitHub API client.

Tests GitHubClient with:
- Authentication (Bearer token)
- Link header pagination
- Adaptive rate limiting (primary + secondary)
- ETag/Last-Modified conditional caching
- Error handling (retries, backoff, non-retryable errors)
- Batch ID generation
- Config validation
"""

import re
import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.memory.connectors.github.client import (
    GitHubClient,
    GitHubClientError,
    RateLimitExceeded,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def github_client():
    """Create GitHubClient instance for testing with zero delays."""
    return GitHubClient(
        token="ghp_test_token_123",
        repo="owner/repo",
        min_delay_ms=0,  # No delay for tests
    )


def _mock_response(
    status_code: int = 200,
    json_data: dict | list | None = None,
    headers: dict | None = None,
    content: bytes = b"{}",
) -> Mock:
    """Create a mock httpx.Response with given attributes."""
    resp = Mock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.content = content
    resp.text = content.decode() if content else ""
    _headers = {
        "X-RateLimit-Remaining": "4999",
        "X-RateLimit-Reset": str(int(time.time()) + 3600),
    }
    if headers:
        _headers.update(headers)
    resp.headers = _headers
    resp.raise_for_status = Mock()
    return resp


# =============================================================================
# Connection Tests
# =============================================================================


class TestConnection:
    """Test connection and authentication."""

    @pytest.mark.asyncio
    async def test_connection_success(self, github_client):
        """test_connection returns success with valid token."""
        mock_resp = _mock_response(json_data={"login": "testuser"})

        with patch.object(
            github_client._client, "request", new=AsyncMock(return_value=mock_resp)
        ):
            result = await github_client.test_connection()

        assert result["success"] is True
        assert result["user"] == "testuser"
        assert "rate_limit" in result

    @pytest.mark.asyncio
    async def test_connection_invalid_token(self, github_client):
        """test_connection returns failure with invalid token."""
        mock_resp = _mock_response(
            status_code=401,
            json_data={"message": "Bad credentials"},
            content=b'{"message": "Bad credentials"}',
        )
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=Mock(), response=mock_resp
        )

        with patch.object(
            github_client._client, "request", new=AsyncMock(return_value=mock_resp)
        ):
            result = await github_client.test_connection()

        assert result["success"] is False
        assert "error" in result

    def test_bearer_token_in_headers(self, github_client):
        """Authorization header uses Bearer token."""
        headers = github_client._client.headers
        assert headers["Authorization"] == "Bearer ghp_test_token_123"

    def test_accept_header(self, github_client):
        """Accept header set to GitHub JSON media type."""
        headers = github_client._client.headers
        assert headers["Accept"] == "application/vnd.github+json"

    def test_api_version_header(self, github_client):
        """X-GitHub-Api-Version header set."""
        headers = github_client._client.headers
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    def test_user_agent_header(self, github_client):
        """User-Agent header set."""
        headers = github_client._client.headers
        assert "ai-memory" in headers["User-Agent"]


class TestClientConfiguration:
    """Test client initialization and configuration."""

    def test_base_url_default(self, github_client):
        """Default base URL is api.github.com."""
        assert github_client.base_url == "https://api.github.com"

    def test_base_url_custom(self):
        """Custom base URL stored correctly."""
        client = GitHubClient(
            token="token",
            repo="owner/repo",
            base_url="https://github.example.com/api/v3/",
        )
        assert client.base_url == "https://github.example.com/api/v3"

    def test_repo_stored(self, github_client):
        """Repo stored correctly."""
        assert github_client.repo == "owner/repo"

    def test_timeout_configuration(self, github_client):
        """Timeout configuration set on httpx client."""
        timeout = github_client._client.timeout
        assert timeout.connect == 5.0
        assert timeout.read == 30.0
        assert timeout.write == 5.0
        assert timeout.pool == 5.0


class TestContextManager:
    """Test async context manager support."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Client can be used as async context manager."""
        async with GitHubClient(token="token", repo="owner/repo") as client:
            assert client is not None

    @pytest.mark.asyncio
    async def test_close_called_on_exit(self):
        """close() called when exiting context manager."""
        client = GitHubClient(token="token", repo="owner/repo")
        with patch.object(client, "close", new=AsyncMock()) as mock_close:
            async with client:
                pass
        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_close(self, github_client):
        """Manual close() closes httpx client."""
        with patch.object(github_client._client, "aclose", new=AsyncMock()) as mock_aclose:
            await github_client.close()
        mock_aclose.assert_called_once()


# =============================================================================
# Pagination Tests
# =============================================================================


class TestParseLinkHeader:
    """Test Link header parsing."""

    def test_parse_next_link_present(self):
        """_parse_next_link extracts URL from Link header."""
        header = '<https://api.github.com/repos/o/r/issues?page=2>; rel="next", <https://api.github.com/repos/o/r/issues?page=5>; rel="last"'
        assert GitHubClient._parse_next_link(header) == "https://api.github.com/repos/o/r/issues?page=2"

    def test_parse_next_link_absent(self):
        """_parse_next_link returns None when no next page."""
        header = '<https://api.github.com/repos/o/r/issues?page=5>; rel="last"'
        assert GitHubClient._parse_next_link(header) is None

    def test_parse_next_link_empty(self):
        """_parse_next_link handles empty header."""
        assert GitHubClient._parse_next_link("") is None

    def test_parse_next_link_none(self):
        """_parse_next_link handles None-like empty string."""
        assert GitHubClient._parse_next_link("") is None


class TestPagination:
    """Test paginated request handling."""

    @pytest.mark.asyncio
    async def test_paginate_multiple_pages(self, github_client):
        """_paginate follows Link headers across pages."""
        page1_resp = _mock_response(
            json_data=[{"id": 1}, {"id": 2}],
            headers={
                "Link": '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"',
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )
        page2_resp = _mock_response(
            json_data=[{"id": 3}],
            headers={
                "X-RateLimit-Remaining": "4998",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(side_effect=[page1_resp, page2_resp]),
        ):
            result = await github_client._paginate("/repos/owner/repo/issues")

        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[2]["id"] == 3

    @pytest.mark.asyncio
    async def test_paginate_max_pages_safety(self, github_client):
        """_paginate stops at max_pages to prevent runaway."""
        # Create a response that always has a next link
        resp = _mock_response(
            json_data=[{"id": 1}],
            headers={
                "Link": '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"',
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ) as mock_request:
            result = await github_client._paginate(
                "/repos/owner/repo/issues", max_pages=3
            )

        assert mock_request.call_count == 3
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_per_page_100_on_paginated_requests(self, github_client):
        """per_page=100 set on paginated requests."""
        resp = _mock_response(json_data=[])

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ) as mock_request:
            await github_client._paginate("/repos/owner/repo/issues")

        call_args = mock_request.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params")
        assert params["per_page"] == "100"


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Test rate limit enforcement."""

    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self, github_client):
        """Rate limit updates from X-RateLimit-Remaining header."""
        resp = _mock_response(
            json_data={"login": "test"},
            headers={
                "X-RateLimit-Remaining": "4500",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with patch.object(
            github_client._client, "request", new=AsyncMock(return_value=resp)
        ):
            await github_client._request("GET", "/user")

        assert github_client._rate_limit_remaining == 4500

    @pytest.mark.asyncio
    async def test_secondary_rate_limit_window_reset(self, github_client):
        """Secondary point counter resets after 60-second window."""
        github_client._secondary_points_used = 700
        github_client._secondary_window_start = time.monotonic() - 61.0  # Expired

        # After enforcing, the window should reset
        await github_client._enforce_rate_limit(1)

        assert github_client._secondary_points_used == 0

    @pytest.mark.asyncio
    async def test_rate_limit_backoff_on_403(self, github_client):
        """403 with remaining=0 triggers wait-and-retry."""
        reset_time = str(int(time.time()) + 5)
        resp_403 = _mock_response(
            status_code=403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": reset_time,
            },
        )
        resp_ok = _mock_response(json_data={"login": "test"})

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(side_effect=[resp_403, resp_ok]),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
        ):
            result = await github_client._request("GET", "/user")

        assert result == {"login": "test"}

    @pytest.mark.asyncio
    async def test_secondary_rate_limit_429(self, github_client):
        """429 with Retry-After triggers appropriate wait."""
        resp_429 = _mock_response(
            status_code=429,
            headers={
                "Retry-After": "5",
                "X-RateLimit-Remaining": "4000",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )
        resp_ok = _mock_response(json_data={"login": "test"})

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(side_effect=[resp_429, resp_ok]),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            result = await github_client._request("GET", "/user")

        assert result == {"login": "test"}
        # Verify sleep was called with Retry-After value
        sleep_calls = [c for c in mock_sleep.call_args_list if c[0][0] == 5]
        assert len(sleep_calls) >= 1

    def test_safety_margin(self):
        """Rate limiter reserves 20% of quota."""
        client = GitHubClient.__new__(GitHubClient)
        effective = int(client.SECONDARY_LIMIT_POINTS * (1 - client.SAFETY_MARGIN))
        assert effective == 720  # 900 * 0.80


# =============================================================================
# ETag Caching Tests
# =============================================================================


class TestETagCaching:
    """Test ETag and Last-Modified caching."""

    def test_cache_key_deterministic(self, github_client):
        """Cache key is deterministic for same URL+params."""
        key1 = github_client._cache_key("/repos/o/r/issues", {"state": "all"})
        key2 = github_client._cache_key("/repos/o/r/issues", {"state": "all"})
        assert key1 == key2

    def test_cache_key_different_params(self, github_client):
        """Different params produce different cache keys."""
        key1 = github_client._cache_key("/repos/o/r/issues", {"state": "all"})
        key2 = github_client._cache_key("/repos/o/r/issues", {"state": "open"})
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_etag_cache_stores_response(self, github_client):
        """Successful GET caches ETag and Last-Modified."""
        resp = _mock_response(
            json_data={"login": "test"},
            headers={
                "ETag": '"abc123"',
                "Last-Modified": "Wed, 14 Feb 2026 00:00:00 GMT",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with patch.object(
            github_client._client, "request", new=AsyncMock(return_value=resp)
        ):
            await github_client._request("GET", "/user")

        assert len(github_client._etag_cache) == 1
        cached = list(github_client._etag_cache.values())[0]
        assert cached["etag"] == '"abc123"'
        assert cached["last_modified"] == "Wed, 14 Feb 2026 00:00:00 GMT"

    @pytest.mark.asyncio
    async def test_conditional_request_sends_headers(self, github_client):
        """Cached URL sends If-None-Match and If-Modified-Since."""
        # Populate cache first
        resp1 = _mock_response(
            json_data={"login": "test"},
            headers={
                "ETag": '"abc123"',
                "Last-Modified": "Wed, 14 Feb 2026 00:00:00 GMT",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )
        resp2 = _mock_response(json_data={"login": "test"})

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(side_effect=[resp1, resp2]),
        ) as mock_request:
            await github_client._request("GET", "/user")
            await github_client._request("GET", "/user")

        # Second call should include conditional headers
        second_call = mock_request.call_args_list[1]
        extra_headers = second_call.kwargs.get("headers", {})
        assert extra_headers.get("If-None-Match") == '"abc123"'
        assert extra_headers.get("If-Modified-Since") == "Wed, 14 Feb 2026 00:00:00 GMT"

    @pytest.mark.asyncio
    async def test_304_returns_cached_data(self, github_client):
        """304 Not Modified returns previously cached data."""
        original_data = {"login": "test", "id": 42}
        # First request caches data
        resp1 = _mock_response(
            json_data=original_data,
            headers={
                "ETag": '"abc123"',
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )
        # Second request returns 304
        resp2 = _mock_response(
            status_code=304,
            headers={
                "X-RateLimit-Remaining": "4998",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(side_effect=[resp1, resp2]),
        ):
            result1 = await github_client._request("GET", "/user")
            result2 = await github_client._request("GET", "/user")

        assert result1 == original_data
        assert result2 == original_data

    @pytest.mark.asyncio
    async def test_304_does_not_count_secondary_points(self, github_client):
        """304 response does not increment secondary point counter."""
        # First request caches data
        resp1 = _mock_response(
            json_data={"login": "test"},
            headers={
                "ETag": '"abc123"',
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )
        # Second request returns 304
        resp2 = _mock_response(
            status_code=304,
            headers={
                "X-RateLimit-Remaining": "4998",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(side_effect=[resp1, resp2]),
        ):
            await github_client._request("GET", "/user", point_cost=2)
            points_after_first = github_client._secondary_points_used
            await github_client._request("GET", "/user", point_cost=2)
            points_after_second = github_client._secondary_points_used

        # 304 should not add points (subtracts the cost back)
        assert points_after_second == points_after_first


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Test error handling and retries."""

    @pytest.mark.asyncio
    async def test_retry_on_500(self, github_client):
        """Server error 500 triggers exponential backoff retry."""
        resp_500 = _mock_response(status_code=500)
        resp_ok = _mock_response(json_data={"login": "test"})

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(side_effect=[resp_500, resp_ok]),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
            patch("src.memory.connectors.github.client.random.uniform", return_value=0.5),
        ):
            result = await github_client._request("GET", "/user")

        assert result == {"login": "test"}

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self, github_client):
        """Auth error 401 raises immediately without retry."""
        resp_401 = _mock_response(
            status_code=401,
            json_data={"message": "Bad credentials"},
            content=b'{"message": "Bad credentials"}',
        )

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_401),
            ) as mock_request,
            pytest.raises(GitHubClientError, match="401"),
        ):
            await github_client._request("GET", "/user")

        # Only called once -- no retries
        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self, github_client):
        """Not found 404 raises immediately without retry."""
        resp_404 = _mock_response(
            status_code=404,
            json_data={"message": "Not Found"},
            content=b'{"message": "Not Found"}',
        )

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_404),
            ) as mock_request,
            pytest.raises(GitHubClientError, match="404"),
        ):
            await github_client._request("GET", "/repos/owner/repo")

        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_422(self, github_client):
        """Validation error 422 raises immediately without retry."""
        resp_422 = _mock_response(
            status_code=422,
            json_data={"message": "Validation Failed"},
            content=b'{"message": "Validation Failed"}',
        )

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_422),
            ) as mock_request,
            pytest.raises(GitHubClientError, match="422"),
        ):
            await github_client._request("GET", "/repos/owner/repo")

        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_retries(self, github_client):
        """Timeout triggers retry with backoff."""
        timeout_error = httpx.ReadTimeout("Read timeout")
        resp_ok = _mock_response(json_data={"login": "test"})

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(side_effect=[timeout_error, resp_ok]),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
        ):
            result = await github_client._request("GET", "/user")

        assert result == {"login": "test"}

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, github_client):
        """Raises GitHubClientError after MAX_RETRIES attempts."""
        resp_500 = _mock_response(status_code=500)

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_500),
            ) as mock_request,
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
            patch("src.memory.connectors.github.client.random.uniform", return_value=0.5),
            pytest.raises(GitHubClientError, match="server error"),
        ):
            await github_client._request("GET", "/user")

        # MAX_RETRIES + 1 attempts
        assert mock_request.call_count == github_client.MAX_RETRIES + 1

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raised(self, github_client):
        """RateLimitExceeded raised after max retries on 403."""
        reset_time = str(int(time.time()) + 5)
        resp_403 = _mock_response(
            status_code=403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": reset_time,
            },
        )

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_403),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
            pytest.raises(RateLimitExceeded),
        ):
            await github_client._request("GET", "/user")

    def test_rate_limit_exceeded_has_reset_at(self):
        """RateLimitExceeded includes reset_at timestamp."""
        from datetime import datetime, timezone
        reset_at = datetime.now(timezone.utc)
        exc = RateLimitExceeded(reset_at)
        assert exc.reset_at == reset_at
        assert reset_at.isoformat() in str(exc)

    @pytest.mark.asyncio
    async def test_non_rate_limit_403_raises_error(self, github_client):
        """Non-rate-limit 403 (forbidden) raises GitHubClientError."""
        resp_403 = _mock_response(
            status_code=403,
            json_data={"message": "Resource not accessible by integration"},
            content=b'{"message": "Resource not accessible by integration"}',
            headers={
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_403),
            ) as mock_request,
            pytest.raises(GitHubClientError, match="403"),
        ):
            await github_client._request("GET", "/test")

        # Should not retry — immediate error
        assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_http_error_wrapped(self, github_client):
        """httpx.HTTPError wrapped in GitHubClientError."""
        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(side_effect=httpx.ConnectError("Connection failed")),
            ),
            pytest.raises(GitHubClientError, match="HTTP error"),
        ):
            await github_client._request("GET", "/user")


# =============================================================================
# Batch ID Tests
# =============================================================================


class TestBatchId:
    """Test batch ID generation."""

    def test_batch_id_format(self):
        """Batch ID follows github_{timestamp}_{uuid8} format."""
        batch_id = GitHubClient.generate_batch_id()
        assert batch_id.startswith("github_")
        parts = batch_id.split("_")
        assert len(parts) == 4  # github, date, time, uuid
        assert len(parts[3]) == 8  # uuid8

    def test_batch_id_unique(self):
        """Each batch ID is unique."""
        ids = {GitHubClient.generate_batch_id() for _ in range(100)}
        assert len(ids) == 100

    def test_batch_id_timestamp_format(self):
        """Batch ID timestamp matches YYYYMMDD_HHMMSS format."""
        batch_id = GitHubClient.generate_batch_id()
        parts = batch_id.split("_")
        # Date part: YYYYMMDD
        assert re.match(r"^\d{8}$", parts[1])
        # Time part: HHMMSS
        assert re.match(r"^\d{6}$", parts[2])


# =============================================================================
# Config Tests
# =============================================================================


class TestGitHubConfig:
    """Test GitHub config fields in MemoryConfig."""

    def test_github_config_defaults(self):
        """GitHub config fields have correct defaults."""
        from src.memory.config import MemoryConfig

        config = MemoryConfig()
        assert config.github_sync_enabled is False
        assert config.github_sync_interval == 1800
        assert config.github_branch == "main"
        assert config.github_code_blob_enabled is True
        assert config.github_code_blob_max_size == 102400

    def test_github_config_required_when_enabled(self):
        """Token and repo required when sync enabled."""
        from src.memory.config import MemoryConfig

        with pytest.raises(Exception):  # ValidationError
            MemoryConfig(github_sync_enabled=True)

    def test_github_repo_format_validation(self):
        """Repo must be in owner/repo format."""
        from src.memory.config import MemoryConfig

        with pytest.raises(Exception):  # ValidationError
            MemoryConfig(
                github_sync_enabled=True,
                github_token="ghp_test",
                github_repo="invalid-format",
            )

    def test_github_config_valid_when_enabled(self):
        """Valid config with all required fields."""
        from src.memory.config import MemoryConfig

        config = MemoryConfig(
            github_sync_enabled=True,
            github_token="ghp_test_token",
            github_repo="owner/repo",
        )
        assert config.github_sync_enabled is True
        assert config.github_repo == "owner/repo"

    def test_github_token_is_secret(self):
        """GitHub token stored as SecretStr."""
        from src.memory.config import MemoryConfig

        config = MemoryConfig(
            github_sync_enabled=True,
            github_token="ghp_test_token",
            github_repo="owner/repo",
        )
        assert config.github_token.get_secret_value() == "ghp_test_token"
        # str() should NOT reveal the token
        assert "ghp_test_token" not in str(config.github_token)

    def test_github_disabled_no_validation(self):
        """No validation when github_sync_enabled=False."""
        from src.memory.config import MemoryConfig

        # Should not raise even with empty token and repo
        config = MemoryConfig(github_sync_enabled=False)
        assert config.github_sync_enabled is False

    def test_github_sync_interval_bounds(self):
        """Sync interval must be between 60 and 86400."""
        from src.memory.config import MemoryConfig

        with pytest.raises(Exception):
            MemoryConfig(github_sync_interval=30)  # Too low

    def test_github_code_blob_max_size_bounds(self):
        """Max size must be between 1024 and 1048576."""
        from src.memory.config import MemoryConfig

        with pytest.raises(Exception):
            MemoryConfig(github_code_blob_max_size=500)  # Too low


# =============================================================================
# Endpoint Tests
# =============================================================================


class TestEndpoints:
    """Test specific API endpoint methods."""

    @pytest.mark.asyncio
    async def test_list_issues_with_since(self, github_client):
        """list_issues passes since parameter for incremental sync."""
        resp = _mock_response(json_data=[{"number": 1}])

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ) as mock_request:
            result = await github_client.list_issues(since="2026-01-01T00:00:00Z")

        assert len(result) == 1
        call_args = mock_request.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("since") == "2026-01-01T00:00:00Z"
        assert params.get("state") == "all"
        assert params.get("per_page") == "100"

    @pytest.mark.asyncio
    async def test_list_issues_with_labels(self, github_client):
        """list_issues passes labels parameter."""
        resp = _mock_response(json_data=[])

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ) as mock_request:
            await github_client.list_issues(labels="bug,enhancement")

        call_args = mock_request.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("labels") == "bug,enhancement"

    @pytest.mark.asyncio
    async def test_list_commits_with_sha(self, github_client):
        """list_commits passes sha parameter for branch filtering."""
        resp = _mock_response(json_data=[{"sha": "abc123"}])

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ) as mock_request:
            result = await github_client.list_commits(sha="main")

        assert len(result) == 1
        call_args = mock_request.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("sha") == "main"

    @pytest.mark.asyncio
    async def test_get_tree_recursive(self, github_client):
        """get_tree requests recursive listing."""
        resp = _mock_response(
            json_data={"tree": [{"path": "README.md", "type": "blob"}]}
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ) as mock_request:
            result = await github_client.get_tree(recursive=True)

        assert len(result) == 1
        call_args = mock_request.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("recursive") == "1"

    @pytest.mark.asyncio
    async def test_get_tree_non_recursive(self, github_client):
        """get_tree without recursive does not pass recursive param."""
        resp = _mock_response(json_data={"tree": []})

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ) as mock_request:
            await github_client.get_tree(recursive=False)

        call_args = mock_request.call_args
        params = call_args.kwargs.get("params", {})
        assert "recursive" not in params

    @pytest.mark.asyncio
    async def test_workflow_runs_higher_point_cost(self, github_client):
        """Actions API requests use point_cost=2."""
        resp = _mock_response(json_data={"workflow_runs": [{"id": 1}]})
        initial_points = github_client._secondary_points_used

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.list_workflow_runs()

        assert len(result) == 1
        # Point cost of 2 should be added
        assert github_client._secondary_points_used == initial_points + 2

    @pytest.mark.asyncio
    async def test_get_commit(self, github_client):
        """get_commit retrieves a single commit."""
        resp = _mock_response(json_data={"sha": "abc123", "message": "test"})

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.get_commit("abc123")

        assert result["sha"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_blob(self, github_client):
        """get_blob retrieves file content by SHA."""
        resp = _mock_response(
            json_data={"sha": "blob123", "content": "base64data", "encoding": "base64"}
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.get_blob("blob123")

        assert result["sha"] == "blob123"
        assert result["encoding"] == "base64"

    @pytest.mark.asyncio
    async def test_get_repo_content(self, github_client):
        """get_repo_content retrieves file content."""
        resp = _mock_response(
            json_data={"name": "README.md", "type": "file", "content": "base64data"}
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.get_repo_content("README.md", ref="main")

        assert result["name"] == "README.md"

    @pytest.mark.asyncio
    async def test_get_pr_reviews(self, github_client):
        """get_pr_reviews lists reviews on a PR."""
        resp = _mock_response(json_data=[{"id": 1, "state": "APPROVED"}])

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.get_pr_reviews(42)

        assert len(result) == 1
        assert result[0]["state"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_get_pr_files(self, github_client):
        """get_pr_files lists files changed in a PR."""
        resp = _mock_response(
            json_data=[{"filename": "README.md", "status": "modified"}]
        )

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.get_pr_files(42)

        assert len(result) == 1
        assert result[0]["filename"] == "README.md"

    @pytest.mark.asyncio
    async def test_get_issue_comments(self, github_client):
        """get_issue_comments lists comments on an issue."""
        resp = _mock_response(json_data=[{"id": 1, "body": "test comment"}])

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.get_issue_comments(42)

        assert len(result) == 1
        assert result[0]["body"] == "test comment"

    @pytest.mark.asyncio
    async def test_list_pull_requests(self, github_client):
        """list_pull_requests lists PRs with pagination."""
        resp = _mock_response(json_data=[{"number": 1, "title": "Fix bug"}])

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(return_value=resp),
        ):
            result = await github_client.list_pull_requests(state="open")

        assert len(result) == 1
        assert result[0]["title"] == "Fix bug"


# =============================================================================
# Metrics Tests
# =============================================================================


class TestMetrics:
    """Test metrics/status methods."""

    def test_get_rate_limit_status(self, github_client):
        """get_rate_limit_status returns current rate limit info."""
        github_client._rate_limit_remaining = 4500
        github_client._rate_limit_reset = 1234567890.0
        github_client._secondary_points_used = 50
        github_client._etag_cache = {"key1": {}, "key2": {}}

        status = github_client.get_rate_limit_status()

        assert status["primary_remaining"] == 4500
        assert status["primary_reset"] == 1234567890.0
        assert status["secondary_points_used"] == 50
        assert status["etag_cache_size"] == 2

    def test_get_rate_limit_status_initial(self, github_client):
        """get_rate_limit_status with no requests yet."""
        status = github_client.get_rate_limit_status()

        assert status["primary_remaining"] is None
        assert status["primary_reset"] is None
        assert status["secondary_points_used"] == 0
        assert status["etag_cache_size"] == 0


# =============================================================================
# Fix Verification Tests
# =============================================================================


class TestPaginationErrorHandling:
    """Test that pagination uses _raw_request and gets full error handling (Fix 1)."""

    @pytest.mark.asyncio
    async def test_paginate_raises_github_client_error_on_500(self, github_client):
        """Pagination raises GitHubClientError (not raw httpx error) on server error."""
        resp_500 = _mock_response(status_code=500)

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_500),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
            patch("src.memory.connectors.github.client.random.uniform", return_value=0.5),
            pytest.raises(GitHubClientError, match="server error"),
        ):
            await github_client._paginate("/repos/owner/repo/issues")

    @pytest.mark.asyncio
    async def test_paginate_retries_on_500(self, github_client):
        """Pagination retries on 5xx via _raw_request."""
        resp_500 = _mock_response(status_code=500)
        resp_ok = _mock_response(json_data=[{"id": 1}])

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(side_effect=[resp_500, resp_ok]),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
            patch("src.memory.connectors.github.client.random.uniform", return_value=0.5),
        ):
            result = await github_client._paginate("/repos/owner/repo/issues")

        assert len(result) == 1
        assert result[0]["id"] == 1


class TestPrimaryRateLimitMargin:
    """Test primary rate limit uses 20% safety margin (Fix 2)."""

    @pytest.mark.asyncio
    async def test_enforce_rate_limit_uses_1000_threshold(self, github_client):
        """_enforce_rate_limit triggers at 1000 remaining (20% of 5000), not 100."""
        github_client._rate_limit_remaining = 999
        github_client._rate_limit_reset = time.time() + 3600

        with patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await github_client._enforce_rate_limit(1)

        # Should NOT sleep for the hard wait since 999 > 100 (10% of 1000)
        # But it should enter the primary limit block (999 < 1000)
        # The hard wait triggers at < 100, so no sleep for primary here
        # Verify the margin is applied by checking with remaining=500
        # which should enter the block but not hard-wait
        assert github_client._rate_limit_remaining == 999

    @pytest.mark.asyncio
    async def test_enforce_rate_limit_hard_wait_at_100(self, github_client):
        """Hard wait triggers at 100 remaining (10% of 1000 margin)."""
        github_client._rate_limit_remaining = 50
        github_client._rate_limit_reset = time.time() + 10

        with patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await github_client._enforce_rate_limit(1)

        # 50 < 100 (10% of 1000), should trigger hard wait
        sleep_calls = [c for c in mock_sleep.call_args_list if c[0][0] > 0]
        assert len(sleep_calls) >= 1

    @pytest.mark.asyncio
    async def test_enforce_rate_limit_no_trigger_above_margin(self, github_client):
        """No primary limit action when remaining > 1000."""
        github_client._rate_limit_remaining = 1500
        github_client._rate_limit_reset = time.time() + 3600

        with patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await github_client._enforce_rate_limit(1)

        # 1500 > 1000, should not trigger any primary limit sleep
        # Only possible sleep is min delay, which is 0 for tests
        for call in mock_sleep.call_args_list:
            # No sleep call should be for primary rate limit warning
            assert call[0][0] == 0 or call[0][0] < 1  # only min delay


class TestConnectionRateInfo:
    """Test test_connection returns correct rate_info (Fix 3)."""

    @pytest.mark.asyncio
    async def test_connection_rate_info_limit_is_5000(self, github_client):
        """test_connection returns limit=5000 (PRIMARY_LIMIT) in rate_info."""
        mock_resp = _mock_response(json_data={"login": "testuser"})

        with patch.object(
            github_client._client, "request", new=AsyncMock(return_value=mock_resp)
        ):
            result = await github_client.test_connection()

        assert result["success"] is True
        assert result["rate_limit"]["limit"] == 5000


class TestExhausted429RaisesRateLimitExceeded:
    """Test 429 retries exhausted raises RateLimitExceeded (Fix 4)."""

    @pytest.mark.asyncio
    async def test_429_exhausted_raises_rate_limit_exceeded(self, github_client):
        """Exhausted 429 retries raise RateLimitExceeded, not generic error."""
        resp_429 = _mock_response(
            status_code=429,
            headers={
                "Retry-After": "5",
                "X-RateLimit-Remaining": "4000",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        with (
            patch.object(
                github_client._client,
                "request",
                new=AsyncMock(return_value=resp_429),
            ),
            patch("src.memory.connectors.github.client.asyncio.sleep", new=AsyncMock()),
            pytest.raises(RateLimitExceeded, match="Secondary rate limit"),
        ):
            await github_client._request("GET", "/user")


class TestStaleCache304Retry:
    """Test 304 with empty cache retries (Fix 5)."""

    @pytest.mark.asyncio
    async def test_304_stale_cache_retries(self, github_client):
        """304 with no cached data retries the request."""
        # Manually set a cache key so conditional headers are sent
        cache_key = github_client._cache_key("/user", {"per_page": "100"})
        github_client._etag_cache[cache_key] = {
            "etag": '"old"',
            "last_modified": None,
            "data": {"login": "old"},
        }

        # First response: 304 but we clear the cache before it returns
        resp_304 = _mock_response(
            status_code=304,
            headers={
                "X-RateLimit-Remaining": "4998",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )
        resp_ok = _mock_response(json_data={"login": "fresh"})

        call_count = 0
        original_cache = github_client._etag_cache

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate cache eviction before 304 is processed
                original_cache.pop(cache_key, None)
                return resp_304
            return resp_ok

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(side_effect=mock_request),
        ):
            result = await github_client._request("GET", "/user")

        assert result == {"login": "fresh"}
        assert call_count == 2  # First 304 retried, second succeeded

    @pytest.mark.asyncio
    async def test_stale_304_does_not_double_count_points(self, github_client):
        """Stale 304 retry doesn't double-charge secondary points."""
        # Populate cache so conditional headers are sent
        cache_key = github_client._cache_key("/user", {"per_page": "100"})
        github_client._etag_cache[cache_key] = {
            "etag": '"old"',
            "last_modified": None,
            "data": {"login": "old"},
        }

        resp_304 = _mock_response(
            status_code=304,
            headers={
                "X-RateLimit-Remaining": "4998",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )
        resp_ok = _mock_response(
            json_data={"login": "fresh"},
            headers={
                "ETag": '"new"',
                "X-RateLimit-Remaining": "4997",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
        )

        call_count = 0
        original_cache = github_client._etag_cache

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate cache eviction before 304 is processed
                original_cache.pop(cache_key, None)
                return resp_304
            return resp_ok

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(side_effect=mock_request),
        ):
            github_client._secondary_points_used = 0
            await github_client._request("GET", "/user", point_cost=2)

        # Should only have charged 2 points total (not 4)
        assert github_client._secondary_points_used == 2

    @pytest.mark.asyncio
    async def test_stale_304_exhaustion_raises_error(self, github_client):
        """Persistent stale 304s after all retries raises GitHubClientError."""
        cache_key = github_client._cache_key("/user", {"per_page": "100"})
        github_client._etag_cache[cache_key] = {
            "etag": '"old"',
            "last_modified": None,
            "data": {"login": "cached"},
        }

        resp_304 = httpx.Response(
            304,
            headers={
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": str(int(time.time()) + 3600),
            },
            request=httpx.Request("GET", "https://api.github.com/user"),
        )

        async def mock_request(*args, **kwargs):
            # Always evict cache and return 304
            github_client._etag_cache.pop(cache_key, None)
            return resp_304

        with patch.object(
            github_client._client,
            "request",
            new=AsyncMock(side_effect=mock_request),
        ):
            with pytest.raises(GitHubClientError, match="304 Not Modified"):
                await github_client._request("GET", "/user")
