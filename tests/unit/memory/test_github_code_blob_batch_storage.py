"""Tests for batched GitHub code blob storage (embedding + Qdrant)."""

from unittest.mock import MagicMock

import pytest

from memory.embeddings import EmbeddingError
from memory.models import MemoryType
from memory.qdrant_client import QdrantUnavailable
from memory.storage import MemoryStorage


def _body(tag: str = "a") -> str:
    """Valid-length code-ish content for validate_payload (min 10 chars)."""
    return f"# File: src/{tag}.py | Language: python\n" + ("def x():\n    pass\n" * 4)


@pytest.fixture
def gh_storage() -> MemoryStorage:
    cfg = MagicMock()
    cfg.hybrid_search_enabled = False
    cfg.security_scanning_enabled = False
    s = MemoryStorage.__new__(MemoryStorage)
    s.config = cfg
    s.embedding_client = MagicMock()
    s.qdrant_client = MagicMock()
    s._scanner = None
    return s


def _item(i: int, path: str = "src/m.py", blob: str = "sha1") -> dict:
    return {
        "content": _body(str(i)),
        "source": "github",
        "github_id": 0,
        "repo": "o/r",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "last_synced": "2026-01-01T00:00:00+00:00",
        "url": f"https://github.com/o/r/blob/main/{path}",
        "version": 1,
        "is_current": True,
        "supersedes": None,
        "update_batch_id": "batch-1",
        "source_authority": 1.0,
        "decay_score": 1.0,
        "freshness_status": "unverified",
        "file_path": path,
        "language": "python",
        "last_commit_sha": blob,
        "symbols": ["x"],
        "blob_hash": blob,
        "chunk_index": i,
        "total_chunks": 5,
        "content_type": "github_code_blob",
    }


def test_github_batch_uses_code_embedding_model(gh_storage: MemoryStorage) -> None:
    gh_storage.embedding_client.embed.return_value = [[0.25] * 768, [0.5] * 768]
    items = [_item(0), _item(1)]
    gh_storage.store_github_code_blob_chunks_batch(
        items,
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=8,
    )
    gh_storage.embedding_client.embed.assert_called_once()
    _args, kwargs = gh_storage.embedding_client.embed.call_args
    assert kwargs.get("model") == "code"


def test_github_batch_sub_batches_split_embed_calls(gh_storage: MemoryStorage) -> None:
    def _emb(texts: list, model: str | None = None) -> list:
        return [[0.0] * 768 for _ in texts]

    gh_storage.embedding_client.embed.side_effect = _emb
    items = [_item(i) for i in range(5)]
    gh_storage.store_github_code_blob_chunks_batch(
        items,
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=2,
    )
    assert gh_storage.embedding_client.embed.call_count == 3


def test_github_batch_size_clamped_to_inflight_envelope(
    gh_storage: MemoryStorage, monkeypatch
) -> None:
    """BUG-327: an operator-set github_code_blob_chunk_batch_size above the in-flight-work
    envelope is clamped to the envelope, so the github embed/sparse calls never exceed it
    (and never earn the server's 413).

    chunk_batch_size=128 (the config max) with the envelope pinned to 4: 9 chunks must
    split into ceil(9/4)=3 embed calls of <=4, not one 9-text call.
    """
    monkeypatch.setenv("EMBEDDING_SAFE_INFLIGHT_TEXTS", "4")

    def _emb(texts: list, model: str | None = None) -> list:
        return [[0.0] * 768 for _ in texts]

    gh_storage.embedding_client.embed.side_effect = _emb
    items = [_item(i) for i in range(9)]
    gh_storage.store_github_code_blob_chunks_batch(
        items,
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=128,
    )
    assert gh_storage.embedding_client.embed.call_count == 3
    for call in gh_storage.embedding_client.embed.call_args_list:
        sent = call.args[0] if call.args else call.kwargs["texts"]
        assert len(sent) <= 4


def test_github_batch_embedding_failure_still_upserts_pending(
    gh_storage: MemoryStorage,
) -> None:
    gh_storage.embedding_client.embed.side_effect = EmbeddingError("upstream timeout")
    items = [_item(0)]
    results = gh_storage.store_github_code_blob_chunks_batch(
        items,
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=8,
    )
    assert len(results) == 1
    assert results[0]["embedding_status"] == "pending"
    assert results[0]["status"] == "stored"
    gh_storage.qdrant_client.upsert.assert_called_once()
    point = gh_storage.qdrant_client.upsert.call_args.kwargs["points"][0]
    assert point.payload["embedding_status"] == "pending"


