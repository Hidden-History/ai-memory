"""Jira Cloud integration package.

Provides client, ADF converter, and document composers for Jira issue/comment ingestion.
"""

from .adf_converter import adf_to_text
from .client import JiraClient, JiraClientError
from .composer import compose_comment_document, compose_issue_document

__all__ = [
    "JiraClient",
    "JiraClientError",
    "adf_to_text",
    "compose_comment_document",
    "compose_issue_document",
]
