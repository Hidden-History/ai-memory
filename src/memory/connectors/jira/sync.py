"""Jira sync orchestrator for AI Memory Module.

Implements PLAN-004 Phase 2: Sync engine that fetches Jira issues and comments,
chunks them, generates embeddings, and stores in Qdrant's jira-data collection.

Pipeline Flow:
1. JQL search (full or incremental based on last_synced timestamp)
2. Token-based pagination for issues
3. Document composition (issue + comments)
4. Intelligent chunking (ContentType.PROSE)
5. Embedding generation (batch where possible)
6. Qdrant storage with metadata
7. State persistence (last_synced timestamp per project)

Error Handling:
- Per-issue fail-open: Log error, continue to next issue
- Graceful degradation: Zero vector if embedding fails
- Resource cleanup: try/finally for async clients
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from qdrant_client.models import FieldCondition, Filter, MatchValue

from ...config import COLLECTION_JIRA_DATA, MemoryConfig, get_config
from ...embeddings import EmbeddingClient
from ...models import MemoryType
from ...qdrant_client import get_qdrant_client
from ...storage import MemoryStorage
from .client import JiraClient
from .composer import compose_comment_document, compose_issue_document

logger = logging.getLogger(__name__)

__all__ = ["JiraSyncEngine", "SyncResult"]


class SyncResult:
    """Result of a sync operation."""

    def __init__(
        self,
        issues_synced: int = 0,
        comments_synced: int = 0,
        errors: list[str] | None = None,
        duration_seconds: float = 0.0,
    ):
        self.issues_synced = issues_synced
        self.comments_synced = comments_synced
        self.errors = errors or []
        self.duration_seconds = duration_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "issues_synced": self.issues_synced,
            "comments_synced": self.comments_synced,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


class JiraSyncEngine:
    """Orchestrates Jira-to-Qdrant synchronization pipeline.

    Attributes:
        config: MemoryConfig instance
        jira_client: JiraClient instance (async)
        storage: MemoryStorage instance (sync)
        embedding_client: EmbeddingClient instance
        qdrant_client: QdrantClient instance
        state_path: Path to jira_sync_state.json
    """

    def __init__(self, config: MemoryConfig | None = None):
        """Initialize sync engine with all required clients.

        Args:
            config: MemoryConfig instance (defaults to get_config())
        """
        self.config = config or get_config()

        # Validate Jira is enabled
        if not self.config.jira_sync_enabled:
            raise ValueError("Jira sync is not enabled (JIRA_SYNC_ENABLED=false)")

        # Validate credentials
        if not self.config.jira_instance_url:
            raise ValueError("JIRA_INSTANCE_URL not configured")
        if not self.config.jira_email:
            raise ValueError("JIRA_EMAIL not configured")
        if not self.config.jira_api_token.get_secret_value():
            raise ValueError("JIRA_API_TOKEN not configured")

        # Extract group_id from Jira instance URL hostname
        # Per verified contract: group_id = Jira instance URL hostname
        self.group_id = urlparse(self.config.jira_instance_url).hostname
        if not self.group_id:
            raise ValueError(
                f"Invalid JIRA_INSTANCE_URL: {self.config.jira_instance_url}"
            )

        # Initialize clients
        self.jira_client = JiraClient(
            instance_url=self.config.jira_instance_url,
            email=self.config.jira_email,
            api_token=self.config.jira_api_token.get_secret_value(),
            delay_ms=self.config.jira_sync_delay_ms,
        )
        self.storage = MemoryStorage(self.config)
        self.embedding_client = EmbeddingClient(self.config)
        self.qdrant_client = get_qdrant_client(self.config)

        # State file path
        self.state_path = self.config.install_dir / "jira_sync_state.json"

    async def sync_project(
        self, project_key: str, mode: str = "incremental"
    ) -> SyncResult:
        """Sync a single Jira project.

        Args:
            project_key: Jira project key (e.g., "PROJ")
            mode: "full" or "incremental"

        Returns:
            SyncResult with counts and errors
        """
        start_time = datetime.now(timezone.utc)
        issues_synced = 0
        comments_synced = 0
        errors = []

        try:
            # Determine updated_since timestamp for incremental mode
            updated_since = self._get_updated_since(project_key, mode)
            logger.info(
                "sync_project_start",
                extra={
                    "project": project_key,
                    "mode": mode,
                    "updated_since": updated_since,
                },
            )

            # Fetch issues with pagination
            issues = await self.jira_client.search_issues(project_key, updated_since)
            logger.info(
                "issues_fetched", extra={"project": project_key, "count": len(issues)}
            )

            # Sync each issue (with fail-open error handling)
            for issue in issues:
                try:
                    result = await self._sync_issue(issue, project_key)
                    if result["success"]:
                        issues_synced += 1
                        comments_synced += result.get("comments_synced", 0)
                    else:
                        errors.append(
                            f"{issue['key']}: {result.get('error', 'Unknown error')}"
                        )
                except Exception as e:
                    # Fail-open: log error, continue to next issue
                    error_msg = f"{issue['key']}: {e!s}"
                    errors.append(error_msg)
                    logger.warning(
                        "issue_sync_failed",
                        extra={"issue_key": issue["key"], "error": str(e)},
                    )

            # Update sync state
            self._save_project_state(project_key, issues_synced, comments_synced)

            # Calculate duration
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            logger.info(
                "sync_project_complete",
                extra={
                    "project": project_key,
                    "issues": issues_synced,
                    "comments": comments_synced,
                    "errors": len(errors),
                    "duration_seconds": duration,
                },
            )

            return SyncResult(
                issues_synced=issues_synced,
                comments_synced=comments_synced,
                errors=errors,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(
                "sync_project_failed",
                extra={"project": project_key, "error": str(e)},
            )
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return SyncResult(errors=[str(e)], duration_seconds=duration)

    async def sync_all_projects(
        self, mode: str = "incremental"
    ) -> dict[str, SyncResult]:
        """Sync all configured Jira projects.

        Args:
            mode: "full" or "incremental"

        Returns:
            Dict mapping project_key -> SyncResult
        """
        if not self.config.jira_projects:
            logger.warning("no_projects_configured")
            return {}

        results = {}
        for project_key in self.config.jira_projects:
            result = await self.sync_project(project_key, mode)
            results[project_key] = result

        return results

    async def _sync_issue(
        self, issue: dict[str, Any], project_key: str
    ) -> dict[str, Any]:
        """Sync a single issue with fail-open error handling.

        Args:
            issue: Issue dict from Jira API
            project_key: Project key

        Returns:
            Dict with success, comments_synced, error fields
        """
        try:
            # Compose issue document
            issue_doc = compose_issue_document(issue)

            # Extract metadata
            priority = issue["fields"].get("priority")
            priority_name = priority["name"] if priority else None

            reporter = issue["fields"].get("reporter")
            reporter_name = reporter["displayName"] if reporter else "Unassigned"

            # Store issue to jira-data collection
            # MemoryStorage handles: chunking, embedding, content_hash, dedup, upsert
            await asyncio.to_thread(
                self.storage.store_memory,
                content=issue_doc,
                cwd="/__jira_sync__",  # Placeholder for project detection
                group_id=self.group_id,  # Jira instance hostname (e.g., company.atlassian.net)
                memory_type=MemoryType.JIRA_ISSUE,
                source_hook="jira_sync",
                session_id="jira_sync",
                collection=COLLECTION_JIRA_DATA,
                # Jira-specific metadata (passed as **kwargs)
                jira_project=project_key,
                jira_issue_key=issue["key"],
                jira_issue_type=issue["fields"]["issuetype"]["name"],
                jira_status=issue["fields"]["status"]["name"],
                jira_priority=priority_name,
                jira_reporter=reporter_name,
                jira_labels=issue["fields"].get("labels", []),
                jira_updated=issue["fields"]["updated"],
                jira_url=f"{self.config.jira_instance_url}/browse/{issue['key']}",
            )

            # Sync comments (delete old + insert new)
            comments_synced = await self._sync_comments(issue, project_key)

            return {"success": True, "comments_synced": comments_synced}

        except Exception as e:
            logger.warning(
                "issue_sync_failed",
                extra={"issue_key": issue.get("key", "unknown"), "error": str(e)},
            )
            return {"success": False, "error": str(e)}

    async def _sync_comments(self, issue: dict[str, Any], project_key: str) -> int:
        """Sync comments for an issue (delete-and-insert pattern).

        Args:
            issue: Issue dict from Jira API
            project_key: Project key

        Returns:
            Number of comments synced
        """
        try:
            # Step 1: Delete old comments by jira_issue_key
            deleted_count = await asyncio.to_thread(
                self._delete_issue_comments, issue["key"]
            )
            logger.debug(
                "deleted_old_comments",
                extra={"issue_key": issue["key"], "count": deleted_count},
            )

            # Step 2: Fetch fresh comments with offset pagination
            comments = await self.jira_client.get_comments(issue["key"])
            logger.debug(
                "fetched_comments",
                extra={"issue_key": issue["key"], "count": len(comments)},
            )

            # Step 3: Store new comments
            synced_count = 0
            for comment in comments:
                try:
                    result = await self._sync_comment(issue, comment, project_key)
                    if result["success"]:
                        synced_count += 1
                except Exception as e:
                    logger.warning(
                        "comment_sync_failed",
                        extra={
                            "issue_key": issue["key"],
                            "comment_id": comment.get("id", "unknown"),
                            "error": str(e),
                        },
                    )
                    # Continue to next comment (fail-open)

            return synced_count

        except Exception as e:
            logger.warning(
                "comments_sync_failed",
                extra={"issue_key": issue.get("key", "unknown"), "error": str(e)},
            )
            return 0

    async def _sync_comment(
        self, issue: dict[str, Any], comment: dict[str, Any], project_key: str
    ) -> dict[str, Any]:
        """Sync a single comment.

        Args:
            issue: Parent issue dict
            comment: Comment dict from Jira API
            project_key: Project key

        Returns:
            Dict with success field
        """
        try:
            # Compose comment document
            comment_doc = compose_comment_document(issue, comment)

            # Extract metadata
            priority = issue["fields"].get("priority")
            priority_name = priority["name"] if priority else None

            # Store comment to jira-data collection
            await asyncio.to_thread(
                self.storage.store_memory,
                content=comment_doc,
                cwd="/__jira_sync__",
                group_id=self.group_id,  # Jira instance hostname (e.g., company.atlassian.net)
                memory_type=MemoryType.JIRA_COMMENT,
                source_hook="jira_sync",
                session_id="jira_sync",
                collection=COLLECTION_JIRA_DATA,
                # Comment metadata
                jira_project=project_key,
                jira_issue_key=issue["key"],
                jira_comment_id=comment["id"],
                jira_author=comment["author"]["displayName"],
                jira_updated=comment.get("updated", comment["created"]),
                jira_url=f"{self.config.jira_instance_url}/browse/{issue['key']}?focusedCommentId={comment['id']}",
                # Parent issue context
                jira_issue_type=issue["fields"]["issuetype"]["name"],
                jira_status=issue["fields"]["status"]["name"],
                jira_priority=priority_name,
            )

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _delete_issue_comments(self, issue_key: str) -> int:
        """Delete all comments for an issue from jira-data collection.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            Number of points deleted
        """
        try:
            # Scroll to find all comment points for this issue
            scroll_result = self.qdrant_client.scroll(
                collection_name=COLLECTION_JIRA_DATA,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="group_id", match=MatchValue(value=self.group_id)
                        ),
                        FieldCondition(
                            key="jira_issue_key", match=MatchValue(value=issue_key)
                        ),
                        FieldCondition(
                            key="type",
                            match=MatchValue(value=MemoryType.JIRA_COMMENT.value),
                        ),
                    ]
                ),
                limit=1000,  # Assume max 1000 comments per issue
            )

            # Extract point IDs
            point_ids = [str(point.id) for point in scroll_result[0]]

            # Delete points
            if point_ids:
                self.qdrant_client.delete(
                    collection_name=COLLECTION_JIRA_DATA,
                    points_selector=point_ids,
                )
                logger.debug(
                    "deleted_comments",
                    extra={"issue_key": issue_key, "count": len(point_ids)},
                )
                return len(point_ids)

            return 0

        except Exception as e:
            logger.warning(
                "delete_comments_failed",
                extra={"issue_key": issue_key, "error": str(e)},
            )
            return 0

    def _get_updated_since(self, project_key: str, mode: str) -> str | None:
        """Get updated_since timestamp for sync mode.

        Args:
            project_key: Project key
            mode: "full" or "incremental"

        Returns:
            ISO 8601 timestamp string for incremental mode, or None for full mode.
        """
        if mode == "full":
            return None

        elif mode == "incremental":
            state = self._load_state()
            last_synced = (
                state.get("projects", {}).get(project_key, {}).get("last_synced")
            )

            if last_synced:
                return last_synced
            else:
                logger.info(
                    "no_previous_sync_falling_back_to_full",
                    extra={"project": project_key},
                )
                return None

        else:
            raise ValueError(f"Invalid mode: {mode} (must be 'full' or 'incremental')")

    def _load_state(self) -> dict[str, Any]:
        """Load sync state from JSON file.

        Returns:
            State dict (empty if file doesn't exist)
        """
        try:
            if self.state_path.exists():
                with open(self.state_path) as f:
                    return json.load(f)
            else:
                # No state file yet - return empty state
                return {"version": "1.0", "projects": {}}
        except Exception as e:
            logger.warning(
                "state_load_failed",
                extra={"path": str(self.state_path), "error": str(e)},
            )
            return {"version": "1.0", "projects": {}}

    def _save_project_state(
        self, project_key: str, issue_count: int, comment_count: int
    ) -> None:
        """Update state for a project after sync.

        Args:
            project_key: Project key
            issue_count: Number of issues synced
            comment_count: Number of comments synced
        """
        try:
            # Load existing state
            state = self._load_state()

            # Update project state
            if "projects" not in state:
                state["projects"] = {}

            state["projects"][project_key] = {
                "last_synced": datetime.now(timezone.utc).isoformat(),
                "last_issue_count": issue_count,
                "last_comment_count": comment_count,
            }

            # Atomic write: write to .tmp file, then rename
            tmp_path = self.state_path.with_suffix(".json.tmp")
            with open(tmp_path, "w") as f:
                json.dump(state, f, indent=2)

            # Atomic rename (POSIX guarantees atomicity)
            tmp_path.rename(self.state_path)

            logger.debug(
                "state_saved",
                extra={"project": project_key, "path": str(self.state_path)},
            )

        except Exception as e:
            logger.warning(
                "state_save_failed",
                extra={"project": project_key, "error": str(e)},
            )

    async def close(self) -> None:
        """Clean up async resources."""
        try:
            await self.jira_client.close()
            self.embedding_client.close()
            logger.debug("sync_engine_closed")
        except Exception as e:
            logger.warning("close_failed", extra={"error": str(e)})
