"""Jira semantic search operations.

Provides semantic search against the jira-data collection with tenant isolation,
and issue lookup functionality for retrieving complete issue context.

Architecture Reference: PLAN-004 Phase 3
"""

import logging
import time
from typing import Any

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    SearchParams,
)

from ...activity_log import log_activity
from ...config import COLLECTION_JIRA_DATA, MemoryConfig, get_config
from ...embeddings import EmbeddingClient, EmbeddingError
from ...qdrant_client import get_qdrant_client

__all__ = ["JiraSearchError", "lookup_issue", "search_jira"]

logger = logging.getLogger("ai_memory.jira.search")


class JiraSearchError(Exception):
    """Raised when Jira search operation fails.

    Wraps underlying Qdrant and embedding errors for consistent error handling.
    """

    pass


def _format_jira_url(
    instance_url: str, issue_key: str, comment_id: str | None = None
) -> str:
    """Build full Jira URL to issue or comment.

    Args:
        instance_url: Jira instance URL from group_id (e.g., "hidden-history.atlassian.net")
        issue_key: Issue key (e.g., "PROJ-123")
        comment_id: Optional comment ID for direct comment link

    Returns:
        Full URL: https://{instance_url}/browse/{issue_key}[?focusedCommentId={comment_id}]

    Example:
        >>> _format_jira_url("company.atlassian.net", "PROJ-123")
        'https://company.atlassian.net/browse/PROJ-123'
        >>> _format_jira_url("company.atlassian.net", "PROJ-123", "10001")
        'https://company.atlassian.net/browse/PROJ-123?focusedCommentId=10001'
    """
    base_url = f"https://{instance_url}/browse/{issue_key}"
    if comment_id:
        return f"{base_url}?focusedCommentId={comment_id}"
    return base_url


def _format_badges(payload: dict[str, Any]) -> str:
    """Create metadata badges for display.

    Format: [Type: Bug] [Status: In Progress] [Priority: High] [Author: Alice]

    Args:
        payload: Memory payload with jira_* fields

    Returns:
        Formatted badge string

    Example:
        >>> payload = {
        ...     "type": "jira_issue",
        ...     "jira_issue_type": "Bug",
        ...     "jira_status": "In Progress",
        ...     "jira_priority": "High",
        ...     "jira_reporter": "Alice"
        ... }
        >>> _format_badges(payload)
        '[Type: Bug] [Status: In Progress] [Priority: High] [Reporter: Alice]'
    """
    badges = []

    # Issue type (Bug, Story, Task, Epic)
    if payload.get("jira_issue_type"):
        badges.append(f"Type: {payload['jira_issue_type']}")

    # Status
    if payload.get("jira_status"):
        badges.append(f"Status: {payload['jira_status']}")

    # Priority (can be None)
    if payload.get("jira_priority"):
        badges.append(f"Priority: {payload['jira_priority']}")

    # Author (jira_author for comments, jira_reporter for issues)
    memory_type = payload.get("type")
    if memory_type == "jira_comment" and payload.get("jira_author"):
        badges.append(f"Author: {payload['jira_author']}")
    elif memory_type == "jira_issue" and payload.get("jira_reporter"):
        badges.append(f"Reporter: {payload['jira_reporter']}")

    return " ".join(f"[{b}]" for b in badges)


def _truncate_content(content: str, max_length: int = 300) -> str:
    """Truncate content to max_length characters, adding ellipsis if truncated.

    Args:
        content: Full content text
        max_length: Maximum length (default: 300)

    Returns:
        Truncated content with "..." if needed

    Example:
        >>> _truncate_content("Short text", 300)
        'Short text'
        >>> _truncate_content("A" * 400, 300)
        'AAA...AAA...'  # First 300 chars + "..."
    """
    if len(content) <= max_length:
        return content
    return content[:max_length] + "..."


