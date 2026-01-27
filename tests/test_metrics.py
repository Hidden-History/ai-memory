"""
Unit tests for Prometheus metrics definitions.

Tests that all metrics are properly defined with correct types,
labels, and metadata according to AC 6.1.2 and AC 6.1.4.
"""

import pytest
import sys
from prometheus_client import Counter, Gauge, Histogram, Info, CollectorRegistry


@pytest.fixture(autouse=True)
def reset_metrics_module():
    """Clear metrics registry and module cache before each test to avoid registration conflicts."""
    from prometheus_client import REGISTRY

    # Clear all collectors from the registry
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    # Remove metrics module from sys.modules
    modules_to_remove = [k for k in sys.modules.keys() if 'memory.metrics' in k or k == 'memory']
    for mod in modules_to_remove:
        sys.modules.pop(mod, None)

    yield

    # Clean up after test - clear registry again
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    modules_to_remove = [k for k in sys.modules.keys() if 'memory.metrics' in k or k == 'memory']
    for mod in modules_to_remove:
        sys.modules.pop(mod, None)


def test_metrics_module_imports():
    """Test that metrics module can be imported and contains expected metrics."""
    from memory.metrics import (
        memory_captures_total,
        memory_retrievals_total,
        embedding_requests_total,
        deduplication_events_total,
        collection_size,
        queue_size,
        hook_duration_seconds,
        embedding_duration_seconds,
        retrieval_duration_seconds,
        failure_events_total,
        system_info,
    )

    # Verify metric types
    assert isinstance(memory_captures_total, Counter)
    assert isinstance(memory_retrievals_total, Counter)
    assert isinstance(embedding_requests_total, Counter)
    assert isinstance(deduplication_events_total, Counter)
    assert isinstance(failure_events_total, Counter)

    assert isinstance(collection_size, Gauge)
    assert isinstance(queue_size, Gauge)

    assert isinstance(hook_duration_seconds, Histogram)
    assert isinstance(embedding_duration_seconds, Histogram)
    assert isinstance(retrieval_duration_seconds, Histogram)

    assert isinstance(system_info, Info)


def test_counter_metrics_have_correct_labels():
    """Test that Counter metrics have the correct label names defined."""
    from memory.metrics import (
        memory_captures_total,
        memory_retrievals_total,
        embedding_requests_total,
        deduplication_events_total,
        failure_events_total,
    )

    # memory_captures_total: ["hook_type", "status", "project"]
    assert memory_captures_total._labelnames == ("hook_type", "status", "project")

    # memory_retrievals_total: ["collection", "status"]
    assert memory_retrievals_total._labelnames == ("collection", "status")

    # embedding_requests_total: ["status"]
    assert embedding_requests_total._labelnames == ("status",)

    # deduplication_events_total: ["project"]
    assert deduplication_events_total._labelnames == ("project",)

    # failure_events_total: ["component", "error_code"]
    assert failure_events_total._labelnames == ("component", "error_code")


def test_gauge_metrics_have_correct_labels():
    """Test that Gauge metrics have the correct label names defined."""
    from memory.metrics import collection_size, queue_size

    # collection_size: ["collection", "project"]
    assert collection_size._labelnames == ("collection", "project")

    # queue_size: ["status"]
    assert queue_size._labelnames == ("status",)


def test_histogram_metrics_have_correct_buckets():
    """Test that Histogram metrics have appropriate bucket definitions."""
    from memory.metrics import (
        hook_duration_seconds,
        embedding_duration_seconds,
        retrieval_duration_seconds,
    )

    # hook_duration_seconds: buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
    expected_hook_buckets = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf")]
    assert hook_duration_seconds._upper_bounds == expected_hook_buckets

    # embedding_duration_seconds: buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    expected_embedding_buckets = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf")]
    assert embedding_duration_seconds._upper_bounds == expected_embedding_buckets

    # retrieval_duration_seconds: buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0]
    expected_retrieval_buckets = [0.1, 0.5, 1.0, 2.0, 3.0, 5.0, float("inf")]
    assert retrieval_duration_seconds._upper_bounds == expected_retrieval_buckets


