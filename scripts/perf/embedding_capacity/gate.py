"""Soak pass/fail gate — BP-179 §4, assert ALL criteria.

The OOM witnesses are cgroup `memory.events:oom_kill` + dmesg + the container
restart-count (TD-792/789) — never the Docker `OOMKilled` flag or the app's own
`oom_events_total` gauge. On the target host a real kill left oom_kill=0,
OOMKilled=false, and the app counter=0; only dmesg and the container restart
witnessed it, so both are asserted so a false-PASS cannot slip through.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CriterionResult:
    name: str
    passed: bool
    detail: str


@dataclass
class LoadValidity:
    valid: bool
    detail: str


def evaluate_load_validity(
    *,
    total_requests: int,
    total_failures: int,
    memory_peak_bytes: int,
    base_rss_bytes: int,
    min_success_ratio: float = 0.5,
    min_peak_above_base_ratio: float = 0.02,
) -> LoadValidity:
    """Guard against certifying a run whose load never actually landed.

    BP-179 §4's trap: an all-503 / wrong-port / not-ready run goes flat and
    would otherwise pass every gate criterion (oom==0, shed==0, etc. all
    trivially hold when nothing happened). Requires both a success-ratio floor
    and memory.peak meaningfully above base_rss.
    """
    if total_requests == 0:
        return LoadValidity(False, "no requests were sent")

    success_ratio = 1 - (total_failures / total_requests)
    if success_ratio < min_success_ratio:
        return LoadValidity(
            False,
            f"success_ratio={success_ratio:.2%} below min={min_success_ratio:.2%} "
            f"({total_failures}/{total_requests} requests failed) — load may not "
            "have landed",
        )

    peak_above_base = memory_peak_bytes - base_rss_bytes
    min_peak_above_base = base_rss_bytes * min_peak_above_base_ratio
    if peak_above_base < min_peak_above_base:
        return LoadValidity(
            False,
            f"memory.peak rose {peak_above_base}B above base_rss "
            f"(min required {min_peak_above_base:.0f}B) — burst may not have "
            "landed",
        )

    return LoadValidity(True, "load validity checks passed")


@dataclass
class GateResult:
    criteria: list[CriterionResult] = field(default_factory=list)
    load_valid: bool = True
    load_validity_detail: str = ""

    @property
    def passed(self) -> bool:
        return (
            self.load_valid
            and bool(self.criteria)
            and all(c.passed for c in self.criteria)
        )

    @property
    def outcome(self) -> str:
        """PASS | FAIL | INVALID — INVALID means the load never landed, so the
        other 6 criteria's trivial passes don't certify anything (BP-179 §4)."""
        if not self.load_valid:
            return "INVALID"
        return "PASS" if self.passed else "FAIL"

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.criteria.append(CriterionResult(name, passed, detail))


def evaluate_gate(
    *,
    oom_kill_delta: int,
    dmesg_oom_count: int,
    restart_count_delta: int,
    shed_delta: float,
    admission_wait_p95_seconds: float | None,
    client_read_timeout_seconds: float,
    working_set_start_bytes: int,
    working_set_end_bytes: int,
    leak_tolerance_ratio: float,
    memory_peak_bytes: int,
    mem_limit_bytes: int,
    total_requests: int,
    total_failures: int,
    base_rss_bytes: int,
    min_success_ratio: float = 0.5,
    min_peak_above_base_ratio: float = 0.02,
) -> GateResult:
    """Evaluate all 7 BP-179 §4 pass/fail criteria plus the load-validity guard.

    The 7 are the 6 BP-179 §4 criteria plus the container restart-count OOM
    witness (TD-792/789). The gate only PASSes if the load-validity guard holds
    AND all 7 criteria pass; if the guard fails, the outcome is the distinct
    INVALID (not PASS or FAIL) — the run didn't prove anything either way.
    """
    validity = evaluate_load_validity(
        total_requests=total_requests,
        total_failures=total_failures,
        memory_peak_bytes=memory_peak_bytes,
        base_rss_bytes=base_rss_bytes,
        min_success_ratio=min_success_ratio,
        min_peak_above_base_ratio=min_peak_above_base_ratio,
    )
    gate = GateResult(load_valid=validity.valid, load_validity_detail=validity.detail)

    gate.add(
        "oom_kill_delta_zero",
        oom_kill_delta == 0,
        f"memory.events:oom_kill delta={oom_kill_delta} (must be 0)",
    )
    gate.add(
        "dmesg_oom_zero",
        dmesg_oom_count == 0,
        f"dmesg OOM-kill lines={dmesg_oom_count} (must be 0)",
    )
    gate.add(
        "container_restart_zero",
        restart_count_delta == 0,
        f"container restart-count delta={restart_count_delta} (must be 0)",
    )
    gate.add(
        "backpressure_shed_zero",
        shed_delta == 0,
        f"embedding_backpressure_total{{action='shed'}} delta={shed_delta} (must be 0)",
    )

    if admission_wait_p95_seconds is None:
        gate.add(
            "admission_wait_p95_within_timeout",
            False,
            "admission_wait p95 unavailable (no samples) — cannot certify",
        )
    else:
        gate.add(
            "admission_wait_p95_within_timeout",
            admission_wait_p95_seconds <= client_read_timeout_seconds,
            f"p95={admission_wait_p95_seconds:.3f}s vs "
            f"read_timeout={client_read_timeout_seconds:.3f}s",
        )

    leak_threshold = working_set_start_bytes * (1 + leak_tolerance_ratio)
    gate.add(
        "no_working_set_climb",
        working_set_end_bytes <= leak_threshold,
        f"end={working_set_end_bytes}B vs start={working_set_start_bytes}B "
        f"(threshold={leak_threshold:.0f}B, tolerance={leak_tolerance_ratio:.0%})",
    )

    gate.add(
        "peak_under_mem_limit",
        memory_peak_bytes < mem_limit_bytes,
        f"memory.peak={memory_peak_bytes}B vs mem_limit={mem_limit_bytes}B",
    )

    return gate
