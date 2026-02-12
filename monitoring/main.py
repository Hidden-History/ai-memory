"""AI Memory Monitoring API.

FastAPI monitoring service following 2026 best practices:
- Kubernetes liveness/readiness probes
- Async-first endpoints
- Pydantic response models with Field descriptions
- Structured logging with extras dict
- OpenAPI auto-documentation
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, Response
from prometheus_client import REGISTRY, make_asgi_app
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse


class StructuredLogFormatter(logging.Formatter):
    """Structured JSON formatter that captures extra fields.

    Collects non-standard LogRecord attributes into 'extra' JSON object.
    2026 best practice for structured logging.
    """

    # Standard LogRecord attributes to exclude from extra
    STANDARD_ATTRS = {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "exc_info",
        "exc_text",
        "thread",
        "threadName",
        "taskName",
        "message",
        "asctime",
    }

    def format(self, record):
        import json

        # Collect extra fields (anything not in standard attrs)
        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self.STANDARD_ATTRS and not key.startswith("_")
        }
        record.extra = json.dumps(extra_fields) if extra_fields else "{}"
        return super().format(record)


# Configure structured logging with custom formatter (2026 standard)
handler = logging.StreamHandler()
handler.setFormatter(
    StructuredLogFormatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "extra": %(extra)s}'
    )
)
logger = logging.getLogger("ai_memory.monitoring")
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent duplicate logs


def sanitize_log_input(value: str, max_length: int = 200) -> str:
    """
    Sanitize user input for safe logging per security best practices.

    Uses repr() for CodeQL-recognized sanitization, then strips quotes
    and truncates to max_length. This prevents log injection by:
    1. Escaping all control characters (repr behavior)
    2. Removing non-printable characters
    3. Truncating to prevent log flooding

    Args:
        value: User-provided input to sanitize
        max_length: Maximum length of output (default 200)

    Returns:
        Sanitized string safe for logging
    """
    if not isinstance(value, str):
        value = str(value)
    # Use repr() for CodeQL-recognized sanitization
    # This escapes newlines, tabs, and other control characters
    sanitized = repr(value)
    # Remove the quotes added by repr()
    if (sanitized.startswith("'") and sanitized.endswith("'")) or (
        sanitized.startswith('"') and sanitized.endswith('"')
    ):
        sanitized = sanitized[1:-1]
    # Additional filter for any remaining non-printable chars
    sanitized = "".join(c for c in sanitized if c.isprintable())
    return sanitized[:max_length]


# Import metrics module to register metrics with Prometheus (Story 6.1)
import sys
from contextlib import asynccontextmanager
from pathlib import Path

src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

try:
    from memory import metrics  # noqa: F401 - imported for side effects
except ImportError:
    logger.warning(
        "metrics_import_failed",
        extra={"error_details": "Could not import memory.metrics module"},
    )

# Initialize async Qdrant client (2026 best practice for async FastAPI)
# BP-040: API key + HTTPS configurable via environment variables
qdrant_host = os.getenv("QDRANT_HOST", "localhost")
qdrant_port = int(os.getenv("QDRANT_PORT", "26350"))
qdrant_api_key = os.getenv("QDRANT_API_KEY")
qdrant_use_https = os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true"
client = AsyncQdrantClient(
    host=qdrant_host,
    port=qdrant_port,
    api_key=qdrant_api_key,
    https=qdrant_use_https,
    timeout=10,
)


def _get_monitorable_collections(sync_client) -> list[str]:
    """Get list of collections to monitor, including conditional ones."""
    collections = ["code-patterns", "conventions", "discussions"]
    # Add jira-data if it exists (conditional collection, only when Jira enabled)
    try:
        sync_client.get_collection("jira-data")
        collections.append("jira-data")
    except Exception:
        pass  # Collection doesn't exist, skip
    return collections


# Lazy-loaded sync client for stats operations (reused across requests)
_sync_client: "QdrantClient | None" = None


def get_sync_client():
    """Get or create sync Qdrant client for stats operations.

    Reuses single client instance to avoid creating new TCP connections
    on every health check request (2026 best practice).
    """
    global _sync_client
    if _sync_client is None:
        from qdrant_client import QdrantClient

        _sync_client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            api_key=qdrant_api_key,
            https=qdrant_use_https,  # BP-040
            timeout=5,
        )
    return _sync_client


# Background task to update collection metrics (Story 6.6)
async def update_metrics_periodically():
    """Update collection statistics metrics every 60 seconds."""
    while True:
        try:
            from memory.metrics import update_collection_metrics
            from memory.metrics_push import push_collection_size_metrics_async
            from memory.stats import get_collection_stats

            # Reuse sync client for stats (avoids creating new connection per update)
            sync_client = get_sync_client()

            for collection_name in _get_monitorable_collections(sync_client):
                try:
                    stats = get_collection_stats(sync_client, collection_name)
                    update_collection_metrics(stats)

                    # Push to Pushgateway for Grafana dashboard visibility (TECH-DEBT-072)
                    try:
                        # Push total collection size
                        push_collection_size_metrics_async(
                            collection=collection_name,
                            project="all",
                            point_count=stats.total_points,
                        )

                        # Push per-project breakdown
                        for project_name, count in stats.points_by_project.items():
                            push_collection_size_metrics_async(
                                collection=collection_name,
                                project=project_name,
                                point_count=count,
                            )
                    except Exception as push_error:
                        # Graceful degradation: log but don't fail the update task
                        logger.warning(
                            "pushgateway_push_failed",
                            extra={
                                "collection": collection_name,
                                "error": str(push_error),
                            },
                        )

                    logger.debug(
                        "metrics_updated",
                        extra={
                            "collection": collection_name,
                            "total_points": stats.total_points,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "metrics_update_failed",
                        extra={"collection": collection_name, "error": str(e)},
                    )
        except Exception as e:
            logger.error("metrics_updater_error", extra={"error": str(e)})

        await asyncio.sleep(60)  # Update every 60 seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle with background tasks."""
    # Start background metrics updater
    task = asyncio.create_task(update_metrics_periodically())
    yield
    # Cleanup on shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# Create FastAPI app with lifespan context
