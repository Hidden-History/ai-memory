"""Bounded file concurrency and batched chunk storage for code blob sync."""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory.connectors.github.code_sync import CodeBlobSync


@pytest.fixture(autouse=True)
def reset_config():
    from memory.config import reset_config

    reset_config()
    yield
    reset_config()


def _tree(path: str, sha: str = "s1") -> dict:
    return {"path": path, "sha": sha, "size": 200, "type": "blob"}


def _make_sync_for_batching(
    tree_entries: list[dict],
    *,
    file_concurrency: int = 2,
    chunk_batch_size: int = 8,
    batch_storage: bool = True,
    total_timeout: int = 300,
    per_file_timeout: int = 30,
):
    mock_client = MagicMock()
    mock_client.get_tree = AsyncMock(return_value=tree_entries)
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
    config.github_sync_circuit_breaker_threshold = 5
    config.github_sync_circuit_breaker_reset = 60
    config.github_code_blob_file_concurrency = file_concurrency
    config.github_code_blob_chunk_batch_size = chunk_batch_size
    config.github_code_blob_batch_storage_enabled = batch_storage
    config.security_scanning_enabled = False
    config.github_token = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_test"

    mock_storage = MagicMock()

    with (
        patch("memory.connectors.github.code_sync.get_config", return_value=config),
        patch(
            "memory.connectors.github.code_sync.MemoryStorage",
            return_value=mock_storage,
        ),
        patch("memory.connectors.github.code_sync.get_qdrant_client"),
    ):
        sync = CodeBlobSync(mock_client, config)

    sync._get_stored_blob_map = MagicMock(return_value={})
    sync._detect_deleted_files = AsyncMock(return_value=0)
    sync._push_metrics = MagicMock()
    sync._batch_update_last_synced = MagicMock()
    return sync, mock_storage, mock_client


@pytest.mark.asyncio
async def test_chunk_batch_size_passed_to_storage():
    entries = [_tree("a.py", sha="n1")]
    sync, mock_storage, mock_client = _make_sync_for_batching(
        entries, chunk_batch_size=4
    )

    sync._should_sync_file = MagicMock(return_value=True)
    py_src = "def hello():\n    return 42\n"
    mock_client.get_blob = AsyncMock(
        return_value={"content": base64.b64encode(py_src.encode()).decode()}
    )

    def _batch_return(chunk_items, **_kwargs):
        return [{"status": "stored"} for _ in chunk_items]

    mock_storage.store_github_code_blob_chunks_batch.side_effect = _batch_return

    await sync.sync_code_blobs("batch-x")

    mock_storage.store_github_code_blob_chunks_batch.assert_called()
    _args, kwargs = mock_storage.store_github_code_blob_chunks_batch.call_args
    assert kwargs.get("chunk_batch_size") == 4


@pytest.mark.asyncio
async def test_file_concurrency_observes_parallel_syncs():
    entries = [_tree(f"src/f{i}.py", sha=f"n{i}") for i in range(4)]
    sync, _, _ = _make_sync_for_batching(entries, file_concurrency=2)

    sync._should_sync_file = MagicMock(return_value=True)

    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def tracked_sync(self, entry, batch_id, old_hash):
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.2)
        async with lock:
            in_flight -= 1
        return 1

    with patch.object(CodeBlobSync, "_sync_file", tracked_sync):
        await sync.sync_code_blobs("batch-y")

    assert peak == 2


@pytest.mark.asyncio
async def test_per_file_timeout_with_concurrency_other_file_completes():
    entries = [
        _tree("src/hang.py", sha="n1"),
        _tree("src/ok.py", sha="n2"),
    ]
    sync, _, _ = _make_sync_for_batching(
        entries,
        file_concurrency=2,
        per_file_timeout=1,
        total_timeout=300,
    )
    sync._should_sync_file = MagicMock(return_value=True)

    async def mixed(self, entry, batch_id, old_hash):
        if entry["path"] == "src/hang.py":
            await asyncio.sleep(10)
        return 1

    with patch.object(CodeBlobSync, "_sync_file", mixed):
        result = await sync.sync_code_blobs("batch-z")

    assert result.files_synced == 1
    assert result.errors == 1
    assert any("per_file_timeout" in d for d in result.error_details)