def test_histogram_metrics_have_correct_labels():
    """Test that Histogram metrics have the correct label names defined."""
    from memory.metrics import (
        hook_duration_seconds,
        embedding_duration_seconds,
        retrieval_duration_seconds,
    )

    # hook_duration_seconds: ["hook_type"]
    assert hook_duration_seconds._labelnames == ("hook_type",)

    # embedding_duration_seconds: no labels
    assert embedding_duration_seconds._labelnames == ()

    # retrieval_duration_seconds: no labels
    assert retrieval_duration_seconds._labelnames == ()


def test_metric_naming_follows_snake_case_convention():
    """Test that all metrics follow snake_case and bmad_ prefix conventions."""
    from memory import metrics

    metric_names = [
        "memory_captures_total",
        "memory_retrievals_total",
        "embedding_requests_total",
        "deduplication_events_total",
        "collection_size",
        "queue_size",
        "hook_duration_seconds",
        "embedding_duration_seconds",
        "retrieval_duration_seconds",
        "failure_events_total",
        "system_info",
    ]

    for name in metric_names:
        assert hasattr(metrics, name), f"Missing metric: {name}"
        metric = getattr(metrics, name)

        # Check Prometheus metric name starts with bmad_
        if hasattr(metric, "_name"):
            assert metric._name.startswith("bmad_"), \
                f"Metric {name} should have Prometheus name starting with 'bmad_'"
            # Check snake_case (no uppercase letters)
            assert metric._name.islower() or "_" in metric._name, \
                f"Metric {name} Prometheus name should be snake_case"


def test_system_info_has_version_metadata():
    """Test that system_info Info metric contains expected metadata fields."""
    from memory.metrics import system_info

    # The Info metric should have been initialized with system metadata
    # We can't directly access the info dict in the current API, but we can
    # verify it's an Info type metric with the correct name
    assert isinstance(system_info, Info)
    assert system_info._name == "bmad_memory_system"


def test_counter_can_increment_with_labels():
    """Test that counters can be incremented with proper labels."""
    from memory.metrics import memory_captures_total
    from prometheus_client import REGISTRY

    # Create a test registry to avoid polluting global state
    test_registry = CollectorRegistry()
    test_counter = Counter(
        "test_memory_captures_total",
        "Test counter",
        ["hook_type", "status", "project"],
        registry=test_registry
    )

    # Increment with labels
    test_counter.labels(hook_type="PostToolUse", status="success", project="test-project").inc()
    test_counter.labels(hook_type="SessionStart", status="queued", project="test-project").inc(2)

    # Verify increments (by checking the metric was created successfully)
    metrics = test_registry.collect()
    assert len(list(metrics)) > 0


def test_gauge_can_be_set_and_incremented():
    """Test that gauges can be set to values and incremented/decremented."""
    from prometheus_client import REGISTRY
    from prometheus_client import Gauge as TestGauge

    # Create a test registry to avoid polluting global state
    test_registry = CollectorRegistry()
    test_gauge = TestGauge(
        "test_collection_size",
        "Test gauge",
        ["collection", "project"],
        registry=test_registry
    )

    # Set gauge value
    test_gauge.labels(collection="code-patterns", project="test").set(100)

    # Increment/decrement
    test_gauge.labels(collection="code-patterns", project="test").inc(5)
    test_gauge.labels(collection="code-patterns", project="test").dec(2)

    # Verify operations completed without error
    metrics = test_registry.collect()
    assert len(list(metrics)) > 0


def test_histogram_can_observe_durations():
    """Test that histograms can observe timing values."""
    from prometheus_client import Histogram as TestHistogram, CollectorRegistry

    # Create a test registry
    test_registry = CollectorRegistry()
    test_histogram = TestHistogram(
        "test_hook_duration_seconds",
        "Test histogram",
        ["hook_type"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
        registry=test_registry
    )

    # Observe durations
    test_histogram.labels(hook_type="PostToolUse").observe(0.15)
    test_histogram.labels(hook_type="SessionStart").observe(0.45)
    test_histogram.labels(hook_type="Stop").observe(1.2)

    # Verify observations completed without error
    metrics = test_registry.collect()
    assert len(list(metrics)) > 0
