"""WP-8 tests: Freshness Injection Gate — collection targeting fixes (PLAN-015 §WP-8).

Verifies:
1. build_ground_truth_map() queries COLLECTION_GITHUB (not COLLECTION_DISCUSSIONS)
2. build_ground_truth_map() does NOT include source='github' filter
3. count_commits_for_file() queries COLLECTION_GITHUB (not COLLECTION_DISCUSSIONS)
4. count_commits_for_file() does NOT include source='github' filter
5. sync() runs freshness scan after sync cycle
6. sync() does NOT propagate exceptions from run_freshness_scan()
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Group 1: build_ground_truth_map() queries COLLECTION_GITHUB
# ---------------------------------------------------------------------------


def test_build_ground_truth_map_uses_github_collection():
    """build_ground_truth_map must query COLLECTION_GITHUB, not COLLECTION_DISCUSSIONS."""
    from memory.config import COLLECTION_GITHUB, get_config
    from memory.freshness import build_ground_truth_map

    mock_client = MagicMock()
    # Return empty on first call (no more pages)
    mock_client.scroll.return_value = ([], None)

    config = get_config()
    build_ground_truth_map(mock_client, config)

    # Verify scroll was called with COLLECTION_GITHUB
    assert mock_client.scroll.called
    call_kwargs = mock_client.scroll.call_args
    assert call_kwargs.kwargs.get("collection_name") == COLLECTION_GITHUB


def test_build_ground_truth_map_no_source_filter():
    """build_ground_truth_map must NOT include source='github' filter (redundant for github collection)."""
    from memory.config import get_config
    from memory.freshness import build_ground_truth_map

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    config = get_config()
    build_ground_truth_map(mock_client, config)

    # Inspect the scroll_filter passed to scroll()
    call_kwargs = mock_client.scroll.call_args
    scroll_filter = call_kwargs.kwargs.get("scroll_filter")
    if scroll_filter and scroll_filter.must:
        for condition in scroll_filter.must:
            # No source="github" condition should be present
            if hasattr(condition, "key") and condition.key == "source":
                pytest.fail(
                    "source='github' filter found — should be removed for github collection"
                )


def test_build_ground_truth_map_not_discussions():
    """build_ground_truth_map must NOT query COLLECTION_DISCUSSIONS."""
    from memory.config import COLLECTION_DISCUSSIONS, get_config
    from memory.freshness import build_ground_truth_map

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    config = get_config()
    build_ground_truth_map(mock_client, config)

    call_kwargs = mock_client.scroll.call_args
    collection_name = call_kwargs.kwargs.get("collection_name")
    assert collection_name != COLLECTION_DISCUSSIONS, (
        f"Expected COLLECTION_GITHUB but got COLLECTION_DISCUSSIONS: {collection_name}"
    )


def test_build_ground_truth_map_retains_type_filter():
    """build_ground_truth_map must still filter by type='github_code_blob'."""
    from memory.config import get_config
    from memory.freshness import build_ground_truth_map

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    config = get_config()
    build_ground_truth_map(mock_client, config)

    call_kwargs = mock_client.scroll.call_args
    scroll_filter = call_kwargs.kwargs.get("scroll_filter")

    assert scroll_filter is not None, "scroll_filter must be provided"
    assert scroll_filter.must is not None, "scroll_filter.must must be provided"

    type_condition_found = False
    for condition in scroll_filter.must:
        if (
            hasattr(condition, "key")
            and condition.key == "type"
            and hasattr(condition, "match")
            and hasattr(condition.match, "value")
            and condition.match.value == "github_code_blob"
        ):
            type_condition_found = True

    assert type_condition_found, (
        "type='github_code_blob' filter must be present in scroll_filter"
    )


# ---------------------------------------------------------------------------
# Group 2: count_commits_for_file() queries COLLECTION_GITHUB
# ---------------------------------------------------------------------------


def test_count_commits_for_file_uses_github_collection():
    """count_commits_for_file must query COLLECTION_GITHUB, not COLLECTION_DISCUSSIONS."""
    from memory.config import COLLECTION_GITHUB
    from memory.freshness import count_commits_for_file

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    result = count_commits_for_file(
        mock_client, "src/memory/search.py", "2026-01-01T00:00:00+00:00"
    )

    assert result == 0
    assert mock_client.scroll.called
    call_kwargs = mock_client.scroll.call_args
    assert call_kwargs.kwargs.get("collection_name") == COLLECTION_GITHUB


def test_count_commits_for_file_no_source_filter():
    """count_commits_for_file must NOT include source='github' filter."""
    from memory.freshness import count_commits_for_file

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    count_commits_for_file(mock_client, "some/file.py", "2026-01-01T00:00:00+00:00")

    call_kwargs = mock_client.scroll.call_args
    scroll_filter = call_kwargs.kwargs.get("scroll_filter")
    if scroll_filter and scroll_filter.must:
        for condition in scroll_filter.must:
            if hasattr(condition, "key") and condition.key == "source":
                pytest.fail(
                    "source filter should not be present for github collection queries"
                )


def test_count_commits_for_file_not_discussions():
    """count_commits_for_file must NOT query COLLECTION_DISCUSSIONS."""
    from memory.config import COLLECTION_DISCUSSIONS
    from memory.freshness import count_commits_for_file

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    count_commits_for_file(mock_client, "some/file.py", "2026-01-01T00:00:00+00:00")

    call_kwargs = mock_client.scroll.call_args
    collection_name = call_kwargs.kwargs.get("collection_name")
    assert collection_name != COLLECTION_DISCUSSIONS, (
        f"Expected COLLECTION_GITHUB but got COLLECTION_DISCUSSIONS: {collection_name}"
    )


def test_count_commits_for_file_retains_type_filter():
    """count_commits_for_file must still filter by type='github_commit'."""
    from memory.freshness import count_commits_for_file

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)

    count_commits_for_file(mock_client, "some/file.py", "2026-01-01T00:00:00+00:00")

    call_kwargs = mock_client.scroll.call_args
    scroll_filter = call_kwargs.kwargs.get("scroll_filter")

    assert scroll_filter is not None, "scroll_filter must be provided"
    assert scroll_filter.must is not None, "scroll_filter.must must be provided"

    type_condition_found = False
    for condition in scroll_filter.must:
        if (
            hasattr(condition, "key")
            and condition.key == "type"
            and hasattr(condition, "match")
            and hasattr(condition.match, "value")
            and condition.match.value == "github_commit"
        ):
            type_condition_found = True

    assert type_condition_found, (
        "type='github_commit' filter must be present in scroll_filter"
    )


def test_count_commits_for_file_invalid_since_returns_zero():
    """count_commits_for_file returns 0 for invalid ISO 8601 timestamp (no scroll)."""
    from memory.freshness import count_commits_for_file

    mock_client = MagicMock()

    result = count_commits_for_file(mock_client, "some/file.py", "not-a-timestamp")

    assert result == 0
    # Should return early without scrolling when since is invalid
    assert not mock_client.scroll.called


# ---------------------------------------------------------------------------
# Group 3: post-sync freshness scan in sync.py
# ---------------------------------------------------------------------------


def _make_sync_engine():
    """Create GitHubSyncEngine with all external dependencies mocked."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_token.get_secret_value.return_value = "ghp_test"
    config.github_branch = "main"
    config.project_path = "/tmp/test-project"
    config.security_scanning_enabled = False

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client") as mock_get_qdrant,
    ):
        mock_get_qdrant.return_value = MagicMock()
        from memory.connectors.github.sync import GitHubSyncEngine

        engine = GitHubSyncEngine(config)

    # Wire up async context manager for self.client
    engine.client = AsyncMock()
    engine.client.__aenter__ = AsyncMock(return_value=engine.client)
    engine.client.__aexit__ = AsyncMock(return_value=False)
    engine.storage = MagicMock()

    # Stub all per-type sync methods to return 0 (no real network calls)
    async def _noop_sync(*args, **kwargs):
        return 0

    engine._sync_pull_requests = _noop_sync
    engine._sync_issues = _noop_sync
    engine._sync_commits = _noop_sync
    engine._sync_ci_results = _noop_sync
    engine._push_metrics = MagicMock()
    engine._load_state = MagicMock(return_value={})
    engine._save_state = MagicMock()

    return engine


