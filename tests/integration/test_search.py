"""Integration tests for search module with running Docker stack.

Tests MemorySearch with real Qdrant and embedding service.
Requires Docker stack to be running (docker compose up -d).

Architecture Reference: architecture.md:747-863 (Search Module)
"""

import pytest

from src.memory.models import MemoryType
from src.memory.search import MemorySearch
from src.memory.storage import MemoryStorage


@pytest.mark.requires_qdrant
class TestSearchIntegration:
    """Test search module with running Docker stack."""

    @pytest.fixture(autouse=True)
    def setup_test_data(self):
        """Create test memories before search tests and clean up after.

        Uses unique group_id per test method to ensure isolation.
        """
        storage = MemoryStorage()

        # Use unique group_id per test to ensure isolation
        # This prevents test interference when fixture cleanup fails
        import uuid
        self.test_group_id = f"search-test-{uuid.uuid4().hex[:8]}"

        # Store test memories for searching
        # Include UUID in content to avoid deduplication from previous runs
        # (dedup is content-hash based, so same content = same group_id from old run)
        self.mem_ids = []
        unique_suffix = self.test_group_id  # Reuse the UUID suffix
        test_data = [
            {
                "content": f"Test implementation for Python async patterns using asyncio [{unique_suffix}]",
                "group_id": self.test_group_id,
                "memory_type": MemoryType.IMPLEMENTATION,
            },
            {
                "content": f"Test pattern for database connection pooling with SQLAlchemy [{unique_suffix}]",
                "group_id": self.test_group_id,
                "memory_type": MemoryType.GUIDELINE,
            },
            {
                "content": f"Test decision to use Redis for caching layer [{unique_suffix}]",
                "group_id": self.test_group_id,
                "memory_type": MemoryType.DECISION,
            },
        ]

        for data in test_data:
            result = storage.store_memory(
                content=data["content"],
                cwd="/test/project",
                group_id=data["group_id"],
                memory_type=data["memory_type"],
                source_hook="PostToolUse",
                session_id="search-test-session",
            )
            # Accept both "stored" and "duplicate" - both mean searchable data exists
            # Deduplication is content-hash based, so same content = same memory
            if result["status"] in ("stored", "duplicate"):
                self.mem_ids.append(result["memory_id"])

        # Brief delay for Qdrant to index new points (eventual consistency)
        import time
        time.sleep(0.5)

        yield

        # Cleanup test data after tests complete
        try:
            from qdrant_client.models import PointIdsList
            for mem_id in self.mem_ids:
                storage.client.delete(
                    collection_name="code-patterns",
                    points_selector=PointIdsList(points=[mem_id]),
                )
        except Exception:
            pass  # Best effort cleanup - don't fail tests on cleanup errors

    def test_search_end_to_end(self):
        """Test full search flow with real services."""
        search = MemorySearch()

        # Use lower threshold for testing - Nomic Embed Code typically produces
        # similarity scores of 0.3-0.6 for related content, not 0.7+ like some models
        results = search.search(
            query="Python async implementation",
            collection="code-patterns",
            group_id=self.test_group_id,
            limit=5,
            score_threshold=0.3,  # Lower threshold for test content
        )

        # Should find at least one result
        assert len(results) > 0, f"Expected results but got empty. group_id={self.test_group_id}"
        # All results should have required fields
        assert all("score" in r for r in results)
        assert all("content" in r for r in results)
        assert all("id" in r for r in results)
        # All results should match group_id filter
        assert all(r["group_id"] == self.test_group_id for r in results)

    def test_search_with_filters(self):
        """Test search with group_id and memory_type filters."""
        search = MemorySearch()

        # Search with both filters
        results = search.search(
            query="test",
            collection="code-patterns",
            group_id=self.test_group_id,
            memory_type="implementation",
        )

        # All results should match both filters
        if results:  # May be empty if no matches above threshold
            assert all(r["group_id"] == self.test_group_id for r in results)
            assert all(r["type"] == "implementation" for r in results)

    def test_search_different_collections(self):
        """Test search on implementations vs best_practices collections."""
        search = MemorySearch()

        # Search implementations
        impl_results = search.search(
            query="implementation",
            collection="code-patterns",
            group_id=self.test_group_id,
        )

        # Search best_practices (likely empty for test project)
        bp_results = search.search(
            query="implementation",
            collection="conventions",
            # No group_id filter - best_practices are shared
        )

        # Both should be valid lists
        assert isinstance(impl_results, list)
        assert isinstance(bp_results, list)

    def test_dual_collection_search(self):
        """Test search_both_collections with real Qdrant."""
        search = MemorySearch()

        results = search.search_both_collections(
            query="Python implementation",
            group_id=self.test_group_id,
            limit=5,
        )

        # Should return both collections
        assert "code-patterns" in results
        assert "conventions" in results
        assert isinstance(results["code-patterns"], list)
        assert isinstance(results["conventions"], list)

    def test_tiered_formatting_with_real_data(self):
        """Test tiered results formatting with real search data."""
        search = MemorySearch()

        # Search for something likely to match
        results = search.search(
            query="test implementation",
            collection="code-patterns",
            group_id=self.test_group_id,
            limit=5,
        )

        # Format results
        formatted = search.format_tiered_results(results)

        # Should be valid markdown string
        assert isinstance(formatted, str)

        # If results exist, should have tier headers
        if results:
            # Should have markdown headers (if any results above threshold)
            has_high_tier = any(r["score"] >= 0.90 for r in results)
            has_medium_tier = any(
                0.78 <= r["score"] < 0.90 for r in results
            )

            if has_high_tier:
                assert "## High Relevance Memories" in formatted
            if has_medium_tier:
                assert "## Medium Relevance Memories" in formatted

            # Should show scores as percentages
            if has_high_tier or has_medium_tier:
                assert "%" in formatted

    def test_search_respects_score_threshold(self):
        """Test that search respects score_threshold parameter."""
        search = MemorySearch()

        # Search with high threshold
        high_threshold_results = search.search(
            query="test",
            collection="code-patterns",
            group_id=self.test_group_id,
            score_threshold=0.95,
        )

        # Search with low threshold
        low_threshold_results = search.search(
            query="test",
            collection="code-patterns",
            group_id=self.test_group_id,
            score_threshold=0.5,
        )

        # Low threshold should return >= high threshold results
        assert len(low_threshold_results) >= len(high_threshold_results)

        # All high threshold results should have score >= 0.95
        if high_threshold_results:
            assert all(r["score"] >= 0.95 for r in high_threshold_results)

    def test_search_respects_limit_parameter(self):
        """Test that search respects limit parameter."""
        search = MemorySearch()

        # Search with limit=2
        results = search.search(
            query="test",
            collection="code-patterns",
            group_id=self.test_group_id,
            limit=2,
        )

        # Should return at most 2 results
        assert len(results) <= 2

    def test_search_empty_results(self):
        """Test search with query unlikely to match.

        Note: Uses high score_threshold (0.8) to filter out low-quality matches.
        conftest.py sets global SIMILARITY_THRESHOLD=0.4 for test coverage,
        but this test verifies empty result handling with strict matching.
        """
        search = MemorySearch()

        results = search.search(
            query="xyzabc123nonexistent",
            collection="code-patterns",
            group_id=self.test_group_id,
            score_threshold=0.8,  # High threshold to ensure nonsense query returns empty
        )

        # Should return empty list (not an error)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_returns_sorted_by_score(self):
        """Test that results are sorted by score (highest first)."""
        search = MemorySearch()

        results = search.search(
            query="Python async implementation",
            collection="code-patterns",
            group_id=self.test_group_id,
            limit=5,
        )

        # If multiple results, verify descending order
        if len(results) > 1:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)


