# Embedding Capacity/Soak Harness — Overnight Runbook

Companion to `scripts/perf/embedding_capacity_harness.py` (PLAN-030 Phase 2,
BP-179, BUG-329). This harness **measures and recommends**; it never modifies
`docker/embedding/main.py` or the shipped `EMBEDDING_MEMORY_LIMIT` /
`EMBEDDING_MAX_CONCURRENCY` defaults. Applying a recommended pair is a
separate, deliberate follow-up decision.

## Before you start

- The `ai-memory-embedding` container is shared across every project on the
  host (BP-179 applicability check). A capacity-ramp or soak run deliberately
  drives it to its OOM ceiling — **notify anyone else relying on the shared
  stack before running ramp or soak**, and prefer an off-hours window.
- **Pause this project's own memory capture for the window** so the soak's
  synthetic load isn't recorded as real project activity and doesn't compete
  with the harness's own embed calls: run the `aim-pause-updates` skill (or
  toggle `auto_update_enabled` off) before starting, and re-enable it after
  the soak completes.
- Confirm `docker exec ai-memory-embedding cat /sys/fs/cgroup/memory.current`
  works from this host before scheduling the run — if it errors, stop and
  fix cgroup access first (see BLOCKER PROTOCOL in the dispatch brief; do not
  guess a value).
- `memory.peak` **reset** needs Linux >= 6.8 AND a writable cgroup mount; on
  the WSL2 6.6 target it is `-r--r--r--` (read-only), so reset fails. The
  harness detects this automatically (`try_reset_peak()`) and falls back to
  dense-polling `memory.current` for the burst/soak duration instead
  (BP-179 §2 corrected) — every result JSON records whether the fallback was
  used via `peak_measurement_fallback_used`. No manual smoke-check needed.
- Confirm `dmesg` is readable (no `Operation not permitted`) — it is one of
  the two authoritative OOM signals (BP-179 §3) and the harness raises
  `CgroupAccessError` rather than silently treating a permission failure as
  "zero kills". `soak` does this pre-flight automatically at start.
- Install harness dependencies: `pip install -e .[dev]` from the repo root
  (adds `httpx`, `prometheus-client`, already in `dev`).

All commands below assume `cwd` is the repo root and the stack is already
running (`docker/stack.sh` up, embedding service healthy on `:28080`).

## Step 1 — Measure (`measure`)

Establishes `base_rss` and `per_request_burst_peak` at your current
concurrency (BP-179 §2). Run once per model (`en`, `code`) you care about.

```bash
python scripts/perf/embedding_capacity_harness.py measure \
    --concurrency 4 --batch-size 30 --model en \
    --corpus-dir /mnt/e/projects/dev-ai-memory/ai-memory/docs
```

- `--corpus-dir` should point at real prose (`docs/`) for `--model en` or a
  code tree (`src/`) for `--model code` — the harness slices real file
  content into batches, never toy strings (BP-179 §2).
- Read the printed `per_request_burst_peak`. If it is far above the ~0.2
  GiB/slot nominal in MEMORY.md, that gap is expected (BP-179 §6) — it is
  *why* you are measuring instead of trusting the nominal figure.

**Optional: re-measure after footprint knobs.** If BP-175's footprint
mitigations (`MALLOC_ARENA_MAX=2`, lower `OMP_NUM_THREADS`) are applied to
the container, restart it and re-run `measure` to get the *post-mitigation*
`per_request_burst_peak` before sizing the envelope in Step 2 — sizing off
the pre-mitigation number leaves headroom on the table.

## Step 2 — Capacity-ramp (`ramp`)

Finds the real ceiling and emits a recommended `(mem_limit, max_concurrency)`
table.

```bash
python scripts/perf/embedding_capacity_harness.py ramp \
    --start-concurrency 1 --max-concurrency 8 --step 1 \
    --batch-size 30 --model en \
    --corpus-dir /mnt/e/projects/dev-ai-memory/ai-memory/docs
```

- Stops the moment `memory.events:oom_kill` increments or backpressure
  sheds — this **will** attempt to OOM the container by design; that is the
  ceiling-finding mechanism (BP-179 §4, capacity test).
- The results JSON (`scripts/perf/results/ramp-<timestamp>.json`) includes a
  `recommendation` table: one `(max_concurrency, mem_limit_bytes)` candidate
  per concurrency level, each satisfying
  `base + max_concurrency × per_req_peak + 15% safety ≤ mem_limit`. Pick the
  row matching your RAM budget vs. throughput tradeoff (BP-179 §1: prefer
  lowering concurrency over raising the cap).
- If the container crash-loops or the host visibly thrashes, stop the ramp
  (Ctrl-C) — you already have the ceiling from the last successful round.