@pytest.mark.asyncio
async def test_post_sync_freshness_scan_called():
    """sync() must call run_freshness_scan() after sync cycle completes.

    The import inside sync() is lazy (`from memory.freshness import run_freshness_scan`),
    so we inject a fake freshness module into sys.modules before calling sync().
    This intercepts the lazy import and lets us track the call.
    """
    import sys
    import types

    engine = _make_sync_engine()

    mock_report = MagicMock()
    mock_report.total_checked = 10
    mock_report.fresh_count = 7
    mock_report.aging_count = 1
    mock_report.stale_count = 1
    mock_report.expired_count = 0
    mock_report.unknown_count = 1

    scan_call_count = {"n": 0}

    def _tracking_scan(*args, **kwargs):
        scan_call_count["n"] += 1
        return mock_report

    fake_freshness = types.ModuleType("memory.freshness")
    fake_freshness.run_freshness_scan = _tracking_scan

    original = sys.modules.get("memory.freshness")
    sys.modules["memory.freshness"] = fake_freshness

    try:
        await engine.sync()
    finally:
        if original is not None:
            sys.modules["memory.freshness"] = original
        else:
            sys.modules.pop("memory.freshness", None)

    assert scan_call_count["n"] == 1, (
        f"run_freshness_scan should be called exactly once after sync, "
        f"but was called {scan_call_count['n']} time(s)"
    )
    assert engine._save_state.called, "sync() should have saved state before freshness scan"


