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

# Poll interval for the memory.current dense-poll fallback (BP-179 §2 corrected):
# short for the seconds-scale measure/ramp burst, configurable and longer by
# default for the hours-scale soak so a multi-hour run doesn't spawn a `docker
# exec` every 50ms.
BURST_POLL_INTERVAL_SECONDS = 0.05
DEFAULT_SOAK_POLL_INTERVAL_SECONDS = 2.0


def _timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _measure_peak_during(
    reader: cgroup.DockerCgroupReader, coro, poll_interval_seconds: float
):
    """Run `coro` (an unawaited coroutine) and return `(result, peak_bytes,
    used_fallback, poll_degraded, poll_error)`.

    Prefers a memory.peak reset before/read after (BP-179 §2); falls back to
    dense-polling memory.current for the coro's duration when reset is
    unsupported (kernel < 6.8 or a read-only cgroup — verified true on the
    WSL2 6.6 target, BP-179 §2 corrected PM #387). `poll_degraded` is True
    when the dense-poll fallback lost its docker exec read mid-run — the
    peak is then a floor, not a confirmed max.
    """
    reset_ok = reader.try_reset_peak()
    poller = None
    if not reset_ok:
        poller = cgroup.PeakPoller(reader, interval_seconds=poll_interval_seconds)
        poller.start()
    try:
        result = asyncio.run(coro)
    finally:
        polled_peak = poller.stop() if poller is not None else None
    peak = reader.read_peak() if reset_ok else polled_peak
    poll_degraded = poller.degraded if poller is not None else False
    poll_error = str(poller._poll_error) if poll_degraded else None
    return result, peak, not reset_ok, poll_degraded, poll_error


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

    corpus_fallback_used = payloads.corpus_is_empty(args.corpus_dir, args.model)
    if corpus_fallback_used:
        print(
            f"WARNING: corpus_dir={args.corpus_dir} has no matching files for "
            f"model={args.model!r} — this run uses placeholder toy strings, NOT "
            "representative of BP-179 §2 realistic payloads"
        )

    dist = payloads.LengthDistribution(
        p50_chars=args.p50_chars, p99_chars=args.p99_chars
    )
    request_batches = [
        payloads.sample_texts(
            args.corpus_dir, args.batch_size, dist, args.model, seed=i
        )
        for i in range(args.concurrency)
    ]
    request_results, peak, peak_fallback_used, peak_poll_degraded, peak_poll_error = (
        _measure_peak_during(
            reader,
            load.run_burst(args.base_url, request_batches, model=args.model),
            BURST_POLL_INTERVAL_SECONDS,
        )
    )
    failures = [r for r in request_results if r.status_code != 200]
    successes = len(request_results) - len(failures)
    # BP-179 §2's (peak-base)/N assumes all N concurrent requests actually
    # drove load; a failed request may not have — annotate rather than
    # silently dividing by the nominal concurrency when that assumption broke.
    per_req_peak = (
        envelope.per_request_burst_peak(peak, base_rss, args.concurrency)
        if successes > 0
        else None
    )

    print(f"memory.peak = {peak} bytes ({peak / 2**30:.3f} GiB)")
    if peak_fallback_used:
        print("  (via memory.current dense-poll fallback — reset unsupported)")
    if peak_poll_degraded:
        print(f"WARNING: peak poll degraded mid-run — {peak_poll_error}")
    if per_req_peak is not None:
        print(
            f"per_request_burst_peak = {per_req_peak:.0f} bytes "
            f"({per_req_peak / 2**20:.1f} MiB) over N={args.concurrency}"
        )
    if failures:
        print(
            f"WARNING: {len(failures)}/{len(request_results)} burst requests "
            "did not return 200 — measured peak may understate the real burst; "
            "per_request_burst_peak divides by the nominal concurrency, not the "
            "successful count"
        )

    data = {
        "mode": "measure",
        "container": args.container,
        "concurrency": args.concurrency,
        "batch_size": args.batch_size,
        "model": args.model,
        "base_rss_bytes": base_rss,
        "memory_peak_bytes": peak,
        "peak_measurement_fallback_used": peak_fallback_used,
        "peak_poll_degraded": peak_poll_degraded,
        "peak_poll_error": peak_poll_error,
        "per_request_burst_peak_bytes": per_req_peak,
        "request_count": len(request_results),
        "request_failures": len(failures),
        "corpus_fallback_used": corpus_fallback_used,
    }
    out_path = args.output_dir / f"measure-{_timestamp()}.json"
    results.write_results_json(out_path, data)
    print(f"results written to {out_path}")
    return 1 if failures else 0


