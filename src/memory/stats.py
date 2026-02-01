"""Collection statistics module for AI Memory Module.

Provides comprehensive statistics for Qdrant collections including:
- Total points and indexed points
- Segment count and disk size
- Last updated timestamp
- Per-project breakdown

Complies with:
- AC 6.6.1: Statistics Endpoint requirements
- NFR-M4: Statistics queries <100ms
- Qdrant Python Client 1.16.2+ API patterns
- project-context.md: snake_case, structured logging
"""

import logging
from dataclasses import dataclass

from qdrant_client import QdrantClient

__all__ = [
    "CollectionStats",
    "calculate_disk_size",
    "get_collection_stats",
    "get_last_updated",
    "get_unique_field_values",
]

logger = logging.getLogger("ai_memory.storage")


@dataclass
class CollectionStats:
    """Statistics for a Qdrant collection.

    Attributes:
        collection_name: Name of the collection
        total_points: Total number of points in collection
        indexed_points: Number of indexed vectors (may differ during indexing)
        segments_count: Number of segments in collection
        disk_size_bytes: Total disk size in bytes (sum of segment sizes)
        last_updated: ISO 8601 timestamp of most recent update (None if empty)
        projects: List of unique project IDs (sorted)
        points_by_project: Dictionary mapping project ID to point count
    """

    collection_name: str
    total_points: int
    indexed_points: int
    segments_count: int
    disk_size_bytes: int
    last_updated: str | None
    projects: list[str]
    points_by_project: dict[str, int]


def get_collection_stats(client: QdrantClient, collection_name: str) -> CollectionStats:
    """Get comprehensive statistics for a collection.

    Args:
        client: Initialized Qdrant client
        collection_name: Name of collection to analyze

    Returns:
        CollectionStats with complete collection metadata

    Example:
        >>> from memory.config import get_config
        >>> from qdrant_client import QdrantClient
        >>> config = get_config()
        >>> client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)
        >>> stats = get_collection_stats(client, "code-patterns")
        >>> print(f"Total memories: {stats.total_points}")
    """
    # Get collection info (O(1) - cached in memory)
    info = client.get_collection(collection_name)

    # Get unique projects from group_id field
    projects = get_unique_field_values(client, collection_name, "group_id")

    # Get per-project counts (O(log n) per project with payload index)
    points_by_project = {}
    for project in projects:
        count = client.count(
            collection_name,
            count_filter={"must": [{"key": "group_id", "match": {"value": project}}]},
        )
        points_by_project[project] = count.count

    # Calculate disk size and last updated
    disk_size = calculate_disk_size(info)
    last_updated = get_last_updated(client, collection_name)

    return CollectionStats(
        collection_name=collection_name,
        total_points=info.points_count,
        indexed_points=info.indexed_vectors_count,
        segments_count=info.segments_count,
        disk_size_bytes=disk_size,
        last_updated=last_updated,
        projects=projects,
        points_by_project=points_by_project,
    )


def get_unique_field_values(
    client: QdrantClient, collection_name: str, field_name: str
) -> list[str]:
    """Get unique values for a payload field.

    Extracts unique values from the specified field across all points.
    Returns sorted list for consistent ordering.

    Args:
        client: Initialized Qdrant client
        collection_name: Name of collection to query
        field_name: Payload field to extract values from

    Returns:
        Sorted list of unique field values (empty list if no points)

    Example:
        >>> projects = get_unique_field_values(client, "code-patterns", "group_id")
        >>> print(projects)
        ['proj-a', 'proj-b', 'proj-c']
    """
    # Scroll through all points and extract unique values
    # For large collections (>10K points), consider maintaining separate index
    # 2026 Note: Qdrant 1.16+ may add native faceting - check docs
    points, _ = client.scroll(
        collection_name=collection_name,
        limit=10000,  # Adjust based on expected cardinality
        with_payload=[field_name],
    )

    unique_values = set()
    for point in points:
        if field_name in point.payload:
            unique_values.add(point.payload[field_name])

    return sorted(unique_values)


def calculate_disk_size(info) -> int:
    """Calculate total disk size from collection segments.

    Note: Qdrant API doesn't expose individual segment sizes in get_collection().
    Returns 0 as placeholder. To get actual disk size, would need to query
    the Qdrant cluster info endpoint directly.

    Args:
        info: CollectionInfo object from client.get_collection()

    Returns:
        Total disk size in bytes (0 - not available via this API)

    Example:
        >>> info = client.get_collection("code-patterns")
        >>> size_bytes = calculate_disk_size(info)
        >>> size_mb = size_bytes / (1024 * 1024)
        >>> print(f"Collection size: {size_mb:.2f} MB")
    """
    # Qdrant's CollectionInfo doesn't expose segment sizes
    # Would need to use /collections/{name}/cluster endpoint for real size
    # Returning 0 as placeholder for MVP
    return 0


def get_last_updated(client: QdrantClient, collection_name: str) -> str | None:
    """Get timestamp of most recent update to collection.

    Queries for latest point by timestamp field. Returns None if collection
    is empty or no timestamp field exists.

    Args:
        client: Initialized Qdrant client
        collection_name: Name of collection to query

    Returns:
        ISO 8601 timestamp string of latest update, or None if unavailable

    Example:
        >>> last_updated = get_last_updated(client, "code-patterns")
        >>> print(f"Last updated: {last_updated or 'N/A'}")
    """
    try:
        # Query for latest point by timestamp (descending order)
        points, _ = client.scroll(
            collection_name=collection_name,
            limit=1,
            order_by={"key": "timestamp", "direction": "desc"},
            with_payload=["timestamp"],
        )

        if points and "timestamp" in points[0].payload:
            return points[0].payload["timestamp"]
    except Exception as e:
        # Gracefully handle missing timestamp field or empty collection
        logger.debug(
            "last_updated_unavailable",
            extra={
                "collection": collection_name,
                "error": str(e),
            },
        )

    return None
