"""Embedding service client for BMAD Memory Module.

Provides httpx-based client for Nomic Embed Code service with connection pooling,
structured logging, and graceful error handling.

Architecture Reference: architecture.md:235-287 (Service Client Architecture)
Best Practices: https://medium.com/@sparknp1/8-httpx-asyncio-patterns-for-safer-faster-clients-f27bc82e93e6
"""

import logging
import os
import time
from typing import Optional

import httpx

from .config import MemoryConfig, get_config

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import (
        embedding_requests_total,
        embedding_duration_seconds,
        failure_events_total,
    )
except ImportError:
    embedding_requests_total = None
    embedding_duration_seconds = None
    failure_events_total = None

__all__ = ["EmbeddingClient", "EmbeddingError"]

logger = logging.getLogger("bmad.memory.embed")


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

    def __init__(self, config: Optional[MemoryConfig] = None):
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
            connect=3.0,   # Connection establishment timeout
            read=read_timeout,  # Read timeout - configurable for CPU vs GPU mode
            write=5.0,     # Write timeout for request body
            pool=3.0,      # Pool acquisition timeout
        )

        # Connection pooling with 2025 recommended defaults
        # Source: https://www.python-httpx.org/advanced/resource-limits/
        limits = httpx.Limits(
            max_keepalive_connections=20,  # Keep-alive pool size
            max_connections=100,           # Total connection limit
            keepalive_expiry=10.0,         # Idle timeout - reduced from 30s to avoid stale connections
        )

        self.client = httpx.Client(timeout=timeout_config, limits=limits)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts.

        Sends batch request to embedding service and returns vector embeddings.
        Uses connection pooling for optimal performance.

        Args:
            texts: List of text strings to embed (supports batch operations).

        Returns:
            List of embedding vectors, one per input text. Each vector has
            768 dimensions (DEC-010: Jina Embeddings v2 Base Code).

        Raises:
            EmbeddingError: If request times out or HTTP error occurs.

        Example:
            >>> client = EmbeddingClient()
            >>> embeddings = client.embed(["text1", "text2"])
            >>> len(embeddings)
            2
            >>> len(embeddings[0])
            768
        """
        start_time = time.perf_counter()

        try:
            response = self.client.post(
                f"{self.base_url}/embed",
                json={"texts": texts},
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]

            # Metrics: Embedding request success (Story 6.1, AC 6.1.3)
            if embedding_requests_total:
                embedding_requests_total.labels(status="success").inc()
            if embedding_duration_seconds:
                duration_seconds = time.perf_counter() - start_time
                embedding_duration_seconds.observe(duration_seconds)

            return embeddings

        except httpx.TimeoutException as e:
            logger.error(
                "embedding_timeout",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "error": str(e),
                },
            )

            # Metrics: Embedding request timeout (Story 6.1, AC 6.1.3)
            if embedding_requests_total:
                embedding_requests_total.labels(status="timeout").inc()
            if embedding_duration_seconds:
                duration_seconds = time.perf_counter() - start_time
                embedding_duration_seconds.observe(duration_seconds)

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding", error_code="EMBEDDING_TIMEOUT"
                ).inc()

            raise EmbeddingError("EMBEDDING_TIMEOUT") from e

        except httpx.HTTPError as e:
            logger.error(
                "embedding_error",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "error": str(e),
                },
            )

            # Metrics: Embedding request failed (Story 6.1, AC 6.1.3)
            if embedding_requests_total:
                embedding_requests_total.labels(status="failed").inc()
            if embedding_duration_seconds:
                duration_seconds = time.perf_counter() - start_time
                embedding_duration_seconds.observe(duration_seconds)

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding", error_code="EMBEDDING_ERROR"
                ).inc()

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
            Uses try/except to handle interpreter shutdown safely.
            Prefer using context manager or explicit close() instead.
        """
        try:
            self.close()
        except Exception:
            # Silently ignore errors during interpreter shutdown
            # when httpx module may already be unloaded
            pass