def cmd_ramp(args: argparse.Namespace) -> int:
    reader = cgroup.DockerCgroupReader(args.container, args.cgroup_root)
    base_rss = reader.read_current()
    baseline_events = reader.read_events()
    baseline_metrics = metrics_client.parse_metrics(
        metrics_client.fetch_metrics_text(args.base_url)
    )
    baseline_shed = baseline_metrics.backpressure.get("shed", 0.0)
    dist = payloads.LengthDistribution(
        p50_chars=args.p50_chars, p99_chars=args.p99_chars
    )

    corpus_fallback_used = payloads.corpus_is_empty(args.corpus_dir, args.model)
    if corpus_fallback_used:
        print(
            f"WARNING: corpus_dir={args.corpus_dir} has no matching files for "
            f"model={args.model!r} — this run uses placeholder toy strings, NOT "
            "representative of BP-179 §2 realistic payloads"
        )

    rounds: list[dict] = []
    concurrency = args.start_concurrency
    while concurrency <= args.max_concurrency:
        request_batches = [
            payloads.sample_texts(
                args.corpus_dir, args.batch_size, dist, args.model, seed=i
            )
            for i in range(concurrency)
        ]
        (
            request_results,
            peak,
            peak_fallback_used,
            peak_poll_degraded,
            peak_poll_error,
        ) = _measure_peak_during(
            reader,
            load.run_burst(args.base_url, request_batches, model=args.model),
            BURST_POLL_INTERVAL_SECONDS,
        )
        events = reader.read_events()
        oom_delta = events.get("oom_kill", 0) - baseline_events.get("oom_kill", 0)
        snapshot = metrics_client.parse_metrics(
            metrics_client.fetch_metrics_text(args.base_url)
        )
        shed_delta = snapshot.backpressure.get("shed", 0.0) - baseline_shed
        request_failures = sum(1 for r in request_results if r.status_code != 200)
        validity = gate.evaluate_load_validity(
            total_requests=len(request_results),
            total_failures=request_failures,
            memory_peak_bytes=peak,
            base_rss_bytes=base_rss,
        )

        round_data = {
            "concurrency": concurrency,
            "memory_peak_bytes": peak,
            "peak_measurement_fallback_used": peak_fallback_used,
            "peak_poll_degraded": peak_poll_degraded,
            "peak_poll_error": peak_poll_error,
            "oom_kill_delta": oom_delta,
            "backpressure_shed_delta": shed_delta,
            "request_failures": request_failures,
            "load_valid": validity.valid,
            "load_validity_detail": validity.detail,
        }
        rounds.append(round_data)
        print(
            f"concurrency={concurrency}: peak={peak / 2**30:.3f} GiB "
            f"oom_kill_delta={oom_delta} shed_delta={shed_delta} "
            f"load_valid={validity.valid}"
        )
        if peak_poll_degraded:
            print(f"  WARNING: peak poll degraded mid-round — {peak_poll_error}")

        if oom_delta > 0 or shed_delta > 0:
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
        if r["oom_kill_delta"] == 0
        and not r["backpressure_shed_delta"]
        and r["load_valid"]
    ]
    per_req_peak = None
    recommendation = None
    ceiling_concurrency = None
    ceiling_message = None
    if clean_rounds:
        last_clean = clean_rounds[-1]
        ceiling_concurrency = last_clean["concurrency"]
        per_req_peak = envelope.per_request_burst_peak(
            last_clean["memory_peak_bytes"], base_rss, last_clean["concurrency"]
        )
        recommendation = envelope.recommend_envelope(
            base_rss, per_req_peak, args.safety_margin_ratio
        )
    else:
        ceiling_message = (
            "no safe concurrency found — every round hit oom_kill, shed, or an "
            "invalid load"
        )
        print(f"WARNING: {ceiling_message}")

    data = {
        "mode": "ramp",
        "container": args.container,
        "base_rss_bytes": base_rss,
        "rounds": rounds,
        "ceiling_concurrency": ceiling_concurrency,
        "ceiling_message": ceiling_message,
        "per_request_burst_peak_bytes": per_req_peak,
        "recommendation": recommendation,
        "corpus_fallback_used": corpus_fallback_used,
    }
    out_path = args.output_dir / f"ramp-{_timestamp()}.json"
    results.write_results_json(out_path, data)
    print(f"results written to {out_path}")
    return 0 if ceiling_concurrency is not None else 1


