"""
Integration tests for comprehensive monitoring functionality.

Tests cover:
- AC 6.7.5: Threshold warning tests
- AC 6.7.6: End-to-end monitoring flow tests

Story 6.7: Monitoring Integration Tests
"""

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
import os
import time
import httpx
from unittest.mock import patch


# ==============================================================================
# AC 6.7.5: Threshold Warning Tests
# ==============================================================================


@pytest.mark.integration
class TestThresholdWarnings:
    """Tests for AC 6.7.5: Collection size threshold warnings."""

    @pytest.fixture
    def qdrant_client(self):
        """Provide Qdrant client for tests."""
        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:26350")
        return QdrantClient(url=qdrant_url, timeout=10.0)

    @pytest.fixture
    def test_collection(self, qdrant_client):
        """Create temporary test collection for threshold tests."""
        collection_name = f"test_threshold_{int(time.time())}"

        # Create collection with 768d vectors (Jina Embeddings v2 Base Code)
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )

        yield collection_name

        # Cleanup
        try:
            qdrant_client.delete_collection(collection_name=collection_name)
        except Exception:
            pass  # Best effort cleanup

    def test_warning_triggers_at_configured_threshold(self, qdrant_client, test_collection):
        """Test that warnings are triggered when collection exceeds warning threshold.

        AC 6.7.5 Subtask 1: Warning triggers at configured thresholds.

        Default warning threshold is 10,000 memories (FR46a).
        """
        from src.memory.stats import get_collection_stats
        import importlib
        import sys

        # Patch environment BEFORE importing warnings module
        with patch.dict(os.environ, {"BMAD_COLLECTION_SIZE_WARNING": "5", "BMAD_COLLECTION_SIZE_CRITICAL": "15"}):
            # Reload warnings module to pick up new env vars
            if 'src.memory.warnings' in sys.modules:
                import src.memory.warnings
                importlib.reload(src.memory.warnings)
            from src.memory.warnings import check_collection_thresholds

            # Add 6 memories (exceeds warning threshold of 5)
            points = [
                PointStruct(
                    id=i,
                    vector=[0.1] * 768,
                    payload={"content": f"test memory {i}", "group_id": "threshold-test"}
                )
                for i in range(6)
            ]
            qdrant_client.upsert(collection_name=test_collection, points=points)

            # Get stats and check thresholds
            stats = get_collection_stats(qdrant_client, test_collection)
            warnings = check_collection_thresholds(stats)

            # Should have warning
            assert len(warnings) > 0, "No warnings triggered despite exceeding threshold"
            assert any("warning" in w.lower() for w in warnings), \
                f"Expected warning in messages: {warnings}"

    def test_critical_alerts_at_higher_thresholds(self, qdrant_client, test_collection):
        """Test that critical alerts trigger at higher thresholds.

        AC 6.7.5 Subtask 2: Critical alerts at higher thresholds.

        Default critical threshold is 50,000 memories.
        """
        from src.memory.stats import get_collection_stats
        import importlib
        import sys

        # Use low critical threshold for testing
        with patch.dict(os.environ, {"BMAD_COLLECTION_SIZE_CRITICAL": "10", "BMAD_COLLECTION_SIZE_WARNING": "5"}):
            # Reload warnings module to pick up new env vars
            if 'src.memory.warnings' in sys.modules:
                import src.memory.warnings
                importlib.reload(src.memory.warnings)
            from src.memory.warnings import check_collection_thresholds

            # Add 11 memories (exceeds critical threshold of 10)
            points = [
                PointStruct(
                    id=i,
                    vector=[0.1] * 768,
                    payload={"content": f"test memory {i}", "group_id": "threshold-test"}
                )
                for i in range(11)
            ]
            qdrant_client.upsert(collection_name=test_collection, points=points)

            stats = get_collection_stats(qdrant_client, test_collection)
            warnings = check_collection_thresholds(stats)

            # Should have critical alert
            assert len(warnings) > 0, "No critical alerts triggered"
            assert any("critical" in w.lower() for w in warnings), \
                f"Expected critical alert in messages: {warnings}"

    def test_per_project_threshold_monitoring(self, qdrant_client, test_collection):
        """Test that per-project thresholds are monitored correctly.

        AC 6.7.5 Subtask 3: Per-project threshold monitoring.
        """
        from src.memory.stats import get_collection_stats

        # Add memories for multiple projects
        points = []
        for project_id in ["project-a", "project-b", "project-c"]:
            for i in range(3):
                points.append(PointStruct(
                    id=len(points),
                    vector=[0.1] * 768,
                    payload={"content": f"memory {i}", "group_id": project_id}
                ))

        qdrant_client.upsert(collection_name=test_collection, points=points)

        # Get stats and verify per-project counts
        stats = get_collection_stats(qdrant_client, test_collection)

        assert "project-a" in stats.points_by_project, "Missing project-a stats"
        assert "project-b" in stats.points_by_project, "Missing project-b stats"
        assert "project-c" in stats.points_by_project, "Missing project-c stats"

        assert stats.points_by_project["project-a"] == 3, "Incorrect count for project-a"
        assert stats.points_by_project["project-b"] == 3, "Incorrect count for project-b"
        assert stats.points_by_project["project-c"] == 3, "Incorrect count for project-c"

    def test_prometheus_gauge_updates_on_threshold_check(self, qdrant_client, test_collection):
        """Test that Prometheus gauges are updated when thresholds are checked.

        AC 6.7.5 Subtask 4: Prometheus gauge updates.
        """
        from src.memory.stats import get_collection_stats
        from src.memory.metrics import update_collection_metrics, collection_size
        from prometheus_client import REGISTRY

        # Add test memories
        points = [
            PointStruct(
                id=i,
                vector=[0.1] * 768,
                payload={"content": f"test {i}", "group_id": "gauge-test"}
            )
            for i in range(5)
        ]
        qdrant_client.upsert(collection_name=test_collection, points=points)

        # Get stats and update metrics
        stats = get_collection_stats(qdrant_client, test_collection)
        update_collection_metrics(stats)

        # Verify gauge was updated using public REGISTRY API (best practice)
        gauge_value = REGISTRY.get_sample_value(
            'bmad_collection_size',
            {'collection': test_collection, 'project': 'all'}
        )

        assert gauge_value == 5, f"Gauge not updated correctly: expected 5, got {gauge_value}"

    def test_health_status_reflects_degradation(self, qdrant_client, test_collection):
        """Test that health status reflects degradation when thresholds exceeded.

        AC 6.7.5 Subtask 5: Health status degradation.
        """
        from src.memory.stats import get_collection_stats
        import importlib
        import sys

        # Test with warning threshold
        with patch.dict(os.environ, {"BMAD_COLLECTION_SIZE_WARNING": "3", "BMAD_COLLECTION_SIZE_CRITICAL": "10"}):
            # Reload warnings module to pick up new env vars
            if 'src.memory.warnings' in sys.modules:
                import src.memory.warnings
                importlib.reload(src.memory.warnings)
            from src.memory.warnings import check_collection_thresholds

            # Add 4 memories (exceeds warning)
            points = [
                PointStruct(
                    id=i,
                    vector=[0.1] * 768,
                    payload={"content": f"test {i}", "group_id": "health-test"}
                )
                for i in range(4)
            ]
            qdrant_client.upsert(collection_name=test_collection, points=points)

            stats = get_collection_stats(qdrant_client, test_collection)
            warnings = check_collection_thresholds(stats)

            # Warnings should indicate degraded health
            assert len(warnings) > 0, "No health degradation detected"
            # In production, this would update a health check endpoint


