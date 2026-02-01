"""Tests for MockQdrantClient.

Verifies mock implementation matches QdrantClient interface behavior.
"""

from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from .qdrant_mock import MockQdrantClient


class TestMockQdrantClient:
    """Test suite for MockQdrantClient."""

    def test_upsert_stores_points(self):
        """Test that upsert stores points in collection."""
        client = MockQdrantClient()

        points = [
            PointStruct(
                id="test-1",
                vector=[0.1, 0.2, 0.3],
                payload={"content": "test content", "type": "implementation"},
            )
        ]

        result = client.upsert("test_collection", points=points)

        assert result["status"] == "completed"
        assert "test_collection" in client.points
        assert len(client.points["test_collection"]) == 1
        assert (
            client.points["test_collection"][0]["payload"]["content"] == "test content"
        )

    def test_search_returns_scored_points(self):
        """Test that search returns ScoredPoint objects."""
        client = MockQdrantClient()

        # Insert test data
        points = [
            PointStruct(
                id=f"test-{i}",
                vector=[0.1, 0.2, 0.3],
                payload={"content": f"content {i}", "type": "implementation"},
            )
            for i in range(5)
        ]
        client.upsert("test_collection", points=points)

        # Search
        results = client.search(
            collection_name="test_collection", query_vector=[0.1, 0.2, 0.3], limit=3
        )

        assert len(results) <= 3
        assert all(hasattr(r, "score") for r in results)
        assert all(hasattr(r, "payload") for r in results)
        # Scores should be sorted descending
        assert all(
            results[i].score >= results[i + 1].score for i in range(len(results) - 1)
        )

    def test_search_with_filter(self):
        """Test that search respects filter conditions."""
        client = MockQdrantClient()

        # Insert mixed data
        points = [
            PointStruct(
                id="impl-1",
                vector=[0.1, 0.2, 0.3],
                payload={
                    "content": "impl",
                    "type": "implementation",
                    "group_id": "project-a",
                },
            ),
            PointStruct(
                id="error-1",
                vector=[0.1, 0.2, 0.3],
                payload={
                    "content": "error",
                    "type": "error_fix",
                    "group_id": "project-a",
                },
            ),
            PointStruct(
                id="impl-2",
                vector=[0.1, 0.2, 0.3],
                payload={
                    "content": "impl2",
                    "type": "implementation",
                    "group_id": "project-b",
                },
            ),
        ]
        client.upsert("test_collection", points=points)

        # Filter by type
        query_filter = Filter(
            must=[FieldCondition(key="type", match=MatchValue(value="implementation"))]
        )

        results = client.search(
            collection_name="test_collection",
            query_vector=[0.1, 0.2, 0.3],
            query_filter=query_filter,
            limit=10,
        )

        # Should only return implementation types
        assert len(results) == 2
        assert all(r.payload["type"] == "implementation" for r in results)

    def test_scroll_pagination(self):
        """Test that scroll supports pagination."""
        client = MockQdrantClient()

        # Insert 15 points
        points = [
            PointStruct(
                id=f"test-{i}",
                vector=[0.1, 0.2, 0.3],
                payload={"content": f"content {i}"},
            )
            for i in range(15)
        ]
        client.upsert("test_collection", points=points)

        # First page
        page1, offset1 = client.scroll("test_collection", limit=5)
        assert len(page1) == 5
        assert offset1 is not None

        # Second page
        page2, offset2 = client.scroll("test_collection", limit=5, offset=offset1)
        assert len(page2) == 5
        assert offset2 is not None

        # Third page (last)
        page3, offset3 = client.scroll("test_collection", limit=5, offset=offset2)
        assert len(page3) == 5
        assert offset3 is None  # No more pages

    def test_get_collections(self):
        """Test that get_collections returns collection names."""
        client = MockQdrantClient()

        # Add points to multiple collections
        for collection in ["code-patterns", "conventions", "discussions"]:
            points = [
                PointStruct(
                    id=f"{collection}-1",
                    vector=[0.1, 0.2, 0.3],
                    payload={"content": "test"},
                )
            ]
            client.upsert(collection, points=points)

        response = client.get_collections()

        collection_names = [c.name for c in response.collections]
        assert "code-patterns" in collection_names
        assert "conventions" in collection_names
        assert "discussions" in collection_names

    def test_search_empty_collection(self):
        """Test that search handles empty collections gracefully."""
        client = MockQdrantClient()

        results = client.search(
            collection_name="nonexistent", query_vector=[0.1, 0.2, 0.3], limit=5
        )

        assert results == []

    def test_reset_clears_state(self):
        """Test that reset clears all mock state."""
        client = MockQdrantClient()

        # Add data
        points = [
            PointStruct(
                id="test-1", vector=[0.1, 0.2, 0.3], payload={"content": "test"}
            )
        ]
        client.upsert("test_collection", points=points)
        client.search("test_collection", query_vector=[0.1, 0.2, 0.3])

        # Reset
        client.reset()

        assert len(client.points) == 0
        assert len(client.upsert_calls) == 0
        assert len(client.search_calls) == 0

    def test_score_threshold_filtering(self):
        """Test that score_threshold filters low-score results."""
        client = MockQdrantClient()

        # Insert points
        points = [
            PointStruct(
                id=f"test-{i}",
                vector=[0.1, 0.2, 0.3],
                payload={"content": f"content {i}"},
            )
            for i in range(10)
        ]
        client.upsert("test_collection", points=points)

        # Search with high threshold (may return fewer results)
        results_high = client.search(
            collection_name="test_collection",
            query_vector=[0.1, 0.2, 0.3],
            limit=10,
            score_threshold=0.90,
        )

        # Search with low threshold (should return more)
        results_low = client.search(
            collection_name="test_collection",
            query_vector=[0.1, 0.2, 0.3],
            limit=10,
            score_threshold=0.70,
        )

        # High threshold should return fewer or equal results
        assert len(results_high) <= len(results_low)
        # All results should meet threshold
        assert all(r.score >= 0.90 for r in results_high)
        assert all(r.score >= 0.70 for r in results_low)
