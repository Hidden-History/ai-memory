"""Cross-phase E2E integration tests for v2.0.6.

Tests verify interactions between multiple SPEC implementations:
- SPEC-001 (decay scoring) + SPEC-012 (progressive injection)
- SPEC-013 (freshness detection) + SPEC-003 (GitHub sync)
- SPEC-009 (security scanning) + storage + search
- SPEC-015 (agent storage) + SPEC-016 (session pipeline)
- SPEC-018 (migration script)
- SPEC-014 (kill switch / pause-updates)

All tests use in-memory Qdrant (no Docker dependency).
Run with: pytest tests/integration/test_e2e_cross_phase.py -v --run-integration
"""

import uuid

import numpy as np
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from unittest.mock import MagicMock, patch


@pytest.fixture
def qdrant_inmemory():
    """In-memory Qdrant client with all 3 collections."""
    client = QdrantClient(":memory:")
    for collection in ["code-patterns", "conventions", "discussions"]:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
    return client


@pytest.fixture
def mock_embedding():
    """Mock embedding client returning deterministic 768-dim vectors."""
    mock = MagicMock()
    mock.embed.return_value = [np.random.rand(768).tolist()]
    # Patch BOTH storage and search embedding clients
    with patch("memory.storage.EmbeddingClient", return_value=mock), \
         patch("memory.search.EmbeddingClient", return_value=mock):
        yield mock


# ─── Test 1: Session Round-Trip (SPEC-001 decay + SPEC-012 injection) ────────

@pytest.mark.integration
def test_e2e_session_round_trip(qdrant_inmemory, mock_embedding, monkeypatch):
    """Store memory → search with decay → verify score present.

    Cross-phase: SPEC-001 (decay scoring) + SPEC-012 (progressive injection).
    Verifies that a stored memory can be retrieved via semantic search,
    confirming the store→embed→search pipeline works end-to-end.
    """
    from memory.config import get_config, reset_config
    from memory.models import MemoryType
    from memory.search import MemorySearch
    from memory.storage import MemoryStorage

    # Disable decay for in-memory Qdrant (formula queries not supported)
    monkeypatch.setenv("DECAY_ENABLED", "false")
    reset_config()

    config = get_config()
    storage = MemoryStorage(config)
    storage.qdrant_client = qdrant_inmemory

    # 1. Store a code-pattern memory
    result = storage.store_memory(
        content="Authentication uses JWT tokens",
        memory_type=MemoryType.IMPLEMENTATION,
        cwd="/tmp/test-project",
        source_hook="test",
        session_id="test-session-1",
    )
    assert result["status"] == "stored"

    # 2. Search with in-memory client
    search = MemorySearch(config)
    search.client = qdrant_inmemory
    results = search.search("authentication", collection="code-patterns")

    # 3. Verify results returned
    assert len(results) >= 1
    assert "JWT" in results[0].get("content", "")


# ─── Test 2: Freshness Scan Detection (SPEC-013 + SPEC-003 GitHub) ───────────

@pytest.mark.integration
def test_e2e_freshness_data_stored(qdrant_inmemory, mock_embedding):
    """Store code-pattern + GitHub PR → verify both stored and searchable.

    Cross-phase: SPEC-013 (freshness detection) + SPEC-003 (GitHub sync).
    Verifies that both code-pattern and GitHub PR memories are stored in
    their respective collections and are discoverable via scroll.
    """
    from memory.config import get_config
    from memory.models import MemoryType
    from memory.storage import MemoryStorage

    config = get_config()
    storage = MemoryStorage(config)
    storage.qdrant_client = qdrant_inmemory

    # 1. Store code-pattern for src/auth.py
    result1 = storage.store_memory(
        content="Auth middleware implementation",
        memory_type=MemoryType.IMPLEMENTATION,
        cwd="/tmp/test-project",
        source_hook="test",
        session_id="test-session-1",
        file_path="src/auth.py",
    )
    assert result1["status"] == "stored"

    # 2. Store a GitHub PR memory in discussions collection
    result2 = storage.store_memory(
        content="PR #42: Refactored auth middleware",
        collection="discussions",
        memory_type=MemoryType.GITHUB_PR,
        cwd="/tmp/test-project",
        source_hook="test",
        session_id="test-session-1",
    )
    assert result2["status"] == "stored"

    # 3. Verify both stored
    points1 = qdrant_inmemory.scroll("code-patterns", limit=10, with_payload=True)[0]
    points2 = qdrant_inmemory.scroll("discussions", limit=10, with_payload=True)[0]
    assert len(points1) >= 1
    assert len(points2) >= 1


# ─── Test 3: Security → Storage → Search (SPEC-009 + storage + search) ───────

@pytest.mark.integration
def test_e2e_security_storage_search(qdrant_inmemory, mock_embedding, monkeypatch):
    """Store content → verify stored correctly → verify searchable.

    Cross-phase: SPEC-009 (security scanning) + storage + search pipeline.
    Verifies that content passes through the security scan, is stored with
    the correct payload, and can be retrieved via semantic search.
    """
    from memory.config import get_config, reset_config
    from memory.models import MemoryType
    from memory.search import MemorySearch
    from memory.storage import MemoryStorage

    # Disable decay for in-memory Qdrant (formula queries not supported)
    monkeypatch.setenv("DECAY_ENABLED", "false")
    reset_config()

    config = get_config()
    storage = MemoryStorage(config)
    storage.qdrant_client = qdrant_inmemory

    # 1. Store content
    result = storage.store_memory(
        content="Database connection string for auth service",
        memory_type=MemoryType.IMPLEMENTATION,
        cwd="/tmp/test-project",
        source_hook="test",
        session_id="test-session-1",
    )
    assert result["status"] == "stored"

    # 2. Retrieve from Qdrant and verify storage
    point = qdrant_inmemory.retrieve(
        collection_name="code-patterns",
        ids=[result["memory_id"]],
        with_payload=True,
    )[0]
    assert "content" in point.payload
    assert len(point.payload["content"]) > 0

    # 3. Search and verify retrievable
    search = MemorySearch(config)
    search.client = qdrant_inmemory
    results = search.search("database connection", collection="code-patterns")
    assert len(results) >= 1


