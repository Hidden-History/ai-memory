"""Tests for GitHub sync engine (SPEC-006 Sections 3.1-3.2)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory.connectors.github.sync import GitHubSyncEngine, SyncResult


# -- SyncResult Tests -------------------------------------------------


def test_sync_result_total():
    """total_synced sums all per-type counts."""
    result = SyncResult(issues_synced=5, prs_synced=3, commits_synced=10)
    assert result.total_synced == 18


def test_sync_result_to_dict():
    """to_dict includes all fields."""
    result = SyncResult(issues_synced=2, errors=1, duration_seconds=12.345)
    d = result.to_dict()
    assert d["issues_synced"] == 2
    assert d["errors"] == 1
    assert d["duration_seconds"] == 12.35


def test_sync_result_defaults():
    """All counts default to zero."""
    result = SyncResult()
    assert result.total_synced == 0
    assert result.items_skipped == 0
    assert result.errors == 0


# -- Engine Init Tests ------------------------------------------------


def test_engine_requires_enabled():
    """Engine raises ValueError when sync not enabled."""
    config = MagicMock()
    config.github_sync_enabled = False
    with pytest.raises(ValueError, match="not enabled"):
        GitHubSyncEngine(config)


def test_engine_group_id_from_repo():
    """group_id derived from github_repo config."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_token.get_secret_value.return_value = "ghp_test"
    with patch("memory.connectors.github.sync.MemoryStorage"), \
         patch("memory.connectors.github.sync.get_qdrant_client"):
        engine = GitHubSyncEngine(config)
    assert engine._group_id == "owner/repo"


# -- Helper: create a mock engine for async tests ---------------------