@pytest.mark.asyncio
async def test_post_sync_freshness_scan_graceful_degradation():
    """If run_freshness_scan raises, sync() must complete normally (no propagation)."""
    engine = _make_sync_engine()

    # We need to make the lazy import inside sync() pick up our mock.
    # Inject the mock into sys.modules so the lazy `from memory.freshness import ...`
    # inside sync() returns our raising version.
    import sys
    import types

    # Build a fake freshness module that raises on run_freshness_scan
    fake_freshness = types.ModuleType("memory.freshness")

    def _raising_scan(*args, **kwargs):
        raise RuntimeError("Simulated freshness scan failure")

    fake_freshness.run_freshness_scan = _raising_scan

    original = sys.modules.get("memory.freshness")
    sys.modules["memory.freshness"] = fake_freshness

    try:
        # sync() must not propagate the RuntimeError
        result = await engine.sync()
    finally:
        # Restore original module (cleanup)
        if original is not None:
            sys.modules["memory.freshness"] = original
        else:
            sys.modules.pop("memory.freshness", None)

    # If we reach here, the exception was swallowed correctly
    assert result is not None, "sync() should return a SyncResult even after scan failure"
    # State should have been saved (sync cycle completed)
    assert engine._save_state.called, "sync() should have saved state before freshness scan"


@pytest.mark.asyncio
async def test_post_sync_freshness_scan_warning_logged_on_failure(caplog):
    """sync() must log a warning when run_freshness_scan raises."""
    import logging
    import sys
    import types

    engine = _make_sync_engine()

    fake_freshness = types.ModuleType("memory.freshness")

    def _raising_scan(*args, **kwargs):
        raise ValueError("Freshness scan boom")

    fake_freshness.run_freshness_scan = _raising_scan

    original = sys.modules.get("memory.freshness")
    sys.modules["memory.freshness"] = fake_freshness

    try:
        with caplog.at_level(logging.WARNING, logger="ai_memory.github.sync"):
            await engine.sync()
    finally:
        if original is not None:
            sys.modules["memory.freshness"] = original
        else:
            sys.modules.pop("memory.freshness", None)

    # The warning message from WP-8 graceful degradation block
    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "post_sync_freshness_scan_failed" in msg for msg in warning_messages
    ), f"Expected 'post_sync_freshness_scan_failed' warning, got: {warning_messages}"
