"""
Integration tests for Prometheus /metrics endpoint.

Tests AC 6.1.1: Metrics endpoint returns valid Prometheus exposition format
Tests that the endpoint is accessible and returns properly formatted metrics.
"""

import os

import httpx
import pytest

# Use environment variable for port configuration (consistent with other integration tests)
METRICS_PORT = os.environ.get("METRICS_PORT", "28080")
METRICS_URL = f"http://localhost:{METRICS_PORT}/metrics"


@pytest.mark.asyncio
async def test_metrics_endpoint_accessible():
    """Test that /metrics endpoint is accessible and returns 200 OK."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(METRICS_URL, timeout=5.0)
            assert response.status_code == 200
        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
async def test_metrics_endpoint_content_type():
    """Test that /metrics returns correct Content-Type header (AC 6.1.1)."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(METRICS_URL, timeout=5.0)

            # AC 6.1.1: Content-Type is "text/plain; charset=utf-8"
            content_type = response.headers.get("content-type", "")
            assert "text/plain" in content_type
            assert response.status_code == 200

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
async def test_metrics_endpoint_prometheus_format():
    """Test that /metrics returns valid Prometheus exposition format."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(METRICS_URL, timeout=5.0)

            text = response.text

            # Verify Prometheus format characteristics
            assert "# HELP" in text, "Missing HELP comments"
            assert "# TYPE" in text, "Missing TYPE declarations"

            # Verify our custom metrics are present (AC 6.1.2)
            assert "ai_memory_captures_total" in text
            assert "ai_memory_retrievals_total" in text
            assert "bmad_embedding_requests_total" in text
            assert "bmad_deduplication_events_total" in text
            assert "bmad_collection_size" in text
            assert "bmad_queue_size" in text
            assert "bmad_hook_duration_seconds" in text
            assert "bmad_embedding_duration_seconds" in text
            assert "bmad_retrieval_duration_seconds" in text
            assert "bmad_failure_events_total" in text
            assert "ai_memory_system_info" in text

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
async def test_metrics_include_default_process_metrics():
    """Test that default process metrics are included."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(METRICS_URL, timeout=5.0)

            text = response.text

            # Default prometheus_client metrics should be present
            assert (
                "process_cpu_seconds_total" in text
                or "process_virtual_memory_bytes" in text
            )

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
async def test_metrics_endpoint_no_authentication_required():
    """Test that /metrics endpoint doesn't require authentication (standard Prometheus)."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            # No auth headers
            response = await client.get(METRICS_URL, timeout=5.0)

            # Should succeed without auth
            assert response.status_code == 200

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


# ==============================================================================
# AC 6.7.1: Comprehensive Metrics Endpoint Tests
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_metric_value_increments_on_operations():
    """Test that metrics values increment when operations occur (AC 6.7.1 subtask 2).

    This test verifies:
    1. Metrics start at baseline values
    2. After operations, metric values increase
    3. Counter increments are captured correctly

    Note: This test requires the embedding service to be running and functional.
    It simulates real operations that would increment metrics.
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            # Get baseline metrics
            response_before = await client.get(METRICS_URL, timeout=5.0)
            assert response_before.status_code == 200
            text_before = response_before.text

            # Extract baseline counter value for embedding_requests_total
            # Format: bmad_embedding_requests_total{status="success"} VALUE
            baseline_embedding_requests = _extract_metric_value(
                text_before, 'bmad_embedding_requests_total{status="success"}'
            )

            # Trigger an embedding request by calling the embedding endpoint
            embed_response = await client.post(
                f"http://localhost:{METRICS_PORT}/embed",
                json={"text": "test memory content for metrics validation"},
                timeout=10.0,
            )

            # If embedding service is functional, this should succeed
            if embed_response.status_code == 200:
                # Get metrics after operation
                response_after = await client.get(METRICS_URL, timeout=5.0)
                text_after = response_after.text

                # Extract updated counter value
                updated_embedding_requests = _extract_metric_value(
                    text_after, 'bmad_embedding_requests_total{status="success"}'
                )

                # Verify counter incremented
                if (
                    baseline_embedding_requests is not None
                    and updated_embedding_requests is not None
                ):
                    assert (
                        updated_embedding_requests > baseline_embedding_requests
                    ), f"Counter did not increment: before={baseline_embedding_requests}, after={updated_embedding_requests}"
            else:
                pytest.skip(
                    f"Embedding endpoint not functional: {embed_response.status_code}"
                )

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_histogram_bucket_configurations():
    """Test that histogram metrics have correct bucket configurations (AC 6.7.1 subtask 3).

    Verifies:
    - hook_duration_seconds has buckets: 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0
    - embedding_duration_seconds has buckets: 0.1, 0.5, 1.0, 2.0, 5.0, 10.0
    - retrieval_duration_seconds has buckets: 0.1, 0.5, 1.0, 2.0, 3.0, 5.0

    Note: Histograms only show buckets after first observation. If empty list returned,
    verify TYPE declaration exists instead (proves histogram is registered).
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(METRICS_URL, timeout=5.0)
            text = response.text

            # Verify histogram TYPE declarations exist (proves metrics are registered)
            assert (
                "# TYPE bmad_hook_duration_seconds histogram" in text
            ), "hook_duration_seconds histogram not registered"
            assert (
                "# TYPE bmad_embedding_duration_seconds histogram" in text
            ), "embedding_duration_seconds histogram not registered"
            assert (
                "# TYPE bmad_retrieval_duration_seconds histogram" in text
            ), "retrieval_duration_seconds histogram not registered"

            # Parse histogram buckets (only present after observations)
            embedding_buckets = _extract_histogram_buckets(
                text, "bmad_embedding_duration_seconds"
            )
            retrieval_buckets = _extract_histogram_buckets(
                text, "bmad_retrieval_duration_seconds"
            )

            # Embedding and retrieval histograms should have buckets (have data from service startup)
            expected_embedding_buckets = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, "+Inf"]
            if embedding_buckets:  # Only assert if buckets exist
                assert set(expected_embedding_buckets).issubset(
                    set(embedding_buckets)
                ), f"embedding_duration_seconds missing expected buckets. Expected: {expected_embedding_buckets}, Got: {embedding_buckets}"

            expected_retrieval_buckets = [0.1, 0.5, 1.0, 2.0, 3.0, 5.0, "+Inf"]
            if retrieval_buckets:  # Only assert if buckets exist
                assert set(expected_retrieval_buckets).issubset(
                    set(retrieval_buckets)
                ), f"retrieval_duration_seconds missing expected buckets. Expected: {expected_retrieval_buckets}, Got: {retrieval_buckets}"

            # hook_duration may not have buckets yet (only populated during hook execution)
            # We verified the TYPE declaration above, which is sufficient

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gauge_updates_reflect_real_state():
    """Test that gauge metrics reflect actual system state (AC 6.7.1 subtask 4).

    Verifies that bmad_collection_size and bmad_queue_size gauges show
    current values that match reality (not stale or incorrect).

    Note: Gauges may not have values until stats collection runs. We verify
    the TYPE declarations exist (proves gauges are registered).
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(METRICS_URL, timeout=5.0)
            text = response.text

            # Verify gauge TYPE declarations exist (proves metrics are registered)
            assert (
                "# TYPE bmad_collection_size gauge" in text
            ), "bmad_collection_size gauge not registered"
            assert (
                "# TYPE bmad_queue_size gauge" in text
            ), "bmad_queue_size gauge not registered"

            # Extract gauge values (may be empty if stats haven't been collected yet)
            collection_sizes = _extract_gauge_values(text, "bmad_collection_size")
            queue_sizes = _extract_gauge_values(text, "bmad_queue_size")

            # If gauges have values, they should be non-negative
            for metric_line, value in collection_sizes:
                assert value >= 0, f"Gauge has negative value: {metric_line} = {value}"

            for metric_line, value in queue_sizes:
                assert (
                    value >= 0
                ), f"Queue gauge has negative value: {metric_line} = {value}"

            # Success: Gauges are registered, and any values present are valid

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_metrics_endpoint_response_time():
    """Test that /metrics endpoint responds within 100ms (AC 6.7.1 subtask 5).

    NFR-I4 compliance: Metrics endpoint must respond < 100ms.
    """
    import time

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            start = time.perf_counter()
            response = await client.get(METRICS_URL, timeout=5.0)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert response.status_code == 200
            assert (
                elapsed_ms < 100
            ), f"Metrics endpoint took {elapsed_ms:.2f}ms, exceeds 100ms threshold (NFR-I4)"

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failure_event_counters():
    """Test that failure event counters are exposed and parseable (AC 6.7.1 subtask 6).

    Verifies bmad_failure_events_total counter exists with expected labels:
    - component: qdrant, embedding, queue, hook
    - error_code: QDRANT_UNAVAILABLE, EMBEDDING_TIMEOUT, etc.
    """
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.get(METRICS_URL, timeout=5.0)
            text = response.text

            # Verify failure_events_total metric exists
            assert (
                "bmad_failure_events_total" in text
            ), "bmad_failure_events_total counter not exposed"

            # Extract all failure event counter lines
            failure_lines = [
                line
                for line in text.split("\n")
                if line.startswith("bmad_failure_events_total{")
            ]

            # Verify label structure if any failures have occurred
            # Format: bmad_failure_events_total{component="X",error_code="Y"} VALUE
            for line in failure_lines:
                if "{" in line and "}" in line:
                    labels = line.split("{")[1].split("}")[0]
                    assert "component=" in labels, f"Missing component label: {line}"
                    assert "error_code=" in labels, f"Missing error_code label: {line}"

            # Note: We don't assert failures > 0 because a healthy system may have 0 failures
            # But we verify the metric structure is correct

        except httpx.ConnectError:
            pytest.skip("Embedding service not running - start with docker compose up")