def _make_engine():
    """Create a GitHubSyncEngine with mocked dependencies."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_token.get_secret_value.return_value = "ghp_test"
    config.github_branch = "main"
    config.project_path = "/tmp/test-project"
    config.get_qdrant_url.return_value = "http://localhost:6333"
    config.qdrant_api_key = None
    with patch("memory.connectors.github.sync.MemoryStorage"), \
         patch("memory.connectors.github.sync.get_qdrant_client") as mock_get_qdrant:
        mock_get_qdrant.return_value = MagicMock()
        engine = GitHubSyncEngine(config)
    engine.client = AsyncMock()
    engine.client.__aenter__ = AsyncMock(return_value=engine.client)
    engine.client.__aexit__ = AsyncMock(return_value=False)
    engine.storage = MagicMock()
    return engine


# -- Sync Orchestration Tests ----------------------------------------


@pytest.mark.asyncio
async def test_sync_calls_all_types():
    """sync() calls all per-type methods in priority order."""
    engine = _make_engine()

    # Mock all per-type methods to track call order
    call_order = []

    async def mock_sync_prs(*args, **kwargs):
        call_order.append("prs")
        return 0

    async def mock_sync_issues(*args, **kwargs):
        call_order.append("issues")
        return 0

    async def mock_sync_commits(*args, **kwargs):
        call_order.append("commits")
        return 0

    async def mock_sync_ci(*args, **kwargs):
        call_order.append("ci")
        return 0

    engine._sync_pull_requests = mock_sync_prs
    engine._sync_issues = mock_sync_issues
    engine._sync_commits = mock_sync_commits
    engine._sync_ci_results = mock_sync_ci
    engine._push_metrics = MagicMock()
    engine._load_state = MagicMock(return_value={})
    engine._save_state = MagicMock()

    result = await engine.sync()

    assert call_order == ["prs", "issues", "commits", "ci"]
    assert isinstance(result, SyncResult)


@pytest.mark.asyncio
async def test_sync_full_mode_ignores_timestamps():
    """sync(mode='full') passes since=None to all type methods."""
    engine = _make_engine()

    captured_since = []

    async def mock_sync_prs(since, batch_id, result):
        captured_since.append(("prs", since))
        return 0

    async def mock_sync_issues(since, batch_id, result):
        captured_since.append(("issues", since))
        return 0

    async def mock_sync_commits(since, batch_id, result):
        captured_since.append(("commits", since))
        return 0

    async def mock_sync_ci(since, batch_id, result):
        captured_since.append(("ci", since))
        return 0

    engine._sync_pull_requests = mock_sync_prs
    engine._sync_issues = mock_sync_issues
    engine._sync_commits = mock_sync_commits
    engine._sync_ci_results = mock_sync_ci
    engine._push_metrics = MagicMock()
    engine._load_state = MagicMock(return_value={
        "pull_requests": {"last_synced": "2026-01-01T00:00:00"},
        "issues": {"last_synced": "2026-01-01T00:00:00"},
    })
    engine._save_state = MagicMock()

    await engine.sync(mode="full")

    # All since values should be None in full mode
    for type_name, since in captured_since:
        assert since is None, f"{type_name} got since={since}, expected None"


@pytest.mark.asyncio
async def test_sync_incremental_uses_state():
    """sync(mode='incremental') loads timestamps from state file."""
    engine = _make_engine()

    captured_since = []

    async def mock_sync_prs(since, batch_id, result):
        captured_since.append(("prs", since))
        return 0

    async def mock_sync_issues(since, batch_id, result):
        captured_since.append(("issues", since))
        return 0

    async def mock_sync_commits(since, batch_id, result):
        captured_since.append(("commits", since))
        return 0

    async def mock_sync_ci(since, batch_id, result):
        captured_since.append(("ci", since))
        return 0

    engine._sync_pull_requests = mock_sync_prs
    engine._sync_issues = mock_sync_issues
    engine._sync_commits = mock_sync_commits
    engine._sync_ci_results = mock_sync_ci
    engine._push_metrics = MagicMock()
    engine._load_state = MagicMock(return_value={
        "pull_requests": {"last_synced": "2026-01-01T00:00:00"},
        "issues": {"last_synced": "2026-01-02T00:00:00"},
    })
    engine._save_state = MagicMock()

    await engine.sync(mode="incremental")

    since_dict = dict(captured_since)
    assert since_dict["prs"] == "2026-01-01T00:00:00"
    assert since_dict["issues"] == "2026-01-02T00:00:00"
    assert since_dict["commits"] is None  # No state for commits
    assert since_dict["ci"] is None  # No state for ci


@pytest.mark.asyncio
async def test_sync_saves_state_after_completion():
    """State file updated after sync completes."""
    engine = _make_engine()

    async def noop(*args, **kwargs):
        return 0

    engine._sync_pull_requests = noop
    engine._sync_issues = noop
    engine._sync_commits = noop
    engine._sync_ci_results = noop
    engine._push_metrics = MagicMock()
    engine._load_state = MagicMock(return_value={})
    engine._save_state = MagicMock()

    await engine.sync()

    engine._save_state.assert_called_once()
    saved_state = engine._save_state.call_args[0][0]
    assert "pull_requests" in saved_state
    assert "issues" in saved_state
    assert "commits" in saved_state
    assert "ci_results" in saved_state


# -- Issue Sync Tests -------------------------------------------------


@pytest.mark.asyncio
async def test_sync_issues_skips_pull_requests():
    """Issues with pull_request field are skipped."""
    engine = _make_engine()
    engine.client.list_issues = AsyncMock(return_value=[
        {"number": 1, "title": "Real issue", "body": "text", "state": "open",
         "html_url": "https://github.com/test", "created_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:00Z", "labels": [], "assignees": [], "milestone": None},
        {"number": 2, "title": "Actually a PR", "body": "text", "state": "open",
         "html_url": "https://github.com/test", "created_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:00Z", "labels": [], "assignees": [], "milestone": None,
         "pull_request": {"url": "https://api.github.com/repos/test/pulls/2"}},
    ])
    engine.client.get_issue_comments = AsyncMock(return_value=[])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    count = await engine._sync_issues(None, "batch-1", result)

    assert count == 1  # Only the real issue
    assert result.issues_synced == 1


@pytest.mark.asyncio
async def test_sync_issues_includes_comments():
    """Issue sync fetches and stores comments."""
    engine = _make_engine()
    engine.client.list_issues = AsyncMock(return_value=[
        {"number": 1, "title": "Issue", "body": "text", "state": "open",
         "html_url": "https://github.com/test", "created_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:00Z", "labels": [], "assignees": [], "milestone": None},
    ])
    engine.client.get_issue_comments = AsyncMock(return_value=[
        {"id": 101, "body": "Comment 1", "user": {"login": "user1"},
         "html_url": "https://github.com/test#1", "created_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:00Z"},
        {"id": 102, "body": "Comment 2", "user": {"login": "user2"},
         "html_url": "https://github.com/test#2", "created_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:00Z"},
    ])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_issues(None, "batch-1", result)

    assert result.issues_synced == 1
    assert result.comments_synced == 2


@pytest.mark.asyncio
async def test_sync_issues_fail_open():
    """Individual issue failure doesn't stop sync."""
    engine = _make_engine()
    engine.client.list_issues = AsyncMock(return_value=[
        {"number": 1, "title": "Good", "body": "text", "state": "open",
         "html_url": "https://github.com/test", "created_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:00Z", "labels": [], "assignees": [], "milestone": None},
        {"number": 2, "title": "Bad", "body": "text", "state": "open",
         "html_url": "https://github.com/test", "created_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:00Z", "labels": [], "assignees": [], "milestone": None},
    ])
    engine.client.get_issue_comments = AsyncMock(return_value=[])

    call_count = 0

    async def mock_store(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return True
        raise RuntimeError("Storage failed")

    engine._store_github_memory = mock_store

    result = SyncResult()
    count = await engine._sync_issues(None, "batch-1", result)

    assert result.issues_synced == 1
    assert result.errors == 1
    assert count == 1  # First succeeded, second failed before count increment


# -- PR Sync Tests ----------------------------------------------------


@pytest.mark.asyncio
async def test_sync_prs_fetches_files():
    """PR sync fetches changed files for composition."""
    engine = _make_engine()
    engine.client.list_pull_requests = AsyncMock(return_value=[
        {"number": 10, "title": "Test PR", "body": "desc", "state": "open",
         "merged_at": None, "html_url": "https://github.com/test/pull/10",
         "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
         "labels": [], "base": {"ref": "main"}, "head": {"ref": "feat"}},
    ])
    engine.client.get_pr_files = AsyncMock(return_value=[
        {"filename": "file.py", "status": "modified", "additions": 5, "deletions": 2,
         "blob_url": "https://github.com/blob/1"},
    ])
    engine.client.get_pr_reviews = AsyncMock(return_value=[])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_pull_requests(None, "batch-1", result)

    engine.client.get_pr_files.assert_awaited_once_with(10)
    assert result.prs_synced == 1


@pytest.mark.asyncio
async def test_sync_prs_includes_reviews():
    """PR sync fetches and stores reviews."""
    engine = _make_engine()
    engine.client.list_pull_requests = AsyncMock(return_value=[
        {"number": 10, "title": "PR", "body": "", "state": "open",
         "merged_at": None, "html_url": "https://github.com/test/pull/10",
         "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
         "labels": [], "base": {"ref": "main"}, "head": {"ref": "feat"}},
    ])
    engine.client.get_pr_files = AsyncMock(return_value=[])
    engine.client.get_pr_reviews = AsyncMock(return_value=[
        {"id": 201, "body": "LGTM", "state": "APPROVED", "user": {"login": "reviewer"},
         "html_url": "https://github.com/review/1", "submitted_at": "2026-01-01T00:00:00Z"},
    ])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_pull_requests(None, "batch-1", result)

    assert result.prs_synced == 1
    assert result.reviews_synced == 1


@pytest.mark.asyncio
async def test_sync_prs_skips_empty_commented_reviews():
    """Only COMMENTED reviews without body are skipped; APPROVED preserved."""
    engine = _make_engine()
    engine.client.list_pull_requests = AsyncMock(return_value=[
        {"number": 10, "title": "PR", "body": "", "state": "open",
         "merged_at": None, "html_url": "https://github.com/test/pull/10",
         "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
         "labels": [], "base": {"ref": "main"}, "head": {"ref": "feat"}},
    ])
    engine.client.get_pr_files = AsyncMock(return_value=[])
    engine.client.get_pr_reviews = AsyncMock(return_value=[
        {"id": 1, "body": "", "state": "APPROVED", "user": {"login": "reviewer"},
         "html_url": "https://github.com/review/1", "submitted_at": "2026-01-01T00:00:00Z"},
        {"id": 2, "body": None, "state": "COMMENTED", "user": {"login": "other"}},
    ])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_pull_requests(None, "batch-1", result)

    # APPROVED with empty body is preserved, COMMENTED with no body is skipped
    assert result.reviews_synced == 1


@pytest.mark.asyncio
async def test_sync_prs_includes_diffs():
    """PR sync stores diff summary per changed file."""
    engine = _make_engine()
    engine.client.list_pull_requests = AsyncMock(return_value=[
        {"number": 10, "title": "PR", "body": "", "state": "open",
         "merged_at": None, "html_url": "https://github.com/test/pull/10",
         "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
         "labels": [], "base": {"ref": "main"}, "head": {"ref": "feat"}},
    ])
    engine.client.get_pr_files = AsyncMock(return_value=[
        {"filename": "a.py", "status": "modified", "additions": 1, "deletions": 0,
         "blob_url": "https://github.com/blob/a"},
        {"filename": "b.py", "status": "added", "additions": 10, "deletions": 0,
         "blob_url": "https://github.com/blob/b"},
    ])
    engine.client.get_pr_reviews = AsyncMock(return_value=[])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_pull_requests(None, "batch-1", result)

    assert result.diffs_synced == 2


@pytest.mark.asyncio
async def test_sync_prs_incremental_filter():
    """Incremental mode filters PRs by updated_at."""
    engine = _make_engine()
    engine.client.list_pull_requests = AsyncMock(return_value=[
        {"number": 1, "title": "Old PR", "body": "", "state": "closed",
         "merged_at": None, "html_url": "https://github.com/test/pull/1",
         "created_at": "2025-01-01T00:00:00Z", "updated_at": "2025-06-01T00:00:00Z",
         "labels": [], "base": {"ref": "main"}, "head": {"ref": "old"}},
        {"number": 2, "title": "New PR", "body": "", "state": "open",
         "merged_at": None, "html_url": "https://github.com/test/pull/2",
         "created_at": "2026-02-01T00:00:00Z", "updated_at": "2026-02-14T00:00:00Z",
         "labels": [], "base": {"ref": "main"}, "head": {"ref": "new"}},
    ])
    engine.client.get_pr_files = AsyncMock(return_value=[])
    engine.client.get_pr_reviews = AsyncMock(return_value=[])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    # Since is after old PR's updated_at but before new PR's
    count = await engine._sync_pull_requests("2026-01-01T00:00:00Z", "batch-1", result)

    assert count == 1  # Only the new PR
    assert result.prs_synced == 1


# -- Commit Sync Tests ------------------------------------------------


@pytest.mark.asyncio
async def test_sync_commits_uses_branch():
    """Commits fetched from configured branch."""
    engine = _make_engine()
    engine.client.list_commits = AsyncMock(return_value=[])

    result = SyncResult()
    await engine._sync_commits(None, "batch-1", result)

    engine.client.list_commits.assert_awaited_once_with(sha="main", since=None)


@pytest.mark.asyncio
async def test_sync_commits_fetches_details():
    """Commit detail fetched for diff stats."""
    engine = _make_engine()
    engine.client.list_commits = AsyncMock(return_value=[
        {"sha": "abc123456789", "html_url": "https://github.com/commit/abc",
         "commit": {"message": "test", "author": {"name": "Dev"},
                    "committer": {"date": "2026-01-01T00:00:00Z"}},
         "author": {"login": "dev"}},
    ])
    engine.client.get_commit = AsyncMock(return_value={
        "sha": "abc123456789",
        "commit": {"message": "test", "author": {"name": "Dev"},
                   "committer": {"date": "2026-01-01T00:00:00Z"}},
        "author": {"login": "dev"},
        "files": [{"filename": "test.py"}],
        "stats": {"total": 5, "additions": 3, "deletions": 2},
    })
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_commits(None, "batch-1", result)

    engine.client.get_commit.assert_awaited_once_with("abc123456789")
    assert result.commits_synced == 1


@pytest.mark.asyncio
async def test_sync_commits_fallback_to_summary():
    """Falls back to summary when detail fetch fails."""
    from memory.connectors.github.client import GitHubClientError

    engine = _make_engine()
    engine.client.list_commits = AsyncMock(return_value=[
        {"sha": "abc123456789", "html_url": "https://github.com/commit/abc",
         "commit": {"message": "test", "author": {"name": "Dev"},
                    "committer": {"date": "2026-01-01T00:00:00Z"}},
         "author": {"login": "dev"}},
    ])
    engine.client.get_commit = AsyncMock(side_effect=GitHubClientError("404"))
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_commits(None, "batch-1", result)

    assert result.commits_synced == 1  # Still stores using summary


# -- CI Results Tests -------------------------------------------------


@pytest.mark.asyncio
async def test_sync_ci_completed_only():
    """Only completed workflow runs are synced."""
    engine = _make_engine()
    engine.client.list_workflow_runs = AsyncMock(return_value=[
        {"id": 100, "name": "tests", "conclusion": "success",
         "head_sha": "abc123", "head_branch": "main",
         "html_url": "https://github.com/actions/100",
         "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"},
    ])
    engine._store_github_memory = AsyncMock(return_value=True)

    result = SyncResult()
    await engine._sync_ci_results(None, "batch-1", result)

    # Verify status="completed" was passed
    engine.client.list_workflow_runs.assert_awaited_once_with(
        created=None, status="completed",
    )
    assert result.ci_results_synced == 1


@pytest.mark.asyncio
async def test_sync_ci_date_filter():
    """Incremental mode filters by created date."""
    engine = _make_engine()
    engine.client.list_workflow_runs = AsyncMock(return_value=[])

    result = SyncResult()
    await engine._sync_ci_results("2026-02-10T12:00:00Z", "batch-1", result)

    engine.client.list_workflow_runs.assert_awaited_once_with(
        created=">=2026-02-10", status="completed",
    )


# -- Dedup/Versioning Tests -------------------------------------------


@pytest.mark.asyncio
async def test_dedup_skips_unchanged():
    """Unchanged content (matching hash) updates last_synced only."""
    engine = _make_engine()

    from memory.connectors.github.schema import compute_content_hash

    content = "Issue #1: Test\n\nState: open"
    content_hash = compute_content_hash(content)

    mock_point = MagicMock()
    mock_point.id = "point-uuid-1"
    mock_point.payload = {"content_hash": content_hash, "version": 1}

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([mock_point], None)
    engine.qdrant = mock_qdrant

    from memory.models import MemoryType
    stored = await engine._store_github_memory(
        content=content,
        memory_type=MemoryType.GITHUB_ISSUE,
        github_id=1,
        batch_id="batch-1",
        url="https://github.com/test/1",
        timestamp="2026-01-01T00:00:00Z",
    )

    assert stored is False
    mock_qdrant.set_payload.assert_called_once()
    call_payload = mock_qdrant.set_payload.call_args[1]["payload"]
    assert "last_synced" in call_payload


@pytest.mark.asyncio
async def test_dedup_supersedes_changed():
    """Changed content marks old as is_current=False, stores new version."""
    engine = _make_engine()

    mock_point = MagicMock()
    mock_point.id = "point-uuid-1"
    mock_point.payload = {"content_hash": "old-hash", "version": 2}

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([mock_point], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType
    stored = await engine._store_github_memory(
        content="Changed content",
        memory_type=MemoryType.GITHUB_ISSUE,
        github_id=1,
        batch_id="batch-1",
        url="https://github.com/test/1",
        timestamp="2026-01-01T00:00:00Z",
    )

    assert stored is True
    # Old point marked as not current
    set_payload_calls = mock_qdrant.set_payload.call_args_list
    assert len(set_payload_calls) == 1
    assert set_payload_calls[0][1]["payload"] == {"is_current": False}

    # store_memory called with version=3
    store_call = engine.storage.store_memory.call_args
    assert store_call[1]["version"] == 3
    assert store_call[1]["supersedes"] == "point-uuid-1"


@pytest.mark.asyncio
async def test_dedup_new_item_version_1():
    """New item stored with version=1."""
    engine = _make_engine()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType
    stored = await engine._store_github_memory(
        content="Brand new content",
        memory_type=MemoryType.GITHUB_ISSUE,
        github_id=99,
        batch_id="batch-1",
        url="https://github.com/test/99",
        timestamp="2026-01-01T00:00:00Z",
    )

    assert stored is True
    store_call = engine.storage.store_memory.call_args
    assert store_call[1]["version"] == 1
    assert store_call[1]["supersedes"] is None


@pytest.mark.asyncio
async def test_dedup_version_increments():
    """Version increments on each update."""
    engine = _make_engine()

    mock_point = MagicMock()
    mock_point.id = "point-uuid-1"
    mock_point.payload = {"content_hash": "old-hash", "version": 5}

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([mock_point], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType
    await engine._store_github_memory(
        content="Updated again",
        memory_type=MemoryType.GITHUB_ISSUE,
        github_id=1,
        batch_id="batch-1",
        url="https://github.com/test/1",
        timestamp="2026-01-01T00:00:00Z",
    )

    store_call = engine.storage.store_memory.call_args
    assert store_call[1]["version"] == 6


@pytest.mark.asyncio
async def test_dedup_batch_id_consistent():
    """All points in a sync share the same batch_id."""
    engine = _make_engine()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType
    batch = "batch-test-42"

    await engine._store_github_memory(
        content="Content A", memory_type=MemoryType.GITHUB_ISSUE,
        github_id=1, batch_id=batch, url="", timestamp="2026-01-01T00:00:00Z",
    )
    await engine._store_github_memory(
        content="Content B", memory_type=MemoryType.GITHUB_PR,
        github_id=2, batch_id=batch, url="", timestamp="2026-01-01T00:00:00Z",
    )

    calls = engine.storage.store_memory.call_args_list
    for call in calls:
        assert call[1]["update_batch_id"] == batch


@pytest.mark.asyncio
async def test_dedup_pre_check_failure_proceeds():
    """Dedup pre-check failure still stores (fail-open)."""
    engine = _make_engine()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.side_effect = Exception("Qdrant unavailable")
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType
    stored = await engine._store_github_memory(
        content="Content despite failure",
        memory_type=MemoryType.GITHUB_ISSUE,
        github_id=1,
        batch_id="batch-1",
        url="https://github.com/test/1",
        timestamp="2026-01-01T00:00:00Z",
    )

    assert stored is True
    engine.storage.store_memory.assert_called_once()


# -- State Persistence Tests ------------------------------------------


def test_load_state_missing_file():
    """Missing state file returns empty dict."""
    engine = _make_engine()
    engine._state_file = Path("/nonexistent/path/state.json")

    state = engine._load_state()
    assert state == {}


def test_load_state_corrupt_file(tmp_path):
    """Corrupt JSON returns empty dict."""
    engine = _make_engine()
    state_file = tmp_path / "state.json"
    state_file.write_text("not valid json{{{", encoding="utf-8")
    engine._state_file = state_file

    state = engine._load_state()
    assert state == {}


def test_save_state_atomic_write(tmp_path):
    """State saved via .tmp rename for atomicity."""
    engine = _make_engine()
    engine._state_dir = tmp_path
    engine._state_file = tmp_path / "github_sync_state.json"

    test_state = {"issues": {"last_synced": "2026-01-01T00:00:00"}}
    engine._save_state(test_state)

    # Verify file exists and content is correct
    assert engine._state_file.exists()
    loaded = json.loads(engine._state_file.read_text(encoding="utf-8"))
    assert loaded == test_state

    # Verify tmp file was cleaned up
    tmp_file = engine._state_file.with_suffix(".json.tmp")
    assert not tmp_file.exists()


def test_save_type_state():
    """Type state includes last_synced and count."""
    state = {}
    GitHubSyncEngine._save_type_state(state, "issues", 42)

    assert "issues" in state
    assert state["issues"]["last_count"] == 42
    assert "last_synced" in state["issues"]


# -- Metrics Tests ----------------------------------------------------


def test_push_metrics_success():
    """Metrics pushed to pushgateway with grouping_key."""
    engine = _make_engine()
    result = SyncResult(issues_synced=5, prs_synced=3, duration_seconds=10.0)

    mock_registry = MagicMock()
    mock_counter = MagicMock()
    mock_gauge = MagicMock()
    mock_pushadd = MagicMock()

    with patch("prometheus_client.CollectorRegistry", return_value=mock_registry), \
         patch("prometheus_client.Counter", return_value=mock_counter), \
         patch("prometheus_client.Gauge", return_value=mock_gauge), \
         patch("prometheus_client.exposition.pushadd_to_gateway", mock_pushadd):
        engine._push_metrics(result)

    mock_pushadd.assert_called_once()
    call_kwargs = mock_pushadd.call_args
    # grouping_key uses _group_id (which equals github_repo)
    assert call_kwargs[1]["grouping_key"] == {"instance": "owner/repo"}


def test_push_metrics_failure_logged():
    """Metrics push failure logged but doesn't raise."""
    engine = _make_engine()
    result = SyncResult()

    with patch.dict("sys.modules", {
        "prometheus_client": MagicMock(side_effect=ImportError("no module")),
    }):
        # Should not raise
        engine._push_metrics(result)


# -- FIX-10: New Tests -----------------------------------------------


@pytest.mark.asyncio
async def test_store_memory_receives_source_hook_and_session_id():
    """store_memory receives source_hook and session_id params (FIX-1)."""
    engine = _make_engine()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType
    await engine._store_github_memory(
        content="Test content",
        memory_type=MemoryType.GITHUB_ISSUE,
        github_id=1,
        batch_id="batch-42",
        url="https://github.com/test/1",
        timestamp="2026-01-01T00:00:00Z",
    )

    store_call = engine.storage.store_memory.call_args
    assert store_call[1]["source_hook"] == "github_sync"
    assert store_call[1]["session_id"] == "github_sync_batch-42"
    assert store_call[1]["group_id"] == "owner/repo"
    assert store_call[1]["cwd"] == "/tmp/test-project"


@pytest.mark.asyncio
async def test_qdrant_not_instantiated_per_item():
    """QdrantClient is shared, not created per _store_github_memory call (FIX-3)."""
    engine = _make_engine()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType
    # Call store_github_memory multiple times
    for i in range(5):
        await engine._store_github_memory(
            content=f"Content {i}",
            memory_type=MemoryType.GITHUB_ISSUE,
            github_id=i,
            batch_id="batch-1",
            url="",
            timestamp="2026-01-01T00:00:00Z",
        )

    # All 5 calls should use the same qdrant instance (5 scroll calls)
    assert mock_qdrant.scroll.call_count == 5
    # The mock_qdrant should be the same object used for all calls
    assert engine.qdrant is mock_qdrant


@pytest.mark.asyncio
async def test_dedup_with_sub_id_for_comments():
    """Two comments on same issue use different sub_ids for dedup (FIX-2)."""
    engine = _make_engine()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType

    # Store two comments on the same issue with different sub_ids
    await engine._store_github_memory(
        content="Comment 1 on issue",
        memory_type=MemoryType.GITHUB_ISSUE_COMMENT,
        github_id=42,
        sub_id="101",
        batch_id="batch-1",
        url="",
        timestamp="2026-01-01T00:00:00Z",
    )
    await engine._store_github_memory(
        content="Comment 2 on issue",
        memory_type=MemoryType.GITHUB_ISSUE_COMMENT,
        github_id=42,
        sub_id="102",
        batch_id="batch-1",
        url="",
        timestamp="2026-01-01T00:00:00Z",
    )

    # Both stored (not deduped against each other)
    assert engine.storage.store_memory.call_count == 2

    # Verify sub_id is included in payload
    for call in engine.storage.store_memory.call_args_list:
        assert "sub_id" in call[1]

    # Verify dedup scroll filter includes sub_id
    from qdrant_client import models as qmodels
    for scroll_call in mock_qdrant.scroll.call_args_list:
        scroll_filter = scroll_call[1]["scroll_filter"]
        sub_id_filters = [
            f for f in scroll_filter.must
            if hasattr(f, "key") and f.key == "sub_id"
        ]
        assert len(sub_id_filters) == 1, "sub_id filter must be in dedup query"


@pytest.mark.asyncio
async def test_dedup_commits_use_sha_as_sub_id():
    """Commits use SHA as sub_id for dedup since github_id=0 for all (FIX-2)."""
    engine = _make_engine()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([], None)
    engine.qdrant = mock_qdrant

    engine.storage.store_memory = MagicMock(return_value={"status": "stored"})

    from memory.models import MemoryType

    await engine._store_github_memory(
        content="Commit A",
        memory_type=MemoryType.GITHUB_COMMIT,
        github_id=0,
        sub_id="abc123",
        batch_id="batch-1",
        url="",
        timestamp="2026-01-01T00:00:00Z",
    )
    await engine._store_github_memory(
        content="Commit B",
        memory_type=MemoryType.GITHUB_COMMIT,
        github_id=0,
        sub_id="def456",
        batch_id="batch-1",
        url="",
        timestamp="2026-01-01T00:00:00Z",
    )

    # Both should be stored (different sub_ids despite same github_id=0)
    assert engine.storage.store_memory.call_count == 2

    # Verify sub_ids differ in the stored payloads
    sub_ids = [call[1]["sub_id"] for call in engine.storage.store_memory.call_args_list]
    assert sub_ids == ["abc123", "def456"]
