"""GitHub REST API client.

Provides async httpx-based client for GitHub REST API v3 with token auth.
Implements Link header pagination, adaptive rate limiting (primary + secondary),
ETag caching for conditional requests, and exponential backoff.

Reference: https://docs.github.com/en/rest
Rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
"""

import asyncio
import hashlib
import logging
import random
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("ai_memory.github.client")


class GitHubClientError(Exception):
    """Raised when GitHub API request fails.

    Wraps httpx errors and HTTP errors for consistent error handling.
    """

    pass


class RateLimitExceeded(GitHubClientError):
    """Raised when GitHub rate limit is exhausted."""

    def __init__(self, reset_at: datetime, message: str = "Rate limit exceeded"):
        self.reset_at = reset_at
        super().__init__(f"{message}. Resets at {reset_at.isoformat()}")


class GitHubClient:
    """GitHub REST API client using httpx with Bearer token auth.

    Uses long-lived httpx.AsyncClient with connection pooling.
    Implements adaptive rate limiting per BP-062:
    - Primary: 5,000 requests/hour (PAT)
    - Secondary: 900 points/minute (calculated cost)
    - Safety margin: 20% reserved
    - ETag caching: 304 Not Modified responses don't count against limit

    Attributes:
        base_url: GitHub API base URL (default: https://api.github.com)
        repo: Target repository in owner/repo format
        _rate_limit_remaining: Tracked from X-RateLimit-Remaining header
        _rate_limit_reset: Tracked from X-RateLimit-Reset header
        _secondary_points_used: Tracked cumulative point cost per minute window
        _etag_cache: URL-keyed cache of ETag/Last-Modified values

    Example:
        >>> async with GitHubClient("ghp_token", "owner/repo") as client:
        ...     result = await client.test_connection()
        ...     if result["success"]:
        ...         issues = await client.list_issues(since="2026-01-01T00:00:00Z")
    """

    # GitHub API base URL
    BASE_URL = "https://api.github.com"

    # Rate limit constants (BP-062)
    PRIMARY_LIMIT = 5000  # requests/hour for PAT
    SECONDARY_LIMIT_POINTS = 900  # points/minute
    SAFETY_MARGIN = 0.20  # Reserve 20% of quota
    MIN_REQUEST_DELAY_MS = 100  # Minimum delay between requests (ms)

    # Timeout configuration (BP-062)
    CONNECT_TIMEOUT = 5.0  # seconds
    READ_TIMEOUT = 30.0  # seconds
    WRITE_TIMEOUT = 5.0  # seconds
    POOL_TIMEOUT = 5.0  # seconds

    # Retry configuration
    MAX_RETRIES = 3
    BASE_BACKOFF = 2  # seconds, exponential: min(60, 2^attempt)
    MAX_BACKOFF = 60  # seconds

    # Pagination
    DEFAULT_PER_PAGE = 100  # Maximum items per page (BP-062)

    # ETag cache size limit (GH-PERF-001: prevent unbounded growth)
    MAX_ETAG_CACHE_SIZE = 1000

    def __init__(
        self,
        token: str,
        repo: str,
        base_url: str | None = None,
        min_delay_ms: int = MIN_REQUEST_DELAY_MS,
    ) -> None:
        """Initialize GitHub client with token authentication.

        Args:
            token: GitHub Personal Access Token (fine-grained recommended)
            repo: Target repository in owner/repo format
            base_url: GitHub API base URL (default: https://api.github.com)
            min_delay_ms: Minimum delay between requests in milliseconds
        """
        self.repo = repo
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self._min_delay_s = min_delay_ms / 1000.0

        # Rate limit tracking
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: float | None = None
        self._secondary_points_used: int = 0
        self._secondary_window_start: float = time.monotonic()
        self._last_request_time: float = 0.0

        # ETag cache: {url_hash: {"etag": str, "last_modified": str, "data": Any}}
        self._etag_cache: dict[str, dict[str, Any]] = {}

        # httpx client with connection pooling
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-memory-github-sync/1.0",
            },
            timeout=httpx.Timeout(
                connect=self.CONNECT_TIMEOUT,
                read=self.READ_TIMEOUT,
                write=self.WRITE_TIMEOUT,
                pool=self.POOL_TIMEOUT,
            ),
        )

    async def __aenter__(self) -> "GitHubClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit -- close httpx client."""
        await self.close()

    async def close(self) -> None:
        """Close the httpx client and release connections."""
        await self._client.aclose()

    # --- Authentication & Connection ---

    async def test_connection(self) -> dict[str, Any]:
        """Validate token and check rate limit status.

        Returns:
            dict with keys: success (bool), user (str), scopes (list),
            rate_limit (dict with limit, remaining, reset)
        """
        try:
            response = await self._request("GET", "/user", point_cost=1)
            rate_info = {
                "limit": self.PRIMARY_LIMIT,
                "remaining": self._rate_limit_remaining,
                "reset": self._rate_limit_reset,
            }
            return {
                "success": True,
                "user": response.get("login", "unknown"),
                "scopes": [],  # Fine-grained PATs don't expose scopes
                "rate_limit": rate_info,
            }
        except GitHubClientError as e:
            return {"success": False, "error": str(e)}

    # --- Repository Data Endpoints ---

    async def list_issues(
        self,
        state: str = "all",
        since: str | None = None,
        labels: str | None = None,
    ) -> list[dict[str, Any]]:
        """List repository issues with pagination.

        Args:
            state: Filter by state (open, closed, all)
            since: ISO 8601 timestamp -- only issues updated after this time
            labels: Comma-separated label names

        Returns:
            List of issue dicts from GitHub API
        """
        params: dict[str, str] = {"state": state, "sort": "updated", "direction": "asc"}
        if since:
            params["since"] = since
        if labels:
            params["labels"] = labels

        return await self._paginate(
            f"/repos/{self.repo}/issues",
            params=params,
            point_cost=1,
        )

    async def get_issue_comments(
        self,
        issue_number: int,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """List comments on an issue.

        Args:
            issue_number: Issue number
            since: ISO 8601 timestamp -- only comments updated after this time

        Returns:
            List of comment dicts
        """
        params: dict[str, str] = {"sort": "updated", "direction": "asc"}
        if since:
            params["since"] = since

        return await self._paginate(
            f"/repos/{self.repo}/issues/{issue_number}/comments",
            params=params,
            point_cost=1,
        )

    async def list_pull_requests(
        self,
        state: str = "all",
        sort: str = "updated",
        direction: str = "desc",
    ) -> list[dict[str, Any]]:
        """List repository pull requests with pagination.

        Args:
            state: Filter by state (open, closed, all)
            sort: Sort by (created, updated, popularity, long-running)
            direction: Sort direction (asc, desc)

        Returns:
            List of PR dicts
        """
        params = {"state": state, "sort": sort, "direction": direction}
        return await self._paginate(
            f"/repos/{self.repo}/pulls",
            params=params,
            point_cost=1,
        )

    async def get_pr_reviews(self, pr_number: int) -> list[dict[str, Any]]:
        """List reviews on a pull request.

        Args:
            pr_number: PR number

        Returns:
            List of review dicts
        """
        return await self._paginate(
            f"/repos/{self.repo}/pulls/{pr_number}/reviews",
            point_cost=1,
        )

    async def get_pr_files(self, pr_number: int) -> list[dict[str, Any]]:
        """List files changed in a pull request.

        Args:
            pr_number: PR number

        Returns:
            List of file dicts with filename, status, additions, deletions, patch
        """
        return await self._paginate(
            f"/repos/{self.repo}/pulls/{pr_number}/files",
            point_cost=1,
        )

    async def list_commits(
        self,
        sha: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        """List repository commits with pagination.

        Args:
            sha: Branch name or commit SHA to start from
            since: ISO 8601 timestamp -- only commits after this time
            until: ISO 8601 timestamp -- only commits before this time

        Returns:
            List of commit dicts
        """
        params: dict[str, str] = {}
        if sha:
            params["sha"] = sha
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        return await self._paginate(
            f"/repos/{self.repo}/commits",
            params=params,
            point_cost=1,
        )

    async def get_commit(self, sha: str) -> dict[str, Any]:
        """Get a single commit with diff stats.

        Args:
            sha: Full commit SHA

        Returns:
            Commit dict with files changed, stats, etc.
        """
        return await self._request(
            "GET",
            f"/repos/{self.repo}/commits/{sha}",
            point_cost=1,
        )

    async def list_workflow_runs(
        self,
        created: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List GitHub Actions workflow runs.

        Args:
            created: Filter by creation date (e.g., ">=2026-01-01")
            status: Filter by status (completed, in_progress, queued)

        Returns:
            List of workflow run dicts
        """
        params: dict[str, str] = {}
        if created:
            params["created"] = created
        if status:
            params["status"] = status

        response = await self._request(
            "GET",
            f"/repos/{self.repo}/actions/runs",
            params=params,
            point_cost=2,  # Actions API has higher point cost
        )
        return response.get("workflow_runs", [])

    async def get_repo_content(
        self,
        path: str,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Get file or directory content from repository.

        Args:
            path: File path in repository
            ref: Branch/tag/commit to read from (default: repo default branch)

        Returns:
            Content dict with type, content (base64), sha, size, etc.
        """
        params: dict[str, str] = {}
        if ref:
            params["ref"] = ref

        return await self._request(
            "GET",
            f"/repos/{self.repo}/contents/{path}",
            params=params,
            point_cost=1,
        )

    async def get_tree(
        self,
        tree_sha: str = "HEAD",
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        """Get repository tree (file listing).

        Args:
            tree_sha: Tree SHA or branch name (default: HEAD)
            recursive: Include subdirectories recursively

        Returns:
            List of tree entry dicts with path, type, sha, size
        """
        params: dict[str, str] = {}
        if recursive:
            params["recursive"] = "1"

        response = await self._request(
            "GET",
            f"/repos/{self.repo}/git/trees/{tree_sha}",
            params=params,
            point_cost=1,
        )
        return response.get("tree", [])

    async def get_blob(self, blob_sha: str) -> dict[str, Any]:
        """Get a git blob (file content by SHA).

        Args:
            blob_sha: Git blob SHA

        Returns:
            Blob dict with content (base64 encoded), encoding, size, sha
        """
        return await self._request(
            "GET",
            f"/repos/{self.repo}/git/blobs/{blob_sha}",
            point_cost=1,
        )

    # --- Rate Limiting (BP-062) ---

    async def _enforce_rate_limit(self, point_cost: int) -> None:
        """Enforce both primary and secondary rate limits.

        Adaptive pacing per BP-062:
        1. Check primary limit (X-RateLimit-Remaining)
        2. Check secondary limit (cumulative point cost per minute)
        3. Enforce minimum delay between requests
        4. Back off when approaching limits

        Args:
            point_cost: Point cost of the upcoming request (1-5)
        """
        now = time.monotonic()

        # Reset secondary window every 60 seconds
        if now - self._secondary_window_start >= 60.0:
            self._secondary_points_used = 0
            self._secondary_window_start = now

        # Check secondary limit (900 points/min with 20% safety margin)
        effective_secondary = int(
            self.SECONDARY_LIMIT_POINTS * (1 - self.SAFETY_MARGIN)
        )
        if self._secondary_points_used + point_cost > effective_secondary:
            wait_time = 60.0 - (now - self._secondary_window_start)
            if wait_time > 0:
                logger.info(
                    "Secondary rate limit approaching (%d/%d points). Waiting %.1fs",
                    self._secondary_points_used,
                    effective_secondary,
                    wait_time,
                )
                await asyncio.sleep(wait_time)
                self._secondary_points_used = 0
                self._secondary_window_start = time.monotonic()

        # Check primary limit (20% safety margin)
        effective_primary_margin = int(self.PRIMARY_LIMIT * self.SAFETY_MARGIN)  # 1000
        if (
            self._rate_limit_remaining is not None
            and self._rate_limit_remaining < effective_primary_margin
            and self._rate_limit_reset
        ):
            wait_time = max(0, self._rate_limit_reset - time.time())
            if wait_time > 0 and self._rate_limit_remaining < int(
                effective_primary_margin * 0.1
            ):
                logger.warning(
                    "Primary rate limit low (%d remaining). Waiting %.1fs for reset",
                    self._rate_limit_remaining,
                    wait_time,
                )
                await asyncio.sleep(min(wait_time, 60.0))

        # Enforce minimum delay between requests
        elapsed = now - self._last_request_time
        if elapsed < self._min_delay_s:
            await asyncio.sleep(self._min_delay_s - elapsed)

    def _update_rate_limits(self, response: httpx.Response) -> None:
        """Update rate limit tracking from response headers.

        Args:
            response: httpx response with rate limit headers
        """
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                self._rate_limit_remaining = int(remaining)
            except ValueError:
                logger.warning(
                    "Non-numeric X-RateLimit-Remaining header: %r", remaining
                )

        reset = response.headers.get("X-RateLimit-Reset")
        if reset is not None:
            try:
                self._rate_limit_reset = float(reset)
            except ValueError:
                logger.warning("Non-numeric X-RateLimit-Reset header: %r", reset)

        # Log rate limit status periodically
        if (
            self._rate_limit_remaining is not None
            and self._rate_limit_remaining % 500 == 0
        ):
            logger.info(
                "Rate limit status: %d remaining, resets at %s",
                self._rate_limit_remaining,
                (
                    datetime.fromtimestamp(
                        self._rate_limit_reset, tz=timezone.utc
                    ).isoformat()
                    if self._rate_limit_reset
                    else "unknown"
                ),
            )

    # --- ETag Caching (BP-062) ---

    def _cache_key(self, url: str, params: dict[str, str] | None = None) -> str:
        """Generate a cache key from URL and parameters.

        Args:
            url: Request URL path
            params: Query parameters

        Returns:
            SHA-256 hash of URL + sorted params
        """
        key_parts = [url]
        if params:
            key_parts.extend(f"{k}={v}" for k, v in sorted(params.items()))
        return hashlib.sha256("|".join(key_parts).encode()).hexdigest()[:16]

    def _get_conditional_headers(self, cache_key: str) -> dict[str, str]:
        """Get conditional request headers from cache.

        Prefer Last-Modified over ETag for polling reliability (BP-062).

        Args:
            cache_key: Cache key from _cache_key()

        Returns:
            Dict with If-None-Match and/or If-Modified-Since headers
        """
        headers: dict[str, str] = {}
        cached = self._etag_cache.get(cache_key)
        if cached:
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
        return headers

    def _update_cache(
        self,
        cache_key: str,
        response: httpx.Response,
        data: Any,
    ) -> None:
        """Update ETag cache from response headers.

        Args:
            cache_key: Cache key
            response: httpx response with ETag/Last-Modified headers
            data: Parsed response data to cache
        """
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if etag or last_modified:
            # GH-PERF-001: LRU eviction — evict oldest 25% when cache is full.
            # Python 3.7+ dicts preserve insertion order, so oldest keys come first.
            if len(self._etag_cache) >= self.MAX_ETAG_CACHE_SIZE:
                oldest_keys = list(self._etag_cache.keys())[
                    : self.MAX_ETAG_CACHE_SIZE // 4
                ]
                for key in oldest_keys:
                    del self._etag_cache[key]
            self._etag_cache[cache_key] = {
                "etag": etag,
                "last_modified": last_modified,
                "data": data,
            }

    # --- Core HTTP Methods ---

    async def _raw_request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        point_cost: int = 1,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a raw HTTP request with rate limiting, retries, and error handling.

        Handles all retry logic (5xx, 429, 403, timeout) and returns the raw
        httpx.Response on success (2xx or 304). Callers handle JSON parsing
        and caching.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., /repos/owner/repo/issues)
            params: Query parameters
            point_cost: Request point cost for secondary rate limit (1-5)
            extra_headers: Additional headers (e.g., conditional cache headers)

        Returns:
            Raw httpx.Response (status 2xx or 304)

        Raises:
            GitHubClientError: On non-retryable errors (auth, not found)
            RateLimitExceeded: When rate limit is exhausted after retries
        """
        for attempt in range(self.MAX_RETRIES + 1):
            await self._enforce_rate_limit(point_cost)

            try:
                self._last_request_time = time.monotonic()
                response = await self._client.request(
                    method, path, params=params, headers=extra_headers or {}
                )

                # Track rate limits and point cost.
                # GH-BUG-001: only charge secondary budget on the FIRST attempt
                # to prevent double-decrement when a request is retried after
                # a rate-limit response.
                self._update_rate_limits(response)
                if attempt == 0:
                    self._secondary_points_used += point_cost

                # Rate limit exceeded -- wait and retry
                if response.status_code == 403:
                    remaining = response.headers.get("X-RateLimit-Remaining", "")
                    if remaining == "0":
                        reset = float(response.headers.get("X-RateLimit-Reset", "0"))
                        reset_dt = datetime.fromtimestamp(reset, tz=timezone.utc)
                        if attempt < self.MAX_RETRIES:
                            wait = max(1, reset - time.time())
                            logger.warning(
                                "Rate limit hit. Waiting %.0fs (attempt %d/%d)",
                                wait,
                                attempt + 1,
                                self.MAX_RETRIES,
                            )
                            await asyncio.sleep(min(wait, self.MAX_BACKOFF))
                            continue
                        raise RateLimitExceeded(reset_dt)
                    else:
                        # Non-rate-limit 403 (forbidden, abuse, insufficient permissions)
                        try:
                            error_body = response.json() if response.content else {}
                        except (ValueError, UnicodeDecodeError):
                            error_body = {}
                        raise GitHubClientError(
                            f"GitHub API error 403: {error_body.get('message', response.text)}"
                        )

                # Secondary rate limit (Retry-After header)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    if attempt < self.MAX_RETRIES:
                        logger.warning(
                            "Secondary rate limit. Retry-After: %ds (attempt %d/%d)",
                            retry_after,
                            attempt + 1,
                            self.MAX_RETRIES,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitExceeded(
                        datetime.fromtimestamp(
                            time.time() + retry_after, tz=timezone.utc
                        ),
                        "Secondary rate limit exceeded",
                    )

                # Client errors (non-retryable)
                if response.status_code in (401, 404, 422):
                    try:
                        error_body = response.json() if response.content else {}
                    except (ValueError, UnicodeDecodeError):
                        error_body = {}
                    raise GitHubClientError(
                        f"GitHub API error {response.status_code}: "
                        f"{error_body.get('message', response.text)}"
                    )

                # Server errors (retryable)
                if response.status_code >= 500:
                    if attempt < self.MAX_RETRIES:
                        backoff = min(
                            self.MAX_BACKOFF,
                            self.BASE_BACKOFF ** (attempt + 1),
                        ) + random.uniform(
                            0, 1
                        )  # jitter
                        logger.warning(
                            "Server error %d. Retrying in %.1fs (attempt %d/%d)",
                            response.status_code,
                            backoff,
                            attempt + 1,
                            self.MAX_RETRIES,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    raise GitHubClientError(
                        f"GitHub API server error {response.status_code} after "
                        f"{self.MAX_RETRIES} retries"
                    )

                # Success (2xx or 304)
                return response

            except httpx.TimeoutException as e:
                if attempt < self.MAX_RETRIES:
                    backoff = min(self.MAX_BACKOFF, self.BASE_BACKOFF ** (attempt + 1))
                    logger.warning(
                        "Request timeout. Retrying in %.1fs (attempt %d/%d)",
                        backoff,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise GitHubClientError(
                    f"Request timeout after {self.MAX_RETRIES} retries: {e}"
                ) from e

            except httpx.HTTPError as e:
                raise GitHubClientError(f"HTTP error: {e}") from e

        # Should not reach here, but defensive
        raise GitHubClientError("Request failed after all retries")

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        point_cost: int = 1,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Make a single API request with rate limiting, caching, and error handling.

        Delegates to _raw_request() for retry/error logic, then handles
        304 caching and JSON parsing.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., /repos/owner/repo/issues)
            params: Query parameters
            point_cost: Request point cost for secondary rate limit (1-5)
            use_cache: Whether to use ETag caching for GET requests

        Returns:
            Parsed JSON response

        Raises:
            GitHubClientError: On non-retryable errors (auth, not found)
            RateLimitExceeded: When rate limit is exhausted after retries
        """
        if params is None:
            params = {}
        params["per_page"] = str(self.DEFAULT_PER_PAGE)

        cache_key = (
            self._cache_key(path, params) if use_cache and method == "GET" else ""
        )

        # Note: This loop handles stale 304 retries (max MAX_RETRIES+1 iterations).
        # Each iteration calls _raw_request() which has its own retry loop for
        # server errors/timeouts. Worst case: (MAX_RETRIES+1)^2 requests, but this
        # only occurs with persistent stale 304s combined with transient server errors.
        for attempt in range(self.MAX_RETRIES + 1):
            # Add conditional headers for GET requests
            extra_headers = {}
            if cache_key:
                extra_headers = self._get_conditional_headers(cache_key)

            response = await self._raw_request(
                method,
                path,
                params=params,
                point_cost=point_cost,
                extra_headers=extra_headers if extra_headers else None,
            )

            # 304 Not Modified -- return cached data (doesn't count against limit)
            if response.status_code == 304 and cache_key:
                cached = self._etag_cache.get(cache_key)
                if cached:
                    # 304 doesn't count against primary rate limit (BP-062)
                    self._secondary_points_used -= point_cost
                    return cached["data"]
                # 304 but cache miss — clear stale conditional headers and retry
                self._etag_cache.pop(cache_key, None)
                self._secondary_points_used -= (
                    point_cost  # 304 is free, undo the charge
                )
                logger.warning("Received 304 but no cached data for %s, retrying", path)
                if attempt < self.MAX_RETRIES:
                    continue
                raise GitHubClientError(
                    f"Received 304 Not Modified but no cached data for {path}"
                )

            # Success -- parse and cache
            data = response.json()
            if cache_key:
                self._update_cache(cache_key, response, data)
            return data

        # Should not reach here, but defensive
        raise GitHubClientError("Request failed after all retries")

    # --- Pagination (BP-062) ---

    async def _paginate(
        self,
        path: str,
        params: dict[str, str] | None = None,
        point_cost: int = 1,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch all pages of a paginated endpoint using Link headers.

        Delegates to _raw_request() per page for full retry/error handling.

        Follows GitHub's Link header pagination pattern (BP-062):
        - Set per_page=100 to minimize total requests
        - Parse Link header to extract next URL
        - Stop when no 'next' link or max_pages reached

        Args:
            path: API path
            params: Query parameters (per_page added automatically)
            point_cost: Point cost per request
            max_pages: Safety limit to prevent runaway pagination

        Returns:
            Concatenated list of all items across all pages
        """
        all_items: list[dict[str, Any]] = []
        if params is None:
            params = {}
        params["per_page"] = str(self.DEFAULT_PER_PAGE)

        current_path = path
        current_params: dict[str, str] | None = params

        for page in range(max_pages):
            response = await self._raw_request(
                "GET",
                current_path,
                params=current_params,
                point_cost=point_cost,
            )

            data = response.json()

            # Handle list responses and dict responses with items
            if isinstance(data, list):
                all_items.extend(data)
            elif isinstance(data, dict) and "items" in data:
                all_items.extend(data["items"])

            # Check for next page via Link header
            next_url = self._parse_next_link(response.headers.get("Link", ""))
            if not next_url:
                break

            # Parse the full URL to extract path and query params
            # The next URL is absolute, so we need to strip the base
            current_path = (
                next_url.split(self.base_url)[-1]
                if self.base_url in next_url
                else next_url
            )
            current_params = None  # Parameters are embedded in the Link URL

            logger.debug(
                "Paginating: page %d, %d items so far", page + 1, len(all_items)
            )

        return all_items

    def _parse_next_link(self, link_header: str) -> str | None:
        """Parse GitHub Link header to extract 'next' URL.

        Format: <https://api.github.com/...?page=2>; rel="next", <...>; rel="last"

        Args:
            link_header: Raw Link header value

        Returns:
            Next page URL or None if no next page
        """
        if not link_header:
            return None

        for part in link_header.split(","):
            match = re.match(r'\s*<([^>]+)>;\s*rel="next"', part.strip())
            if match:
                url = match.group(1)
                # GH-SEC-006: reject any pagination URL not from our base URL
                # to prevent open-redirect / SSRF via a crafted Link header.
                if not url.startswith(self.base_url + "/"):
                    logger.warning(
                        "Rejecting Link header URL not matching base_url: %.100s",
                        url,
                    )
                    return None
                return url
        return None

    # --- Batch ID Generation (BP-074) ---

    @staticmethod
    def generate_batch_id() -> str:
        """Generate a unique batch ID for sync operations.

        Format: github_{YYYYMMDD_HHMMSS}_{uuid8}
        Used by sync engine to group all points created in a single sync run,
        enabling batch rollback per BP-074.

        Returns:
            Unique batch ID string
        """
        import uuid

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"github_{timestamp}_{short_uuid}"

    # --- Metrics ---

    def get_rate_limit_status(self) -> dict[str, Any]:
        """Get current rate limit status for metrics/logging.

        Returns:
            Dict with remaining, reset, secondary_points_used, cache_size
        """
        return {
            "primary_remaining": self._rate_limit_remaining,
            "primary_reset": self._rate_limit_reset,
            "secondary_points_used": self._secondary_points_used,
            "etag_cache_size": len(self._etag_cache),
        }
