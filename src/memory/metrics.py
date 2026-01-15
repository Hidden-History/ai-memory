"""
Prometheus metrics definitions for BMAD Memory Module.

Defines Counter, Gauge, Histogram, and Info metrics for monitoring
memory capture, retrieval, embedding generation, and system health.

Complies with:
- AC 6.1.2: Core metrics definitions
- AC 6.1.4: Failure event counters for alerting
- AC 6.6.3: Collection statistics gauge updates
- prometheus_client v0.24.0 best practices (2026)
- Project naming conventions: snake_case, bmad_ prefix
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ==============================================================================
# COUNTERS - Monotonically increasing values
# ==============================================================================

memory_captures_total = Counter(
    "bmad_memory_captures_total",
    "Total memory capture attempts",
    ["hook_type", "status", "project"]
    # status: success, queued, failed
    # hook_type: PostToolUse, SessionStart, Stop
)

memory_retrievals_total = Counter(
    "bmad_memory_retrievals_total",
    "Total memory retrieval attempts",
    ["collection", "status"]
    # status: success, empty, failed
    # collection: implementations, best_practices, combined
)

embedding_requests_total = Counter(
    "bmad_embedding_requests_total",
    "Total embedding generation requests",
    ["status"]
    # status: success, timeout, failed
)

deduplication_events_total = Counter(
    "bmad_deduplication_events_total",
    "Memories deduplicated (not stored)",
    ["project"]
)

failure_events_total = Counter(
    "bmad_failure_events_total",
    "Total failure events for alerting",
    ["component", "error_code"]
    # component: qdrant, embedding, queue, hook
    # error_code: QDRANT_UNAVAILABLE, EMBEDDING_TIMEOUT, QUEUE_FULL, VALIDATION_ERROR
)

# ==============================================================================
# GAUGES - Point-in-time values (can go up or down)
# ==============================================================================

collection_size = Gauge(
    "bmad_collection_size",
    "Number of memories in collection",
    ["collection", "project"]
)

queue_size = Gauge(
    "bmad_queue_size",
    "Pending items in retry queue",
    ["status"]
    # status: pending, exhausted
)

# ==============================================================================
# HISTOGRAMS - Distributions of observed values
# ==============================================================================

hook_duration_seconds = Histogram(
    "bmad_hook_duration_seconds",
    "Hook execution time in seconds",
    ["hook_type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
    # Buckets optimized for NFR-P1 <500ms target
)

embedding_duration_seconds = Histogram(
    "bmad_embedding_duration_seconds",
    "Embedding generation time in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    # Buckets optimized for NFR-P2 <2s target
)

retrieval_duration_seconds = Histogram(
    "bmad_retrieval_duration_seconds",
    "Memory retrieval time in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0]
    # Buckets optimized for SessionStart <3s target
)

# ==============================================================================
# INFO - Static metadata about the system
# ==============================================================================

system_info = Info(
    "bmad_memory_system",
    "Memory system configuration"
)

# Initialize system info with static metadata
system_info.info({
    "version": "1.0.0",
    "embedding_model": "nomic-embed-code",
    "vector_dimensions": "768"
})


# ==============================================================================
# COLLECTION STATISTICS UPDATES (AC 6.6.3)
# ==============================================================================

def update_collection_metrics(stats) -> None:
    """Update Prometheus gauges with current collection stats.

    Updates collection_size gauge with both overall collection metrics
    and per-project breakdown. Enables monitoring of collection growth
    and per-project memory usage.

    Args:
        stats: CollectionStats with current collection data

    Example:
        >>> from memory.config import get_config
        >>> from qdrant_client import QdrantClient
        >>> from memory.stats import get_collection_stats
        >>> config = get_config()
        >>> client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)
        >>> stats = get_collection_stats(client, "implementations")
        >>> update_collection_metrics(stats)
    """
    # Overall collection size
    collection_size.labels(
        collection=stats.collection_name,
        project="all"
    ).set(stats.total_points)

    # Per-project sizes
    for project, count in stats.points_by_project.items():
        collection_size.labels(
            collection=stats.collection_name,
            project=project
        ).set(count)