def cmd_soak(args: argparse.Namespace) -> int:
    reader = cgroup.DockerCgroupReader(args.container, args.cgroup_root)
    # Pre-flight dmesg readability NOW, not hours into the soak (M2): raises
    # CgroupAccessError immediately if unreadable, and its return value
    # baselines the ring buffer so stale prior-run kills aren't re-reported.
    dmesg_baseline_ts = cgroup.dmesg_baseline()
    # Second authoritative OOM witness (TD-792/789): a real kill is invisible to
    # memory.events/docker-OOMKilled/app-counter on this host — only dmesg and
    # a container restart witness it. Baseline the restart count NOW so a delta
    # over the soak reflects only kills during the run.
    restart_count_start = cgroup.container_restart_count(args.container)

    baseline_events = reader.read_events()
    working_set_start = reader.read_current()
    baseline_metrics = metrics_client.parse_metrics(
        metrics_client.fetch_metrics_text(args.base_url)
    )
    baseline_shed = baseline_metrics.backpressure.get("shed", 0.0)

    corpus_fallback_used = payloads.corpus_is_empty(args.corpus_dir, args.model)
    if corpus_fallback_used:
        print(
            f"WARNING: corpus_dir={args.corpus_dir} has no matching files for "
            f"model={args.model!r} — this run uses placeholder toy strings, NOT "
            "representative of BP-179 §2 realistic payloads"
        )

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
    caller_stats, peak, peak_fallback_used, peak_poll_degraded, peak_poll_error = (
        _measure_peak_during(
            reader,
            load.run_soak_callers(
                args.base_url,
                n_callers,
                args.duration_seconds,
                payload_fn,
                model=args.model,
            ),
            args.peak_poll_interval_seconds,
        )
    )

    working_set_end = reader.read_current()
    final_events = reader.read_events()
    oom_kill_delta = final_events.get("oom_kill", 0) - baseline_events.get(
        "oom_kill", 0
    )
    dmesg_lines = cgroup.scan_dmesg_oom(since_timestamp=dmesg_baseline_ts)
    restart_count_end = cgroup.container_restart_count(args.container)
    restart_count_delta = restart_count_end - restart_count_start
    final_metrics = metrics_client.parse_metrics(
        metrics_client.fetch_metrics_text(args.base_url)
    )
    shed_delta = final_metrics.backpressure.get("shed", 0.0) - baseline_shed

    total_requests = sum(c.requests_sent for c in caller_stats)
    total_failures = sum(
        1 for c in caller_stats for r in c.results if r.status_code != 200
    )

    gate_result = gate.evaluate_gate(
        oom_kill_delta=oom_kill_delta,
        dmesg_oom_count=len(dmesg_lines),
        restart_count_delta=restart_count_delta,
        shed_delta=shed_delta,
        admission_wait_p95_seconds=final_metrics.admission_wait_p95_seconds,
        client_read_timeout_seconds=args.read_timeout_seconds,
        working_set_start_bytes=working_set_start,
        working_set_end_bytes=working_set_end,
        leak_tolerance_ratio=args.leak_tolerance_ratio,
        memory_peak_bytes=peak,
        mem_limit_bytes=args.mem_limit_bytes,
        total_requests=total_requests,
        total_failures=total_failures,
        base_rss_bytes=working_set_start,
    )

    print(f"soak complete: {total_requests} requests sent, {total_failures} non-200")
    if peak_poll_degraded:
        print(f"  WARNING: peak poll degraded mid-soak — {peak_poll_error}")
    if not gate_result.load_valid:
        print(f"  LOAD INVALID: {gate_result.load_validity_detail}")
    for criterion in gate_result.criteria:
        status = "PASS" if criterion.passed else "FAIL"
        print(f"  [{status}] {criterion.name}: {criterion.detail}")
    print(f"GATE: {gate_result.outcome}")

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
        "restart_count_start": restart_count_start,
        "restart_count_end": restart_count_end,
        "restart_count_delta": restart_count_delta,
        "shed_delta": shed_delta,
        "working_set_start_bytes": working_set_start,
        "working_set_end_bytes": working_set_end,
        "memory_peak_bytes": peak,
        "peak_measurement_fallback_used": peak_fallback_used,
        "peak_poll_degraded": peak_poll_degraded,
        "peak_poll_error": peak_poll_error,
        "mem_limit_bytes": args.mem_limit_bytes,
        "admission_wait_p95_seconds": final_metrics.admission_wait_p95_seconds,
        "gate": gate_result,
        "gate_outcome": gate_result.outcome,
        "gate_passed": gate_result.passed,
        "corpus_fallback_used": corpus_fallback_used,
    }
    out_path = args.output_dir / f"soak-{_timestamp()}.json"
    results.write_results_json(out_path, data)
    print(f"results written to {out_path}")
    if gate_result.outcome == "PASS":
        return 0
    return 2 if gate_result.outcome == "INVALID" else 1


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
    p_soak.add_argument(
        "--peak-poll-interval-seconds",
        type=float,
        default=DEFAULT_SOAK_POLL_INTERVAL_SECONDS,
        help="memory.current poll interval for the dense-poll peak fallback "
        "when memory.peak reset is unsupported (default: "
        f"{DEFAULT_SOAK_POLL_INTERVAL_SECONDS}s)",
    )
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
