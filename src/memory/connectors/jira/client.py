"""Jira Cloud REST API client.

Provides async httpx-based client for Jira Cloud API v3 with Basic Auth.
Implements token-based pagination for issue search and offset-based pagination for comments.

Reference: https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/
"""

import asyncio
import base64
import logging
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger("ai_memory.jira.client")


class JiraClientError(Exception):
    """Raised when Jira API request fails.

    This exception wraps httpx errors and HTTP errors for consistent error handling.
    """

    pass


class JiraClient:
    """Jira Cloud REST API client using httpx with Basic Auth.

    Uses long-lived httpx.AsyncClient with connection pooling for optimal performance.
    Implements proper timeout configuration and rate limiting via configurable delays.

    Attributes:
        base_url: Jira instance URL (e.g., https://company.atlassian.net)
        auth_header: Basic Auth header (base64 encoded email:api_token)
        delay_ms: Delay between requests for rate limiting

    Example:
        >>> async with JiraClient("https://company.atlassian.net", "user@example.com", "token") as client:
        ...     result = await client.test_connection()
        ...     if result["success"]:
        ...         projects = await client.list_projects()
    """

    def __init__(
        self,
        instance_url: str,
        email: str,
        api_token: str,
        delay_ms: int = 100,
    ) -> None:
        """Initialize Jira client with authentication.

        Args:
            instance_url: Jira instance URL (e.g., https://company.atlassian.net)
            email: Jira account email for Basic Auth
            api_token: Jira API token for authentication
            delay_ms: Delay between requests in milliseconds (default: 100)

        Note:
            Creates a long-lived httpx.AsyncClient with connection pooling.
            Reuse this client instance across requests for optimal performance.
        """
        self.base_url = instance_url.rstrip("/")
        self.delay_ms = delay_ms

        # Create Basic Auth header: base64(email:api_token)
        credentials = f"{email}:{api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.auth_header = f"Basic {encoded}"

        # Timeout configuration (similar to EmbeddingClient pattern)
        timeout_config = httpx.Timeout(
            connect=3.0,  # Connection establishment timeout
            read=15.0,  # Read timeout for API responses
            write=5.0,  # Write timeout for request body
            pool=3.0,  # Pool acquisition timeout
        )

        # Connection pooling with recommended defaults
        limits = httpx.Limits(
            max_keepalive_connections=20,  # Keep-alive pool size
            max_connections=100,  # Total connection limit
            keepalive_expiry=10.0,  # Idle timeout
        )

        self.client = httpx.AsyncClient(
            timeout=timeout_config,
            limits=limits,
            headers={
                "Authorization": self.auth_header,
                "Accept": "application/json",
            },
        )

    async def test_connection(self) -> dict[str, Any]:
        """Test Jira API connectivity and authentication.

        Sends GET request to /rest/api/3/myself to verify credentials.

        Returns:
            dict with keys:
                - success (bool): True if authenticated successfully
                - user_email (str | None): Authenticated user's email
                - error (str | None): Error message if failed

        Example:
            >>> result = await client.test_connection()
            >>> if result["success"]:
            ...     print(f"Connected as: {result['user_email']}")
        """
        try:
            response = await self.client.get(f"{self.base_url}/rest/api/3/myself")
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "user_email": data.get("emailAddress"),
                "error": None,
            }
        except httpx.TimeoutException as e:
            logger.error("jira_connection_timeout", extra={"error": str(e)})
            return {
                "success": False,
                "user_email": None,
                "error": f"Connection timeout: {e}",
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                "jira_connection_failed",
                extra={"status_code": e.response.status_code, "error": str(e)},
            )
            return {
                "success": False,
                "user_email": None,
                "error": f"HTTP {e.response.status_code}: {e}",
            }
        except httpx.HTTPError as e:
            logger.error("jira_connection_error", extra={"error": str(e)})
            return {
                "success": False,
                "user_email": None,
                "error": f"Connection error: {e}",
            }

    async def list_projects(self) -> list[dict[str, Any]]:
        """List all accessible projects.

        Sends GET request to /rest/api/3/project.

        Returns:
            List of project dicts with keys: key, name, id, projectTypeKey

        Raises:
            JiraClientError: If request fails

        Example:
            >>> projects = await client.list_projects()
            >>> for p in projects:
            ...     print(f"{p['key']}: {p['name']}")
        """
        try:
            response = await self.client.get(f"{self.base_url}/rest/api/3/project")
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as e:
            logger.error("jira_list_projects_timeout", extra={"error": str(e)})
            raise JiraClientError("JIRA_LIST_PROJECTS_TIMEOUT") from e
        except httpx.HTTPError as e:
            logger.error("jira_list_projects_error", extra={"error": str(e)})
            raise JiraClientError(f"JIRA_LIST_PROJECTS_ERROR: {e}") from e

    async def search_issues(
        self,
        project_key: str,
        updated_since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search issues in a project using JQL with token-based pagination.

        Uses /rest/api/3/search/jql endpoint with nextPageToken/isLast pagination.

        CRITICAL: Jira Cloud requires bounded JQL queries. The JQL MUST include
        'project = {KEY}' to avoid 400 Bad Request errors.

        Args:
            project_key: Jira project key (e.g., 'PROJ')
            updated_since: Optional ISO 8601 timestamp to filter by updated date

        Returns:
            List of issue dicts (full Jira API response objects)

        Raises:
            JiraClientError: If request fails

        Example:
            >>> issues = await client.search_issues("PROJ", updated_since="2026-01-01T00:00:00Z")
            >>> for issue in issues:
            ...     print(f"{issue['key']}: {issue['fields']['summary']}")
        """
        # Build JQL query (bounded by project)
        jql = f"project = {project_key}"
        if updated_since:
            # Convert ISO 8601 to Jira JQL format (YYYY-MM-DD HH:mm)
            # Jira rejects ISO 8601 T-separator format silently (returns 0 results)
            try:
                # Python 3.10 compat: fromisoformat() doesn't support "Z" suffix until 3.11
                dt = datetime.fromisoformat(updated_since.replace("Z", "+00:00"))
                jql_date = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                # Fallback: use as-is if already in Jira format
                jql_date = updated_since
            jql += f" AND updated >= '{jql_date}'"

        all_issues: list[dict[str, Any]] = []
        next_token: str | None = None
        is_last = False

        try:
            while not is_last:
                # Build request parameters (GET query params)
                params: dict[str, Any] = {
                    "jql": jql,
                    "maxResults": 50,
                    "fields": "*all",
                }
                if next_token:
                    params["nextPageToken"] = next_token

                # Send request — /search/jql (replaces deprecated /search which returns 410)
                # Both GET and POST work; GET is canonical per Atlassian API docs
                response = await self.client.get(
                    f"{self.base_url}/rest/api/3/search/jql",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                # Extract issues and pagination info
                issues = data.get("issues", [])
                all_issues.extend(issues)

                # Check pagination (token-based)
                is_last = data.get("isLast", True)
                next_token = data.get("nextPageToken")

                logger.info(
                    "jira_search_issues_page",
                    extra={
                        "project_key": project_key,
                        "page_issues": len(issues),
                        "total_so_far": len(all_issues),
                        "is_last": is_last,
                    },
                )

                # Rate limiting delay (except on last page)
                if not is_last and self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

            logger.info(
                "jira_search_issues_complete",
                extra={"project_key": project_key, "total_issues": len(all_issues)},
            )
            return all_issues

        except httpx.TimeoutException as e:
            logger.error(
                "jira_search_issues_timeout",
                extra={"project_key": project_key, "error": str(e)},
            )
            raise JiraClientError("JIRA_SEARCH_ISSUES_TIMEOUT") from e
        except httpx.HTTPError as e:
            logger.error(
                "jira_search_issues_error",
                extra={"project_key": project_key, "error": str(e)},
            )
            raise JiraClientError(f"JIRA_SEARCH_ISSUES_ERROR: {e}") from e

    async def get_comments(self, issue_key: str) -> list[dict[str, Any]]:
        """Get all comments for an issue using offset-based pagination.

        Uses /rest/api/3/issue/{key}/comment endpoint with startAt/maxResults pagination.

        Args:
            issue_key: Jira issue key (e.g., 'PROJ-123')

        Returns:
            List of comment dicts (full Jira API comment objects)

        Raises:
            JiraClientError: If request fails

        Example:
            >>> comments = await client.get_comments("PROJ-123")
            >>> for comment in comments:
            ...     print(f"Comment by {comment['author']['displayName']}")
        """
        all_comments: list[dict[str, Any]] = []
        start_at = 0
        max_results = 50
        total = None

        try:
            while total is None or start_at < total:
                # Send request
                response = await self.client.get(
                    f"{self.base_url}/rest/api/3/issue/{issue_key}/comment",
                    params={"startAt": start_at, "maxResults": max_results},
                )
                response.raise_for_status()
                data = response.json()

                # Extract comments and pagination info
                comments = data.get("comments", [])
                all_comments.extend(comments)

                # Update pagination (offset-based)
                total = data.get("total", 0)
                start_at += len(comments)

                logger.debug(
                    "jira_get_comments_page",
                    extra={
                        "issue_key": issue_key,
                        "page_comments": len(comments),
                        "total_so_far": len(all_comments),
                        "total": total,
                    },
                )

                # Rate limiting delay (except on last page)
                if start_at < total and self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

            logger.debug(
                "jira_get_comments_complete",
                extra={"issue_key": issue_key, "total_comments": len(all_comments)},
            )
            return all_comments

        except httpx.TimeoutException as e:
            logger.error(
                "jira_get_comments_timeout",
                extra={"issue_key": issue_key, "error": str(e)},
            )
            raise JiraClientError("JIRA_GET_COMMENTS_TIMEOUT") from e
        except httpx.HTTPError as e:
            logger.error(
                "jira_get_comments_error",
                extra={"issue_key": issue_key, "error": str(e)},
            )
            raise JiraClientError(f"JIRA_GET_COMMENTS_ERROR: {e}") from e

    async def close(self) -> None:
        """Close the HTTP client connection.

        Call this method when done with the client, or use context manager.

        Example:
            >>> client = JiraClient(...)
            >>> try:
            ...     await client.test_connection()
            ... finally:
            ...     await client.close()
        """
        if hasattr(self, "client") and self.client is not None:
            await self.client.aclose()

    async def __aenter__(self) -> "JiraClient":
        """Enter async context manager.

        Returns:
            Self for use in async with statement.

        Example:
            >>> async with JiraClient(...) as client:
            ...     result = await client.test_connection()
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and close client.

        Args:
            exc_type: Exception type if raised, None otherwise.
            exc_val: Exception value if raised, None otherwise.
            exc_tb: Exception traceback if raised, None otherwise.
        """
        await self.close()
