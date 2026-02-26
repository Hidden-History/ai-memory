"""Unit tests for storage module.

Tests MemoryStorage with mocked dependencies (Qdrant, embedding service).
Implements Story 1.5 Task 5.
"""

from unittest.mock import MagicMock, Mock

import pytest

from src.memory.embeddings import EmbeddingError
from src.memory.models import MemoryType
from src.memory.qdrant_client import QdrantUnavailable
from src.memory.storage import MemoryStorage


@pytest.fixture(autouse=True)
def _disable_detect_secrets(monkeypatch):
    """Disable detect-secrets in CI to prevent Layer 2 entropy scanning from blocking test content."""
    from src.memory import security_scanner

    monkeypatch.setattr(security_scanner, "_detect_secrets_available", False)


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration."""
    mock_cfg = Mock()
    mock_cfg.qdrant_host = "localhost"
    mock_cfg.qdrant_port = 26350
    mock_cfg.embedding_host = "localhost"
    mock_cfg.embedding_port = 28080
    monkeypatch.setattr("src.memory.storage.get_config", lambda: mock_cfg)
    return mock_cfg


@pytest.fixture
def mock_qdrant_client(monkeypatch):
    """Mock Qdrant client."""
    mock_client = Mock()
    mock_client.upsert = Mock()
    mock_client.scroll = Mock(return_value=([], None))
    monkeypatch.setattr("src.memory.storage.get_qdrant_client", lambda x: mock_client)
    return mock_client


@pytest.fixture
def mock_embedding_client(monkeypatch):
    """Mock embedding client."""
    mock_ec = Mock()
    mock_ec.embed = Mock(return_value=[[0.1] * 768])
    monkeypatch.setattr("src.memory.storage.EmbeddingClient", lambda x: mock_ec)
    return mock_ec


def test_store_memory_success(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """Test successful memory storage (AC 1.5.1)."""
    # Mock detect_project to avoid real project detection (imported inside store_memory)
    mock_detect = Mock(return_value="test-project")
    monkeypatch.setattr("src.memory.project.detect_project", mock_detect)

    storage = MemoryStorage()
    result = storage.store_memory(
        content="Test implementation code",
        cwd=str(tmp_path),  # Story 4.2: cwd now required
        group_id="test-project",  # Can still explicitly override
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="PostToolUse",
        session_id="sess-123",
    )

    assert result["status"] == "stored"
    assert result["memory_id"] is not None
    assert result["embedding_status"] == "complete"
    mock_embedding_client.embed.assert_called_once()
    mock_qdrant_client.upsert.assert_called_once()

    # Verify stored point payload contains timestamp in ISO datetime format (stored_at)
    upsert_call = mock_qdrant_client.upsert.call_args
    stored_point = upsert_call[1]["points"][0]
    assert "timestamp" in stored_point.payload
    from datetime import datetime

    datetime.fromisoformat(stored_point.payload["timestamp"])  # Validates ISO format


def test_store_memory_embedding_failure(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """Test storage with embedding failure - graceful degradation (AC 1.5.4)."""
    mock_embedding_client.embed.side_effect = EmbeddingError("Service down")
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "test-project")

    storage = MemoryStorage()
    result = storage.store_memory(
        content="Test content with embedding failure",
        cwd=str(tmp_path),  # Story 4.2: cwd now required
        group_id="test-project",
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="PostToolUse",
        session_id="sess-123",
    )

    assert result["status"] == "stored"
    assert result["embedding_status"] == "pending"
    # Verify zero vector used as placeholder
    call_args = mock_qdrant_client.upsert.call_args
    assert call_args[1]["points"][0].vector == [0.0] * 768


def test_store_memory_qdrant_failure(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """Test Qdrant failure raises exception (AC 1.5.4)."""
    mock_qdrant_client.upsert.side_effect = Exception("Connection refused")
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "proj")

    storage = MemoryStorage()
    with pytest.raises(QdrantUnavailable, match="Failed to store"):
        storage.store_memory(
            content="Test content",
            cwd=str(tmp_path),  # Story 4.2: cwd now required
            group_id="proj",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="sess",
        )


def test_store_memory_duplicate(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """Test duplicate detection skips storage and returns existing memory_id (AC 1.5.3)."""
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "test-project")
    # Mock metrics to avoid Prometheus label errors in tests
    monkeypatch.setattr("src.memory.storage.deduplication_events_total", MagicMock())

    storage = MemoryStorage()

    # Patch qdrant_client on instance AFTER creation to ensure mock is used
    existing_point = MagicMock()
    existing_point.id = "existing-uuid-12345"
    storage.qdrant_client = MagicMock()
    storage.qdrant_client.scroll.return_value = ([existing_point], None)
    storage.qdrant_client.upsert = MagicMock()

    result = storage.store_memory(
        content="Duplicate content",
        cwd=str(tmp_path),  # Story 4.2: cwd now required
        group_id="test-project",
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="PostToolUse",
        session_id="sess-123",
    )

    assert result["status"] == "duplicate"
    assert (
        result["memory_id"] == "existing-uuid-12345"
    )  # AC 1.5.3: Returns existing memory_id
    storage.qdrant_client.upsert.assert_not_called()


def test_store_memory_validation_failure(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """Test validation failure raises ValueError."""
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "test-project")

    storage = MemoryStorage()
    with pytest.raises(ValueError, match="Validation failed"):
        storage.store_memory(
            content="",  # Empty content - should fail validation
            cwd=str(tmp_path),  # Story 4.2: cwd now required
            group_id="test-project",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="sess-123",
        )


def test_store_memories_batch(mock_config, mock_qdrant_client, mock_embedding_client):
    """Test batch storage (AC 1.5.2)."""
    mock_embedding_client.embed.return_value = [[0.1] * 768, [0.2] * 768]

    memories = [
        {
            "content": "Memory 1 implementation",
            "group_id": "proj",
            "type": MemoryType.IMPLEMENTATION.value,
            "source_hook": "PostToolUse",
            "session_id": "sess",
        },
        {
            "content": "Memory 2 implementation",
            "group_id": "proj",
            "type": MemoryType.IMPLEMENTATION.value,
            "source_hook": "PostToolUse",
            "session_id": "sess",
        },
    ]

    storage = MemoryStorage()
    results = storage.store_memories_batch(memories)

    assert len(results) == 2
    assert all(r["status"] == "stored" for r in results)
    # SPEC-010: embed() now includes model parameter
    mock_embedding_client.embed.assert_called_once_with(
        ["Memory 1 implementation", "Memory 2 implementation"],
        model="code",  # code-patterns collection uses code model
    )
    mock_qdrant_client.upsert.assert_called_once()


def test_store_memories_batch_mixed_content_types(
    mock_config, mock_qdrant_client, mock_embedding_client
):
    """Test batch storage groups memories by embedding model (H-1 fix).

    Mixed batches with different content_type values should route to
    the correct embedding model per SPEC-010.
    """
    # Track calls with their model arg
    call_log = []

    def mock_embed(texts, model="en"):
        call_log.append({"texts": texts, "model": model})
        return [[0.1] * 768 for _ in texts]

    mock_embedding_client.embed.side_effect = mock_embed

    memories = [
        {
            "content": "Normal prose memory content here",
            "group_id": "proj",
            "type": MemoryType.IMPLEMENTATION.value,
            "source_hook": "PostToolUse",
            "session_id": "sess",
            # No content_type → code-patterns defaults to "code"
        },
        {
            "content": "Code blob from GitHub sync",
            "group_id": "proj",
            "type": MemoryType.IMPLEMENTATION.value,
            "source_hook": "PostToolUse",
            "session_id": "sess",
            "content_type": "github_code_blob",  # Should route to "code"
        },
    ]

    storage = MemoryStorage()
    results = storage.store_memories_batch(memories, collection="code-patterns")

    assert len(results) == 2
    assert all(r["status"] == "stored" for r in results)
    # Both should use "code" model for code-patterns collection
    assert all(c["model"] == "code" for c in call_log)


def test_store_memories_batch_embedding_failure(
    mock_config, mock_qdrant_client, mock_embedding_client
):
    """Test batch storage with embedding failure - graceful degradation (AC 1.5.4)."""
    mock_embedding_client.embed.side_effect = EmbeddingError("Service down")

    memories = [
        {
            "content": "Memory 1 with enough content to pass validation",
            "group_id": "proj",
            "type": MemoryType.IMPLEMENTATION.value,
            "source_hook": "PostToolUse",
            "session_id": "sess",
        },
    ]

    storage = MemoryStorage()
    results = storage.store_memories_batch(memories)

    assert len(results) == 1
    assert results[0]["embedding_status"] == "pending"
    # Verify zero vectors used
    call_args = mock_qdrant_client.upsert.call_args
    assert all(p.vector == [0.0] * 768 for p in call_args[1]["points"])


def test_check_duplicate_found(
    mock_config, mock_qdrant_client, mock_embedding_client, monkeypatch
):
    """Test duplicate check returns existing memory_id when hash exists."""
    # Mock metrics to avoid Prometheus label errors in tests
    monkeypatch.setattr("src.memory.storage.deduplication_events_total", MagicMock())

    storage = MemoryStorage()

    # Patch qdrant_client on instance AFTER creation to ensure mock is used
    existing_point = MagicMock()
    existing_point.id = "found-memory-uuid"
    storage.qdrant_client = MagicMock()
    storage.qdrant_client.scroll.return_value = ([existing_point], None)

    existing_id = storage._check_duplicate("hash123", "code-patterns", "test-project")

    assert existing_id == "found-memory-uuid"


def test_check_duplicate_not_found(
    mock_config, mock_qdrant_client, mock_embedding_client
):
    """Test duplicate check returns None when hash not found."""
    mock_qdrant_client.scroll.return_value = ([], None)

    storage = MemoryStorage()
    existing_id = storage._check_duplicate("hash456", "code-patterns", "test-project")

    assert existing_id is None


def test_check_duplicate_query_failure(
    mock_config, mock_qdrant_client, mock_embedding_client
):
    """Test duplicate check fails open when query fails."""
    mock_qdrant_client.scroll.side_effect = Exception("Query error")

    storage = MemoryStorage()
    existing_id = storage._check_duplicate("hash789", "code-patterns", "test-project")

    # Should fail open - allow storage if check fails (returns None)
    assert existing_id is None


# =============================================================================
# BUG-109: store_memory passes source_type through to scanner
# =============================================================================


def test_store_memory_passes_source_type_to_scanner(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """BUG-109: Verify source_type is forwarded to SecurityScanner.scan()."""
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "test-project")

    storage = MemoryStorage()

    # Replace the scanner with a mock to capture the source_type argument
    mock_scanner = MagicMock()
    mock_scan_result = MagicMock()
    mock_scan_result.action = MagicMock()
    mock_scan_result.action.__eq__ = lambda self, other: False  # Not BLOCKED
    mock_scan_result.content = "Test content for source_type forwarding"
    mock_scanner.scan.return_value = mock_scan_result
    storage._scanner = mock_scanner

    storage.store_memory(
        content="Test content for source_type forwarding",
        cwd=str(tmp_path),
        group_id="test-project",
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="github_sync",
        session_id="sess-109",
        source_type="github_issue",
    )

    # Verify scanner.scan() was called with source_type="github_issue"
    mock_scanner.scan.assert_called_once_with(
        "Test content for source_type forwarding",
        source_type="github_issue",
    )


def test_store_memory_defaults_source_type_to_user_session(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """BUG-109: Verify source_type defaults to 'user_session' when not provided."""
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "test-project")

    storage = MemoryStorage()

    mock_scanner = MagicMock()
    mock_scan_result = MagicMock()
    mock_scan_result.action = MagicMock()
    mock_scan_result.action.__eq__ = lambda self, other: False
    mock_scan_result.content = "Test content default source_type"
    mock_scanner.scan.return_value = mock_scan_result
    storage._scanner = mock_scanner

    storage.store_memory(
        content="Test content default source_type",
        cwd=str(tmp_path),
        group_id="test-project",
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="PostToolUse",
        session_id="sess-109b",
        # No source_type — should default to "user_session"
    )

    mock_scanner.scan.assert_called_once_with(
        "Test content default source_type",
        source_type="user_session",
    )


def test_store_memories_batch_passes_source_type(
    mock_config, mock_qdrant_client, mock_embedding_client, monkeypatch
):
    """BUG-109: Verify store_memories_batch forwards source_type to scanner."""
    mock_embedding_client.embed.return_value = [[0.1] * 768]

    storage = MemoryStorage()

    mock_scanner = MagicMock()
    mock_scan_result = MagicMock()
    mock_scan_result.action = MagicMock()
    mock_scan_result.action.__eq__ = lambda self, other: False
    mock_scan_result.content = "Batch content with source_type"
    mock_scanner.scan.return_value = mock_scan_result
    storage._scanner = mock_scanner

    memories = [
        {
            "content": "Batch content with source_type",
            "group_id": "proj",
            "type": MemoryType.IMPLEMENTATION.value,
            "source_hook": "github_sync",
            "session_id": "sess",
        },
    ]

    storage.store_memories_batch(memories, source_type="github_pr")

    # Verify scanner.scan() was called with the forwarded source_type
    mock_scanner.scan.assert_called_once_with(
        "Batch content with source_type",
        force_ner=True,
        source_type="github_pr",
    )


def test_github_content_not_double_blocked(
    mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch
):
    """BUG-109 integration: GitHub content with QDRANT_API_KEY discussion should NOT be blocked in relaxed mode."""
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "test-project")
    # Disable detect-secrets so only Layer 1 regex runs (already done by autouse fixture)

    storage = MemoryStorage()

    # Content that discusses API keys without containing real secrets
    content = "Configure QDRANT_API_KEY in your .env file. The GITHUB_TOKEN variable is also needed."
    result = storage.store_memory(
        content=content,
        cwd=str(tmp_path),
        group_id="test-project",
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="github_sync",
        session_id="sess-integration",
        source_type="github_issue",  # BUG-109: Pass through source_type
    )

    # This content does NOT contain real secrets (no ghp_*, AKIA*, etc.)
    # Layer 1 regex should NOT block it, and Layer 2 is skipped for github_ in relaxed mode
    assert result["status"] in ("stored", "duplicate"), (
        f"Expected stored/duplicate but got {result['status']}. "
        f"GitHub content discussing env vars should not be blocked when source_type is passed."
    )


# =============================================================================
# Unit tests for MemoryStorage stats wrapper methods (Review Finding #4)
# =============================================================================


class TestMemoryStorageStats:
    """Tests for MemoryStorage.get_collection_stats(), get_unique_field_values(),
    and get_last_updated() wrapper methods."""

    def test_get_collection_stats_returns_all_core_collections(
        self, mock_config, mock_qdrant_client
    ):
        """Stats should include all 3 core collections."""
        mock_info = Mock()
        mock_info.points_count = 100
        mock_info.vectors_count = 100
        mock_info.status = Mock()
        mock_info.status.value = "green"

        def _get_collection_side_effect(name):
            if name == "jira-data":
                raise Exception("not found")
            return mock_info

        mock_qdrant_client.get_collection.side_effect = _get_collection_side_effect

        storage = MemoryStorage()
        stats = storage.get_collection_stats()

        assert "code-patterns" in stats
        assert "conventions" in stats
        assert "discussions" in stats
        assert "jira-data" not in stats

    def test_get_collection_stats_includes_jira_data_when_exists(
        self, mock_config, mock_qdrant_client
    ):
        """Stats should include jira-data when the collection exists."""
        mock_info = Mock()
        mock_info.points_count = 50
        mock_info.vectors_count = 50
        mock_info.status = Mock()
        mock_info.status.value = "green"

        mock_qdrant_client.get_collection.return_value = mock_info

        storage = MemoryStorage()
        stats = storage.get_collection_stats()

        assert "jira-data" in stats
        assert len(stats) == 4

    def test_get_collection_stats_handles_qdrant_error(
        self, mock_config, mock_qdrant_client
    ):
        """A Qdrant failure for a core collection yields status='error'."""

        def _get_collection_side_effect(name):
            if name == "jira-data":
                raise Exception("not found")
            if name == "code-patterns":
                raise Exception("Qdrant unreachable")
            mock_info = Mock()
            mock_info.points_count = 10
            mock_info.vectors_count = 10
            mock_info.status = Mock()
            mock_info.status.value = "green"
            return mock_info

        mock_qdrant_client.get_collection.side_effect = _get_collection_side_effect

        storage = MemoryStorage()
        stats = storage.get_collection_stats()

        assert stats["code-patterns"]["status"] == "error"
        assert stats["code-patterns"]["points_count"] == 0
        assert stats["code-patterns"]["vectors_count"] == 0

    def test_get_collection_stats_stat_values_present(
        self, mock_config, mock_qdrant_client
    ):
        """Each collection entry must contain points_count, vectors_count, and status."""
        mock_info = Mock()
        mock_info.points_count = 42
        mock_info.vectors_count = 42
        mock_info.status = Mock()
        mock_info.status.value = "green"

        def _get_collection_side_effect(name):
            if name == "jira-data":
                raise Exception("not found")
            return mock_info

        mock_qdrant_client.get_collection.side_effect = _get_collection_side_effect

        storage = MemoryStorage()
        stats = storage.get_collection_stats()

        for info in stats.values():
            assert "points_count" in info
            assert "vectors_count" in info
            assert "status" in info

    def test_get_unique_field_values_with_limit(
        self, mock_config, mock_qdrant_client, monkeypatch
    ):
        """Limit parameter should truncate results."""
        full_list = [f"project-{i}" for i in range(10)]
        monkeypatch.setattr(
            "src.memory.storage._get_unique_field_values",
            lambda client, collection, field: full_list,
        )

        storage = MemoryStorage()
        result = storage.get_unique_field_values("code-patterns", "group_id", limit=5)

        assert len(result) == 5
        assert result == full_list[:5]

    def test_get_unique_field_values_handles_exception(
        self, mock_config, mock_qdrant_client, monkeypatch
    ):
        """Should return empty list when the underlying function raises."""

        def _raise(*args, **kwargs):
            raise Exception("Qdrant scroll failed")

        monkeypatch.setattr("src.memory.storage._get_unique_field_values", _raise)

        storage = MemoryStorage()
        result = storage.get_unique_field_values("code-patterns", "group_id")

        assert result == []

    def test_get_last_updated_delegates_correctly(
        self, mock_config, mock_qdrant_client, monkeypatch
    ):
        """get_last_updated() should delegate to the stats module function."""
        expected = "2026-02-24T10:00:00Z"
        monkeypatch.setattr(
            "src.memory.storage._get_last_updated",
            lambda client, collection: expected,
        )

        storage = MemoryStorage()
        result = storage.get_last_updated("code-patterns")

        assert result == expected

    def test_get_last_updated_returns_none_for_empty(
        self, mock_config, mock_qdrant_client, monkeypatch
    ):
        """Should return None for empty collection."""
        monkeypatch.setattr(
            "src.memory.storage._get_last_updated",
            lambda client, collection: None,
        )

        storage = MemoryStorage()
        result = storage.get_last_updated("code-patterns")

        assert result is None
