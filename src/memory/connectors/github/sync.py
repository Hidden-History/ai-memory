"""GitHub sync engine for ingesting issues, PRs, commits, and CI results.

Orchestrates GitHubClient (SPEC-004) to fetch data, composes embeddable
documents, applies dedup/versioning protocol (SPEC-005), and stores via
store_memory(). Mirrors JiraSyncEngine pattern.

Reference: PLAN-006 Section 3.1 (GitHub Sync Service)
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qdrant_client import models

from memory.config import COLLECTION_CODE_PATTERNS, MemoryConfig, get_config
from memory.connectors.github.client import GitHubClient, GitHubClientError
from memory.connectors.github.composer import (
    compose_ci_result,
    compose_commit,
    compose_issue,
    compose_issue_comment,
    compose_pr,
    compose_pr_diff,
    compose_pr_review,
)
from memory.connectors.github.schema import (
    DISCUSSIONS_COLLECTION,
    SOURCE_AUTHORITY_MAP,
    compute_content_hash,
)
from memory.models import MemoryType
from memory.qdrant_client import get_qdrant_client
from memory.storage import MemoryStorage

logger = logging.getLogger("ai_memory.github.sync")


@dataclass
class SyncResult:
    """Result of a GitHub sync operation.

    Tracks per-type counts, skips, errors, and timing for metrics.
    """

    issues_synced: int = 0
    comments_synced: int = 0
    prs_synced: int = 0
    reviews_synced: int = 0
    diffs_synced: int = 0
    commits_synced: int = 0
    ci_results_synced: int = 0
    items_skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    error_details: list[str] = field(default_factory=list)

    @property
    def total_synced(self) -> int:
        """Total items successfully synced."""
        return (
            self.issues_synced
            + self.comments_synced
            + self.prs_synced
            + self.reviews_synced
            + self.diffs_synced
            + self.commits_synced
            + self.ci_results_synced
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for metrics and logging."""
        return {
            "issues_synced": self.issues_synced,
            "comments_synced": self.comments_synced,
            "prs_synced": self.prs_synced,
            "reviews_synced": self.reviews_synced,
            "diffs_synced": self.diffs_synced,
            "commits_synced": self.commits_synced,
            "ci_results_synced": self.ci_results_synced,
            "items_skipped": self.items_skipped,
            "errors": self.errors,
            "total_synced": self.total_synced,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class GitHubSyncEngine:
    """Orchestrates GitHub data sync into discussions collection.

    Mirrors JiraSyncEngine pattern: per-type sync methods, fail-open
    per-item error handling, JSON state persistence, pushgateway metrics.

    Sync priority order (Section 3.1):
    PRs (+ reviews + diffs) -> Issues (+ comments) -> Commits -> CI Results

    Attributes:
        config: Memory configuration with GitHub settings
        client: GitHubClient instance for API calls
        storage: MemoryStorage for store_memory() pipeline
        state_file: Path to sync state JSON in .audit/state/
    """

    # State file prefix (within .audit/state/ per SPEC-003); full name is per-repo
    STATE_FILENAME_PREFIX = "github_sync_state_"

    def __init__(
        self,
        config: MemoryConfig | None = None,
        repo: str | None = None,
        branch: str | None = None,
    ) -> None:
        """Initialize sync engine with config validation.

        Args:
            config: Memory configuration. Uses get_config() if None.
            repo: Repository in "owner/repo" format. Overrides config.github_repo.

        Raises:
            ValueError: If GitHub sync not enabled or config incomplete
        """
        self.config = config or get_config()
        if not self.config.github_sync_enabled:
            raise ValueError("GitHub sync not enabled (GITHUB_SYNC_ENABLED=false)")

        self.repo = repo or self.config.github_repo
        if not self.repo:
            raise ValueError("No repo specified and GITHUB_REPO not configured")
        self._branch = branch or self.config.github_branch

        self.client = GitHubClient(
            token=self.config.github_token.get_secret_value(),
            repo=self.repo,
        )
        self.storage = MemoryStorage(self.config)
        self._group_id = self.repo  # owner/repo as tenant ID
        self.qdrant = get_qdrant_client(self.config)

        # SEC-2: Security scanner for GitHub content before storage
        if self.config.security_scanning_enabled:
            from memory.security_scanner import SecurityScanner

            self._scanner = SecurityScanner(
                enable_ner=self.config.security_scanning_ner_enabled
            )
        else:
            self._scanner = None

        # Resolve state file path
        # .audit/state/ created by SPEC-003 / install script
        project_root = (
            Path(self.config.project_path)
            if hasattr(self.config, "project_path")
            else Path.cwd()
        )
        self._project_root = project_root
        self._state_dir = project_root / ".audit" / "state"
        # Use __ for / to avoid collisions with - (which stays as-is)
        repo_safe = self.repo.replace("/", "__")
        self._state_file = self._state_dir / f"github_sync_state_{repo_safe}.json"

    async def sync(self, mode: str = "incremental") -> SyncResult:
        """Run full sync cycle across all document types.

        Sync priority order: PRs -> Issues -> Commits -> CI Results
        (Section 3.1: PRs have richest intent context)

        Args:
            mode: "incremental" (default) or "full"
                  incremental: only items updated since last sync
                  full: re-sync all items (ignores timestamps)

        Returns:
            SyncResult with per-type counts and timing
        """
        start = time.monotonic()
        result = SyncResult()
        batch_id = GitHubClient.generate_batch_id()
        state = self._load_state()

        logger.info(
            "Starting GitHub sync: mode=%s, repo=%s, batch=%s",
            mode,
            self.repo,
            batch_id,
        )

        async with self.client:
            # Priority order: PRs -> Issues -> Commits -> CI Results
            since = (
                None
                if mode == "full"
                else state.get("pull_requests", {}).get("last_synced")
            )
            pr_count = await self._sync_pull_requests(since, batch_id, result)
            self._save_type_state(state, "pull_requests", pr_count)

            since = (
                None if mode == "full" else state.get("issues", {}).get("last_synced")
            )
            issue_count = await self._sync_issues(since, batch_id, result)
            self._save_type_state(state, "issues", issue_count)

            since = (
                None if mode == "full" else state.get("commits", {}).get("last_synced")
            )
            commit_count = await self._sync_commits(since, batch_id, result)
            self._save_type_state(state, "commits", commit_count)

            since = (
                None
                if mode == "full"
                else state.get("ci_results", {}).get("last_synced")
            )
            ci_count = await self._sync_ci_results(since, batch_id, result)
            self._save_type_state(state, "ci_results", ci_count)

        result.duration_seconds = time.monotonic() - start
        self._save_state(state)
        self._push_metrics(result)

        logger.info(
            "GitHub sync complete: %d synced, %d skipped, %d errors in %.1fs",
            result.total_synced,
            result.items_skipped,
            result.errors,
            result.duration_seconds,
        )
        return result

    # -- Per-Type Sync Methods -----------------------------------------

    async def _sync_issues(
        self,
        since: str | None,
        batch_id: str,
        result: SyncResult,
    ) -> int:
        """Sync issues and their comments.

        Args:
            since: ISO 8601 timestamp for incremental sync (None = full)
            batch_id: Sync batch ID for versioning (BP-074)
            result: SyncResult to update counts

        Returns:
            Count of issues processed
        """
        try:
            issues = await self.client.list_issues(state="all", since=since)
        except GitHubClientError as e:
            logger.error("Failed to fetch issues: %s", e)
            result.errors += 1
            result.error_details.append(f"list_issues: {e}")
            return 0

        count = 0
        for issue in issues:
            # Skip pull requests (GitHub Issues API returns PRs too)
            if issue.get("pull_request"):
                continue

            try:
                # Sync the issue itself
                composed = compose_issue(issue)
                stored = await self._store_github_memory(
                    content=composed,
                    memory_type=MemoryType.GITHUB_ISSUE,
                    github_id=issue["number"],
                    batch_id=batch_id,
                    url=issue["html_url"],
                    timestamp=issue.get("updated_at") or issue["created_at"],
                    extra_payload={
                        "state": issue["state"],
                        "labels": [lbl["name"] for lbl in issue.get("labels", [])],
                        "milestone": (issue.get("milestone") or {}).get("title"),
                        "assignees": [a["login"] for a in issue.get("assignees", [])],
                    },
                )
                if stored:
                    result.issues_synced += 1
                else:
                    result.items_skipped += 1

                # Sync comments for this issue
                try:
                    comments = await self.client.get_issue_comments(
                        issue["number"],
                        since=since,
                    )
                    for comment in comments:
                        try:
                            composed_comment = compose_issue_comment(
                                comment, issue["number"]
                            )
                            comment_stored = await self._store_github_memory(
                                content=composed_comment,
                                memory_type=MemoryType.GITHUB_ISSUE_COMMENT,
                                github_id=issue["number"],
                                sub_id=str(comment["id"]),
                                batch_id=batch_id,
                                url=comment["html_url"],
                                timestamp=comment.get("updated_at")
                                or comment["created_at"],
                                extra_payload={
                                    "state": issue["state"],
                                    "labels": [
                                        lbl["name"] for lbl in issue.get("labels", [])
                                    ],
                                },
                            )
                            if comment_stored:
                                result.comments_synced += 1
                            else:
                                result.items_skipped += 1
                        except Exception as e:
                            logger.warning(
                                "Failed to sync comment on issue #%d: %s",
                                issue["number"],
                                e,
                            )
                            result.errors += 1
                except GitHubClientError as e:
                    logger.warning(
                        "Failed to fetch comments for issue #%d: %s", issue["number"], e
                    )

                count += 1
            except Exception as e:
                # Fail-open per-item: log and continue (Jira pattern)
                logger.error("Failed to sync issue #%d: %s", issue["number"], e)
                result.errors += 1
                result.error_details.append(f"issue #{issue['number']}: {e}")

        return count

    async def _sync_pull_requests(
        self,
        since: str | None,
        batch_id: str,
        result: SyncResult,
    ) -> int:
        """Sync pull requests, their reviews, and diff summaries.

        Args:
            since: ISO 8601 timestamp for incremental sync
            batch_id: Sync batch ID
            result: SyncResult to update counts

        Returns:
            Count of PRs processed
        """
        try:
            prs = await self.client.list_pull_requests(state="all")
        except GitHubClientError as e:
            logger.error("Failed to fetch PRs: %s", e)
            result.errors += 1
            result.error_details.append(f"list_pull_requests: {e}")
            return 0

        count = 0
        for pr in prs:
            # Filter by updated_at if incremental
            if since and pr.get("updated_at", "") < since:
                continue

            try:
                # Get files changed for composition
                try:
                    files = await self.client.get_pr_files(pr["number"])
                except GitHubClientError:
                    files = []

                # Sync the PR itself
                composed = compose_pr(pr, files)
                stored = await self._store_github_memory(
                    content=composed,
                    memory_type=MemoryType.GITHUB_PR,
                    github_id=pr["number"],
                    batch_id=batch_id,
                    url=pr["html_url"],
                    timestamp=pr.get("updated_at") or pr["created_at"],
                    extra_payload={
                        "state": "merged" if pr.get("merged_at") else pr["state"],
                        "base_branch": (pr.get("base") or {}).get("ref", "unknown"),
                        "head_branch": (pr.get("head") or {}).get("ref", "unknown"),
                        "files_changed": [f["filename"] for f in files],
                        "review_state": None,
                        "ci_status": None,
                        "labels": [lbl["name"] for lbl in pr.get("labels", [])],
                        "merged_at": pr.get("merged_at"),
                    },
                )
                if stored:
                    result.prs_synced += 1
                    # Trigger freshness flagging for merged PRs
                    if pr.get("merged_at"):
                        try:
                            files_list = [f["filename"] for f in files]
                            self._trigger_freshness_for_merged_pr(files_list)
                        except Exception as e:
                            logger.warning(
                                "freshness_trigger_failed",
                                extra={"pr": pr["number"], "error": str(e)},
                            )
                else:
                    result.items_skipped += 1

                # Sync reviews
                try:
                    reviews = await self.client.get_pr_reviews(pr["number"])
                    for review in reviews:
                        try:
                            if (
                                not review.get("body")
                                and review.get("state", "").upper() == "COMMENTED"
                            ):
                                continue  # Skip empty COMMENTED reviews (preserve APPROVED/CHANGES_REQUESTED)
                            composed_review = compose_pr_review(review, pr["number"])
                            review_stored = await self._store_github_memory(
                                content=composed_review,
                                memory_type=MemoryType.GITHUB_PR_REVIEW,
                                github_id=pr["number"],
                                sub_id=str(review["id"]),
                                batch_id=batch_id,
                                url=review.get("html_url", pr["html_url"]),
                                timestamp=review.get("submitted_at")
                                or pr["updated_at"],
                                extra_payload={
                                    "pr_number": pr["number"],
                                    "review_state": (
                                        review.get("state") or "commented"
                                    ).lower(),
                                    "reviewer": (review.get("user") or {}).get(
                                        "login", "unknown"
                                    ),
                                },
                            )
                            if review_stored:
                                result.reviews_synced += 1
                            else:
                                result.items_skipped += 1
                        except Exception as e:
                            logger.warning(
                                "Failed to sync review %s on PR #%d: %s",
                                review.get("id"),
                                pr["number"],
                                e,
                            )
                            result.errors += 1
                except GitHubClientError as e:
                    logger.warning(
                        "Failed to fetch reviews for PR #%d: %s", pr["number"], e
                    )

                # Sync diff summaries (one per changed file)
                for file_entry in files:
                    try:
                        composed_diff = compose_pr_diff(pr["number"], file_entry)
                        diff_stored = await self._store_github_memory(
                            content=composed_diff,
                            memory_type=MemoryType.GITHUB_PR_DIFF,
                            github_id=pr["number"],
                            sub_id=file_entry.get("filename", "unknown"),
                            batch_id=batch_id,
                            url=file_entry.get("blob_url", pr["html_url"]),
                            timestamp=pr.get("updated_at") or pr["created_at"],
                            extra_payload={
                                "pr_number": pr["number"],
                                "file_path": file_entry.get("filename", "unknown"),
                                "change_type": file_entry.get("status", "modified"),
                                "chunk_index": 0,
                                "total_chunks": 1,
                            },
                        )
                        if diff_stored:
                            result.diffs_synced += 1
                        else:
                            result.items_skipped += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to sync diff for %s on PR #%d: %s",
                            file_entry.get("filename"),
                            pr["number"],
                            e,
                        )
                        result.errors += 1

                count += 1
            except Exception as e:
                logger.error("Failed to sync PR #%d: %s", pr["number"], e)
                result.errors += 1
                result.error_details.append(f"PR #{pr['number']}: {e}")

        return count

    async def _sync_commits(
        self,
        since: str | None,
        batch_id: str,
        result: SyncResult,
    ) -> int:
        """Sync commits with diff stats.

        Args:
            since: ISO 8601 timestamp for incremental sync
            batch_id: Sync batch ID
            result: SyncResult to update counts

        Returns:
            Count of commits processed
        """
        try:
            commits = await self.client.list_commits(
                sha=self._branch,
                since=since,
            )
        except GitHubClientError as e:
            logger.error("Failed to fetch commits: %s", e)
            result.errors += 1
            result.error_details.append(f"list_commits: {e}")
            return 0

        count = 0
        for commit_summary in commits:
            sha = commit_summary.get("sha", "unknown")
            try:
                # Fetch full commit for diff stats
                try:
                    commit_detail = await self.client.get_commit(sha)
                except GitHubClientError:
                    commit_detail = commit_summary  # Fallback to summary

                composed = compose_commit(commit_detail)
                stored = await self._store_github_memory(
                    content=composed,
                    memory_type=MemoryType.GITHUB_COMMIT,
                    github_id=0,  # Commits don't have numbers
                    sub_id=sha,
                    batch_id=batch_id,
                    url=commit_summary.get("html_url", ""),
                    timestamp=commit_summary["commit"]["committer"]["date"],
                    extra_payload={
                        "sha": sha,
                        "branch": self._branch,
                        "files_changed": [
                            f["filename"] for f in commit_detail.get("files", [])
                        ],
                        "stats": commit_detail.get("stats", {}),
                        "author": (commit_summary.get("author") or {}).get(
                            "login", "unknown"
                        ),
                    },
                )
                if stored:
                    result.commits_synced += 1
                else:
                    result.items_skipped += 1
                count += 1
            except Exception as e:
                logger.error("Failed to sync commit %s: %s", sha[:8], e)
                result.errors += 1
                result.error_details.append(f"commit {sha[:8]}: {e}")

        return count

    async def _sync_ci_results(
        self,
        since: str | None,
        batch_id: str,
        result: SyncResult,
    ) -> int:
        """Sync GitHub Actions workflow runs.

        Args:
            since: ISO 8601 timestamp for incremental sync
            batch_id: Sync batch ID
            result: SyncResult to update counts

        Returns:
            Count of CI results processed
        """
        created_filter = f">={since[:10]}" if since else None
        try:
            runs = await self.client.list_workflow_runs(
                created=created_filter,
                status="completed",
            )
        except GitHubClientError as e:
            logger.error("Failed to fetch workflow runs: %s", e)
            result.errors += 1
            result.error_details.append(f"list_workflow_runs: {e}")
            return 0

        count = 0
        for run in runs:
            try:
                composed = compose_ci_result(run)
                stored = await self._store_github_memory(
                    content=composed,
                    memory_type=MemoryType.GITHUB_CI_RESULT,
                    github_id=run["id"],
                    batch_id=batch_id,
                    url=run.get("html_url", ""),
                    timestamp=run.get("updated_at") or run["created_at"],
                    extra_payload={
                        "workflow": run.get("name", "unknown"),
                        "run_id": run["id"],
                        "commit_sha": run.get("head_sha", ""),
                        "status": run.get("conclusion", run.get("status", "unknown")),
                        "failure_summary": None,  # Populated from logs if failure
                        "duration_seconds": 0,  # Calculated if timestamps available
                    },
                )
                if stored:
                    result.ci_results_synced += 1
                else:
                    result.items_skipped += 1
                count += 1
            except Exception as e:
                logger.error(
                    "Failed to sync CI run %s: %s", run.get("id", "unknown"), e
                )
                result.errors += 1
                result.error_details.append(f"CI run {run.get('id', 'unknown')}: {e}")

        return count

    # -- Post-Sync Freshness Feedback Loop -----------------------------

    def _trigger_freshness_for_merged_pr(
        self,
        files_changed: list[str],
    ) -> int:
        """Flag code-patterns memories as stale for files changed in a merged PR.

        Scrolls code-patterns collection for memories matching any of the
        changed file paths, and updates their freshness_status to "stale".

        Args:
            files_changed: List of file paths from the merged PR.

        Returns:
            Number of memories flagged as stale.
        """
        if not files_changed:
            return 0

        flagged = 0
        for file_path in files_changed:
            offset = None
            while True:
                points, next_offset = self.qdrant.scroll(
                    collection_name=COLLECTION_CODE_PATTERNS,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="file_path",
                                match=models.MatchValue(value=file_path),
                            ),
                            models.FieldCondition(
                                key="group_id",
                                match=models.MatchValue(value=self._group_id),
                            ),
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=["freshness_status"],
                )

                for point in points:
                    try:
                        self.qdrant.set_payload(
                            collection_name=COLLECTION_CODE_PATTERNS,
                            payload={
                                "freshness_status": "stale",
                                "freshness_checked_at": datetime.now(
                                    timezone.utc
                                ).isoformat(),
                                "freshness_trigger": "post_sync_pr_merge",
                            },
                            points=[point.id],
                        )
                        flagged += 1
                    except Exception as e:
                        logger.warning(
                            "freshness_flag_failed",
                            extra={"point_id": str(point.id), "error": str(e)},
                        )

                if next_offset is None:
                    break
                offset = next_offset

        if flagged > 0:
            logger.info(
                "post_sync_freshness_flagged",
                extra={
                    "flagged_count": flagged,
                    "files_checked": len(files_changed),
                },
            )
        return flagged

    # -- Core Storage with Dedup/Versioning ----------------------------

    async def _store_github_memory(
        self,
        content: str,
        memory_type: MemoryType,
        github_id: int,
        batch_id: str,
        url: str,
        timestamp: str,
        sub_id: str | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Store a GitHub memory with dedup pre-check and versioning.

        Implements SPEC-005 Section 6 dedup/versioning protocol:
        1. Compute content_hash on composed document
        2. Query for existing point: source=github, type=X, github_id=N, is_current=True
        3. If unchanged (hash match) -> update last_synced only -> return False
        4. If changed -> mark old is_current=False -> store new via store_memory()
        5. If new -> store via store_memory() with version=1

        Args:
            content: Composed document text (output of composer function)
            memory_type: MemoryType enum value (e.g., GITHUB_ISSUE)
            github_id: Issue/PR number or run ID
            batch_id: Sync batch grouping ID (BP-074)
            url: GitHub web URL for linking back
            timestamp: ISO 8601 UTC from GitHub API
            sub_id: Sub-resource identifier for dedup (e.g., comment ID, SHA)
            extra_payload: Type-specific payload fields

        Returns:
            True if new/updated content was stored, False if skipped (unchanged)
        """
        content_hash = compute_content_hash(content)
        type_value = memory_type.value
        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 1: Build dedup filter and query for existing current version
        must_filters = [
            models.FieldCondition(
                key="group_id",
                match=models.MatchValue(value=self._group_id),
            ),
            models.FieldCondition(
                key="source",
                match=models.MatchValue(value="github"),
            ),
            models.FieldCondition(
                key="type",
                match=models.MatchValue(value=type_value),
            ),
            models.FieldCondition(
                key="github_id",
                match=models.MatchValue(value=github_id),
            ),
            models.FieldCondition(
                key="is_current",
                match=models.MatchValue(value=True),
            ),
        ]
        if sub_id is not None:
            must_filters.append(
                models.FieldCondition(
                    key="sub_id",
                    match=models.MatchValue(value=sub_id),
                )
            )

        try:
            existing = self.qdrant.scroll(
                collection_name=DISCUSSIONS_COLLECTION,
                scroll_filter=models.Filter(must=must_filters),
                limit=1,
            )
            existing_points = existing[0] if existing else []
        except Exception as e:
            logger.warning("Dedup pre-check failed, proceeding with store: %s", e)
            existing_points = []

        # Step 2: Check content hash
        version = 1
        supersedes = None

        if existing_points:
            old_point = existing_points[0]
            old_hash = old_point.payload.get("content_hash", "")

            if old_hash == content_hash:
                # Unchanged -- update last_synced only, skip embedding
                try:
                    self.qdrant.set_payload(
                        collection_name=DISCUSSIONS_COLLECTION,
                        payload={"last_synced": now_iso},
                        points=[old_point.id],
                    )
                except Exception as e:
                    logger.warning("Failed to update last_synced: %s", e)
                return False

            # Security scan BEFORE supersession (GH-REV-001: prevents data loss
            # if scan blocks — old version stays is_current=True)
            if self._scanner is not None:
                from memory.security_scanner import ScanAction

                scan_result = self._scanner.scan(content, source_type=type_value)
                if scan_result.action == ScanAction.BLOCKED:
                    logger.warning(
                        "Security scan blocked %s #%s: %d secret finding(s)",
                        type_value,
                        github_id,
                        len(scan_result.findings),
                    )
                    return False
                content = scan_result.content  # Use masked version
                content_hash = compute_content_hash(
                    content
                )  # W4C-003: rehash post-scan

            # Changed -- mark old as superseded (only after scan passes)
            version = old_point.payload.get("version", 1) + 1
            supersedes = str(old_point.id)
            try:
                self.qdrant.set_payload(
                    collection_name=DISCUSSIONS_COLLECTION,
                    payload={"is_current": False},
                    points=[old_point.id],
                )
            except Exception as e:
                logger.warning("Failed to mark old point as superseded: %s", e)

        else:
            # No old point — still run security scan for new content
            if self._scanner is not None:
                from memory.security_scanner import ScanAction

                scan_result = self._scanner.scan(content, source_type=type_value)
                if scan_result.action == ScanAction.BLOCKED:
                    logger.warning(
                        "Security scan blocked %s #%s: %d secret finding(s)",
                        type_value,
                        github_id,
                        len(scan_result.findings),
                    )
                    return False
                content = scan_result.content  # Use masked version
                content_hash = compute_content_hash(
                    content
                )  # W4C-003: rehash post-scan

        # Step 4: Store via store_memory() pipeline
        source_authority = SOURCE_AUTHORITY_MAP.get(type_value, 0.4)

        github_payload = {
            "source": "github",
            "github_id": github_id,
            "sub_id": sub_id,
            "repo": self.repo,
            "github_updated_at": timestamp,
            "content_hash": content_hash,
            "last_synced": now_iso,
            "url": url,
            "version": version,
            "is_current": True,
            "supersedes": supersedes,
            "update_batch_id": batch_id,
            "source_authority": source_authority,
            "decay_score": 1.0,
            "freshness_status": "unverified",
        }
        if extra_payload:
            github_payload.update(extra_payload)

        try:
            store_result = await asyncio.to_thread(
                self.storage.store_memory,
                content=content,
                cwd=str(self._project_root),
                group_id=self._group_id,
                memory_type=memory_type,
                source_hook="github_sync",
                session_id=f"github_sync_{batch_id}",
                collection=DISCUSSIONS_COLLECTION,
                source_type=type_value,
                **github_payload,
            )
            if store_result and store_result.get("status") != "error":
                logger.debug(
                    "Stored %s #%d (v%d, batch=%s)",
                    type_value,
                    github_id,
                    version,
                    batch_id,
                )
                return True
            return False
        except Exception as e:
            logger.error("Failed to store %s #%d: %s", type_value, github_id, e)
            return False

    # -- State Persistence ---------------------------------------------

    def _load_state(self) -> dict[str, Any]:
        """Load sync state from JSON file.

        Returns:
            State dict with per-type last_synced timestamps.
            Empty dict if file doesn't exist.
        """
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load sync state: %s", e)
        return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        """Save sync state to JSON file.

        Uses atomic write via .tmp rename (Jira pattern).

        Args:
            state: State dict to persist
        """
        self._state_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = self._state_file.with_suffix(".json.tmp")
        try:
            tmp_file.write_text(
                json.dumps(state, indent=2, default=str),
                encoding="utf-8",
            )
            tmp_file.replace(self._state_file)
        except OSError as e:
            logger.error("Failed to save sync state: %s", e)

    @staticmethod
    def _save_type_state(state: dict, type_key: str, count: int) -> None:
        """Update state for a specific document type.

        Args:
            state: Mutable state dict
            type_key: Type key (e.g., "issues", "pull_requests")
            count: Items processed in this sync
        """
        state[type_key] = {
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "last_count": count,
        }

    # -- Metrics -------------------------------------------------------

    def _push_metrics(self, result: SyncResult) -> None:
        """Push sync metrics to pushgateway.

        Uses changes() not increase() in Grafana queries (BUG-083/084/085).
        Uses grouping_key per BP-007 convention.

        Args:
            result: SyncResult with counts and timing
        """
        try:
            from prometheus_client import CollectorRegistry, Counter, Gauge
            from prometheus_client.exposition import pushadd_to_gateway

            registry = CollectorRegistry()

            sync_total = Counter(
                "github_sync_items_total",
                "Total GitHub items synced",
                ["type", "status"],
                registry=registry,
            )
            sync_duration = Gauge(
                "github_sync_duration_seconds",
                "GitHub sync cycle duration",
                registry=registry,
            )

            # Record per-type counts
            sync_total.labels(type="issue", status="synced").inc(result.issues_synced)
            sync_total.labels(type="comment", status="synced").inc(
                result.comments_synced
            )
            sync_total.labels(type="pr", status="synced").inc(result.prs_synced)
            sync_total.labels(type="review", status="synced").inc(result.reviews_synced)
            sync_total.labels(type="diff", status="synced").inc(result.diffs_synced)
            sync_total.labels(type="commit", status="synced").inc(result.commits_synced)
            sync_total.labels(type="ci_result", status="synced").inc(
                result.ci_results_synced
            )
            sync_total.labels(type="all", status="skipped").inc(result.items_skipped)
            sync_total.labels(type="all", status="error").inc(result.errors)
            sync_duration.set(result.duration_seconds)

            pushadd_to_gateway(
                os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
                job="github_sync",
                registry=registry,
                grouping_key={"instance": self._group_id},
            )
        except Exception as e:
            logger.warning("Failed to push metrics: %s", e)