def search_jira(
    query: str,
    group_id: str,  # REQUIRED - tenant isolation
    project: str | None = None,
    memory_type: str | None = None,  # "jira_issue" or "jira_comment"
    issue_type: str | None = None,  # Bug, Story, Task, Epic
    status: str | None = None,
    priority: str | None = None,
    author: str | None = None,  # jira_author OR jira_reporter
    limit: int = 5,
    config: MemoryConfig | None = None,
) -> list[dict[str, Any]]:
    """Semantic search against jira-data collection with filters.

    CRITICAL: group_id is REQUIRED for tenant isolation. This prevents cross-tenant
    data leakage in multi-instance deployments.

    Args:
        query: Search query text (will be embedded for semantic search)
        group_id: Jira instance hostname (e.g., "company.atlassian.net") - REQUIRED
        project: Optional Jira project key filter (e.g., "PROJ")
        memory_type: Optional type filter ("jira_issue" or "jira_comment")
        issue_type: Optional issue type filter (Bug, Story, Task, Epic)
        status: Optional status filter (In Progress, Done, etc.)
        priority: Optional priority filter (High, Medium, Low, etc.)
        author: Optional author filter (matches jira_author OR jira_reporter)
        limit: Maximum results to return (default: 5)
        config: Optional MemoryConfig instance

    Returns:
        List of search result dicts with:
            - id: Memory UUID
            - score: Similarity score (0.0-1.0)
            - content: Full content text
            - jira_url: Full URL to issue/comment
            - badges: Formatted metadata badges
            - snippet: Truncated content (~300 chars)
            - All jira_* payload fields

    Raises:
        ValueError: If group_id is None or empty
        JiraSearchError: If search operation fails

    Example:
        >>> results = search_jira(
        ...     query="authentication bug",
        ...     group_id="company.atlassian.net",
        ...     project="PROJ",
        ...     issue_type="Bug",
        ...     status="In Progress",
        ...     limit=5
        ... )
        >>> for r in results:
        ...     print(f"{r['score']:.0%} - {r['jira_url']}")
        ...     print(f"{r['badges']}")
        ...     print(f"{r['snippet']}")
    """
    # Validate required parameter
    if not group_id:
        raise ValueError("group_id is required for tenant isolation")

    config = config or get_config()

    # Initialize clients
    qdrant_client = get_qdrant_client(config)
    embedding_client = EmbeddingClient(config)

    # Generate query embedding
    try:
        query_embedding = embedding_client.embed([query])[0]
    except EmbeddingError as e:
        logger.error(
            "jira_search_embedding_failed",
            extra={"query": query[:50], "error": str(e)},
        )
        raise JiraSearchError(f"Embedding generation failed: {e}") from e

    # Build filter conditions
    filter_conditions = []

    # MANDATORY: group_id filter (tenant isolation)
    filter_conditions.append(
        FieldCondition(key="group_id", match=MatchValue(value=group_id))
    )

    # Optional filters
    if project:
        filter_conditions.append(
            FieldCondition(key="jira_project", match=MatchValue(value=project))
        )

    if memory_type:
        filter_conditions.append(
            FieldCondition(key="type", match=MatchValue(value=memory_type))
        )

    if issue_type:
        filter_conditions.append(
            FieldCondition(key="jira_issue_type", match=MatchValue(value=issue_type))
        )

    if status:
        filter_conditions.append(
            FieldCondition(key="jira_status", match=MatchValue(value=status))
        )

    if priority:
        filter_conditions.append(
            FieldCondition(key="jira_priority", match=MatchValue(value=priority))
        )

    if author:
        filter_conditions.append(
            Filter(
                should=[
                    FieldCondition(key="jira_author", match=MatchValue(value=author)),
                    FieldCondition(key="jira_reporter", match=MatchValue(value=author)),
                ]
            )
        )

    query_filter = Filter(must=filter_conditions)

    # Search Qdrant
    start_time = time.perf_counter()
    try:
        response = qdrant_client.query_points(
            collection_name=COLLECTION_JIRA_DATA,
            query=query_embedding,
            query_filter=query_filter,
            limit=limit,
            score_threshold=config.similarity_threshold,
            with_payload=True,
            search_params=SearchParams(hnsw_ef=config.hnsw_ef_accurate),
        )
        results = response.points
    except Exception as e:
        duration_seconds = time.perf_counter() - start_time
        logger.error(
            "jira_search_failed",
            extra={
                "group_id": group_id,
                "query": query[:50],
                "error": str(e),
                "duration_seconds": duration_seconds,
            },
        )
        raise JiraSearchError(f"Qdrant search failed: {e}") from e

    # Format results
    formatted_results = []
    for result in results:
        payload = result.payload or {}

        # Extract fields
        issue_key = payload.get("jira_issue_key", "UNKNOWN")
        comment_id = payload.get("jira_comment_id")
        content = payload.get("content", "")

        # Build Jira URL
        jira_url = _format_jira_url(group_id, issue_key, comment_id)

        # Create formatted result
        formatted = {
            "id": result.id,
            "score": result.score,
            "jira_url": jira_url,
            "badges": _format_badges(payload),
            "snippet": _truncate_content(content, max_length=300),
            "content": content,  # Include full content
            **payload,  # Include all jira_* fields
        }
        formatted_results.append(formatted)

    # Log search activity
    duration_ms = (time.perf_counter() - start_time) * 1000
    log_activity(
        "🔍",
        f'JiraSearch: {len(formatted_results)} results for "{query[:50]}" [{duration_ms:.0f}ms]',
    )

    logger.info(
        "jira_search_completed",
        extra={
            "group_id": group_id,
            "query": query[:50],
            "results_count": len(formatted_results),
            "duration_ms": duration_ms,
            "filters": {
                "project": project,
                "memory_type": memory_type,
                "issue_type": issue_type,
                "status": status,
                "priority": priority,
                "author": author,
            },
        },
    )

    return formatted_results


