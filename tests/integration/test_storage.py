"""Integration tests for storage module with real services.

Tests MemoryStorage against running Docker stack (Qdrant + Embedding service).
Requires: docker compose -f docker/docker-compose.yml up -d

Implements Story 1.5 Task 6.
"""

import pytest
from datetime import datetime, timezone

from qdrant_client.models import Filter, FieldCondition, MatchText

from src.memory.storage import MemoryStorage
from src.memory.models import MemoryType, EmbeddingStatus
from src.memory.config import get_config
from src.memory.qdrant_client import get_qdrant_client


class TestStorageIntegration:
    """Integration tests with running Docker stack.

    Prerequisites:
        - Qdrant running on localhost:26350
        - Embedding service running on localhost:28080
        - Collections 'implementations' and 'best_practices' exist

    Run with: pytest tests/integration/test_storage.py -v
    """

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test data before and after each test."""
        # Setup: Query and delete test data before test
        from src.memory.qdrant_client import get_qdrant_client
        from src.memory.config import get_config

        config = get_config()
        client = get_qdrant_client(config)

        # Clear test data before running test
        # Scroll to find all test-* session_id points and delete them
        for collection in ["implementations", "best_practices"]:
            try:
                # Scroll with filter to find test points
                scroll_result = client.scroll(
                    collection_name=collection,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="session_id",
                                match=MatchText(text="test-"),
                            )
                        ]
                    ),
                    limit=1000,
                )

                # Extract IDs
                point_ids = [point.id for point in scroll_result[0]]

                # Delete if any found
                if point_ids:
                    client.delete(collection_name=collection, points_selector=point_ids)

            except Exception:
                pass  # Collection might not exist yet

        yield

        # Cleanup: Same as setup - delete test data after test
        for collection in ["implementations", "best_practices"]:
            try:
                scroll_result = client.scroll(
                    collection_name=collection,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="session_id",
                                match=MatchText(text="test-"),
                            )
                        ]
                    ),
                    limit=1000,
                )

                point_ids = [point.id for point in scroll_result[0]]

                if point_ids:
                    client.delete(collection_name=collection, points_selector=point_ids)

            except Exception:
                pass

    def test_store_memory_end_to_end(self):
        """Test full storage flow with real services (AC 1.5.1)."""
        storage = MemoryStorage()

        result = storage.store_memory(
            content="def hello_world(): return 'Hello from integration test'",
            cwd="/test/integration",
            group_id="bmad-memory-module-test",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-integration-001",
        )

        # Verify response
        assert result["status"] == "stored"
        assert result["memory_id"] is not None
        # Accept either complete or pending (CPU embedding may timeout on slow systems)
        assert result["embedding_status"] in ["complete", "pending"]

        # Verify stored in Qdrant
        config = get_config()
        client = get_qdrant_client(config)
        retrieved = client.retrieve(
            collection_name="implementations", ids=[result["memory_id"]]
        )

        assert len(retrieved) == 1
        assert (
            retrieved[0].payload["content"]
            == "def hello_world(): return 'Hello from integration test'"
        )
        assert retrieved[0].payload["group_id"] == "bmad-memory-module-test"
        assert retrieved[0].payload["type"] == "implementation"
        # Accept either complete or pending status
        assert retrieved[0].payload["embedding_status"] in ["complete", "pending"]
        assert retrieved[0].payload["embedding_model"] == "jina-embeddings-v2-base-code"

        # Verify vector dimensions (DEC-010)
        # If embedding succeeded, verify proper dimensions; if pending, verify zero vector
        if retrieved[0].vector is not None:
            assert len(retrieved[0].vector) == 768
            if result["embedding_status"] == "complete":
                assert any(v != 0.0 for v in retrieved[0].vector)  # Not all zeros
            else:
                assert all(v == 0.0 for v in retrieved[0].vector)  # All zeros

    def test_batch_storage_end_to_end(self):
        """Test batch storage with real services (AC 1.5.2)."""
        storage = MemoryStorage()

        memories = [
            {
                "content": f"Implementation {i}: test batch storage with real services",
                "group_id": "test-batch-project",
                "type": MemoryType.IMPLEMENTATION.value,
                "source_hook": "PostToolUse",
                "session_id": "test-integration-batch",
            }
            for i in range(5)
        ]

        results = storage.store_memories_batch(memories)

        # Verify all stored
        assert len(results) == 5
        assert all(r["status"] == "stored" for r in results)
        # Accept either complete or pending (CPU embedding may timeout on slow systems)
        assert all(r["embedding_status"] in ["complete", "pending"] for r in results)
        assert all(r["memory_id"] is not None for r in results)

        # Verify in Qdrant
        config = get_config()
        client = get_qdrant_client(config)

        for i, result in enumerate(results):
            retrieved = client.retrieve(
                collection_name="implementations", ids=[result["memory_id"]]
            )
            assert len(retrieved) == 1
            assert (
                f"Implementation {i}: test batch storage"
                in retrieved[0].payload["content"]
            )

    def test_duplicate_detection_end_to_end(self):
        """Test deduplication with real Qdrant (AC 1.5.3)."""
        storage = MemoryStorage()

        unique_content = f"Unique test content for dedup {datetime.now(timezone.utc).isoformat()}"

        # Store first time
        result1 = storage.store_memory(
            content=unique_content,
            cwd="/test/integration",
            group_id="test-dedup-project",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-integration-dedup",
        )
        assert result1["status"] == "stored"
        assert result1["memory_id"] is not None

        # Store duplicate
        result2 = storage.store_memory(
            content=unique_content,  # Same content
            cwd="/test/integration",
            group_id="test-dedup-project",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-integration-dedup",
        )
        assert result2["status"] == "duplicate"
        # AC 1.5.3: Returns existing memory_id on duplicate
        assert result2["memory_id"] == result1["memory_id"]

    def test_different_memory_types(self):
        """Test storing different memory types."""
        storage = MemoryStorage()

        memory_types = [
            MemoryType.IMPLEMENTATION,
            MemoryType.SESSION_SUMMARY,
            MemoryType.DECISION,
            MemoryType.PATTERN,
        ]

        for mem_type in memory_types:
            result = storage.store_memory(
                content=f"Test content for {mem_type.value} type with enough length",
                cwd="/test/integration",
                group_id="test-types-project",
                memory_type=mem_type,
                source_hook="PostToolUse",
                session_id="test-integration-types",
            )

            assert result["status"] == "stored"
            assert result["memory_id"] is not None

            # Verify type stored correctly
            config = get_config()
            client = get_qdrant_client(config)
            retrieved = client.retrieve(
                collection_name="implementations", ids=[result["memory_id"]]
            )
            assert retrieved[0].payload["type"] == mem_type.value

    def test_extra_fields_storage(self):
        """Test storing memories with extra fields (domain, importance, tags)."""
        storage = MemoryStorage()

        result = storage.store_memory(
            content="Test implementation with extra metadata fields",
            cwd="/test/integration",
            group_id="test-metadata-project",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-integration-metadata",
            domain="backend",
            importance="high",
            tags=["python", "async", "testing"],
        )

        assert result["status"] == "stored"

        # Verify extra fields stored
        config = get_config()
        client = get_qdrant_client(config)
        retrieved = client.retrieve(
            collection_name="implementations", ids=[result["memory_id"]]
        )

        assert retrieved[0].payload["domain"] == "backend"
        assert retrieved[0].payload["importance"] == "high"
        assert retrieved[0].payload["tags"] == ["python", "async", "testing"]

    def test_store_to_best_practices_collection(self):
        """Test storing to best_practices collection."""
        storage = MemoryStorage()

        result = storage.store_memory(
            content="Always use structured logging with extras dict for production systems",
            cwd="/test/integration",
            group_id="general",
            memory_type=MemoryType.PATTERN,
            source_hook="seed_script",
            session_id="test-integration-bp",
            collection="best_practices",
            importance="high",
        )

        assert result["status"] == "stored"

        # Verify in best_practices collection
        config = get_config()
        client = get_qdrant_client(config)
        retrieved = client.retrieve(
            collection_name="best_practices", ids=[result["memory_id"]]
        )

        assert len(retrieved) == 1
        assert "structured logging" in retrieved[0].payload["content"]