app = FastAPI(
    title="AI Memory Monitoring API",
    description="Testing and verification API for AI Memory Module",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    lifespan=lifespan,
)

# Mount Prometheus metrics endpoint (Story 6.1, AC 6.1.5)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


class HealthResponse(BaseModel):
    """Health check response model (2026 standard)."""

    status: str = Field(
        ..., description="Health status: healthy, degraded, or unhealthy"
    )
    qdrant_available: bool = Field(..., description="Qdrant service availability")
    collections_count: int = Field(..., description="Number of collections")
    warnings: list[str] = Field(
        default_factory=list, description="Collection size warnings"
    )


class MemoryResponse(BaseModel):
    """Memory retrieval response model."""

    status: str = Field(
        ..., description="Response status: success, not_found, or error"
    )
    data: Optional[Dict[str, Any]] = Field(None, description="Memory payload if found")
    error: Optional[str] = Field(None, description="Error message if failed")


class SearchRequest(BaseModel):
    """Search request model for semantic search."""

    query: str = Field(..., description="Search query text")
    collection: str = Field("code-patterns", description="Collection to search")
    limit: int = Field(10, description="Maximum results to return")


class SearchResponse(BaseModel):
    """Search response model."""

    status: str = Field(..., description="Response status: success or error")
    results: list = Field(default_factory=list, description="List of matching memories")
    error: Optional[str] = Field(None, description="Error message if failed")


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """
    Kubernetes-style health check endpoint (2026 best practice).

    Returns service health status including Qdrant availability and
    collection size warnings (AC 6.6.5).

    Status values:
    - healthy: All services OK, no warnings
    - degraded: Services OK but collection size warnings present
    - unhealthy: Qdrant unavailable

    Used for Docker healthchecks and integration tests.
    """
    try:
        # Check Qdrant availability (async call)
        collections = await client.get_collections()
        collections_count = len(collections.collections)

        # Check collection size thresholds (AC 6.6.5)
        # Import here to avoid circular import issues
        import sys
        from pathlib import Path

        src_path = Path(__file__).parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        from memory.stats import get_collection_stats
        from memory.warnings import check_collection_thresholds

        # Reuse sync client for stats (avoids creating new connection per request)
        sync_client = get_sync_client()

        all_warnings = []
        for collection_name in _get_monitorable_collections(sync_client):
            try:
                stats = get_collection_stats(sync_client, collection_name)
                warnings = check_collection_thresholds(stats)
                all_warnings.extend(warnings)
            except Exception as e:
                logger.warning(
                    "stats_check_failed",
                    extra={"collection": collection_name, "error": str(e)},
                )

        # Determine status based on warnings
        has_critical = any("CRITICAL" in w for w in all_warnings)
        health_status = (
            "degraded" if has_critical else ("degraded" if all_warnings else "healthy")
        )

        logger.info(
            "health_check_passed",
            extra={
                "qdrant_available": True,
                "collections_count": collections_count,
                "warnings_count": len(all_warnings),
                "status": health_status,
            },
        )

        return HealthResponse(
            status=health_status,
            qdrant_available=True,
            collections_count=collections_count,
            warnings=all_warnings,
        )
    except Exception as e:
        logger.error("health_check_failed", extra={"error": str(e)})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "qdrant_available": False,
                "collections_count": 0,
                "warnings": [],
            },
        )


