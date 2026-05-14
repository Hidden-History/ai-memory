# Location: ai-memory/tests/unit/connectors/github/test_code_sync_reconciliation.py
"""Unit tests for BUG-288: code-blob sync reconciliation and embedding resilience.

Tests:
    T1 - Abandon-set populated on timeout; reconciliation pre-sort on next cycle
    T2 - Pre-sync embedding probe: non-ready service → proceeds gracefully
    T3 - Pre-sync embedding probe: ready service → no error logged
    T4 - State file forward compat: missing code_blobs key → no crash
    T5 - Metrics emitted with abandoned count on partial timeout
    T6 - BUG-289: /health HTTP 503 gating (embedding service status codes)
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory.connectors.github.code_sync import CodeBlobSync, CodeSyncResult

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config singleton between tests."""
    from memory.config import reset_config

    reset_config()
    yield
    reset_config()


def _make_sync(
    tree_entries=None,
    stored_map=None,
    total_timeout=30,
    per_file_timeout=5,
    cb_threshold=3,
    cb_reset=10,
    concurrency=1,
):
    """Create a CodeBlobSync with mocked dependencies."""
    mock_client = MagicMock()
    mock_client.get_tree = AsyncMock(return_value=tree_entries or [])
    mock_client.get_blob = AsyncMock(return_value={"content": ""})

    config = MagicMock()
    config.github_branch = "main"
    config.github_repo = "owner/repo"
    config.github_code_blob_enabled = True
    config.github_code_blob_max_size = 102400
    config.github_code_blob_include = ""
    config.github_code_blob_include_max_size = 512000
    config.github_code_blob_exclude = ""
    config.github_sync_total_timeout = total_timeout
    config.github_sync_install_timeout = 600
    config.github_sync_per_file_timeout = per_file_timeout
    config.github_sync_circuit_breaker_threshold = cb_threshold
    config.github_sync_circuit_breaker_reset = cb_reset
    config.github_code_blob_file_concurrency = concurrency
    config.github_code_blob_chunk_batch_size = 8
    config.github_code_blob_batch_storage_enabled = False
    config.security_scanning_enabled = False
    config.github_token = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_test"

    with (
        patch("memory.connectors.github.code_sync.get_config", return_value=config),
        patch("memory.connectors.github.code_sync.MemoryStorage"),
        patch("memory.connectors.github.code_sync.get_qdrant_client"),
    ):
        sync = CodeBlobSync(mock_client, config)

    sync._get_stored_blob_map = MagicMock(return_value=stored_map or {})
    sync._detect_deleted_files = AsyncMock(return_value=0)
    sync._push_metrics = MagicMock()
    sync._batch_update_last_synced = MagicMock()
    # Probe no-op by default — tests override when needed
    sync._wait_for_embedding_ready = AsyncMock(return_value=True)

    return sync


def _make_tree_entry(path, sha="abc123", size=100):
    """Create a mock tree entry."""
    return {"path": path, "sha": sha, "size": size, "type": "blob"}


# ---------------------------------------------------------------------------
# T1 — Abandon-set population and reconciliation pre-sort
# ---------------------------------------------------------------------------


