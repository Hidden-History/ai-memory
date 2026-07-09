#!/usr/bin/env python3
"""Embedding capacity + soak harness — PLAN-030 Phase 2 (BP-179).

Measures the real memory footprint of the ai-memory-embedding service under
burst (measure), ramps concurrency to find the ceiling (ramp), and soaks a
chosen envelope asserting the BP-179 §4 pass/fail gate (soak).

This is a MEASUREMENT tool: it drives and observes the shipped resilience
mechanism in docker/embedding/main.py (semaphore, AIMD, cgroup memory.events)
over HTTP + `docker exec`; it never modifies the service or its defaults.

Usage:
    python scripts/perf/embedding_capacity_harness.py measure \\
        --concurrency 4 --batch-size 30

    python scripts/perf/embedding_capacity_harness.py ramp \\
        --start-concurrency 1 --max-concurrency 8

    python scripts/perf/embedding_capacity_harness.py soak \\
        --duration-hours 4 --concurrency-ceiling 4 --waiters 4 \\
        --mem-limit-bytes 6442450944

See scripts/perf/runbook.md for the overnight measure -> size -> soak sequence.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from embedding_capacity import (
    cgroup,
    envelope,
    gate,
    load,
    metrics_client,
    payloads,
    results,
)

DEFAULT_CONTAINER = "ai-memory-embedding"
DEFAULT_BASE_URL = "http://localhost:28080"
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--cgroup-root", default=cgroup.DEFAULT_CGROUP_ROOT)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--model", choices=["en", "code"], default="en")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--p50-chars", type=int, default=800)
    parser.add_argument("--p99-chars", type=int, default=2048)


def cmd_measure(args: argparse.Namespace) -> int:
    reader = cgroup.DockerCgroupReader(args.container, args.cgroup_root)
    base_rss = reader.read_current()
    print(f"base_rss = {base_rss} bytes ({base_rss / 2**30:.3f} GiB)")

    reader.reset_peak()
    dist = payloads.LengthDistribution(
        p50_chars=args.p50_chars, p99_chars=args.p99_chars
    )
    request_batches = [
        payloads.sample_texts(
            args.corpus_dir, args.batch_size, dist, args.model, seed=i
        )
        for i in range(args.concurrency)
    ]
    request_results = asyncio.run(
        load.run_burst(args.base_url, request_batches, model=args.model)
    )
    peak = reader.read_peak()
    per_req_peak = envelope.per_request_burst_peak(peak, base_rss, args.concurrency)

    failures = [r for r in request_results if r.status_code != 200]
    print(f"memory.peak = {peak} bytes ({peak / 2**30:.3f} GiB)")
    print(
        f"per_request_burst_peak = {per_req_peak:.0f} bytes "
        f"({per_req_peak / 2**20:.1f} MiB) over N={args.concurrency}"
    )
    if failures:
        print(
            f"WARNING: {len(failures)}/{len(request_results)} burst requests "
            "did not return 200 — measured peak may understate the real burst"
        )

    data = {
        "mode": "measure",
        "container": args.container,
        "concurrency": args.concurrency,
        "batch_size": args.batch_size,
        "model": args.model,
        "base_rss_bytes": base_rss,
        "memory_peak_bytes": peak,
        "per_request_burst_peak_bytes": per_req_peak,
        "request_count": len(request_results),
        "request_failures": len(failures),
    }
    out_path = args.output_dir / f"measure-{_timestamp()}.json"
    results.write_results_json(out_path, data)
    print(f"results written to {out_path}")
    return 1 if failures else 0


def cmd_ramp(args: argparse.Namespace) -> int:
    reader = cgroup.DockerCgroupReader(args.container, args.cgroup_root)
    base_rss = reader.read_current()
    baseline_events = reader.read_events()
    dist = payloads.LengthDistribution(
        p50_chars=args.p50_chars, p99_chars=args.p99_chars
    )

    rounds: list[dict] = []
    concurrency = args.start_concurrency
    ceiling = args.max_concurrency
    while concurrency <= args.max_concurrency:
        reader.reset_peak()
        request_batches = [
            payloads.sample_texts(
                args.corpus_dir, args.batch_size, dist, args.model, seed=i
            )
            for i in range(concurrency)
        ]
        request_results = asyncio.run(
            load.run_burst(args.base_url, request_batches, model=args.model)
        )
        peak = reader.read_peak()
        events = reader.read_events()
        oom_delta = events.get("oom_kill", 0) - baseline_events.get("oom_kill", 0)
        snapshot = metrics_client.parse_metrics(
            metrics_client.fetch_metrics_text(args.base_url)
        )
        shed_total = snapshot.backpressure.get("shed", 0.0)

        round_data = {
            "concurrency": concurrency,
            "memory_peak_bytes": peak,
            "oom_kill_delta": oom_delta,
            "backpressure_shed_total": shed_total,
            "request_failures": sum(1 for r in request_results if r.status_code != 200),
        }
        rounds.append(round_data)
        print(
            f"concurrency={concurrency}: peak={peak / 2**30:.3f} GiB "
            f"oom_kill_delta={oom_delta} shed_total={shed_total}"
        )

        if oom_delta > 0 or shed_total > 0:
            ceiling = max(args.start_concurrency, concurrency - args.step)
            print(
                f"ceiling reached: concurrency={concurrency} triggered oom_kill or shed"
            )
            break
        concurrency += args.step
    else:
        print(
            f"reached max_concurrency={args.max_concurrency} without hitting a ceiling"
        )

    clean_rounds = [
        r
        for r in rounds
        if r["oom_kill_delta"] == 0 and not r["backpressure_shed_total"]
    ]
    per_req_peak = None
    recommendation = None
    if clean_rounds:
        last_clean = clean_rounds[-1]
        per_req_peak = envelope.per_request_burst_peak(
            last_clean["memory_peak_bytes"], base_rss, last_clean["concurrency"]
        )
        recommendation = envelope.recommend_envelope(
            base_rss, per_req_peak, args.safety_margin_ratio
        )

    data = {
        "mode": "ramp",
        "container": args.container,
        "base_rss_bytes": base_rss,
        "rounds": rounds,
        "ceiling_concurrency": ceiling,
        "per_request_burst_peak_bytes": per_req_peak,
        "recommendation": recommendation,
    }
    out_path = args.output_dir / f"ramp-{_timestamp()}.json"
    results.write_results_json(out_path, data)
    print(f"results written to {out_path}")
    return 0


def cmd_soak(args: argparse.Namespace) -> int:
    reader = cgroup.DockerCgroupReader(args.container, args.cgroup_root)
    baseline_events = reader.read_events()
    working_set_start = reader.read_current()
    reader.reset_peak()
    baseline_metrics = metrics_client.parse_metrics(
        metrics_client.fetch_metrics_text(args.base_url)
    )
    baseline_shed = baseline_metrics.backpressure.get("shed", 0.0)

    dist = payloads.LengthDistribution(
        p50_chars=args.p50_chars, p99_chars=args.p99_chars
    )

    def payload_fn() -> list[str]:
        return payloads.sample_texts(args.corpus_dir, args.batch_size, dist, args.model)

    n_callers = args.callers or (args.concurrency_ceiling + args.waiters)
    print(
        f"soak starting: callers={n_callers} duration={args.duration_seconds:.0f}s "
        f"model={args.model} batch_size={args.batch_size}"
    )
    caller_stats = asyncio.run(
        load.run_soak_callers(
            args.base_url,
            n_callers,
            args.duration_seconds,
            payload_fn,
            model=args.model,
        )
    )

    working_set_end = reader.read_current()
    peak = reader.read_peak()
    final_events = reader.read_events()
    oom_kill_delta = final_events.get("oom_kill", 0) - baseline_events.get(
        "oom_kill", 0
    )
    dmesg_lines = cgroup.scan_dmesg_oom()
    final_metrics = metrics_client.parse_metrics(
        metrics_client.fetch_metrics_text(args.base_url)
    )
    shed_delta = final_metrics.backpressure.get("shed", 0.0) - baseline_shed

    gate_result = gate.evaluate_gate(
        oom_kill_delta=oom_kill_delta,
        dmesg_oom_count=len(dmesg_lines),
        shed_delta=shed_delta,
        admission_wait_p95_seconds=final_metrics.admission_wait_p95_seconds,
        client_read_timeout_seconds=args.read_timeout_seconds,
        working_set_start_bytes=working_set_start,
        working_set_end_bytes=working_set_end,
        leak_tolerance_ratio=args.leak_tolerance_ratio,
        memory_peak_bytes=peak,
        mem_limit_bytes=args.mem_limit_bytes,
    )

    total_requests = sum(c.requests_sent for c in caller_stats)
    total_failures = sum(
        1 for c in caller_stats for r in c.results if r.status_code != 200
    )

    print(f"soak complete: {total_requests} requests sent, {total_failures} non-200")
    for criterion in gate_result.criteria:
        status = "PASS" if criterion.passed else "FAIL"
        print(f"  [{status}] {criterion.name}: {criterion.detail}")
    print(f"GATE: {'PASS' if gate_result.passed else 'FAIL'}")

    data = {
        "mode": "soak",
        "container": args.container,
        "duration_seconds": args.duration_seconds,
        "callers": n_callers,
        "total_requests": total_requests,
        "total_failures": total_failures,
        "baseline_events": baseline_events,
        "final_events": final_events,
        "oom_kill_delta": oom_kill_delta,
        "dmesg_oom_lines": dmesg_lines,
        "shed_delta": shed_delta,
        "working_set_start_bytes": working_set_start,
        "working_set_end_bytes": working_set_end,
        "memory_peak_bytes": peak,
        "mem_limit_bytes": args.mem_limit_bytes,
        "admission_wait_p95_seconds": final_metrics.admission_wait_p95_seconds,
        "gate": gate_result,
        "gate_passed": gate_result.passed,
    }
    out_path = args.output_dir / f"soak-{_timestamp()}.json"
    results.write_results_json(out_path, data)
    print(f"results written to {out_path}")
    return 0 if gate_result.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_measure = sub.add_parser(
        "measure", help="Measure base_rss + per_request_burst_peak"
    )
    _add_common_args(p_measure)
    p_measure.add_argument("--concurrency", type=int, default=4)
    p_measure.set_defaults(func=cmd_measure)

    p_ramp = sub.add_parser("ramp", help="Ramp concurrency to find the ceiling")
    _add_common_args(p_ramp)
    p_ramp.add_argument("--start-concurrency", type=int, default=1)
    p_ramp.add_argument("--max-concurrency", type=int, default=8)
    p_ramp.add_argument("--step", type=int, default=1)
    p_ramp.add_argument("--safety-margin-ratio", type=float, default=0.15)
    p_ramp.set_defaults(func=cmd_ramp)

    p_soak = sub.add_parser("soak", help="Soak the chosen envelope and assert the gate")
    _add_common_args(p_soak)
    p_soak.add_argument("--duration-seconds", type=float, default=None)
    p_soak.add_argument("--duration-hours", type=float, default=None)
    p_soak.add_argument("--callers", type=int, default=0)
    p_soak.add_argument("--concurrency-ceiling", type=int, default=4)
    p_soak.add_argument("--waiters", type=int, default=4)
    p_soak.add_argument("--mem-limit-bytes", type=int, required=True)
    p_soak.add_argument("--read-timeout-seconds", type=float, default=30.0)
    p_soak.add_argument("--leak-tolerance-ratio", type=float, default=0.10)
    p_soak.set_defaults(func=cmd_soak)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.mode == "soak":
        if args.duration_seconds is None and args.duration_hours is None:
            parser.error("soak requires --duration-seconds or --duration-hours")
        if args.duration_seconds is None:
            args.duration_seconds = args.duration_hours * 3600
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