@app.get("/live", tags=["Health"])
async def liveness():
    """
    Kubernetes liveness probe (2026 best practice).

    Checks if the application process is running.
    Returns 200 if alive, used by K8s liveness probes.
    """
    return {"status": "alive"}


@app.get("/ready", tags=["Health"])
async def readiness():
    """
    Kubernetes readiness probe (2026 best practice).

    Checks if the application can handle traffic (Qdrant available).
    Returns 200 if ready, 503 if not ready for traffic.
    """
    try:
        await client.get_collections()
        logger.info("readiness_check_passed", extra={"qdrant_available": True})
        return {"status": "ready", "qdrant_available": True}
    except Exception as e:
        logger.warning("readiness_check_failed", extra={"error": str(e)})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "qdrant_available": False},
        )


@app.get(
    "/memory/{memory_id}", response_model=MemoryResponse, tags=["Memory Operations"]
)
async def get_memory(memory_id: str, collection: str = "code-patterns"):
    """
    Retrieve a specific memory by ID for testing verification.

    Args:
        memory_id: UUID of the memory to retrieve
        collection: Collection name (code-patterns, conventions, or discussions)

    Returns:
        Memory payload if found, error if not found or Qdrant unavailable
    """
    try:
        result = await client.retrieve(
            collection_name=collection,
            ids=[memory_id],
            with_payload=True,
            with_vectors=False,  # Don't return vectors for readability
        )

        if result:
            logger.info(
                "memory_retrieved",
                extra={
                    "memory_id": sanitize_log_input(memory_id),
                    "collection": sanitize_log_input(collection),
                },
            )
            return MemoryResponse(status="success", data=result[0].payload)
        else:
            logger.info(
                "memory_not_found",
                extra={
                    "memory_id": sanitize_log_input(memory_id),
                    "collection": sanitize_log_input(collection),
                },
            )
            return MemoryResponse(
                status="not_found",
                data=None,
                error=f"Memory {sanitize_log_input(memory_id)} not found in {sanitize_log_input(collection)}",
            )

    except UnexpectedResponse as e:
        logger.error(
            "qdrant_error",
            extra={"error": str(e), "memory_id": sanitize_log_input(memory_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Qdrant unavailable"
        )


@app.get("/stats/{collection}", tags=["Collection Statistics"])
async def collection_stats(collection: str):
    """
    Get collection statistics for testing verification.

    Args:
        collection: Collection name (code-patterns, conventions, or discussions)

    Returns:
        Collection info including point count and status
    """
    try:
        info = await client.get_collection(collection)
        logger.info(
            "collection_stats_retrieved",
            extra={
                "collection": sanitize_log_input(collection),
                "points_count": info.points_count,
            },
        )
        return {
            "status": "success",
            "collection": collection,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "qdrant_status": info.status,
        }
    except UnexpectedResponse:
        logger.warning(
            "collection_not_found",
            extra={"collection": sanitize_log_input(collection)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection {sanitize_log_input(collection)} not found",
        )


@app.post("/search", response_model=SearchResponse, tags=["Memory Operations"])
async def search_memories(request: SearchRequest):
    """
    Search memories using text query for testing verification.

    This endpoint supports integration tests that verify memories are
    stored correctly and retrievable via semantic search.

    Args:
        request: Search request with query, collection, and limit

    Returns:
        List of matching memories with payloads
    """
    try:
        # Use scroll to get recent memories matching query text in payload
        # For testing, we search by content field in payload
        result = await client.scroll(
            collection_name=request.collection,
            scroll_filter=None,  # Get all points for now (simple implementation)
            limit=min(request.limit * 10, 100),  # Fetch more to search through
            with_payload=True,
            with_vectors=False,
        )

        # Filter results by query text in content field
        matching_results = []
        for point in result[0]:
            payload = point.payload
            content = payload.get("content", "")
            # Simple substring match for testing
            if request.query.lower() in content.lower():
                matching_results.append(
                    {
                        "id": point.id,
                        "payload": payload,
                        "score": 1.0,  # Simple match score
                    }
                )
                if len(matching_results) >= request.limit:
                    break

        logger.info(
            "search_completed",
            extra={
                "collection": sanitize_log_input(request.collection),
                "query_length": len(request.query),
                "results_count": len(matching_results),
            },
        )

        return SearchResponse(status="success", results=matching_results)

    except UnexpectedResponse as e:
        logger.error(
            "search_failed",
            extra={
                "error": str(e),
                "collection": sanitize_log_input(request.collection),
            },
        )
        return SearchResponse(
            status="error",
            results=[],
            error=f"Search failed: {sanitize_log_input(str(e))}",
        )