## Step 3 — Apply the envelope (manual, out of harness scope)

Update `EMBEDDING_MEMORY_LIMIT` and `EMBEDDING_MAX_CONCURRENCY` in the
deployment's `.env` per the chosen row from Step 2, then
`docker/stack.sh restart` to pick up the new container memory limit (image
changes need a restart; `install.sh` alone won't recreate the container —
`feedback_stack_restart_required_for_image_changes`). This is a deliberate,
reviewed decision — not something the harness does automatically.

## Step 4 — Soak (`soak`)

Validates the chosen envelope survives sustained, burst-shaped, genuine
multi-caller load and asserts all 6 BP-179 §4 gate criteria. Run overnight.

```bash
python scripts/perf/embedding_capacity_harness.py soak \
    --duration-hours 8 \
    --concurrency-ceiling 4 --waiters 4 \
    --mem-limit-bytes 6442450944 \
    --model en --corpus-dir /mnt/e/projects/dev-ai-memory/ai-memory/docs \
    --read-timeout-seconds 30
```

- `--concurrency-ceiling` + `--waiters` sets the caller count (defaults to
  their sum unless `--callers` is given explicitly) — BP-179 §4 point 1
  requires concurrency **at or above** the envelope ceiling plus waiters, so
  the backpressure queue is genuinely exercised, not just the semaphore.
- `--mem-limit-bytes` must match whatever `EMBEDDING_MEMORY_LIMIT` is
  actually set to on the container right now (Step 3) — the gate's
  `peak_under_mem_limit` criterion is meaningless against the wrong number.
- The harness snapshots `memory.events` **before** the run and reports
  deltas — a baseline is mandatory per BP-179 §4; without it, pre-existing
  kills would be misattributed to this soak.
- The gate has three possible outcomes — exit code **0** (`PASS`, all 6
  criteria pass), **1** (`FAIL`, at least one criterion failed), or **2**
  (`INVALID`, the load-validity guard tripped before the 6 criteria were
  even meaningful). `INVALID` fires when either too few requests succeeded
  (success ratio below the floor) or the measured peak never rose
  meaningfully above the base RSS — both indicate the burst/soak load never
  actually landed (e.g. wrong port, all-503s, not-ready container), so a
  trivial all-PASS on the 6 criteria wouldn't certify anything. On
  `INVALID`, fix why the load didn't land (check `--base-url`/`--container`,
  confirm the target is warm and serving) and re-run — it is not a capacity
  verdict either way.
- Results land in `scripts/perf/results/soak-<timestamp>.json` plus a
  human-readable PASS/FAIL/INVALID line per criterion on stdout.

## Reading a soak failure

| Failing criterion | What it means | Where to look |
|---|---|---|
| `oom_kill_delta_zero` / `dmesg_oom_zero` | The envelope is unsafe — the primary gate. | `docker exec ai-memory-embedding cat /sys/fs/cgroup/memory.events`, `dmesg` |
| `backpressure_shed_zero` | A request was dropped (lost memory), not just delayed. | `embedding_backpressure_total{action="shed"}` on `:28080/metrics` |
| `admission_wait_p95_within_timeout` | Clients would time out and retry-storm under this envelope. | `embedding_admission_wait_seconds` histogram |
| `no_working_set_climb` | Possible slow leak/fragmentation drift (BUG-324 axis). | Compare `working_set_start_bytes`/`working_set_end_bytes` in the results JSON |
| `peak_under_mem_limit` | The measured peak reached or exceeded the cap even without a kill — no safety margin left. | `memory_peak_bytes` in the results JSON vs `--mem-limit-bytes` |

The `memory_peak_bytes` value is the polled `memory.current` max (dense-poll
fallback on kernels < 6.8 or a read-only cgroup mount — the case on the
WSL2 6.6 target), not `memory.peak` directly; check
`peak_measurement_fallback_used` in the results JSON to confirm which path
was used. If `peak_poll_degraded` is `true`, the poller lost its `docker
exec` read partway through the run — `peak_poll_error` has the detail, and
`memory_peak_bytes` is a floor (last value observed before the failure),
not a confirmed max; treat a `peak_under_mem_limit` PASS on a degraded run
with less confidence and consider re-running.

A failed soak means: go back to Step 1/2 with a lower `max_concurrency` or
apply BP-175 §5 footprint knobs and re-measure — do not raise `mem_limit`
alone (BP-179 §1, lever 3 is last-resort).

## After the run

- Re-enable project memory capture (`aim-pause-updates` toggle back on).
- Archive the `scripts/perf/results/*.json` files you want to keep — they
  are gitignored by default (see `.gitignore`); commit selected results
  explicitly if they should be preserved as evidence for a decision record.
