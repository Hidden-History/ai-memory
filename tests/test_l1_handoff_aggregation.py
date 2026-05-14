"""TD-518 (F-001): L1 handoff retrieval aggregation tests.

Verifies that ``retrieve_bootstrap_context``'s Layer 1 handoff fetch reassembles
multi-chunk agent_handoff emits via scroll-and-concat, restoring cross-session
continuity that was previously delivering only the highest-scoring chunk
(~0.5% of intended payload in the testV2 Session 45 / 37-chunk case).

Test approach: in-memory Qdrant (no Docker dependency, mirrors
``tests/integration/test_e2e_cross_phase.py:qdrant_inmemory`` precedent).
Synthetic chunked handoff inserted directly via ``upsert``; bootstrap retrieval
exercised through the real ``retrieve_bootstrap_context`` path with mocked
embedding for the SEMANTIC layers.

References:
    - TECH-DEBT-518 §"Fix Design"
    - oversight/tasks/pm285-v240-ship-fix/recommendation-first-r1.md §B-1
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

FIXED_VECTOR = [0.5] * 768


@pytest.fixture(autouse=True)
def _disable_detect_secrets(monkeypatch):
    """Match precedent — keep entropy scanner out of unit-test path."""
    from memory import security_scanner

    monkeypatch.setattr(security_scanner, "_detect_secrets_available", False)


@pytest.fixture
def qdrant_inmemory():
    """In-memory Qdrant client with discussions collection (TD-518 only needs one)."""
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="discussions",
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    return client


@pytest.fixture
def mock_embedding():
    """Deterministic 768-dim embedding for the SEMANTIC bootstrap layers."""
    mock = MagicMock()
    mock.embed.return_value = [FIXED_VECTOR]
    with (
        patch("memory.storage.EmbeddingClient", return_value=mock),
        patch("memory.search.EmbeddingClient", return_value=mock),
    ):
        yield mock


def _insert_handoff_chunks(
    client: QdrantClient,
    *,
    group_id: str,
    created_at: str,
    chunks: list[str],
    total_chunks: int | None = None,
) -> list[str]:
    """Insert N synthetic agent_handoff chunks at the same created_at timestamp.

    Returns list of point ids (uuid strings) inserted, in chunk_index order.
    """
    total = total_chunks if total_chunks is not None else len(chunks)
    point_ids: list[str] = []
    points = []
    for idx, content in enumerate(chunks):
        pid = str(uuid.uuid4())
        point_ids.append(pid)
        points.append(
            PointStruct(
                id=pid,
                vector=FIXED_VECTOR,
                payload={
                    "content": content,
                    "type": "agent_handoff",
                    "agent_id": "parzival",
                    "group_id": group_id,
                    "created_at": created_at,
                    "timestamp": created_at,
                    "chunking_metadata": {
                        "chunk_type": "prose",
                        "chunk_index": idx,
                        "total_chunks": total,
                    },
                },
            )
        )
    client.upsert(collection_name="discussions", points=points)
    return point_ids


def _make_search_client(qdrant_inmemory, monkeypatch):
    """Return a MemorySearch wired to the in-memory Qdrant client."""
    from memory.config import get_config, reset_config
    from memory.search import MemorySearch

    monkeypatch.setenv("DECAY_ENABLED", "false")
    reset_config()
    config = get_config()
    search = MemorySearch(config)
    search.client = qdrant_inmemory
    return search, config


# ─── T1: Whole-emit (total_chunks=1) bypasses aggregation ───────────────────


def test_T1_whole_emit_bypasses_aggregation(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """A single-chunk handoff (total_chunks=1) must be returned as-is.

    No extra scroll call required; metadata.aggregated_from_chunks should be
    absent or False.
    """
    from memory.injection import retrieve_bootstrap_context

    group_id = "test-td518-t1"
    created_at = "2026-05-09T10:00:00Z"
    body = "Whole-emit handoff body — single chunk, no reassembly required."
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=[body],
        total_chunks=1,
    )

    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    results, _meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert len(handoff_results) == 1
    assert handoff_results[0]["content"] == body
    cm = handoff_results[0].get("chunking_metadata") or {}
    assert cm.get("aggregated_from_chunks") is not True


# ─── T2: 5-chunk handoff aggregates byte-equivalent ─────────────────────────


def test_T2_five_chunks_aggregate_byte_equivalent(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """A 5-chunk handoff with all siblings present must reassemble in
    chunk_index order, byte-equivalent to original concatenation.
    """
    from memory.injection import retrieve_bootstrap_context

    group_id = "test-td518-t2"
    created_at = "2026-05-09T10:05:00Z"
    chunk_bodies = [
        "Section A — header content.\n",
        "Section B — middle content paragraph.\n",
        "Section C — additional middle content.\n",
        "Section D — penultimate content.\n",
        "Section E — final trailer content.\n",
    ]
    expected_aggregated = "".join(chunk_bodies)

    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=chunk_bodies,
        total_chunks=5,
    )

    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    results, _meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert len(handoff_results) == 1, "Layer 1 should still produce one logical result"
    assert (
        handoff_results[0]["content"] == expected_aggregated
    ), "Aggregated content must be byte-equivalent to original concatenation"
    cm = handoff_results[0].get("chunking_metadata") or {}
    assert cm.get("aggregated_from_chunks") is True
    # F-r2-5 dual-field shape: complete reassembly → advertised == found
    assert (
        cm.get("total_chunks_advertised") == 5
    ), "Original advertised count must be preserved as total_chunks_advertised"
    assert (
        cm.get("total_chunks") == 5
    ), "total_chunks reflects siblings actually concatenated (5 of 5 = complete)"


# ─── T3: Missing siblings — fallback returns the trigger chunk + WARN ───────


def test_T3_missing_siblings_partial_aggregation_warns(
    qdrant_inmemory, mock_embedding, monkeypatch, caplog
):
    """If only 3 of 5 advertised siblings are present, aggregation produces
    partial content + emits ``bootstrap_aggregation_partial`` WARN; never
    crashes bootstrap.
    """
    import logging

    from memory.injection import retrieve_bootstrap_context

    group_id = "test-td518-t3"
    created_at = "2026-05-09T10:10:00Z"
    # Insert 3 chunks but advertise total_chunks=5 (drift / loss case).
    chunk_bodies = [
        "Chunk0 prefix.\n",
        "Chunk1 middle.\n",
        "Chunk2 fragment.\n",
    ]
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=chunk_bodies,
        total_chunks=5,  # advertise more than present
    )

    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    with caplog.at_level(logging.WARNING, logger="ai_memory.injection"):
        results, _meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert (
        len(handoff_results) == 1
    ), "Bootstrap must remain functional under partial aggregation"
    # All 3 found chunks concatenated
    assert handoff_results[0]["content"] == "".join(chunk_bodies)
    # F-r2-5 dual-field shape: drift visible in result metadata, not just WARN
    cm = handoff_results[0].get("chunking_metadata") or {}
    assert cm.get("total_chunks_advertised") == 5, (
        "Original advertised count (5) preserved as total_chunks_advertised "
        "for drift detection"
    )
    assert (
        cm.get("total_chunks") == 3
    ), "total_chunks reflects siblings actually found (3 of 5 = partial)"
    # Partial WARN emitted
    warn_messages = [r.message for r in caplog.records]
    assert any(
        "bootstrap_aggregation_partial" in m for m in warn_messages
    ), f"Expected bootstrap_aggregation_partial WARN; got {warn_messages!r}"


# ─── T4: Out-of-order insertion — chunk_index sort enforces order ──────────


def test_T4_chunks_sorted_by_chunk_index(qdrant_inmemory, mock_embedding, monkeypatch):
    """Even if chunks were upserted out of insertion order, the aggregated
    content must be in chunk_index ascending order.
    """
    from qdrant_client.models import PointStruct

    from memory.injection import retrieve_bootstrap_context

    group_id = "test-td518-t4"
    created_at = "2026-05-09T10:15:00Z"
    bodies_in_index_order = [
        "[0] head.\n",
        "[1] body1.\n",
        "[2] body2.\n",
        "[3] tail.\n",
    ]
    # Upsert in a deliberately scrambled order (3, 0, 2, 1).
    insertion_order = [3, 0, 2, 1]
    points = []
    for _ins_idx, idx in enumerate(insertion_order):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=FIXED_VECTOR,
                payload={
                    "content": bodies_in_index_order[idx],
                    "type": "agent_handoff",
                    "agent_id": "parzival",
                    "group_id": group_id,
                    "created_at": created_at,
                    "timestamp": created_at,
                    "chunking_metadata": {
                        "chunk_type": "prose",
                        "chunk_index": idx,
                        "total_chunks": 4,
                    },
                },
            )
        )
    qdrant_inmemory.upsert(collection_name="discussions", points=points)

    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    results, _meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert len(handoff_results) == 1
    assert handoff_results[0]["content"] == "".join(
        bodies_in_index_order
    ), "Aggregated content must respect chunk_index order regardless of insertion order"


# ─── T5: aggregated_from_chunks diagnostic field set ────────────────────────


def test_T5_aggregated_from_chunks_diagnostic_field(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """The aggregated result must expose ``chunking_metadata.aggregated_from_chunks=True``
    and ``chunk_type='whole_aggregated'`` for diagnostic visibility — operators
    and Parzival can detect at-a-glance whether reassembly occurred.
    """
    from memory.injection import retrieve_bootstrap_context

    group_id = "test-td518-t5"
    created_at = "2026-05-09T10:20:00Z"
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=["A.\n", "B.\n", "C.\n"],
        total_chunks=3,
    )

    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    results, _meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert len(handoff_results) == 1
    cm = handoff_results[0].get("chunking_metadata") or {}
    assert cm.get("aggregated_from_chunks") is True
    assert cm.get("chunk_type") == "whole_aggregated"
    assert cm.get("total_chunks") == 3
    # F-r2-5 dual-field shape: complete reassembly preserves both counts
    assert cm.get("total_chunks_advertised") == 3


# ─── T6: collection-aware aggregation (F-r2-4) ──────────────────────────────


def test_T6_aggregation_uses_result_collection_field(qdrant_inmemory, mock_embedding):
    """F-r2-4: ``_aggregate_chunked_result`` must scroll the collection
    indicated by ``result.get("collection")``, not the hardcoded
    ``COLLECTION_DISCUSSIONS``. This makes the helper truly type-agnostic
    for future emit types that route to non-discussions collections.

    Synthetic test: insert 3 chunks into a freshly-created secondary
    collection (``code-patterns``), call the helper directly with a
    synthetic trigger result naming that collection, and assert the helper
    found and aggregated all 3 (would return original chunk if it had
    scrolled discussions instead).
    """
    from qdrant_client.models import Distance, VectorParams

    from memory.injection import _aggregate_chunked_result

    # Set up a secondary collection (not discussions) — synthetic future-type case.
    secondary_collection = "code-patterns"
    qdrant_inmemory.create_collection(
        collection_name=secondary_collection,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )

    group_id = "test-td518-t6-collection-aware"
    created_at = "2026-05-09T10:25:00Z"
    chunk_bodies = [
        "Secondary-collection chunk 0.\n",
        "Secondary-collection chunk 1.\n",
        "Secondary-collection chunk 2.\n",
    ]
    points = []
    for idx, content in enumerate(chunk_bodies):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=FIXED_VECTOR,
                payload={
                    "content": content,
                    "type": "future_type_example",
                    "agent_id": "parzival",
                    "group_id": group_id,
                    "created_at": created_at,
                    "timestamp": created_at,
                    "chunking_metadata": {
                        "chunk_type": "prose",
                        "chunk_index": idx,
                        "total_chunks": 3,
                    },
                },
            )
        )
    qdrant_inmemory.upsert(collection_name=secondary_collection, points=points)

    # Synthetic trigger result, as if a future Layer X retrieval had returned
    # one of the 3 chunks from code-patterns. Critically, sets `collection`.
    trigger_result = {
        "content": chunk_bodies[1],
        "type": "future_type_example",
        "agent_id": "parzival",
        "group_id": group_id,
        "created_at": created_at,
        "timestamp": created_at,
        "collection": secondary_collection,  # <-- the F-r2-4 contract field
        "chunking_metadata": {
            "chunk_type": "prose",
            "chunk_index": 1,
            "total_chunks": 3,
        },
    }

    aggregated = _aggregate_chunked_result(qdrant_inmemory, trigger_result)

    # If the helper had scrolled COLLECTION_DISCUSSIONS (pre-F-r2-4), the
    # scroll would return zero points → aggregation falls back to original
    # trigger chunk → content == chunk_bodies[1] (the trigger's own content)
    # and aggregated_from_chunks would be missing/False.
    assert aggregated["content"] == "".join(chunk_bodies), (
        "Helper must scroll the collection from result['collection'], not "
        "the hardcoded COLLECTION_DISCUSSIONS. If this fails with content == "
        "chunk_bodies[1] only, the F-r2-4 collection-aware fix has regressed."
    )
    cm = aggregated.get("chunking_metadata") or {}
    assert cm.get("aggregated_from_chunks") is True
    assert cm.get("total_chunks_advertised") == 3
    assert cm.get("total_chunks") == 3


def test_T7_aggregation_default_collection_when_field_missing(
    qdrant_inmemory, mock_embedding
):
    """F-r2-4 backward-compat: when the result dict lacks a ``collection``
    key entirely, the helper must default to ``COLLECTION_DISCUSSIONS``
    (same behavior as pre-F-r2-4). Defensive guard against any caller
    whose result format omits the field.
    """
    from memory.injection import _aggregate_chunked_result

    group_id = "test-td518-t7-default-collection"
    created_at = "2026-05-09T10:30:00Z"
    chunk_bodies = ["Default-collection chunk 0.\n", "Default-collection chunk 1.\n"]
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=chunk_bodies,
        total_chunks=2,
    )

    # Trigger result WITHOUT a `collection` key — pre-F-r2-4 caller shape.
    trigger_result = {
        "content": chunk_bodies[0],
        "type": "agent_handoff",
        "agent_id": "parzival",
        "group_id": group_id,
        "created_at": created_at,
        "timestamp": created_at,
        # no `collection` field
        "chunking_metadata": {
            "chunk_type": "prose",
            "chunk_index": 0,
            "total_chunks": 2,
        },
    }

    aggregated = _aggregate_chunked_result(qdrant_inmemory, trigger_result)

    # Defaults to discussions → finds the 2 inserted chunks → aggregates.
    assert aggregated["content"] == "".join(chunk_bodies)
    cm = aggregated.get("chunking_metadata") or {}
    assert cm.get("aggregated_from_chunks") is True
    assert cm.get("total_chunks_advertised") == 2
    assert cm.get("total_chunks") == 2
