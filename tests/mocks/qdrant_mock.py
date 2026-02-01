"""Mock Qdrant client for testing.

Provides in-memory mock implementation of QdrantClient interface for unit tests.
Simulates vector search, scoring, and collection management without external dependencies.
"""

import random
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass
class ScoredPoint:
    """Mock ScoredPoint matching qdrant_client.models.ScoredPoint."""

    id: str
    score: float
    payload: dict[str, Any]
    vector: list[float] | None = None


@dataclass
class CollectionInfo:
    """Mock CollectionInfo matching qdrant_client.models.CollectionInfo."""

    name: str


@dataclass
class CollectionsResponse:
    """Mock CollectionsResponse."""

    collections: list[CollectionInfo]


class MockQdrantClient:
    """Mock QdrantClient for testing.

    Stores points in memory and simulates search with randomized scores.
    Supports upsert, search, scroll, and get_collections operations.

    Example:
        >>> client = MockQdrantClient()
        >>> client.upsert("test_collection", points=[...])
        >>> results = client.search("test_collection", query_vector=[...])
    """

    def __init__(self):
        """Initialize mock client with empty collections."""
        # Collection -> list of points
        self.points: dict[str, list[dict[str, Any]]] = {}
        # Track upsert calls for test assertions
        self.upsert_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []

    def upsert(
        self, collection_name: str, points: list[Any], wait: bool = True, **kwargs
    ) -> dict[str, Any]:
        """Store points in collection.

        Args:
            collection_name: Target collection name
            points: List of PointStruct objects to store
            wait: Whether to wait for operation completion
            **kwargs: Additional arguments (ignored)

        Returns:
            Operation result dict with status
        """
        if collection_name not in self.points:
            self.points[collection_name] = []

        # Track call for test assertions
        self.upsert_calls.append(
            {
                "collection_name": collection_name,
                "points": points,
                "wait": wait,
            }
        )

        # Convert PointStruct to dict and store
        for point in points:
            point_dict = {
                "id": str(point.id) if hasattr(point, "id") else str(uuid4()),
                "vector": point.vector if hasattr(point, "vector") else None,
                "payload": point.payload if hasattr(point, "payload") else {},
            }
            self.points[collection_name].append(point_dict)

        return {"status": "completed", "operation_id": 0}

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        query_filter: Any | None = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        score_threshold: float | None = None,
        **kwargs,
    ) -> list[ScoredPoint]:
        """Search collection with simulated scoring.

        Args:
            collection_name: Collection to search
            query_vector: Query embedding vector
            limit: Maximum results to return
            query_filter: Filter conditions (applied to payload)
            with_payload: Include payload in results
            with_vectors: Include vectors in results
            score_threshold: Minimum score threshold
            **kwargs: Additional arguments (ignored)

        Returns:
            List of ScoredPoint objects with simulated scores
        """
        # Track call for test assertions
        self.search_calls.append(
            {
                "collection_name": collection_name,
                "query_vector": query_vector,
                "limit": limit,
                "query_filter": query_filter,
            }
        )

        if collection_name not in self.points:
            return []

        points = self.points[collection_name]

        # Apply filter if provided
        if query_filter:
            points = self._apply_filter(points, query_filter)

        # Simulate scoring with random values (0.7-0.95 range for realistic scores)
        results = []
        for point in points[:limit]:
            score = random.uniform(0.7, 0.95)

            # Apply score threshold
            if score_threshold and score < score_threshold:
                continue

            scored_point = ScoredPoint(
                id=point["id"],
                score=score,
                payload=point["payload"] if with_payload else {},
                vector=point["vector"] if with_vectors else None,
            )
            results.append(scored_point)

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def scroll(
        self,
        collection_name: str,
        limit: int = 10,
        offset: str | None = None,
        scroll_filter: Any | None = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        **kwargs,
    ) -> tuple[list[Any], str | None]:
        """Paginate through collection.

        Args:
            collection_name: Collection to scroll
            limit: Maximum results per page
            offset: Pagination offset (point ID)
            scroll_filter: Filter conditions
            with_payload: Include payload in results
            with_vectors: Include vectors in results
            **kwargs: Additional arguments (ignored)

        Returns:
            Tuple of (points, next_offset)
        """
        if collection_name not in self.points:
            return [], None

        points = self.points[collection_name]

        # Apply filter if provided
        if scroll_filter:
            points = self._apply_filter(points, scroll_filter)

        # Simple offset-based pagination
        start = int(offset) if offset else 0
        end = start + limit
        page = points[start:end]

        # Convert to result objects
        results = []
        for point in page:
            result = type(
                "Point",
                (),
                {
                    "id": point["id"],
                    "payload": point["payload"] if with_payload else {},
                    "vector": point["vector"] if with_vectors else None,
                },
            )
            results.append(result)

        # Calculate next offset
        next_offset = str(end) if end < len(points) else None

        return results, next_offset

    def get_collections(self) -> CollectionsResponse:
        """List all collections.

        Returns:
            CollectionsResponse with collection names
        """
        collections = [CollectionInfo(name=name) for name in self.points]
        return CollectionsResponse(collections=collections)

    def _apply_filter(
        self, points: list[dict[str, Any]], query_filter: Any
    ) -> list[dict[str, Any]]:
        """Apply filter conditions to points.

        Simplified filter implementation for testing.
        Supports FieldCondition with MatchValue checks.

        Args:
            points: Points to filter
            query_filter: Filter object with conditions

        Returns:
            Filtered points list
        """
        if not hasattr(query_filter, "must"):
            return points

        filtered = []
        for point in points:
            matches = True
            for condition in query_filter.must:
                # Support both FieldCondition objects and dict-like conditions
                if hasattr(condition, "key"):
                    key = condition.key
                    # Handle different match types
                    if hasattr(condition, "match"):
                        if hasattr(condition.match, "value"):
                            expected = condition.match.value
                        else:
                            # MatchAny case
                            expected = getattr(condition.match, "any", None)
                    else:
                        expected = None

                    # Check if payload field matches
                    actual = point["payload"].get(key)

                    # Handle MatchAny (list of values)
                    if isinstance(expected, list):
                        if actual not in expected:
                            matches = False
                            break
                    # Handle MatchValue (single value)
                    elif actual != expected:
                        matches = False
                        break

            if matches:
                filtered.append(point)

        return filtered

    def reset(self):
        """Reset mock state for test isolation."""
        self.points.clear()
        self.upsert_calls.clear()
        self.search_calls.clear()
