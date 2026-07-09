"""Joint memory-envelope sizing math (BP-179 §0/§1).

    peak_mem ~= base_rss + (max_concurrency x per_request_burst_peak)

The safe envelope is any (mem_limit, max_concurrency) pair satisfying:

    base_rss + max_concurrency x per_request_burst_peak + safety_margin <= mem_limit
"""

from __future__ import annotations

from dataclasses import dataclass


def per_request_burst_peak(
    peak_bytes: int, base_bytes: int, n_concurrent: int
) -> float:
    """(peak - base) / N — BP-179 §2. `n_concurrent` must be >= 1."""
    if n_concurrent < 1:
        raise ValueError("n_concurrent must be >= 1")
    return (peak_bytes - base_bytes) / n_concurrent


def projected_peak(
    base_rss: float, max_concurrency: int, per_request_peak: float
) -> float:
    """base + max_concurrency x per_req_peak — the joint envelope model (BP-179 §1)."""
    return base_rss + max_concurrency * per_request_peak


def required_mem_limit(
    base_rss: float,
    per_request_peak: float,
    max_concurrency: int,
    safety_margin_ratio: float = 0.15,
) -> int:
    """Smallest mem_limit satisfying the envelope for a target concurrency ceiling."""
    projected = projected_peak(base_rss, max_concurrency, per_request_peak)
    return round(projected * (1 + safety_margin_ratio))


@dataclass
class EnvelopeCandidate:
    max_concurrency: int
    mem_limit_bytes: int
    projected_peak_bytes: float
    safety_margin_ratio: float


def recommend_envelope(
    base_rss: float,
    per_request_peak: float,
    safety_margin_ratio: float = 0.15,
    candidate_concurrencies: range = range(1, 9),
) -> list[EnvelopeCandidate]:
    """A table of joint (mem_limit, max_concurrency) candidates, one per concurrency level.

    Callers pick the row matching their throughput/RAM tradeoff, per BP-179 §1's
    three levers in preference order: lower concurrency, lower per-request peak,
    then raise mem_limit.
    """
    return [
        EnvelopeCandidate(
            max_concurrency=concurrency,
            mem_limit_bytes=required_mem_limit(
                base_rss, per_request_peak, concurrency, safety_margin_ratio
            ),
            projected_peak_bytes=projected_peak(
                base_rss, concurrency, per_request_peak
            ),
            safety_margin_ratio=safety_margin_ratio,
        )
        for concurrency in candidate_concurrencies
    ]
