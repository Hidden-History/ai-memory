"""Unit tests for memory payload models.

Tests AC 1.3.2 from Story 1.3.
"""

import pytest
from src.memory.models import MemoryPayload, MemoryType, EmbeddingStatus


class TestMemoryType:
    """Test MemoryType enum."""

    def test_memory_types_exist(self):
        """All required memory types are defined."""
        assert MemoryType.IMPLEMENTATION.value == "implementation"
        assert MemoryType.SESSION_SUMMARY.value == "session_summary"
        assert MemoryType.DECISION.value == "decision"
        assert MemoryType.PATTERN.value == "pattern"


class TestEmbeddingStatus:
    """Test EmbeddingStatus enum."""

    def test_embedding_statuses_exist(self):
        """All required embedding statuses are defined."""
        assert EmbeddingStatus.COMPLETE.value == "complete"
        assert EmbeddingStatus.PENDING.value == "pending"
        assert EmbeddingStatus.FAILED.value == "failed"


class TestMemoryPayload:
    """Test MemoryPayload dataclass."""

    def test_memory_payload_required_fields(self):
        """MemoryPayload can be created with required fields only."""
        payload = MemoryPayload(
            content="Test implementation code",
            content_hash="abc123",
            group_id="test-project",
            type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="sess_123",
            timestamp="2026-01-11T00:00:00Z",
        )

        assert payload.content == "Test implementation code"
        assert payload.group_id == "test-project"
        assert payload.type == MemoryType.IMPLEMENTATION
        assert payload.source_hook == "PostToolUse"

    def test_memory_payload_optional_fields_defaults(self):
        """MemoryPayload optional fields have correct defaults."""
        payload = MemoryPayload(
            content="Test",
            content_hash="abc",
            group_id="proj",
            type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="sess_1",
            timestamp="2026-01-11T00:00:00Z",
        )

        assert payload.domain == "general"
        assert payload.importance == "normal"
        assert payload.embedding_status == EmbeddingStatus.COMPLETE
        assert payload.embedding_model == "nomic-embed-code"
        assert payload.relationships == []
        assert payload.tags == []

    def test_memory_payload_to_dict_enum_conversion(self):
        """to_dict() converts enum values to strings."""
        payload = MemoryPayload(
            content="Test implementation",
            content_hash="hash123",
            group_id="test-project",
            type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="sess_123",
            timestamp="2026-01-11T00:00:00Z",
        )

        d = payload.to_dict()

        # Enums should be converted to string values
        assert d["type"] == "implementation"
        assert isinstance(d["type"], str)
        assert d["embedding_status"] == "complete"
        assert isinstance(d["embedding_status"], str)

    def test_memory_payload_to_dict_all_fields(self):
        """to_dict() includes all fields in snake_case."""
        payload = MemoryPayload(
            content="Test content",
            content_hash="hash123",
            group_id="proj-1",
            type=MemoryType.PATTERN,
            source_hook="Stop",
            session_id="sess_456",
            timestamp="2026-01-11T12:00:00Z",
            domain="frontend",
            importance="high",
            embedding_status=EmbeddingStatus.PENDING,
            embedding_model="nomic-embed-code",
            relationships=["mem_1", "mem_2"],
            tags=["react", "hooks"],
        )

        d = payload.to_dict()

        # Verify all fields present with correct snake_case names
        assert d["content"] == "Test content"
        assert d["content_hash"] == "hash123"
        assert d["group_id"] == "proj-1"
        assert d["type"] == "pattern"
        assert d["source_hook"] == "Stop"
        assert d["session_id"] == "sess_456"
        assert d["timestamp"] == "2026-01-11T12:00:00Z"
        assert d["domain"] == "frontend"
        assert d["importance"] == "high"
        assert d["embedding_status"] == "pending"
        assert d["embedding_model"] == "nomic-embed-code"
        assert d["relationships"] == ["mem_1", "mem_2"]
        assert d["tags"] == ["react", "hooks"]

    def test_memory_payload_to_dict_string_type_passthrough(self):
        """to_dict() handles string values for type/status (not just enums)."""
        # This handles cases where payloads are constructed from dicts
        payload = MemoryPayload(
            content="Test",
            content_hash="hash",
            group_id="proj",
            type="implementation",  # String instead of enum
            source_hook="PostToolUse",
            session_id="sess_1",
            timestamp="2026-01-11T00:00:00Z",
        )

        d = payload.to_dict()
        assert d["type"] == "implementation"
        assert isinstance(d["type"], str)