def lookup_issue(
    issue_key: str,
    group_id: str,  # REQUIRED - tenant isolation
    config: MemoryConfig | None = None,
) -> dict[str, Any]:
    """Retrieve issue document and all its comments chronologically.

    This is a retrieval operation, not semantic search. Returns complete issue
    context for display.

    Args:
        issue_key: Jira issue key (e.g., "PROJ-123")
        group_id: Jira instance hostname (e.g., "company.atlassian.net") - REQUIRED
        config: Optional MemoryConfig instance

    Returns:
        Dict with:
            - issue: Issue document dict (or None if not found)
            - comments: List of comment dicts, sorted by jira_updated (chronological)
            - total_count: Total documents (1 issue + N comments)

    Raises:
        ValueError: If group_id or issue_key is empty
        JiraSearchError: If retrieval operation fails

    Example:
        >>> result = lookup_issue("PROJ-123", "company.atlassian.net")
        >>> print(result["issue"]["content"])
        '[PROJ-123] Fix login bug...'
        >>> for comment in result["comments"]:
        ...     print(f"Comment by {comment['jira_author']}: {comment['snippet']}")
    """
    # Validate required parameters
    if not group_id:
        raise ValueError("group_id is required for tenant isolation")
    if not issue_key:
        raise ValueError("issue_key is required")

    config = config or get_config()
    qdrant_client = get_qdrant_client(config)

    # Build filter: group_id AND jira_issue_key
    filter_conditions = [
        FieldCondition(key="group_id", match=MatchValue(value=group_id)),
        FieldCondition(key="jira_issue_key", match=MatchValue(value=issue_key)),
    ]
    query_filter = Filter(must=filter_conditions)

    # Retrieve all documents for this issue key
    # Note: No semantic search, just filtered retrieval
    # Use scroll() for exhaustive retrieval (more efficient than query_points with high limit)
    start_time = time.perf_counter()
    try:
        scroll_result = qdrant_client.scroll(
            collection_name=COLLECTION_JIRA_DATA,
            scroll_filter=query_filter,
            limit=100,  # Page size (should be enough for issue + comments)
            with_payload=True,
        )
        points = scroll_result[0]  # scroll() returns (points, next_offset)
    except Exception as e:
        duration_seconds = time.perf_counter() - start_time
        logger.error(
            "jira_lookup_failed",
            extra={
                "group_id": group_id,
                "issue_key": issue_key,
                "error": str(e),
                "duration_seconds": duration_seconds,
            },
        )
        raise JiraSearchError(f"Issue lookup failed: {e}") from e

    # Separate issue and comments
    issue_doc = None
    comment_docs = []

    for point in points:
        payload = point.payload or {}
        memory_type = payload.get("type")

        # Add formatted fields for consistency with search_jira()
        issue_key_payload = payload.get("jira_issue_key", "UNKNOWN")
        comment_id = payload.get("jira_comment_id")
        content = payload.get("content", "")

        formatted = {
            "id": point.id,
            "jira_url": _format_jira_url(group_id, issue_key_payload, comment_id),
            "badges": _format_badges(payload),
            "snippet": _truncate_content(content, max_length=300),
            "content": content,
            **payload,
        }

        if memory_type == "jira_issue":
            issue_doc = formatted
        elif memory_type == "jira_comment":
            comment_docs.append(formatted)

    # Sort comments chronologically by jira_updated
    comment_docs.sort(key=lambda c: c.get("jira_updated", ""))

    # Log lookup activity
    duration_ms = (time.perf_counter() - start_time) * 1000
    total_count = (1 if issue_doc else 0) + len(comment_docs)
    log_activity(
        "🔍", f"JiraLookup: {issue_key} - {total_count} documents [{duration_ms:.0f}ms]"
    )

    logger.info(
        "jira_lookup_completed",
        extra={
            "group_id": group_id,
            "issue_key": issue_key,
            "has_issue": issue_doc is not None,
            "comment_count": len(comment_docs),
            "duration_ms": duration_ms,
        },
    )

    return {
        "issue": issue_doc,
        "comments": comment_docs,
        "total_count": total_count,
    }
