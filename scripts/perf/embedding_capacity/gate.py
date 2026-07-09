"""Soak pass/fail gate — BP-179 §4, assert ALL six criteria.

The OOM signal is cgroup `memory.events:oom_kill` + dmesg ONLY (BP-179 §3/§5) —
never the Docker `OOMKilled` flag or the app's own `oom_events_total` gauge,
both of which are blind to a killed worker/child process.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CriterionResult:
    name: str
    passed: bool
    detail: str


@dataclass
class GateResult:
    criteria: list[CriterionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.criteria) and all(c.passed for c in self.criteria)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.criteria.append(CriterionResult(name, passed, detail))


def evaluate_gate(
    *,
    oom_kill_delta: int,
    dmesg_oom_count: int,
    shed_delta: float,
    admission_wait_p95_seconds: float | None,
    client_read_timeout_seconds: float,
    working_set_start_bytes: int,
    working_set_end_bytes: int,
    leak_tolerance_ratio: float,
    memory_peak_bytes: int,
    mem_limit_bytes: int,
) -> GateResult:
    """Evaluate all 6 BP-179 §4 pass/fail criteria; the gate passes only if all pass."""
    gate = GateResult()

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
