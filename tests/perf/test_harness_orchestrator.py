"""Edge-case tests for scripts/perf/embedding_capacity_harness.py's CLI modes.

Fully mocked at the `subprocess.run` / `load.run_*` boundaries (never a live
container or service) — covers the three orchestrator gaps that let B2/M1/M3
slip through the round-1 review: the reset-unsupported fallback path, an
empty-clean-rounds ramp, and an all-failed soak.
"""

import json

import embedding_capacity_harness as harness
from embedding_capacity import load


class _FakeResult:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_subprocess_run(responses, default=(0, "0\n", "")):
    """`responses` maps a command key to either a static (rc, stdout, stderr)
    tuple, or a list of such tuples consumed in call order (for a command
    invoked more than once with a different answer each time, e.g. a
    baseline vs. a later read of the same file)."""
    counters: dict[str, int] = {}

    def run(cmd, **kwargs):
        key = " ".join(cmd[3:]) if cmd[0] == "docker" else " ".join(cmd)
        entry = responses.get(key, default)
        if isinstance(entry, list):
            idx = counters.get(key, 0)
            counters[key] = idx + 1
            rc, out, err = entry[min(idx, len(entry) - 1)]
        else:
            rc, out, err = entry
        return _FakeResult(rc, out, err)

    return run


async def _fake_run_burst(base_url, requests, model="en", timeout=60.0, client=None):
    return [load.RequestResult(status_code=200, elapsed_seconds=0.01) for _ in requests]


def test_cmd_measure_falls_back_to_dense_poll_when_reset_unsupported(
    tmp_path, monkeypatch
):
    # B2: kernel 6.6 / read-only cgroup -> memory.peak reset fails; the burst
    # peak must still be measured via the memory.current dense-poll fallback,
    # not a crash or a guessed value.
    responses = {
        "cat /sys/fs/cgroup/memory.current": (0, "3221225472\n", ""),
        "sh -c echo 0 > /sys/fs/cgroup/memory.peak": (1, "", "Read-only file system"),
    }
    monkeypatch.setattr(
        harness.cgroup.subprocess, "run", _fake_subprocess_run(responses)
    )
    monkeypatch.setattr(harness.load, "run_burst", _fake_run_burst)
    (tmp_path / "notes.md").write_text("real corpus content " * 50)

    args = harness.build_parser().parse_args(
        [
            "measure",
            "--concurrency",
            "2",
            "--batch-size",
            "5",
            "--corpus-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path),
        ]
    )
    rc = harness.cmd_measure(args)

    assert rc == 0
    out_files = list(tmp_path.glob("measure-*.json"))
    assert len(out_files) == 1
    data = json.loads(out_files[0].read_text())
    assert data["peak_measurement_fallback_used"] is True
    assert data["memory_peak_bytes"] == 3221225472


def test_cmd_ramp_reports_null_ceiling_when_every_round_fails(tmp_path, monkeypatch):
    # M1: the very first round OOMs -> there is no safe concurrency at all.
    # The old code reported start_concurrency as the "ceiling" even though
    # that level itself triggered the failure; it must now report null.
    responses = {
        "cat /sys/fs/cgroup/memory.current": (0, "1000000000\n", ""),
        "sh -c echo 0 > /sys/fs/cgroup/memory.peak": (0, "", ""),
        "cat /sys/fs/cgroup/memory.peak": (0, "1000000000\n", ""),
        "cat /sys/fs/cgroup/memory.events": [
            (0, "oom_kill 0\n", ""),  # baseline
            (0, "oom_kill 1\n", ""),  # after round 1 -> delta 1
        ],
    }
    monkeypatch.setattr(
        harness.cgroup.subprocess, "run", _fake_subprocess_run(responses)
    )
    monkeypatch.setattr(harness.load, "run_burst", _fake_run_burst)
    monkeypatch.setattr(
        harness.metrics_client, "fetch_metrics_text", lambda *a, **k: ""
    )
    (tmp_path / "notes.md").write_text("real corpus content " * 50)

    args = harness.build_parser().parse_args(
        [
            "ramp",
            "--start-concurrency",
            "1",
            "--max-concurrency",
            "1",
            "--corpus-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path),
        ]
    )
    rc = harness.cmd_ramp(args)

    assert rc == 1
    out_files = list(tmp_path.glob("ramp-*.json"))
    data = json.loads(out_files[0].read_text())
    assert data["ceiling_concurrency"] is None
    assert "no safe concurrency found" in data["ceiling_message"]


async def _fake_run_soak_callers_all_fail(
    base_url, n_callers, duration_seconds, payload_fn, model="en", **kwargs
):
    return [
        load.CallerStats(
            caller_id=i,
            requests_sent=5,
            results=[load.RequestResult(503, 0.01) for _ in range(5)],
        )
        for i in range(n_callers)
    ]


def test_cmd_soak_all_failed_requests_is_invalid_not_pass(tmp_path, monkeypatch):
    # M3: every request 503s (e.g. wrong port) -> oom==0, shed==0, no climb —
    # every criterion trivially "passes", but the load never landed. The gate
    # must report INVALID, not PASS.
    responses = {
        "cat /sys/fs/cgroup/memory.current": (0, "1000000000\n", ""),
        "sh -c echo 0 > /sys/fs/cgroup/memory.peak": (0, "", ""),
        "cat /sys/fs/cgroup/memory.peak": (0, "1000000000\n", ""),
        "cat /sys/fs/cgroup/memory.events": (0, "oom_kill 0\n", ""),
        "dmesg": (0, "", ""),
    }
    monkeypatch.setattr(
        harness.cgroup.subprocess, "run", _fake_subprocess_run(responses)
    )
    monkeypatch.setattr(
        harness.load, "run_soak_callers", _fake_run_soak_callers_all_fail
    )
    monkeypatch.setattr(
        harness.metrics_client, "fetch_metrics_text", lambda *a, **k: ""
    )

    args = harness.build_parser().parse_args(
        [
            "soak",
            "--duration-seconds",
            "1",
            "--callers",
            "2",
            "--mem-limit-bytes",
            "6442450944",
            "--corpus-dir",
            str(tmp_path),
            "--output-dir",
            str(tmp_path),
        ]
    )
    rc = harness.cmd_soak(args)

    assert rc == 2
    out_files = list(tmp_path.glob("soak-*.json"))
    data = json.loads(out_files[0].read_text())
    assert data["gate_outcome"] == "INVALID"
    assert data["gate_passed"] is False
    assert data["total_requests"] == 10
    assert data["total_failures"] == 10
