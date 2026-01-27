"""Unit tests for storage module.

Tests MemoryStorage with mocked dependencies (Qdrant, embedding service).
Implements Story 1.5 Task 5.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from src.memory.storage import MemoryStorage
from src.memory.models import MemoryType, EmbeddingStatus
from src.memory.embeddings import EmbeddingError
from src.memory.qdrant_client import QdrantUnavailable
from src.memory.validation import ValidationError


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


def test_store_memory_success(mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch):
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


def test_store_memory_embedding_failure(mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch):
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


def test_store_memory_qdrant_failure(mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch):
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


def test_store_memory_duplicate(mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch):
    """Test duplicate detection skips storage and returns existing memory_id (AC 1.5.3)."""
    # Mock scroll to return existing memory with ID
    existing_point = Mock()
    existing_point.id = "existing-uuid-12345"
    mock_qdrant_client.scroll.return_value = ([existing_point], None)
    monkeypatch.setattr("src.memory.project.detect_project", lambda cwd: "test-project")

    storage = MemoryStorage()
    result = storage.store_memory(
        content="Duplicate content",
        cwd=str(tmp_path),  # Story 4.2: cwd now required
        group_id="test-project",
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="PostToolUse",
        session_id="sess-123",
    )

    assert result["status"] == "duplicate"
    assert result["memory_id"] == "existing-uuid-12345"  # AC 1.5.3: Returns existing memory_id
    mock_qdrant_client.upsert.assert_not_called()


def test_store_memory_validation_failure(mock_config, mock_qdrant_client, mock_embedding_client, tmp_path, monkeypatch):
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
    mock_embedding_client.embed.assert_called_once_with(
        ["Memory 1 implementation", "Memory 2 implementation"]
    )
    mock_qdrant_client.upsert.assert_called_once()


def test_store_memories_batch_embedding_failure(mock_config, mock_qdrant_client, mock_embedding_client):
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


def test_check_duplicate_found(mock_config, mock_qdrant_client, mock_embedding_client):
    """Test duplicate check returns existing memory_id when hash exists."""
    existing_point = Mock()
    existing_point.id = "found-memory-uuid"
    mock_qdrant_client.scroll.return_value = ([existing_point], None)

    storage = MemoryStorage()
    existing_id = storage._check_duplicate("hash123", "code-patterns", "test-project")

    assert existing_id == "found-memory-uuid"


def test_check_duplicate_not_found(mock_config, mock_qdrant_client, mock_embedding_client):
    """Test duplicate check returns None when hash not found."""
    mock_qdrant_client.scroll.return_value = ([], None)

    storage = MemoryStorage()
    existing_id = storage._check_duplicate("hash456", "code-patterns", "test-project")

    assert existing_id is None


def test_check_duplicate_query_failure(mock_config, mock_qdrant_client, mock_embedding_client):
    """Test duplicate check fails open when query fails."""
    mock_qdrant_client.scroll.side_effect = Exception("Query error")

    storage = MemoryStorage()
    existing_id = storage._check_duplicate("hash789", "code-patterns", "test-project")

    # Should fail open - allow storage if check fails (returns None)
    assert existing_id is None