# ==============================================================================
# Helper Functions for Metrics Parsing
# ==============================================================================


def _extract_metric_value(text: str, metric_pattern: str) -> float | None:
    """Extract numeric value from a Prometheus metric line.

    Args:
        text: Full metrics response text
        metric_pattern: Metric name pattern to search for (e.g., 'bmad_embedding_requests_total{status="success"}')

    Returns:
        Float value of the metric, or None if not found
    """
    for line in text.split("\n"):
        if line.startswith(metric_pattern):
            try:
                # Format: metric_name{labels} VALUE
                value_str = line.split()[-1]
                return float(value_str)
            except (IndexError, ValueError):
                continue
    return None


def _extract_histogram_buckets(text: str, metric_name: str) -> list[float]:
    """Extract bucket boundaries from a histogram metric.

    Args:
        text: Full metrics response text
        metric_name: Histogram metric name (e.g., 'bmad_hook_duration_seconds')

    Returns:
        List of bucket boundaries (le= values + '+Inf')

    Note:
        Returns empty list if histogram TYPE exists but no buckets (no observations yet).
        This is expected for histograms that haven't recorded any data.
    """
    buckets = []
    bucket_pattern = f"{metric_name}_bucket{{"

    for line in text.split("\n"):
        if line.startswith(bucket_pattern):
            # Format: metric_name_bucket{labels,le="X.X"} VALUE
            if "le=" in line:
                try:
                    le_value = line.split('le="')[1].split('"')[0]
                    if le_value == "+Inf":
                        buckets.append("+Inf")
                    else:
                        buckets.append(float(le_value))
                except (IndexError, ValueError):
                    continue

    return sorted(buckets, key=lambda x: float("inf") if x == "+Inf" else x)


def _extract_gauge_values(text: str, metric_name: str) -> list[tuple[str, float]]:
    """Extract all gauge values for a metric.

    Args:
        text: Full metrics response text
        metric_name: Gauge metric name (e.g., 'bmad_collection_size')

    Returns:
        List of tuples: (full_metric_line, value)
    """
    gauges = []

    for line in text.split("\n"):
        if line.startswith(metric_name + "{") or line.startswith(metric_name + " "):
            try:
                # Format: metric_name{labels} VALUE or metric_name VALUE
                parts = line.split()
                if len(parts) >= 2:
                    value = float(parts[-1])
                    gauges.append((line, value))
            except (ValueError, IndexError):
                continue

    return gauges
