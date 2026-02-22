"""Embedding service client for AI Memory Module.

Provides httpx-based client for Nomic Embed Code service with connection pooling,
structured logging, and graceful error handling.

Architecture Reference: architecture.md:235-287 (Service Client Architecture)
Best Practices: https://medium.com/@sparknp1/8-httpx-asyncio-patterns-for-safer-faster-clients-f27bc82e93e6
"""

import contextlib
import logging
import os
import random
import time

import httpx

from .config import MemoryConfig, get_config
from .metrics_push import push_embedding_metrics_async, push_failure_metrics_async

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import (
        embedding_duration_seconds,
        embedding_requests_total,
        failure_events_total,
    )
except ImportError:
    embedding_requests_total = None
    embedding_duration_seconds = None
    failure_events_total = None

__all__ = ["EmbeddingClient", "EmbeddingError"]

logger = logging.getLogger("ai_memory.embed")


class EmbeddingError(Exception):
    """Raised when embedding generation fails.

    This exception wraps httpx errors and timeouts for consistent error handling.
    """

    pass


class EmbeddingClient:
    """Client for the embedding service.

    Uses long-lived httpx.Client with connection pooling for optimal performance.
    Implements 2025 best practices: granular timeouts, connection pooling, structured logging.

    Attributes:
        config: MemoryConfig instance with service endpoints
        base_url: Full URL to embedding service
        client: Shared httpx.Client instance with connection pooling

    Example:
        >>> client = EmbeddingClient()
        >>> embeddings = client.embed(["def hello(): return 'world'"])
        >>> len(embeddings[0])
        768  # DEC-010: Jina Embeddings v2 Base Code dimensions
    """

    def __init__(self, config: MemoryConfig | None = None):
        """Initialize embedding client with configuration.

        Args:
            config: Optional MemoryConfig instance. Uses get_config() if not provided.

        Note:
            Creates a long-lived httpx.Client with connection pooling. Reuse this
            client instance across requests for optimal performance (60%+ latency reduction).
        """
        self.config = config or get_config()
        self.base_url = (
            f"http://{self.config.embedding_host}:{self.config.embedding_port}"
        )

        # 2025 Best Practice: Granular timeouts per operation type
        # Source: https://www.python-httpx.org/advanced/timeouts/
        # Read timeout is configurable via EMBEDDING_READ_TIMEOUT for integration tests
        # CPU mode (7B model): 20-30s typical, use 60s for safety
        # GPU mode: <2s (NFR-P2 compliant)
        read_timeout = float(os.getenv("EMBEDDING_READ_TIMEOUT", "15.0"))
        timeout_config = httpx.Timeout(
            connect=3.0,  # Connection establishment timeout
            read=read_timeout,  # Read timeout - configurable for CPU vs GPU mode
            write=5.0,  # Write timeout for request body
            pool=3.0,  # Pool acquisition timeout
        )

        # Connection pooling with 2025 recommended defaults
        # Source: https://www.python-httpx.org/advanced/resource-limits/
        limits = httpx.Limits(
            max_keepalive_connections=20,  # Keep-alive pool size
            max_connections=100,  # Total connection limit
            keepalive_expiry=10.0,  # Idle timeout - reduced from 30s to avoid stale connections
        )

        self.client = httpx.Client(timeout=timeout_config, limits=limits)

        # BUG-113: Retry configuration for transient timeout failures
        self._max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "2"))
        self._backoff_base = float(os.getenv("EMBEDDING_BACKOFF_BASE", "1.0"))
        self._backoff_cap = float(os.getenv("EMBEDDING_BACKOFF_CAP", "15.0"))

    def embed(
        self, texts: list[str], model: str = "en", project: str = "unknown"
    ) -> list[list[float]]:
        """Generate embeddings with retry on timeout errors.

        Wraps _embed_once() with exponential backoff + full jitter (AWS formula,
        BP-091). Only retries on timeout errors; non-timeout errors raise immediately.

        Args:
            texts: List of text strings to embed.
            model: "en" for prose, "code" for code content.
            project: Project identifier for metrics.

        Returns:
            List of embedding vectors (768 dimensions each).

        Raises:
            EmbeddingError: If all retries exhausted or non-timeout error occurs.
        """
        last_error: EmbeddingError | None = None
        for attempt in range(1 + self._max_retries):
            try:
                return self._embed_once(texts, model=model, project=project)
            except EmbeddingError as e:
                if "timeout" not in str(e).lower():
                    raise  # Non-timeout errors: no retry
                last_error = e
                if attempt < self._max_retries:
                    sleep_time = random.uniform(
                        0, min(self._backoff_cap, self._backoff_base * (2**attempt))
                    )
                    logger.warning(
                        "embedding_retry",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self._max_retries,
                            "sleep_seconds": round(sleep_time, 2),
                            "texts_count": len(texts),
                            "model": model,
                        },
                    )
                    time.sleep(sleep_time)
        raise last_error  # type: ignore[misc]

    def _embed_once(
        self, texts: list[str], model: str = "en", project: str = "unknown"
    ) -> list[list[float]]:
        """Generate embeddings for texts using specified model.

        Sends batch request to embedding service and returns vector embeddings.
        Uses connection pooling for optimal performance.

        Args:
            texts: List of text strings to embed (supports batch operations).
            model: "en" for prose, "code" for code content. Default: "en".

        Returns:
            List of embedding vectors, one per input text. Each vector has
            768 dimensions (SPEC-010: Jina Embeddings v2 dual model support).

        Raises:
            EmbeddingError: If request times out or HTTP error occurs.

        Example:
            >>> client = EmbeddingClient()
            >>> embeddings = client.embed(["text1", "text2"], model="en")
            >>> len(embeddings)
            2
            >>> len(embeddings[0])
            768
        """
        start_time = time.perf_counter()

        try:
            response = self.client.post(
                f"{self.base_url}/embed/dense",
                json={"texts": texts, "model": model},
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]

            # Metrics: Embedding request success (Story 6.1, AC 6.1.3)
            # TECH-DEBT-067: Add embedding_type and context labels
            duration_seconds = time.perf_counter() - start_time
            if embedding_requests_total:
                embedding_requests_total.labels(
                    status="success",
                    embedding_type="dense",
                    context="realtime",
                    project=project,
                    model=model,
                ).inc()
            if embedding_duration_seconds:
                embedding_duration_seconds.labels(
                    embedding_type="dense", model=model
                ).observe(duration_seconds)

            # Push to Pushgateway for hook subprocess visibility
            push_embedding_metrics_async(
                status="success",
                embedding_type="dense",
                duration_seconds=duration_seconds,
                context="realtime",
                model=model,
            )

            return embeddings

        except httpx.TimeoutException as e:
            logger.error(
                "embedding_timeout",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "model": model,
                    "error": str(e),
                },
            )

            # Metrics: Embedding request timeout (Story 6.1, AC 6.1.3)
            # TECH-DEBT-067: Add embedding_type and context labels
            duration_seconds = time.perf_counter() - start_time
            if embedding_requests_total:
                embedding_requests_total.labels(
                    status="timeout",
                    embedding_type="dense",
                    context="realtime",
                    project=project,
                    model=model,
                ).inc()
            if embedding_duration_seconds:
                embedding_duration_seconds.labels(
                    embedding_type="dense", model=model
                ).observe(duration_seconds)

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding",
                    error_code="EMBEDDING_TIMEOUT",
                    project=project,
                ).inc()

            # Push to Pushgateway for hook subprocess visibility
            push_embedding_metrics_async(
                status="timeout",
                embedding_type="dense",
                duration_seconds=duration_seconds,
                context="realtime",
                model=model,
            )
            push_failure_metrics_async(
                component="embedding",
                error_code="EMBEDDING_TIMEOUT",
                project=project,
            )

            raise EmbeddingError("EMBEDDING_TIMEOUT") from e

        except httpx.HTTPError as e:
            logger.error(
                "embedding_error",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "model": model,
                    "error": str(e),
                },
            )

            # Metrics: Embedding request failed (Story 6.1, AC 6.1.3)
            # TECH-DEBT-067: Add embedding_type and context labels
            duration_seconds = time.perf_counter() - start_time
            if embedding_requests_total:
                embedding_requests_total.labels(
                    status="failed",
                    embedding_type="dense",
                    context="realtime",
                    project=project,
                    model=model,
                ).inc()
            if embedding_duration_seconds:
                embedding_duration_seconds.labels(
                    embedding_type="dense", model=model
                ).observe(duration_seconds)

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding",
                    error_code="EMBEDDING_ERROR",
                    project=project,
                ).inc()

            # Push to Pushgateway for hook subprocess visibility
            push_embedding_metrics_async(
                status="failed",
                embedding_type="dense",
                duration_seconds=duration_seconds,
                context="realtime",
                model=model,
            )
            push_failure_metrics_async(
                component="embedding",
                error_code="EMBEDDING_ERROR",
                project=project,
            )

            raise EmbeddingError(f"EMBEDDING_ERROR: {e}") from e

    def health_check(self) -> bool:
        """Check if embedding service is healthy.

        Sends GET request to /health endpoint with timeout handling.

        Returns:
            True if service responds with 200, False otherwise.

        Example:
            >>> client = EmbeddingClient()
            >>> if client.health_check():
            ...     embeddings = client.embed(["test"])
        """
        try:
            response = self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(
                "embedding_health_check_failed",
                extra={"base_url": self.base_url, "error": str(e)},
            )
            return False

    def close(self) -> None:
        """Close httpx client and release resources.

        Call this method when done with the client, or use context manager.

        Example:
            >>> client = EmbeddingClient()
            >>> try:
            ...     embeddings = client.embed(["test"])
            ... finally:
            ...     client.close()
        """
        if hasattr(self, "client") and self.client is not None:
            self.client.close()

    def __enter__(self) -> "EmbeddingClient":
        """Enter context manager.

        Returns:
            Self for use in with statement.

        Example:
            >>> with EmbeddingClient() as client:
            ...     embeddings = client.embed(["test"])
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close client.

        Args:
            exc_type: Exception type if raised, None otherwise.
            exc_val: Exception value if raised, None otherwise.
            exc_tb: Exception traceback if raised, None otherwise.
        """
        self.close()

    def __del__(self) -> None:
        """Close httpx client on garbage collection.

        Note:
            Uses contextlib.suppress to handle interpreter shutdown safely.
            Prefer using context manager or explicit close() instead.
        """
        # Silently ignore errors during interpreter shutdown
        # when httpx module may already be unloaded
        with contextlib.suppress(Exception):
            self.close()
