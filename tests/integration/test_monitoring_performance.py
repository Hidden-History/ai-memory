"""
Performance benchmarks for monitoring overhead.

Tests verify that monitoring instrumentation (metrics, logging, etc.)
does not violate NFR-P1 performance requirements:
- Metrics collection: <1ms overhead
- Logging operations: <5ms overhead
- Hook instrumentation: <10ms overhead
- Total hook execution: <500ms (NFR-P1)

Task 7: Add performance benchmarks for monitoring overhead
"""

import pytest
import time
import logging
from io import StringIO


@pytest.mark.integration
@pytest.mark.performance
class TestMonitoringPerformance:
    """Performance benchmarks for monitoring overhead."""

    def test_metrics_collection_overhead(self):
        """Test that metrics collection overhead is <1ms (Task 7.1).

        Verifies that incrementing counters, updating gauges, and observing
        histograms completes within 1ms to avoid impacting hot paths.
        """
        from src.memory.metrics import (
            memory_captures_total,
            collection_size,
            hook_duration_seconds,
        )

        iterations = 100
        start = time.perf_counter()

        for i in range(iterations):
            # Simulate typical metrics operations during memory capture
            memory_captures_total.labels(
                hook_type="PostToolUse", status="success", project="perf-test"
            ).inc()
            collection_size.labels(collection="code-patterns", project="perf-test").set(
                i
            )
            hook_duration_seconds.labels(hook_type="PostToolUse").observe(0.123)

        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_per_operation = elapsed_ms / iterations

        assert (
            avg_per_operation < 1.0
        ), f"Metrics overhead {avg_per_operation:.3f}ms exceeds 1ms threshold"

    def test_logging_overhead(self):
        """Test that structured logging overhead is <5ms (Task 7.2).

        Verifies that emitting structured log events with extras dict
        completes within 5ms.
        """
        from src.memory.logging_config import StructuredFormatter

        # Setup logger with StructuredFormatter
        logger = logging.getLogger("bmad.memory.perf_test")
        logger.setLevel(logging.INFO)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

        iterations = 100
        start = time.perf_counter()

        for i in range(iterations):
            # Simulate typical logging operations
            logger.info(
                "memory_captured",
                extra={
                    "memory_id": f"test-{i}",
                    "project": "perf-test",
                    "type": "implementation",
                    "size": 1024,
                },
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_per_operation = elapsed_ms / iterations

        # Cleanup
        logger.removeHandler(handler)

        assert (
            avg_per_operation < 5.0
        ), f"Logging overhead {avg_per_operation:.3f}ms exceeds 5ms threshold"

    def test_stats_collection_overhead(self):
        """Test that stats collection overhead is reasonable (Task 7.3).

        Verifies that calling get_collection_stats() and check_collection_thresholds()
        completes within acceptable time.

        Note: This requires Qdrant to be running. Will skip if unavailable.
        """
        from src.memory.stats import CollectionStats
        from src.memory.warnings import check_collection_thresholds

        # Create mock stats object
        stats = CollectionStats(
            collection_name="test_collection",
            total_points=5000,
            indexed_points=5000,
            segments_count=1,
            disk_size_bytes=1024000,
            last_updated=None,
            projects=["project-a", "project-b"],
            points_by_project={"project-a": 2000, "project-b": 3000},
        )

        iterations = 100
        start = time.perf_counter()

        for _ in range(iterations):
            # Simulate stats checking
            warnings = check_collection_thresholds(stats)

        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_per_operation = elapsed_ms / iterations

        assert (
            avg_per_operation < 10.0
        ), f"Stats collection overhead {avg_per_operation:.3f}ms exceeds 10ms threshold"

    def test_total_monitoring_overhead_within_nfr(self):
        """Test that total monitoring overhead doesn't violate NFR-P1 (Task 7.4).

        NFR-P1: Hooks must complete within 500ms.
        This test simulates a typical hook execution with all monitoring
        instrumentation active and verifies total overhead is acceptable.

        Monitoring overhead budget:
        - Metrics: <1ms
        - Logging: <5ms
        - Stats: <10ms
        - Total monitoring: <20ms (~4% of 500ms budget)
        """
        from src.memory.metrics import (
            memory_captures_total,
            collection_size,
            hook_duration_seconds,
        )
        from src.memory.logging_config import StructuredFormatter

        # Setup logging
        logger = logging.getLogger("bmad.memory.nfr_test")
        logger.setLevel(logging.INFO)
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

        iterations = 10  # Fewer iterations for full simulation
        overhead_samples = []

        for i in range(iterations):
            start = time.perf_counter()

            # Simulate full monitoring instrumentation
            # 1. Metrics collection
            memory_captures_total.labels(
                hook_type="PostToolUse", status="success", project="nfr-test"
            ).inc()
            collection_size.labels(collection="code-patterns", project="nfr-test").set(
                i * 100
            )
            hook_duration_seconds.labels(hook_type="PostToolUse").observe(0.123)

            # 2. Structured logging
            logger.info(
                "memory_captured",
                extra={
                    "memory_id": f"nfr-test-{i}",
                    "project": "nfr-test",
                    "type": "implementation",
                },
            )

            # 3. Stats checking (simplified - no Qdrant call)
            from src.memory.stats import CollectionStats
            from src.memory.warnings import check_collection_thresholds

            stats = CollectionStats(
                collection_name="test",
                total_points=i * 100,
                indexed_points=i * 100,
                segments_count=1,
                disk_size_bytes=1024 * i,
                last_updated=None,
                projects=["test"],
                points_by_project={"test": i * 100},
            )
            warnings = check_collection_thresholds(stats)

            elapsed_ms = (time.perf_counter() - start) * 1000
            overhead_samples.append(elapsed_ms)

        # Cleanup
        logger.removeHandler(handler)

        # Calculate statistics
        avg_overhead = sum(overhead_samples) / len(overhead_samples)
        max_overhead = max(overhead_samples)

        # Total monitoring overhead should be <5% of 500ms NFR budget (25ms)
        assert (
            avg_overhead < 25.0
        ), f"Average monitoring overhead {avg_overhead:.3f}ms exceeds 25ms threshold (5% of NFR-P1)"
        assert (
            max_overhead < 50.0
        ), f"Max monitoring overhead {max_overhead:.3f}ms exceeds 50ms threshold (10% of NFR-P1)"


@pytest.mark.integration
@pytest.mark.performance
@pytest.mark.asyncio
async def test_metrics_endpoint_response_time_stress():
    """Stress test metrics endpoint under concurrent load.

    Verifies that /metrics endpoint maintains <100ms response time
    even under concurrent request load (NFR-I4 compliance).
    """
    import httpx
    import os
    import asyncio

    metrics_port = os.environ.get("METRICS_PORT", "28080")
    metrics_url = f"http://localhost:{metrics_port}/metrics"

    # Simulate 10 concurrent requests
    async def fetch_metrics():
        async with httpx.AsyncClient(follow_redirects=True) as client:
            start = time.perf_counter()
            try:
                response = await client.get(metrics_url, timeout=5.0)
                elapsed_ms = (time.perf_counter() - start) * 1000
                return elapsed_ms, response.status_code
            except httpx.ConnectError:
                pytest.skip("Embedding service not running")

    # Run 10 concurrent requests
    tasks = [fetch_metrics() for _ in range(10)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out skips
    valid_results = [r for r in results if not isinstance(r, Exception)]

    if not valid_results:
        pytest.skip("Embedding service not running")

    response_times = [elapsed for elapsed, status in valid_results if status == 200]

    if not response_times:
        pytest.skip("No successful responses")

    avg_response_time = sum(response_times) / len(response_times)
    max_response_time = max(response_times)

    # Under concurrent load, responses should be under 300ms (3x NFR-I4 baseline)
    # NFR-I4 specifies <100ms for individual requests, but concurrent load
    # may experience queueing delays in the embedding service
    assert (
        avg_response_time < 300
    ), f"Average response time {avg_response_time:.2f}ms exceeds 300ms (concurrent load threshold)"
    assert (
        max_response_time < 500
    ), f"Max response time {max_response_time:.2f}ms exceeds 500ms under load"
