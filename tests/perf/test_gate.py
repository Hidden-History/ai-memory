"""Unit tests for scripts/perf/embedding_capacity/gate.py — BP-179 §4 pass/fail gate.

Each of the 6 criteria is tested independently for its failure case, plus the
overall pass case, matching the "assert ALL" requirement (a single failing
criterion must fail the whole gate).
"""

from embedding_capacity import gate

BASE_KWARGS = {
    "oom_kill_delta": 0,
    "dmesg_oom_count": 0,
    "restart_count_delta": 0,
    "shed_delta": 0.0,
    "admission_wait_p95_seconds": 0.5,
    "client_read_timeout_seconds": 30.0,
    "working_set_start_bytes": 2_000_000_000,
    "working_set_end_bytes": 2_050_000_000,
    "leak_tolerance_ratio": 0.10,
    "memory_peak_bytes": 5_500_000_000,
    "mem_limit_bytes": 6_000_000_000,
    "total_requests": 100,
    "total_failures": 0,
    "base_rss_bytes": 2_000_000_000,
}


def test_all_criteria_pass_gate_passes():
    result = gate.evaluate_gate(**BASE_KWARGS)
    assert result.passed
    assert result.outcome == "PASS"
    assert len(result.criteria) == 7
    assert all(c.passed for c in result.criteria)


def test_oom_kill_delta_nonzero_fails_gate():
    kwargs = {**BASE_KWARGS, "oom_kill_delta": 1}
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    assert not next(
        c for c in result.criteria if c.name == "oom_kill_delta_zero"
    ).passed


def test_dmesg_oom_count_nonzero_fails_gate():
    kwargs = {**BASE_KWARGS, "dmesg_oom_count": 3}
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    assert not next(c for c in result.criteria if c.name == "dmesg_oom_zero").passed


def test_restart_count_delta_nonzero_fails_gate():
    # TD-792/789: the authoritative OOM witness on this host. A restart during
    # the soak means the container's main process was killed (kernel OOM) even
    # though memory.events:oom_kill stayed 0 — the gate must fail.
    kwargs = {**BASE_KWARGS, "restart_count_delta": 1}
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    assert not next(
        c for c in result.criteria if c.name == "container_restart_zero"
    ).passed


def test_restart_witnesses_oom_when_cgroup_and_app_counters_blind():
    # The exact TD-792 scenario: oom_kill delta 0, dmesg would be the only
    # other witness — here dmesg also 0 but the restart count caught the kill.
    # A gate relying only on oom_kill/dmesg would false-PASS; restart-count
    # must independently fail it.
    kwargs = {
        **BASE_KWARGS,
        "oom_kill_delta": 0,
        "dmesg_oom_count": 0,
        "restart_count_delta": 1,
    }
    result = gate.evaluate_gate(**kwargs)
    assert result.outcome == "FAIL"
    assert not next(
        c for c in result.criteria if c.name == "container_restart_zero"
    ).passed


def test_shed_delta_nonzero_fails_gate():
    kwargs = {**BASE_KWARGS, "shed_delta": 2.0}
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    assert not next(
        c for c in result.criteria if c.name == "backpressure_shed_zero"
    ).passed


def test_admission_wait_p95_over_timeout_fails_gate():
    kwargs = {**BASE_KWARGS, "admission_wait_p95_seconds": 45.0}
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    assert not next(
        c for c in result.criteria if c.name == "admission_wait_p95_within_timeout"
    ).passed


def test_admission_wait_p95_none_fails_gate_not_silently_passes():
    kwargs = {**BASE_KWARGS, "admission_wait_p95_seconds": None}
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    criterion = next(
        c for c in result.criteria if c.name == "admission_wait_p95_within_timeout"
    )
    assert not criterion.passed
    assert "unavailable" in criterion.detail


def test_working_set_climb_beyond_tolerance_fails_gate():
    kwargs = {
        **BASE_KWARGS,
        "working_set_start_bytes": 2_000_000_000,
        "working_set_end_bytes": 3_000_000_000,  # 50% climb, tolerance is 10%
    }
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    assert not next(
        c for c in result.criteria if c.name == "no_working_set_climb"
    ).passed


def test_working_set_within_tolerance_passes():
    kwargs = {
        **BASE_KWARGS,
        "working_set_start_bytes": 2_000_000_000,
        "working_set_end_bytes": 2_100_000_000,  # 5% climb, within 10% tolerance
    }
    result = gate.evaluate_gate(**kwargs)
    assert next(c for c in result.criteria if c.name == "no_working_set_climb").passed


def test_peak_at_or_over_mem_limit_fails_gate():
    kwargs = {
        **BASE_KWARGS,
        "memory_peak_bytes": 6_000_000_000,
        "mem_limit_bytes": 6_000_000_000,
    }
    result = gate.evaluate_gate(**kwargs)
    assert not result.passed
    assert not next(
        c for c in result.criteria if c.name == "peak_under_mem_limit"
    ).passed


def test_single_failing_criterion_fails_the_whole_gate():
    # 6 of 7 pass; the gate must still fail (assert ALL, not majority).
    kwargs = {**BASE_KWARGS, "oom_kill_delta": 1}
    result = gate.evaluate_gate(**kwargs)
    passing = [c for c in result.criteria if c.passed]
    assert len(passing) == 6
    assert not result.passed
    assert result.outcome == "FAIL"


def test_load_never_landed_is_invalid_not_pass():
    # All requests failed (e.g. wrong port) — every criterion trivially holds
    # (0 oom, 0 shed, no working-set climb) but the run proved nothing.
    kwargs = {
        **BASE_KWARGS,
        "total_requests": 100,
        "total_failures": 100,
        "memory_peak_bytes": 2_000_000_100,  # never rose above base_rss
    }
    result = gate.evaluate_gate(**kwargs)
    assert result.outcome == "INVALID"
    assert not result.passed
    assert "load may not have landed" in result.load_validity_detail


def test_peak_never_rose_above_base_is_invalid():
    kwargs = {
        **BASE_KWARGS,
        "memory_peak_bytes": 2_000_000_000,  # == base_rss, no burst landed
    }
    result = gate.evaluate_gate(**kwargs)
    assert result.outcome == "INVALID"
    assert "burst may not have landed" in result.load_validity_detail


def test_zero_requests_is_invalid():
    kwargs = {**BASE_KWARGS, "total_requests": 0, "total_failures": 0}
    result = gate.evaluate_gate(**kwargs)
    assert result.outcome == "INVALID"
    assert "no requests were sent" in result.load_validity_detail


def test_evaluate_load_validity_passes_with_healthy_run():
    validity = gate.evaluate_load_validity(
        total_requests=100,
        total_failures=2,
        memory_peak_bytes=5_500_000_000,
        base_rss_bytes=2_000_000_000,
    )
    assert validity.valid