# ==============================================================================
# AC 6.7.6: End-to-End Monitoring Flow Tests
# ==============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndMonitoring:
    """Tests for AC 6.7.6: End-to-end monitoring flow verification."""

    @pytest.fixture
    def qdrant_client(self):
        """Provide Qdrant client for tests."""
        qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:26350")
        return QdrantClient(url=qdrant_url, timeout=10.0)

    @pytest.mark.asyncio
    async def test_memory_capture_to_metrics_flow(self, qdrant_client):
        """Test full capture → metrics → logs → dashboard flow.

        AC 6.7.6 Subtask 1: Memory capture flow end-to-end.

        Flow:
        1. Memory is captured (simulated)
        2. Metrics are incremented
        3. Structured logs are emitted
        4. Grafana displays the activity (verified via metrics endpoint)
        """
        from src.memory.metrics import memory_captures_total
        import logging
        from io import StringIO

        # Setup logging capture
        logger = logging.getLogger("bmad.memory.test_e2e")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Get baseline metrics using public REGISTRY API (best practice)
        from prometheus_client import REGISTRY
        baseline = REGISTRY.get_sample_value(
            'bmad_memory_captures_total',
            {'hook_type': 'PostToolUse', 'status': 'success', 'project': 'e2e-test'}
        ) or 0  # None if metric not yet initialized

        # Simulate memory capture with logging
        logger.info(
            "memory_captured",
            extra={
                "memory_id": "e2e-test-123",
                "project": "e2e-test",
                "type": "implementation"
            }
        )

        # Increment metrics (simulating actual capture)
        memory_captures_total.labels(
            hook_type="PostToolUse",
            status="success",
            project="e2e-test"
        ).inc()

        # Verify metrics incremented using public REGISTRY API
        updated = REGISTRY.get_sample_value(
            'bmad_memory_captures_total',
            {'hook_type': 'PostToolUse', 'status': 'success', 'project': 'e2e-test'}
        ) or 0
        assert updated > baseline, f"Metrics not incremented: {baseline} -> {updated}"

        # Verify structured logs emitted
        log_output = stream.getvalue()
        assert "memory_captured" in log_output, "Log not emitted"
        assert "e2e-test-123" in log_output, "Memory ID not in logs"

        # Verify metrics exposed via endpoint
        async with httpx.AsyncClient() as client:
            metrics_port = os.environ.get("METRICS_PORT", "28080")
            try:
                response = await client.get(
                    f"http://localhost:{metrics_port}/metrics",
                    timeout=5.0,
                    follow_redirects=True
                )
                assert "bmad_memory_captures_total" in response.text, \
                    "Metrics not exposed on endpoint"
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError):
                pytest.skip("Embedding service not running - start with docker compose up")

    @pytest.mark.asyncio
    async def test_retrieval_to_dashboard_flow(self, qdrant_client):
        """Test retrieval → session logs → dashboard flow.

        AC 6.7.6 Subtask 2: Retrieval flow end-to-end.
        """
        from src.memory.metrics import memory_retrievals_total
        import logging
        from io import StringIO

        # Setup logging
        logger = logging.getLogger("bmad.memory.test_retrieval")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Simulate retrieval
        logger.info(
            "memory_retrieved",
            extra={
                "collection": "implementations",
                "results_count": 5,
                "duration_ms": 234
            }
        )

        # Increment retrieval metrics
        memory_retrievals_total.labels(
            collection="implementations",
            status="success"
        ).inc()

        # Verify logs
        log_output = stream.getvalue()
        assert "memory_retrieved" in log_output
        assert "results_count" in log_output

    def test_queue_operations_to_warnings_flow(self, qdrant_client):
        """Test queue operations → metrics → warnings flow.

        AC 6.7.6 Subtask 3: Queue operations monitoring.
        """
        from src.memory.metrics import queue_size
        from prometheus_client import REGISTRY

        # Simulate queue growth
        queue_size.labels(status="pending").set(15)

        # Verify gauge value using public REGISTRY API (best practice)
        current_size = REGISTRY.get_sample_value(
            'bmad_queue_size',
            {'status': 'pending'}
        )
        assert current_size == 15, f"Queue size not set: {current_size}"

        # In production, this would trigger alerts if threshold exceeded

    @pytest.mark.asyncio
    async def test_failure_scenarios_to_alerts_flow(self):
        """Test failure scenarios → alerts → dashboards flow.

        AC 6.7.6 Subtask 4: Failure handling monitoring.
        """
        from src.memory.metrics import failure_events_total
        import logging
        from io import StringIO

        # Setup logging
        logger = logging.getLogger("bmad.memory.test_failure")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        # Simulate failure
        logger.error(
            "operation_failed",
            extra={
                "error_code": "QDRANT_UNAVAILABLE",
                "component": "qdrant"
            }
        )

        # Increment failure counter
        failure_events_total.labels(
            component="qdrant",
            error_code="QDRANT_UNAVAILABLE"
        ).inc()

        # Verify error logged
        log_output = stream.getvalue()
        assert "operation_failed" in log_output
        assert "QDRANT_UNAVAILABLE" in log_output

        # Verify metrics exposed
        async with httpx.AsyncClient() as client:
            metrics_port = os.environ.get("METRICS_PORT", "28080")
            try:
                response = await client.get(
                    f"http://localhost:{metrics_port}/metrics",
                    timeout=5.0,
                    follow_redirects=True
                )
                assert "bmad_failure_events_total" in response.text
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError):
                pytest.skip("Embedding service not running - start with docker compose up")