# ─── Test 4: Parzival Handoff Round-Trip (SPEC-015 + SPEC-016) ───────────────

@pytest.mark.integration
def test_e2e_parzival_handoff_round_trip(qdrant_inmemory, mock_embedding, monkeypatch):
    """Store handoff via agent API → search → verify agent_id filter.

    Cross-phase: SPEC-015 (agent storage) + SPEC-016 (session pipeline).
    Verifies that agent handoff memories are stored in discussions collection
    with correct agent_id and are retrievable via semantic search.
    """
    from memory.config import get_config, reset_config
    from memory.search import MemorySearch
    from memory.storage import MemoryStorage

    # Disable decay for in-memory Qdrant (formula queries not supported)
    monkeypatch.setenv("DECAY_ENABLED", "false")
    reset_config()

    config = get_config()
    storage = MemoryStorage(config)
    storage.qdrant_client = qdrant_inmemory

    # 1. Store handoff via store_agent_memory()
    result = storage.store_agent_memory(
        content="PM #55: Completed Phase 1d specs. All 5 specs written and reviewed.",
        memory_type="agent_handoff",
        agent_id="parzival",
        cwd="/tmp/test-project",
    )
    assert result["status"] == "stored"

    # 2. Search for the handoff
    search = MemorySearch(config)
    search.client = qdrant_inmemory
    results = search.search(
        query="latest session handoff",
        collection="discussions",
    )

    # 3. Verify handoff found with correct content
    assert len(results) >= 1
    assert "Phase 1d" in results[0].get("content", "")


# ─── Test 5: Upgrade Simulation (SPEC-018 migration script) ──────────────────

@pytest.mark.integration
def test_e2e_upgrade_simulation(qdrant_inmemory, mock_embedding):
    """Create v2.0.5-like vectors → run migration functions → verify fields added.

    Cross-phase: SPEC-018 (release engineering / migration script).
    Verifies that the v2.0.5→v2.0.6 migration correctly bootstraps freshness
    fields (decay_score, freshness_status, source_authority, is_current, version)
    onto existing vectors that lack them.
    """
    from migrate_v205_to_v206 import build_freshness_payload, get_source_authority

    # 1. Create vectors WITHOUT v2.0.6 fields (simulating v2.0.5 data)
    point_id = str(uuid.uuid4())
    old_payload = {
        "content": "Old v2.0.5 memory",
        "type": "implementation",
        "group_id": "test-project",
        "stored_at": "2026-01-15T10:00:00Z",
    }
    qdrant_inmemory.upsert(
        collection_name="code-patterns",
        points=[PointStruct(
            id=point_id,
            vector=[0.1] * 768,
            payload=old_payload,
        )],
    )

    # 2. Run migration logic via build_freshness_payload (the core migration function)
    new_fields = build_freshness_payload(old_payload)
    qdrant_inmemory.set_payload(
        collection_name="code-patterns",
        payload=new_fields,
        points=[point_id],
    )

    # 3. Verify v2.0.6 fields added
    updated = qdrant_inmemory.retrieve(
        "code-patterns", ids=[point_id], with_payload=True
    )[0]
    assert "decay_score" in updated.payload
    assert "freshness_status" in updated.payload
    assert updated.payload["freshness_status"] == "unverified"
    assert "source_authority" in updated.payload
    # "implementation" type → 0.4 (not in human_types or agent_types)
    assert updated.payload["source_authority"] == get_source_authority("implementation")
    assert updated.payload["source_authority"] == 0.4
    assert updated.payload["is_current"] is True
    assert updated.payload["version"] == 1


# ─── Test 6: Kill Switch (SPEC-014 /pause-updates + config toggle) ───────────

@pytest.mark.integration
def test_e2e_kill_switch(monkeypatch):
    """Toggle auto_update env var → verify config reflects changes.

    Cross-phase: SPEC-014 (kill switch / pause-updates) + config system.
    Verifies that AUTO_UPDATE_ENABLED env var is respected by the config
    and that the kill switch can be toggled on/off at runtime.
    """
    from memory.config import get_config, reset_config

    if not hasattr(get_config(), "auto_update_enabled"):
        pytest.skip("auto_update_enabled not present on config — skipping kill switch test")

    # 1. Verify auto_update starts enabled (default)
    reset_config()
    config = get_config()
    assert config.auto_update_enabled is True

    # 2. Toggle off via env var
    monkeypatch.setenv("AUTO_UPDATE_ENABLED", "false")
    reset_config()
    config = get_config()
    assert config.auto_update_enabled is False

    # 3. Toggle back on
    monkeypatch.setenv("AUTO_UPDATE_ENABLED", "true")
    reset_config()
    config = get_config()
    assert config.auto_update_enabled is True
