"""Prometheus /metrics scraping + parsing for the embedding capacity harness.

Parses the raw exposition text the embedding service's own `/metrics` endpoint
returns (BP-179 §6): `embedding_backpressure_total{action}`,
`embedding_effective_concurrency_limit`, and the `embedding_admission_wait_seconds`
histogram. Matches on each sample's own name rather than its family name — the
service's Counter/Histogram collectors are registered under a base name (e.g.
"embedding_backpressure") while their exposed samples carry the OpenMetrics
suffix ("embedding_backpressure_total"), which the parser surfaces as separate,
mismatched families. Working from sample names is robust to that and requires
no live service to test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import httpx
from prometheus_client.parser import text_string_to_metric_families


@dataclass
class MetricsSnapshot:
    backpressure: dict[str, float]  # action -> counter value
    effective_concurrency_limit: float | None
    admission_wait_p95_seconds: float | None
    admission_wait_count: float
    admission_wait_sum: float


def fetch_metrics_text(base_url: str, timeout: float = 10.0) -> str:
    # The embedding service serves /metrics behind a 307 redirect; httpx does
    # not follow redirects by default, so without follow_redirects the scrape
    # returns the empty redirect body and every downstream metric goes missing
    # — silently rendering the soak's admission-wait gate criterion inert
    # (TD-793). A 307 is not a 4xx/5xx, so raise_for_status would not catch it.
    response = httpx.get(
        f"{base_url.rstrip('/')}/metrics", timeout=timeout, follow_redirects=True
    )
    response.raise_for_status()
    return response.text


def parse_metrics(text: str) -> MetricsSnapshot:
    backpressure: dict[str, float] = {}
    effective_limit: float | None = None
    hist_buckets: dict[float, float] = {}
    hist_count = 0.0
    hist_sum = 0.0

    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name == "embedding_backpressure_total":
                action = sample.labels.get("action", "unknown")
                backpressure[action] = sample.value
            elif sample.name == "embedding_effective_concurrency_limit":
                effective_limit = sample.value
            elif sample.name == "embedding_admission_wait_seconds_bucket":
                le = sample.labels.get("le")
                if le is not None:
                    hist_buckets[float(le)] = sample.value
            elif sample.name == "embedding_admission_wait_seconds_count":
                hist_count = sample.value
            elif sample.name == "embedding_admission_wait_seconds_sum":
                hist_sum = sample.value

    p95 = _histogram_quantile(hist_buckets, hist_count, 0.95) if hist_buckets else None

    return MetricsSnapshot(
        backpressure=backpressure,
        effective_concurrency_limit=effective_limit,
        admission_wait_p95_seconds=p95,
        admission_wait_count=hist_count,
        admission_wait_sum=hist_sum,
    )


def _histogram_quantile(
    buckets: dict[float, float], total_count: float, q: float
) -> float | None:
    """Linear-interpolation histogram quantile (the PromQL histogram_quantile algorithm).

    `buckets` maps upper bound `le` -> cumulative count. Returns None if there is
    no data or the target quantile falls beyond the highest finite bucket.
    """
    if total_count <= 0:
        return None
    target = q * total_count
    sorted_bounds = sorted(b for b in buckets if not math.isinf(b))
    prev_bound = 0.0
    prev_count = 0.0
    for bound in sorted_bounds:
        count = buckets[bound]
        if count >= target:
            if count == prev_count:
                return bound
            fraction = (target - prev_count) / (count - prev_count)
            return prev_bound + fraction * (bound - prev_bound)
        prev_bound, prev_count = bound, count
    return None
