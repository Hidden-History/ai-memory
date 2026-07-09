"""Unit tests for scripts/perf/embedding_capacity/metrics_client.py — /metrics parsing.

Works entirely off raw exposition text, matching what a live embedding
container's `/metrics` endpoint returns (BP-179 §6) — no live service needed.
"""

import pytest
from embedding_capacity import metrics_client

SAMPLE_METRICS = """
# HELP embedding_backpressure Backpressure actions
# TYPE embedding_backpressure counter
embedding_backpressure_total{action="waited"} 12.0
embedding_backpressure_total{action="shed"} 0.0
embedding_backpressure_total{action="over_envelope_reject"} 3.0
# HELP embedding_effective_concurrency_limit AIMD effective limit
# TYPE embedding_effective_concurrency_limit gauge
embedding_effective_concurrency_limit 4.0
# HELP embedding_admission_wait_seconds Admission wait
# TYPE embedding_admission_wait_seconds histogram
embedding_admission_wait_seconds_bucket{le="0.01"} 0.0
embedding_admission_wait_seconds_bucket{le="0.1"} 2.0
embedding_admission_wait_seconds_bucket{le="0.5"} 8.0
embedding_admission_wait_seconds_bucket{le="1"} 10.0
embedding_admission_wait_seconds_bucket{le="2"} 10.0
embedding_admission_wait_seconds_bucket{le="+Inf"} 10.0
embedding_admission_wait_seconds_sum 3.2
embedding_admission_wait_seconds_count 10.0
"""


def test_parse_metrics_backpressure_by_action():
    snapshot = metrics_client.parse_metrics(SAMPLE_METRICS)
    assert snapshot.backpressure == {
        "waited": 12.0,
        "shed": 0.0,
        "over_envelope_reject": 3.0,
    }


def test_parse_metrics_effective_concurrency_limit():
    snapshot = metrics_client.parse_metrics(SAMPLE_METRICS)
    assert snapshot.effective_concurrency_limit == 4.0


def test_parse_metrics_histogram_p95_interpolates():
    snapshot = metrics_client.parse_metrics(SAMPLE_METRICS)
    # target = 0.95 * 10 = 9.5, falls between le=0.5 (count 8) and le=1 (count 10)
    expected = 0.5 + (9.5 - 8) / (10 - 8) * (1 - 0.5)
    assert snapshot.admission_wait_p95_seconds == pytest.approx(expected)


def test_parse_metrics_histogram_count_and_sum():
    snapshot = metrics_client.parse_metrics(SAMPLE_METRICS)
    assert snapshot.admission_wait_count == 10.0
    assert snapshot.admission_wait_sum == 3.2


def test_parse_metrics_missing_metrics_return_defaults():
    snapshot = metrics_client.parse_metrics("# empty\n")
    assert snapshot.backpressure == {}
    assert snapshot.effective_concurrency_limit is None
    assert snapshot.admission_wait_p95_seconds is None


def test_histogram_quantile_at_exact_bucket_boundary():
    buckets = {0.1: 5.0, 0.5: 10.0, 1.0: 10.0}
    # q=0.5 * total(10) = 5, matches the first bucket exactly
    assert metrics_client._histogram_quantile(buckets, total_count=10.0, q=0.5) == 0.1


def test_histogram_quantile_beyond_finite_buckets_returns_none():
    # Highest finite bucket's cumulative count (5) never reaches the q=0.99
    # target (9.9 of 10) — the quantile falls in the (unbounded) +Inf bucket.
    buckets = {0.1: 2.0, 0.5: 5.0}
    assert metrics_client._histogram_quantile(buckets, total_count=10.0, q=0.99) is None


def test_histogram_quantile_zero_total_count_returns_none():
    assert (
        metrics_client._histogram_quantile({0.1: 0.0}, total_count=0.0, q=0.95) is None
    )