@pytest.mark.asyncio
async def test_circuit_breaker_cancels_in_flight_tasks_when_threshold_reached():
    entries = [
        _tree("src/fail.py", sha="n1"),
        _tree("src/slow.py", sha="n2"),
        _tree("src/later.py", sha="n3"),
    ]
    sync, _, _ = _make_sync_for_batching(entries, file_concurrency=2)
    sync._should_sync_file = MagicMock(return_value=True)
    sync._circuit_breaker.failure_threshold = 1

    started: list[str] = []
    cancelled: list[str] = []

    async def mixed(self, entry, batch_id, old_hash):
        started.append(entry["path"])
        if entry["path"] == "src/fail.py":
            raise RuntimeError("boom")
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(entry["path"])
            raise
        return 1

    with patch.object(CodeBlobSync, "_sync_file", mixed):
        result = await sync.sync_code_blobs("batch-cb")

    assert "src/later.py" not in started
    assert cancelled == ["src/slow.py"]
    assert result.files_synced == 0
    assert result.errors == 1
    assert any("circuit_breaker_open" in d for d in result.error_details)


@pytest.mark.asyncio
async def test_same_cycle_success_does_not_reclose_circuit_breaker():
    entries = [
        _tree("src/fail.py", sha="n1"),
        _tree("src/ok.py", sha="n2"),
        _tree("src/later.py", sha="n3"),
    ]
    sync, _, _ = _make_sync_for_batching(entries, file_concurrency=2)
    sync._should_sync_file = MagicMock(return_value=True)
    sync._circuit_breaker.failure_threshold = 1

    started: list[str] = []
    real_wait = asyncio.wait

    async def wait_all(tasks, timeout=None, return_when=None):
        done, pending = await real_wait(tasks, timeout=timeout)
        if pending:
            more_done, pending = await real_wait(pending, timeout=timeout)
            done |= more_done
        return done, pending

    async def mixed(self, entry, batch_id, old_hash):
        started.append(entry["path"])
        if entry["path"] == "src/fail.py":
            await asyncio.sleep(0)
            raise RuntimeError("boom")
        if entry["path"] == "src/ok.py":
            await asyncio.sleep(0.001)
            return 1
        return 1

    with (
        patch.object(CodeBlobSync, "_sync_file", mixed),
        patch("memory.connectors.github.code_sync.asyncio.wait", wait_all),
    ):
        result = await sync.sync_code_blobs("batch-cycle")

    assert "src/later.py" not in started
    assert result.files_synced == 1
    assert result.errors == 1
    assert any("circuit_breaker_open" in d for d in result.error_details)


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_storage", [True, False])
async def test_sync_file_supersedes_only_previous_blob_hash(batch_storage: bool):
    entry = _tree("src/file.py", sha="newsha")
    sync, mock_storage, mock_client = _make_sync_for_batching(
        [entry], batch_storage=batch_storage
    )
    py_src = "def hello():\n    return 42\n"
    mock_client.get_blob = AsyncMock(
        return_value={"content": base64.b64encode(py_src.encode()).decode()}
    )

    if batch_storage:
        mock_storage.store_github_code_blob_chunks_batch.return_value = [
            {"status": "stored"}
        ]
    else:
        mock_storage.store_memory.return_value = {"status": "stored"}

    sync._supersede_old_blobs = MagicMock()

    stored = await sync._sync_file(entry, "batch-1", "oldsha")

    assert stored >= 1
    sync._supersede_old_blobs.assert_called_once_with("src/file.py", "oldsha")


@pytest.mark.asyncio
async def test_legacy_sync_file_does_not_supersede_on_partial_chunk_failure():
    entry = _tree("src/file.py", sha="newsha")
    sync, mock_storage, mock_client = _make_sync_for_batching(
        [entry], batch_storage=False
    )
    py_src = "def alpha():\n    return 1\n\ndef beta():\n    return 2\n"
    mock_client.get_blob = AsyncMock(
        return_value={"content": base64.b64encode(py_src.encode()).decode()}
    )

    mock_storage.store_memory.side_effect = [
        {"status": "stored"},
        RuntimeError("boom"),
    ]
    sync._supersede_old_blobs = MagicMock()

    stored = await sync._sync_file(entry, "batch-1", "oldsha")

    assert stored == 1
    sync._supersede_old_blobs.assert_not_called()


@pytest.mark.asyncio
async def test_batch_sync_does_not_supersede_with_zero_vector_embeddings():
    """F-26: Don't supersede old blobs when new chunks only have zero-vector embeddings."""
    entry = _tree("src/file.py", sha="newsha")
    sync, mock_storage, mock_client = _make_sync_for_batching(
        [entry], batch_storage=True
    )
    py_src = "def hello():\n    return 42\n"
    mock_client.get_blob = AsyncMock(
        return_value={"content": base64.b64encode(py_src.encode()).decode()}
    )

    # All results have embedding_status=pending (zero-vector embeddings)
    mock_storage.store_github_code_blob_chunks_batch.return_value = [
        {"status": "stored", "embedding_status": "pending"}
    ]
    sync._supersede_old_blobs = MagicMock()

    await sync._sync_file(entry, "batch-1", "oldsha")

    sync._supersede_old_blobs.assert_not_called()
