"""Collection threshold warnings module for AI Memory Module.

Checks collection sizes against WARNING and CRITICAL thresholds and emits
structured log events for monitoring and alerting.

Thresholds are configurable via environment variables:
- AI_MEMORY_COLLECTION_SIZE_WARNING: Default 10,000 (FR46a)
- AI_MEMORY_COLLECTION_SIZE_CRITICAL: Default 50,000

Complies with:
- AC 6.6.2: Threshold Warning Implementation (FR46a)
- project-context.md: structured logging with extra dict
- 2026 best practices: Environment-based configuration
"""

import logging
import os

from .stats import CollectionStats

__all__ = [
    "COLLECTION_SIZE_CRITICAL",
    "COLLECTION_SIZE_WARNING",
    "check_collection_thresholds",
]

logger = logging.getLogger("ai_memory.storage")

# Configurable thresholds (FR46a: default 10,000)
COLLECTION_SIZE_WARNING = int(os.getenv("AI_MEMORY_COLLECTION_SIZE_WARNING", "10000"))
COLLECTION_SIZE_CRITICAL = int(os.getenv("AI_MEMORY_COLLECTION_SIZE_CRITICAL", "50000"))

# Validate thresholds on module load
assert COLLECTION_SIZE_WARNING > 0, "WARNING threshold must be positive"
assert COLLECTION_SIZE_CRITICAL > COLLECTION_SIZE_WARNING, "CRITICAL must be > WARNING"


def check_collection_thresholds(stats: CollectionStats) -> list[str]:
    """Check collection against thresholds and emit warnings.

    Checks both overall collection size and per-project sizes against
    WARNING and CRITICAL thresholds. Emits structured log events and
    returns human-readable warning strings.

    Args:
        stats: CollectionStats with current collection data

    Returns:
        List of human-readable warning strings (empty if no warnings)

    Example:
        >>> stats = get_collection_stats(client, "code-patterns")
        >>> warnings = check_collection_thresholds(stats)
        >>> for warning in warnings:
        ...     print(f"⚠️  {warning}")
    """
    warnings = []

    # Check overall collection size
    if stats.total_points >= COLLECTION_SIZE_CRITICAL:
        logger.error(
            "collection_size_critical",
            extra={
                "collection": stats.collection_name,
                "size": stats.total_points,
                "threshold": COLLECTION_SIZE_CRITICAL,
            },
        )
        warnings.append(
            f"CRITICAL: {stats.collection_name} has {stats.total_points} "
            f"memories (threshold: {COLLECTION_SIZE_CRITICAL})"
        )

    elif stats.total_points >= COLLECTION_SIZE_WARNING:
        logger.warning(
            "collection_size_warning",
            extra={
                "collection": stats.collection_name,
                "size": stats.total_points,
                "threshold": COLLECTION_SIZE_WARNING,
            },
        )
        warnings.append(
            f"WARNING: {stats.collection_name} has {stats.total_points} "
            f"memories (threshold: {COLLECTION_SIZE_WARNING})"
        )

    # Per-project warnings (check all projects, not just overall)
    for project, count in stats.points_by_project.items():
        if count >= COLLECTION_SIZE_WARNING:
            logger.warning(
                "project_size_warning",
                extra={
                    "collection": stats.collection_name,
                    "project": project,
                    "size": count,
                    "threshold": COLLECTION_SIZE_WARNING,
                },
            )
            warnings.append(f"WARNING: Project '{project}' has {count} memories")

    return warnings
