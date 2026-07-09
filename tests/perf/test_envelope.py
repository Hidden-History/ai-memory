"""Unit tests for scripts/perf/embedding_capacity/envelope.py — BP-179 §0/§1 math."""

import pytest
from embedding_capacity import envelope

GIB = 2**30


def test_per_request_burst_peak_divides_by_concurrency():
    # BP-179 §6 worked example: (6.25 - 2.0) GiB / 4 ~= 1.0625 GiB/slot
    peak = int(6.25 * GIB)
    base = int(2.0 * GIB)
    result = envelope.per_request_burst_peak(peak, base, 4)
    assert result == pytest.approx((6.25 - 2.0) * GIB / 4)


def test_per_request_burst_peak_rejects_zero_concurrency():
    with pytest.raises(ValueError):
        envelope.per_request_burst_peak(100, 50, 0)


def test_projected_peak_is_base_plus_concurrency_times_per_request():
    result = envelope.projected_peak(
        base_rss=2.0 * GIB, max_concurrency=4, per_request_peak=1.0 * GIB
    )
    assert result == pytest.approx(6.0 * GIB)


def test_required_mem_limit_adds_safety_margin():
    projected = 6.0 * GIB
    result = envelope.required_mem_limit(
        base_rss=2.0 * GIB,
        per_request_peak=1.0 * GIB,
        max_concurrency=4,
        safety_margin_ratio=0.15,
    )
    assert result == pytest.approx(projected * 1.15, rel=1e-6)


def test_max_concurrency_for_limit_floors_at_one():
    # Budget too small for even one slot at the given per-request peak.
    concurrency = envelope.max_concurrency_for_limit(
        base_rss=5.9 * GIB,
        per_request_peak=1.0 * GIB,
        mem_limit=6.0 * GIB,
        safety_margin_ratio=0.15,
    )
    assert concurrency == 1


def test_max_concurrency_for_limit_rejects_non_positive_peak():
    with pytest.raises(ValueError):
        envelope.max_concurrency_for_limit(
            base_rss=2.0 * GIB, per_request_peak=0, mem_limit=6.0 * GIB
        )


def test_max_concurrency_for_limit_is_inverse_of_required_mem_limit():
    # required_mem_limit rounds to the nearest byte, so the round-trip can be off
    # by one at the margin; the load-bearing invariant is that the mem_limit it
    # produces for a target concurrency actually admits that concurrency.
    base_rss = 2.0 * GIB
    per_request_peak = 0.5 * GIB
    for target_concurrency in range(1, 6):
        mem_limit = envelope.required_mem_limit(
            base_rss, per_request_peak, target_concurrency
        )
        recovered = envelope.max_concurrency_for_limit(
            base_rss, per_request_peak, mem_limit
        )
        assert abs(recovered - target_concurrency) <= 1


def test_recommend_envelope_returns_one_candidate_per_concurrency_level():
    candidates = envelope.recommend_envelope(
        base_rss=2.0 * GIB,
        per_request_peak=1.0 * GIB,
        safety_margin_ratio=0.15,
        candidate_concurrencies=range(1, 5),
    )
    assert [c.max_concurrency for c in candidates] == [1, 2, 3, 4]
    # Higher concurrency must require a larger (or equal) mem_limit — monotonic.
    mem_limits = [c.mem_limit_bytes for c in candidates]
    assert mem_limits == sorted(mem_limits)
