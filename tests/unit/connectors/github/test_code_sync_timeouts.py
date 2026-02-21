# Location: ai-memory/tests/unit/connectors/github/test_code_sync_timeouts.py
"""Unit tests for BUG-112: Code sync timeouts, circuit breaker, and progress logging."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory.connectors.github.code_sync import CodeBlobSync


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
    config.github_code_blob_exclude = ""
    config.github_sync_total_timeout = total_timeout
    config.github_sync_install_timeout = 600
    config.github_sync_per_file_timeout = per_file_timeout
    config.github_sync_circuit_breaker_threshold = cb_threshold
    config.github_sync_circuit_breaker_reset = cb_reset
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
    sync._update_last_synced = MagicMock()

    return sync


def _make_tree_entry(path, sha="abc123", size=100):
    """Create a mock tree entry."""
    return {"path": path, "sha": sha, "size": size, "type": "blob"}


class TestTotalTimeout:
    """Tests for total timeout triggering early exit."""

    @pytest.mark.asyncio
    async def test_total_timeout_stops_sync(self):
        """Sync should stop when total timeout is exceeded."""
        entries = [_make_tree_entry(f"src/file{i}.py") for i in range(20)]
        sync = _make_sync(tree_entries=entries, total_timeout=0)  # Immediate timeout

        # _should_sync_file returns True for .py files
        sync._should_sync_file = MagicMock(return_value=True)

        result = await sync.sync_code_blobs("batch-1", total_timeout=0)

        # Should have stopped early — no files synced because timeout hit immediately
        assert result.files_synced == 0
        assert any("total_timeout" in d for d in result.error_details)

    @pytest.mark.asyncio
    async def test_sync_completes_within_timeout(self):
        """Sync should complete all files when within timeout."""
        entries = [_make_tree_entry(f"src/file{i}.py", sha=f"new{i}") for i in range(3)]
        sync = _make_sync(tree_entries=entries, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(return_value=2)

        result = await sync.sync_code_blobs("batch-1", total_timeout=300)

        assert result.files_synced == 3
        assert result.chunks_created == 6
        assert not any("total_timeout" in d for d in result.error_details)


class TestPerFileTimeout:
    """Tests for per-file timeout catching hanging files."""

    @pytest.mark.asyncio
    async def test_per_file_timeout_catches_hang(self):
        """A hanging _sync_file should be caught by per-file timeout."""
        entries = [_make_tree_entry("src/hang.py", sha="new1")]
        sync = _make_sync(tree_entries=entries, per_file_timeout=1, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)

        async def slow_sync(*args, **kwargs):
            await asyncio.sleep(10)  # Will be cancelled by timeout
            return 1

        sync._sync_file = slow_sync

        result = await sync.sync_code_blobs("batch-1")

        assert result.files_synced == 0
        assert result.errors == 1
        assert any("per_file_timeout" in d for d in result.error_details)

    @pytest.mark.asyncio
    async def test_per_file_timeout_does_not_crash_sync(self):
        """After a per-file timeout, sync should continue to next file."""
        entries = [
            _make_tree_entry("src/hang.py", sha="new1"),
            _make_tree_entry("src/ok.py", sha="new2"),
        ]
        sync = _make_sync(tree_entries=entries, per_file_timeout=1, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)

        call_count = 0

        async def mixed_sync(entry, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if entry["path"] == "src/hang.py":
                await asyncio.sleep(10)
            return 1

        sync._sync_file = mixed_sync

        result = await sync.sync_code_blobs("batch-1")

        assert result.files_synced == 1
        assert result.errors == 1


class TestCircuitBreaker:
    """Tests for circuit breaker opening after threshold failures."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self):
        """Circuit breaker should open after N consecutive failures."""
        entries = [
            _make_tree_entry(f"src/fail{i}.py", sha=f"new{i}") for i in range(10)
        ]
        sync = _make_sync(
            tree_entries=entries,
            total_timeout=300,
            per_file_timeout=60,
            cb_threshold=3,
        )
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(side_effect=RuntimeError("embedding failed"))

        result = await sync.sync_code_blobs("batch-1")

        # Should have stopped after circuit breaker opened (3 failures + breaker check)
        assert result.errors >= 3
        assert result.files_synced == 0
        assert any("circuit_breaker_open" in d for d in result.error_details)

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_on_success(self):
        """A success should reset the circuit breaker failure count."""
        entries = [
            _make_tree_entry("src/fail1.py", sha="new1"),
            _make_tree_entry("src/fail2.py", sha="new2"),
            _make_tree_entry("src/ok.py", sha="new3"),
            _make_tree_entry("src/fail3.py", sha="new4"),
            _make_tree_entry("src/fail4.py", sha="new5"),
            _make_tree_entry("src/ok2.py", sha="new6"),
        ]
        sync = _make_sync(
            tree_entries=entries,
            total_timeout=300,
            per_file_timeout=60,
            cb_threshold=3,
        )
        sync._should_sync_file = MagicMock(return_value=True)

        call_idx = 0

        async def alternating_sync(entry, *args, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if "ok" in entry["path"]:
                return 1
            raise RuntimeError("embedding failed")

        sync._sync_file = alternating_sync

        result = await sync.sync_code_blobs("batch-1")

        # Success resets counter, so breaker should NOT have opened
        assert result.files_synced == 2
        assert "circuit_breaker_open" not in str(result.error_details)


class TestProgressLogging:
    """Tests for progress logging every 10 files."""

    @pytest.mark.asyncio
    async def test_progress_logged_every_10_files(self, caplog):
        """Should log progress every 10 files."""
        entries = [_make_tree_entry(f"src/f{i}.py", sha=f"new{i}") for i in range(25)]
        sync = _make_sync(tree_entries=entries, total_timeout=300)
        sync._should_sync_file = MagicMock(return_value=True)
        sync._sync_file = AsyncMock(return_value=1)

        with caplog.at_level(logging.INFO, logger="ai_memory.github.code_sync"):
            await sync.sync_code_blobs("batch-1")

        progress_logs = [r for r in caplog.records if "progress:" in r.message]
        # With 25 files, expect progress at idx 10 and 20
        assert len(progress_logs) == 2