def test_github_batch_payload_preserves_blob_metadata(
    gh_storage: MemoryStorage,
) -> None:
    gh_storage.embedding_client.embed.return_value = [[0.1] * 768]
    items = [_item(0, path="lib/foo.py", blob="deadbeef")]
    gh_storage.store_github_code_blob_chunks_batch(
        items,
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=8,
    )
    payload = gh_storage.qdrant_client.upsert.call_args.kwargs["points"][0].payload
    assert payload["file_path"] == "lib/foo.py"
    assert payload["blob_hash"] == "deadbeef"
    assert payload["chunk_index"] == 0
    assert payload["total_chunks"] == 5
    assert payload["content_type"] == "github_code_blob"
    assert payload["chunking_metadata"]["chunk_index"] == 0
    assert payload["chunking_metadata"]["total_chunks"] == 5


def test_github_batch_reuses_deterministic_ids_for_same_chunk(
    gh_storage: MemoryStorage,
) -> None:
    gh_storage.embedding_client.embed.return_value = [[0.1] * 768]
    item = _item(2, path="lib/foo.py", blob="sameblob")
    gh_storage.store_github_code_blob_chunks_batch(
        [item],
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=8,
    )
    first_point = gh_storage.qdrant_client.upsert.call_args.kwargs["points"][0]
    gh_storage.qdrant_client.upsert.reset_mock()

    gh_storage.store_github_code_blob_chunks_batch(
        [dict(item)],
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-2",
        chunk_batch_size=8,
    )
    second_point = gh_storage.qdrant_client.upsert.call_args.kwargs["points"][0]

    assert first_point.id == second_point.id


def test_github_batch_embedding_non_embedding_error_still_degrades(
    gh_storage: MemoryStorage,
) -> None:
    gh_storage.embedding_client.embed.side_effect = RuntimeError("boom")
    results = gh_storage.store_github_code_blob_chunks_batch(
        [_item(0)],
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=8,
    )

    assert results[0]["embedding_status"] == "pending"


def test_github_batch_embedding_count_mismatch_still_degrades(
    gh_storage: MemoryStorage,
) -> None:
    gh_storage.embedding_client.embed.return_value = [[0.1] * 768]
    results = gh_storage.store_github_code_blob_chunks_batch(
        [_item(0), _item(1)],
        cwd="/tmp",
        collection="github",
        group_id="o/r",
        memory_type=MemoryType.GITHUB_CODE_BLOB,
        source_hook="github_code_sync",
        session_id="batch-1",
        chunk_batch_size=8,
    )

    assert len(results) == 2
    assert all(result["embedding_status"] == "pending" for result in results)


def test_github_batch_rolls_back_partial_sub_batch_failure(
    gh_storage: MemoryStorage,
) -> None:
    gh_storage.embedding_client.embed.side_effect = lambda texts, model=None: [
        [0.1] * 768 for _ in texts
    ]
    gh_storage.qdrant_client.upsert.side_effect = [None, RuntimeError("boom")]

    with pytest.raises(QdrantUnavailable):
        gh_storage.store_github_code_blob_chunks_batch(
            [_item(0), _item(1), _item(2)],
            cwd="/tmp",
            collection="github",
            group_id="o/r",
            memory_type=MemoryType.GITHUB_CODE_BLOB,
            source_hook="github_code_sync",
            session_id="batch-1",
            chunk_batch_size=2,
        )

    gh_storage.qdrant_client.delete.assert_called_once()
    delete_call = gh_storage.qdrant_client.delete.call_args
    selector = delete_call.kwargs.get("points_selector") or delete_call[1].get(
        "points_selector"
    )
    assert len(selector.points) == 2

    # Verify deleted IDs exactly match the first sub-batch's stored point IDs
    first_upsert_call = gh_storage.qdrant_client.upsert.call_args_list[0]
    first_batch_ids = {p.id for p in first_upsert_call.kwargs["points"]}
    assert set(selector.points) == first_batch_ids
