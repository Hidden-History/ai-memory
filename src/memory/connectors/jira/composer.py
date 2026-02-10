"""Document composers for Jira issues and comments.

Transforms raw Jira API response data into embeddable document text.
Handles nullable fields gracefully for team-managed projects.
"""

import logging
from typing import Any

from .adf_converter import adf_to_text

logger = logging.getLogger("ai_memory.jira.composer")


def compose_issue_document(issue: dict[str, Any]) -> str:
    """Compose embeddable document text from Jira issue data.

    Format:
        [PROJ-123] Issue Title Here
        Type: Bug | Priority: High | Status: In Progress
        Reporter: Alex | Assigned: Sarah
        Labels: authentication, frontend
        Created: 2026-02-01 | Updated: 2026-02-07

        Description:
        {ADF-converted description text}

    Handles nullable fields gracefully (priority, assignee, labels, resolution).

    Args:
        issue: Raw Jira API issue response dict

    Returns:
        Formatted document text ready for embedding

    Example:
        >>> issue = {
        ...     "key": "PROJ-123",
        ...     "fields": {
        ...         "summary": "Fix login bug",
        ...         "issuetype": {"name": "Bug"},
        ...         "status": {"name": "In Progress"},
        ...         "priority": {"name": "High"},
        ...         "reporter": {"displayName": "Alice"},
        ...         "assignee": {"displayName": "Bob"},
        ...         "labels": ["security", "auth"],
        ...         "created": "2026-02-01T10:00:00.000+0000",
        ...         "updated": "2026-02-07T15:30:00.000+0000",
        ...         "description": {"type": "doc", "content": [...]}
        ...     }
        ... }
        >>> text = compose_issue_document(issue)
    """
    # Extract required fields
    key = issue.get("key", "UNKNOWN")
    fields = issue.get("fields", {})

    summary = fields.get("summary", "No summary")
    issue_type = fields.get("issuetype", {}).get("name", "Unknown")
    status = fields.get("status", {}).get("name", "Unknown")

    # Extract nullable fields with defaults
    priority_obj = fields.get("priority")
    priority = priority_obj.get("name") if priority_obj else "None"

    reporter_obj = fields.get("reporter")
    reporter = reporter_obj.get("displayName", "Unknown") if reporter_obj else "Unknown"

    assignee_obj = fields.get("assignee")
    assignee = assignee_obj.get("displayName") if assignee_obj else "Unassigned"

    labels = fields.get("labels", [])
    labels_str = ", ".join(labels) if labels else "None"

    # Extract and format dates (ISO 8601 -> YYYY-MM-DD)
    created = fields.get("created", "")[:10]  # "2026-02-01T10:00:00.000+0000" -> "2026-02-01"
    updated = fields.get("updated", "")[:10]

    # Convert description from ADF to text
    description_adf = fields.get("description")
    description_text = adf_to_text(description_adf) if description_adf else "(No description)"

    # Build document
    lines = [
        f"[{key}] {summary}",
        f"Type: {issue_type} | Priority: {priority} | Status: {status}",
        f"Reporter: {reporter} | Assigned: {assignee}",
        f"Labels: {labels_str}",
        f"Created: {created} | Updated: {updated}",
        "",
        "Description:",
        description_text,
    ]

    return "\n".join(lines)


def compose_comment_document(
    issue: dict[str, Any],
    comment: dict[str, Any],
) -> str:
    """Compose embeddable document text from Jira comment data.

    Format:
        [PROJ-123] Issue Title Here (Bug, High, In Progress)

        Comment by Mike (2026-02-07):
        {ADF-converted comment text}

    Args:
        issue: Parent issue dict (for context in header)
        comment: Raw Jira API comment response dict

    Returns:
        Formatted document text ready for embedding

    Example:
        >>> issue = {
        ...     "key": "PROJ-123",
        ...     "fields": {
        ...         "summary": "Fix login bug",
        ...         "issuetype": {"name": "Bug"},
        ...         "priority": {"name": "High"},
        ...         "status": {"name": "In Progress"}
        ...     }
        ... }
        >>> comment = {
        ...     "id": "10001",
        ...     "author": {"displayName": "Mike"},
        ...     "created": "2026-02-07T14:00:00.000+0000",
        ...     "body": {"type": "doc", "content": [...]}
        ... }
        >>> text = compose_comment_document(issue, comment)
    """
    # Extract issue context
    key = issue.get("key", "UNKNOWN")
    fields = issue.get("fields", {})
    summary = fields.get("summary", "No summary")
    issue_type = fields.get("issuetype", {}).get("name", "Unknown")
    status = fields.get("status", {}).get("name", "Unknown")

    # Extract nullable priority
    priority_obj = fields.get("priority")
    priority = priority_obj.get("name") if priority_obj else "None"

    # Extract comment fields
    author_obj = comment.get("author", {})
    author = author_obj.get("displayName", "Unknown")

    created = comment.get("created", "")[:10]  # "2026-02-07T14:00:00.000+0000" -> "2026-02-07"

    # Convert comment body from ADF to text
    body_adf = comment.get("body")
    body_text = adf_to_text(body_adf) if body_adf else "(Empty comment)"

    # Build document
    lines = [
        f"[{key}] {summary} ({issue_type}, {priority}, {status})",
        "",
        f"Comment by {author} ({created}):",
        body_text,
    ]

    return "\n".join(lines)
