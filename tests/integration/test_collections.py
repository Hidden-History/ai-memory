"""Integration tests for Qdrant collection creation and schema validation.

Tests AC 1.3.1, 1.3.2, 1.3.3, 1.3.4 from Story 1.3.
"""

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
from src.memory.models import MemoryPayload, MemoryType, EmbeddingStatus
from src.memory.validation import validate_payload, compute_content_hash


class TestCollectionSchema:
    """Test Qdrant collection creation and schema validation."""

    @pytest.fixture
    def qdrant_client(self):
        """Qdrant client connected to test instance."""
        return QdrantClient(host="localhost", port=26350)

    def test_collections_exist(self, qdrant_client):
        """Both collections exist after running setup script (AC 1.3.1)."""
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        assert "implementations" in collection_names, "implementations collection not found"
        assert "best_practices" in collection_names, "best_practices collection not found"

    def test_collection_vector_config(self, qdrant_client):
        """Collections have correct vector configuration (AC 1.3.4)."""
        for name in ["implementations", "best_practices"]:
            info = qdrant_client.get_collection(name)
            assert info.config.params.vectors.size == 768, f"{name}: Expected 768 dimensions (DEC-010)"
            assert info.config.params.vectors.distance == Distance.COSINE, f"{name}: Expected COSINE distance"

    def test_payload_indexes_exist(self, qdrant_client):
        """Payload indexes created for filtering (AC 1.3.1, 1.3.4)."""
        for name in ["implementations", "best_practices"]:
            info = qdrant_client.get_collection(name)
            # Qdrant exposes payload_schema at the result level, not in params
            payload_schema = info.payload_schema

            # Check for keyword indexes on filtering fields
            assert "group_id" in payload_schema, f"{name}: Missing group_id index"
            assert "type" in payload_schema, f"{name}: Missing type index"
            assert "source_hook" in payload_schema, f"{name}: Missing source_hook index"
            assert "content" in payload_schema, f"{name}: Missing content text index"

            # Verify index types
            assert payload_schema["group_id"].data_type == "keyword", f"{name}: group_id should be keyword index"
            assert payload_schema["type"].data_type == "keyword", f"{name}: type should be keyword index"
            assert payload_schema["source_hook"].data_type == "keyword", f"{name}: source_hook should be keyword index"
            assert payload_schema["content"].data_type == "text", f"{name}: content should be text index"


class TestPayloadValidation:
    """Test payload validation with models integration (AC 1.3.2, 1.3.3)."""

    def test_memory_payload_to_dict_validates(self):
        """MemoryPayload.to_dict() produces valid payload dict."""
        payload = MemoryPayload(
            content="Test implementation pattern for React hooks",
            content_hash=compute_content_hash("Test implementation pattern for React hooks"),
            group_id="test-project",
            type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="sess_test_123",
            timestamp="2026-01-11T12:00:00Z",
        )

        payload_dict = payload.to_dict()
        errors = validate_payload(payload_dict)
        assert errors == [], f"Valid MemoryPayload.to_dict() should pass validation but got: {errors}"

    def test_validation_with_all_memory_types(self):
        """Validation accepts all defined MemoryType enum values."""
        for memory_type in MemoryType:
            payload = MemoryPayload(
                content=f"Testing {memory_type.value} memory type",
                content_hash=compute_content_hash(f"Testing {memory_type.value} memory type"),
                group_id="test-project",
                type=memory_type,
                source_hook="PostToolUse",
                session_id="sess_123",
                timestamp="2026-01-11T12:00:00Z",
            )

            payload_dict = payload.to_dict()
            errors = validate_payload(payload_dict)
            assert errors == [], f"MemoryType.{memory_type.name} should be valid but got: {errors}"

    def test_validation_edge_case_minimum_content_length(self):
        """Payload with exactly 10 chars passes validation."""
        payload_dict = {
            "content": "0123456789",  # Exactly 10 chars
            "group_id": "proj",
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload_dict)
        assert errors == []

    def test_validation_edge_case_maximum_content_length(self):
        """Payload with exactly 100,000 chars passes validation."""
        payload_dict = {
            "content": "x" * 100000,  # Exactly 100,000 chars
            "group_id": "proj",
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload_dict)
        assert errors == []