class TestSearchGracefulDegradation:
    """Test graceful degradation with service outages."""

    def test_search_with_embedding_service_down(self, monkeypatch):
        """Test search fails gracefully when embedding service unavailable."""
        from src.memory.embeddings import EmbeddingError

        # Mock EmbeddingClient to raise error
        def mock_embed_init(config):
            mock = type("MockClient", (), {})()
            mock.embed = lambda texts: (_ for _ in ()).throw(
                EmbeddingError("Service down")
            )
            return mock

        monkeypatch.setattr(
            "src.memory.search.EmbeddingClient", mock_embed_init
        )

        search = MemorySearch()

        # Should raise EmbeddingError (caller handles graceful degradation)
        with pytest.raises(EmbeddingError):
            search.search(query="test")

    def test_search_with_qdrant_down(self, monkeypatch):
        """Test search fails gracefully when Qdrant unavailable (AC 1.6.4)."""
        from src.memory.qdrant_client import QdrantUnavailable

        # Mock get_qdrant_client to return client that raises on search
        def mock_get_qdrant_client(config):
            mock = type("MockClient", (), {})()
            mock.search = lambda *args, **kwargs: (_ for _ in ()).throw(
                Exception("Connection refused")
            )
            return mock

        monkeypatch.setattr(
            "src.memory.search.get_qdrant_client", mock_get_qdrant_client
        )

        search = MemorySearch()

        # Should raise QdrantUnavailable (caller handles graceful degradation)
        with pytest.raises(QdrantUnavailable, match="Search failed"):
            search.search(query="test")
