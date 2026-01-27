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
        assert MemoryType.SESSION.value == "session"
        assert MemoryType.DECISION.value == "decision"
        assert MemoryType.GUIDELINE.value == "guideline"


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
        assert payload.importance == "medium"
        assert payload.embedding_status == EmbeddingStatus.COMPLETE
        assert payload.embedding_model == "jina-embeddings-v2-base-en"
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
            type=MemoryType.GUIDELINE,
            source_hook="Stop",
            session_id="sess_456",
            timestamp="2026-01-11T12:00:00Z",
            domain="frontend",
            importance="high",
            embedding_status=EmbeddingStatus.PENDING,
            embedding_model="jina-embeddings-v2-base-en",
            relationships=["mem_1", "mem_2"],
            tags=["react", "hooks"],
        )

        d = payload.to_dict()

        # Verify all fields present with correct snake_case names
        assert d["content"] == "Test content"
        assert d["content_hash"] == "hash123"
        assert d["group_id"] == "proj-1"
        assert d["type"] == "guideline"
        assert d["source_hook"] == "Stop"
        assert d["session_id"] == "sess_456"
        assert d["timestamp"] == "2026-01-11T12:00:00Z"
        assert d["domain"] == "frontend"
        assert d["importance"] == "high"
        assert d["embedding_status"] == "pending"
        assert d["embedding_model"] == "jina-embeddings-v2-base-en"
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

    def test_memory_payload_research_fields(self):
        """BUG-006: Verify research provenance fields accepted and serialized."""
        payload = MemoryPayload(
            content="Always use explicit timeouts for async HTTP requests",
            content_hash="abc123",
            group_id="shared",
            type=MemoryType.GUIDELINE,
            source_hook="manual",
            session_id="test_session",
            timestamp="2026-01-21T00:00:00Z",
            source="https://docs.python.org/3/library/asyncio.html",
            source_date="2026-01-15",
            auto_seeded=True,
        )

        # Verify fields accepted by constructor
        assert payload.source == "https://docs.python.org/3/library/asyncio.html"
        assert payload.source_date == "2026-01-15"
        assert payload.auto_seeded is True

        # Verify to_dict includes fields
        d = payload.to_dict()
        assert d["source"] == "https://docs.python.org/3/library/asyncio.html"
        assert d["source_date"] == "2026-01-15"
        assert d["auto_seeded"] is True

    def test_memory_payload_research_fields_defaults(self):
        """BUG-006: Research fields have correct defaults when not provided."""
        payload = MemoryPayload(
            content="Test",
            content_hash="hash",
            group_id="proj",
            type=MemoryType.GUIDELINE,
            source_hook="manual",
            session_id="sess_1",
            timestamp="2026-01-21T00:00:00Z",
        )

        # Verify defaults
        assert payload.source is None
        assert payload.source_date is None
        assert payload.auto_seeded is False

        # Verify to_dict behavior with defaults
        d = payload.to_dict()
        assert "source" not in d  # None values excluded
        assert "source_date" not in d  # None values excluded
        assert d["auto_seeded"] is False  # Always included with default
