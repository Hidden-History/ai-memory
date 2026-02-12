"""Health check utilities for graceful degradation.

This module provides service health checks and fallback mode selection logic.
Health checks are fast (<2s total per NFR-P1) and never raise exceptions.

Health Check Strategy:
    - Qdrant: Test connectivity using get_collections()
    - Embedding: Test availability using /health endpoint
    - Total timeout: <2s for both checks combined
    - Never raises exceptions - always returns status dict

Fallback Modes:
    - normal: All services healthy
    - queue_to_file: Qdrant unavailable → queue operations to file
    - pending_embedding: Embedding unavailable → store with pending status
    - passthrough: Both unavailable → log and exit gracefully

Best Practices (2025):
    - Fast health checks minimize monitoring overhead
    - Never raise exceptions from health checks
    - Log results with structured extras dict
    - Return simple dict format for easy decision logic

References:
    - https://www.index.dev/blog/how-to-implement-health-check-in-python
    - https://medium.com/@encodedots/python-health-check-endpoint-example-...
"""

import logging
import socket

from .activity_log import log_activity
from .embeddings import EmbeddingClient
from .qdrant_client import check_qdrant_health, get_qdrant_client

# Health check timeout per NFR-P1 (2s max for all checks)
HEALTH_CHECK_TIMEOUT = 2.0

# Configure logger for health check operations
logger = logging.getLogger("ai_memory.health")


def check_services() -> dict[str, bool]:
    """Check all service availability quickly.

    Performs fast health checks on Qdrant and embedding service.
    Never raises exceptions - always returns status dict.
    Completes within 2 seconds total (NFR-P1 requirement).

    Returns:
        dict: Service health status with keys:
            - qdrant (bool): Qdrant service availability
            - embedding (bool): Embedding service availability
            - all_healthy (bool): True if both services are healthy

    Example:
        health = check_services()
        if health["all_healthy"]:
            # Normal operation
            store_with_embedding(...)
        elif not health["qdrant"]:
            # Queue to file
            queue_operation(...)
        elif not health["embedding"]:
            # Store with pending embedding
            store_with_pending_embedding(...)
        else:
            # Passthrough
            logger.warning("Both services unavailable")

    Performance:
        - <2s total for both checks (NFR-P1) - enforced with socket timeout
        - No retry logic (fast fail for health checks)
        - Exceptions caught and converted to False status
    """
    qdrant_ok = False
    embedding_ok = False

    # Set socket timeout to enforce 2s limit per NFR-P1
    # This prevents hanging if services are unresponsive
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(HEALTH_CHECK_TIMEOUT)

    try:
        # Check Qdrant health
        try:
            client = get_qdrant_client()
            qdrant_ok = check_qdrant_health(client)
        except Exception as e:
            # Never raise from health check - return False status
            logger.warning(
                "qdrant_health_check_failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            qdrant_ok = False

        # Check Embedding service health
        try:
            ec = EmbeddingClient()
            embedding_ok = ec.health_check()
        except Exception as e:
            # Never raise from health check - return False status
            logger.warning(
                "embedding_health_check_failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            embedding_ok = False
    finally:
        # Restore original socket timeout
        socket.setdefaulttimeout(old_timeout)

    # Log overall health status (structured logging)
    logger.info(
        "service_health",
        extra={
            "qdrant": qdrant_ok,
            "embedding": embedding_ok,
            "all_healthy": qdrant_ok and embedding_ok,
        },
    )

    # Log to activity log (user-visible)
    if qdrant_ok and embedding_ok:
        log_activity(
            "✅", "HealthCheck: All services healthy (Qdrant OK, Embedding OK)"
        )
    else:
        status_parts = []
        status_parts.append("Qdrant OK" if qdrant_ok else "Qdrant FAIL")
        status_parts.append("Embedding OK" if embedding_ok else "Embedding FAIL")
        log_activity("⚠️", f"HealthCheck: Service issues ({', '.join(status_parts)})")

    return {
        "qdrant": qdrant_ok,
        "embedding": embedding_ok,
        "all_healthy": qdrant_ok and embedding_ok,
    }


def get_fallback_mode(health: dict[str, bool]) -> str:
    """Determine fallback mode based on service health status.

    Implements graceful degradation decision logic based on which
    services are available. Priority: check both-down first.

    Args:
        health: Service health status dict from check_services()

    Returns:
        str: Fallback mode for graceful degradation:
            - "normal": All services healthy - full functionality
            - "queue_to_file": Qdrant down - queue to ~/.ai-memory/queue/
            - "pending_embedding": Embedding down - store with embedding_status=pending
            - "passthrough": Both down - log and exit gracefully

    Example:
        health = check_services()
        mode = get_fallback_mode(health)

        if mode == "normal":
            # Full operation
            embedding = generate_embedding(content)
            store_in_qdrant(content, embedding)
        elif mode == "queue_to_file":
            # Qdrant unavailable
            queue_operation({"content": content, "type": "implementation"})
        elif mode == "pending_embedding":
            # Embedding unavailable
            store_in_qdrant(content, embedding_status="pending")
        elif mode == "passthrough":
            # Both unavailable
            logger.error("memory_system_unavailable")
            exit_graceful("All services down")

    Decision Logic:
        1. All healthy → "normal"
        2. Both down → "passthrough"
        3. Qdrant down (embedding up) → "queue_to_file"
        4. Embedding down (Qdrant up) → "pending_embedding"
    """
    if health["all_healthy"]:
        return "normal"
    elif not health["qdrant"] and not health["embedding"]:
        # Both down - passthrough mode
        return "passthrough"
    elif not health["qdrant"]:
        # Qdrant down, embedding up - queue operations for later
        return "queue_to_file"
    elif not health["embedding"]:
        # Qdrant up, embedding down - store with pending embedding
        return "pending_embedding"
    else:
        # Defensive fallback (shouldn't reach here)
        return "passthrough"


# Export public API
__all__ = [
    "HEALTH_CHECK_TIMEOUT",
    "check_services",
    "get_fallback_mode",
]
