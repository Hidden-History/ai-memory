"""Unit tests for scripts/perf/embedding_capacity/results.py — machine-readable output."""

import json

from embedding_capacity import gate, results


def test_write_results_json_creates_parent_dirs_and_valid_json(tmp_path):
    out_path = tmp_path / "nested" / "measure.json"
    results.write_results_json(out_path, {"mode": "measure", "base_rss_bytes": 123})

    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data == {"mode": "measure", "base_rss_bytes": 123}


def test_write_results_json_serializes_nested_dataclasses(tmp_path):
    gate_result = gate.evaluate_gate(
        oom_kill_delta=0,
        dmesg_oom_count=0,
        restart_count_delta=0,
        shed_delta=0.0,
        admission_wait_p95_seconds=0.5,
        client_read_timeout_seconds=30.0,
        working_set_start_bytes=1000,
        working_set_end_bytes=1010,
        leak_tolerance_ratio=0.10,
        memory_peak_bytes=5000,
        mem_limit_bytes=6000,
        total_requests=100,
        total_failures=0,
        base_rss_bytes=1000,
    )
    out_path = tmp_path / "soak.json"
    results.write_results_json(
        out_path, {"gate": gate_result, "gate_passed": gate_result.passed}
    )

    data = json.loads(out_path.read_text())
    assert data["gate_passed"] is True
    assert len(data["gate"]["criteria"]) == 7
    assert data["gate"]["criteria"][0]["name"] == "oom_kill_delta_zero"