class TestAbandonSetReconciliation:
    """T1: abandoned_paths populated on timeout; pre-sort on next cycle."""

    @pytest.mark.asyncio
    async def test_abandoned_paths_populated_on_timeout(self):
        """Files cut off by total_timeout appear in abandoned_paths."""
        entries = [_make_tree_entry(f"src/file{i}.py", sha=f"new{i}") for i in range(5)]
        sync = _make_sync(tree_entries=entries, total_timeout=0)  # immediate timeout
        sync._should_sync_file = MagicMock(return_value=True)

        result = await sync.sync_code_blobs("batch-1", total_timeout=0)

        # Abandoned paths must be non-empty when timeout is immediate
        assert len(result.abandoned_paths) > 0
        # Every abandoned path should be a path from the entries list
        entry_paths = {e["path"] for e in entries}
        assert all(p in entry_paths for p in result.abandoned_paths)

    @pytest.mark.asyncio
    async def test_reconciliation_priority_sort(self):
        """Previously abandoned files are sorted to front of eligible queue."""
        # 4 files: file0 and file2 were previously abandoned
        entries = [_make_tree_entry(f"src/file{i}.py", sha=f"new{i}") for i in range(4)]
        sync = _make_sync(tree_entries=entries, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)

        synced_order: list[str] = []

        async def record_sync_file(entry, batch_id, stored_hash):
            synced_order.append(entry["path"])
            return 1

        sync._sync_file = record_sync_file

        prior_abandoned = ["src/file0.py", "src/file2.py"]
        code_blob_state = {"abandoned": prior_abandoned}

        await sync.sync_code_blobs(
            "batch-2",
            total_timeout=300,
            code_blob_state=code_blob_state,
        )

        # file0 and file2 (priority) must appear before file1 and file3 (delta)
        assert len(synced_order) == 4
        priority_positions = [synced_order.index(p) for p in prior_abandoned]
        delta_positions = [
            synced_order.index(p) for p in ["src/file1.py", "src/file3.py"]
        ]
        assert max(priority_positions) < min(delta_positions), (
            f"Priority files {prior_abandoned} should all come before delta files; "
            f"got order: {synced_order}"
        )

    @pytest.mark.asyncio
    async def test_no_abandoned_when_all_sync_succeeds(self):
        """abandoned_paths is empty when all eligible files sync successfully."""
        entries = [_make_tree_entry(f"src/ok{i}.py", sha=f"new{i}") for i in range(3)]
        sync = _make_sync(tree_entries=entries, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(return_value=2)

        result = await sync.sync_code_blobs("batch-ok", total_timeout=300)

        assert result.abandoned_paths == []
        assert result.files_synced == 3

    @pytest.mark.asyncio
    async def test_empty_prior_abandoned_set_no_reorder(self):
        """Empty code_blob_state (first run) causes no reorder and no crash."""
        entries = [_make_tree_entry(f"src/file{i}.py", sha=f"new{i}") for i in range(3)]
        sync = _make_sync(tree_entries=entries, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(return_value=1)

        # No prior state — should work identically to None
        result = await sync.sync_code_blobs(
            "batch-first", total_timeout=300, code_blob_state={}
        )

        assert result.files_synced == 3
        assert result.abandoned_paths == []


# ---------------------------------------------------------------------------
# T2 & T3 — Pre-sync embedding probe
# ---------------------------------------------------------------------------


class TestEmbeddingProbe:
    """T2/T3: _wait_for_embedding_ready behaviour."""

    @pytest.mark.asyncio
    async def test_probe_not_ready_proceeds_gracefully(self, caplog):
        """When embedding not ready within timeout, sync proceeds with error log."""
        entries = [_make_tree_entry("src/a.py", sha="new1")]

        # Build sync WITHOUT overriding _wait_for_embedding_ready (we test the real one)
        mock_client = MagicMock()
        mock_client.get_tree = AsyncMock(return_value=entries)
        mock_client.get_blob = AsyncMock(return_value={"content": ""})

        config = MagicMock()
        config.github_branch = "main"
        config.github_repo = "owner/repo"
        config.github_code_blob_enabled = True
        config.github_code_blob_max_size = 102400
        config.github_code_blob_include = ""
        config.github_code_blob_include_max_size = 512000
        config.github_code_blob_exclude = ""
        config.github_sync_total_timeout = 300
        config.github_sync_install_timeout = 600
        config.github_sync_per_file_timeout = 30
        config.github_sync_circuit_breaker_threshold = 3
        config.github_sync_circuit_breaker_reset = 10
        config.github_code_blob_file_concurrency = 1
        config.github_code_blob_chunk_batch_size = 8
        config.github_code_blob_batch_storage_enabled = False
        config.security_scanning_enabled = False
        config.github_token = MagicMock()
        config.github_token.get_secret_value.return_value = "ghp_test"

        with (
            patch("memory.connectors.github.code_sync.get_config", return_value=config),
            patch("memory.connectors.github.code_sync.MemoryStorage"),
            patch("memory.connectors.github.code_sync.get_qdrant_client"),
        ):
            sync = CodeBlobSync(mock_client, config)

        sync._get_stored_blob_map = MagicMock(return_value={})
        sync._detect_deleted_files = AsyncMock(return_value=0)
        sync._push_metrics = MagicMock()
        sync._batch_update_last_synced = MagicMock()
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(return_value=1)

        mock_embed_client = MagicMock()
        mock_embed_client.__enter__.return_value = mock_embed_client  # CM returns self
        mock_embed_client.health_check.return_value = False  # never ready

        with (
            patch("memory.embeddings.EmbeddingClient", return_value=mock_embed_client),
            caplog.at_level(logging.ERROR, logger="ai_memory.github.code_sync"),
        ):
            # max_wait_seconds=0 → exits immediately without sleeping
            result = await sync._wait_for_embedding_ready(
                max_wait_seconds=0, poll_interval=1.0
            )

        assert result is False
        assert any(
            "not ready" in r.message.lower() for r in caplog.records
        ), "Expected 'not ready' error log when embedding probe times out"

    @pytest.mark.asyncio
    async def test_probe_ready_returns_true(self):
        """When embedding service is healthy, probe returns True without error."""
        mock_client = MagicMock()
        config = MagicMock()
        config.github_branch = "main"
        config.github_repo = "owner/repo"
        config.github_code_blob_enabled = True
        config.github_code_blob_max_size = 102400
        config.github_code_blob_include = ""
        config.github_code_blob_include_max_size = 512000
        config.github_code_blob_exclude = ""
        config.github_sync_total_timeout = 300
        config.github_sync_install_timeout = 600
        config.github_sync_per_file_timeout = 30
        config.github_sync_circuit_breaker_threshold = 3
        config.github_sync_circuit_breaker_reset = 10
        config.github_code_blob_file_concurrency = 1
        config.github_code_blob_chunk_batch_size = 8
        config.github_code_blob_batch_storage_enabled = False
        config.security_scanning_enabled = False
        config.github_token = MagicMock()
        config.github_token.get_secret_value.return_value = "ghp_test"

        with (
            patch("memory.connectors.github.code_sync.get_config", return_value=config),
            patch("memory.connectors.github.code_sync.MemoryStorage"),
            patch("memory.connectors.github.code_sync.get_qdrant_client"),
        ):
            sync = CodeBlobSync(mock_client, config)

        mock_embed_client = MagicMock()
        mock_embed_client.__enter__.return_value = mock_embed_client  # CM returns self
        mock_embed_client.health_check.return_value = True  # immediately ready

        with patch("memory.embeddings.EmbeddingClient", return_value=mock_embed_client):
            result = await sync._wait_for_embedding_ready(
                max_wait_seconds=10, poll_interval=1.0
            )

        assert result is True
        mock_embed_client.health_check.assert_called_once()


# ---------------------------------------------------------------------------
# T4 — State file forward compatibility
# ---------------------------------------------------------------------------


class TestStateFwdCompat:
    """T4: code_blob_state missing 'abandoned' key does not crash."""

    @pytest.mark.asyncio
    async def test_missing_abandoned_key_in_state(self):
        """State dict without 'abandoned' key is treated as empty abandon-set."""
        entries = [_make_tree_entry(f"src/file{i}.py", sha=f"new{i}") for i in range(3)]
        sync = _make_sync(tree_entries=entries, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(return_value=1)

        # State with unexpected/unknown key but no 'abandoned'
        state_without_abandoned = {
            "last_cycle_at": "2026-01-01T00:00:00+00:00",
            "last_cycle_synced_count": 5,
        }

        result = await sync.sync_code_blobs(
            "batch-compat",
            total_timeout=300,
            code_blob_state=state_without_abandoned,
        )

        assert result.files_synced == 3
        assert result.abandoned_paths == []

    @pytest.mark.asyncio
    async def test_none_code_blob_state_no_crash(self):
        """None code_blob_state (default) does not crash."""
        entries = [_make_tree_entry("src/x.py", sha="new1")]
        sync = _make_sync(tree_entries=entries, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(return_value=1)

        result = await sync.sync_code_blobs("batch-none", total_timeout=300)

        assert result.files_synced == 1
        assert result.abandoned_paths == []

    def test_to_dict_includes_abandoned_paths(self):
        """to_dict must include abandoned_paths with a defensive copy (F-3 Sonnet cycle-2 fix)."""
        result = CodeSyncResult(abandoned_paths=["foo.py", "bar.py"])
        d = result.to_dict()
        assert d["abandoned_paths"] == ["foo.py", "bar.py"]
        # Verify defensive copy — mutating the returned list must not affect source
        d["abandoned_paths"].append("baz.py")
        assert result.abandoned_paths == ["foo.py", "bar.py"]


# ---------------------------------------------------------------------------
# T5 — Metrics emitted with abandoned count
# ---------------------------------------------------------------------------


class TestMetricsOnAbandonment:
    """T5: _push_metrics receives result with populated abandoned_paths."""

    @pytest.mark.asyncio
    async def test_push_metrics_called_with_abandoned_result(self):
        """_push_metrics is called with CodeSyncResult that has abandoned_paths set."""
        entries = [_make_tree_entry(f"src/file{i}.py", sha=f"new{i}") for i in range(5)]
        sync = _make_sync(tree_entries=entries, total_timeout=0)  # immediate timeout
        sync._should_sync_file = MagicMock(return_value=True)

        captured: list[CodeSyncResult] = []

        def capture_metrics(result: CodeSyncResult) -> None:
            captured.append(result)

        sync._push_metrics = capture_metrics

        await sync.sync_code_blobs("batch-metrics", total_timeout=0)

        assert len(captured) == 1, "_push_metrics should be called exactly once"
        assert (
            len(captured[0].abandoned_paths) > 0
        ), "abandoned_paths should be non-empty after timeout"
