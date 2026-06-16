---
name: aim-tracking-rotate
description: Enforce oversight-file caps at session-close and rotate over-cap append-only-logs and registers into dated archive shards while preserving chronology and an O(1) by-id manifest. The rotate companion to aim-tracking-freshness.
allowed-tools: Bash
---

# Tracking Rotate — Oversight Cap Enforcement and Archival

**Purpose**: Bound oversight-file bloat without breaking the chronological
trail or by-id lookup (PLAN-028 D3 / BP-167 Part C). `--check` is the
session-close enforcement gate; `--apply` is the BP-167 Part C rotation that
fixes an over-cap file. Complements `aim-tracking-freshness` (which *detects*
INDEX drift); rotate *bounds* the append-only-logs and registers.

**Ownership boundary**: rotate owns append-only-log + register archival
(`decision-log` shards + manifest, `blockers-log`/`risk-register` archive,
`SESSION_WORK_INDEX` tail-shed, `session-index` quarterly shards). It does NOT
touch `bugs/INDEX.md` or `tech-debt/INDEX.md` — those generated files and their
`CLOSED.md` shards are owned by `aim-tracking-freshness`.

---

## Usage

```bash
# Enforcement gate (session-close): exit non-zero if any governed file is over cap.
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --check \
  --oversight-root /path/to/oversight

# Rotate an over-cap file's oldest entries into a dated archive shard:
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --apply /path/to/oversight/tracking/decision-log.md \
  --oversight-root /path/to/oversight

# Oversight root can also come from the environment:
AI_MEMORY_OVERSIGHT_ROOT=/path/to/oversight \
  python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py --check
```

Optional flags: `--entry-pattern '<regex>'` (entry-boundary line; resolution
order is this flag → the file's contract `entry_pattern` → the built-in
id-prefixed H3 default `^### [A-Z]{2,4}-`. Table-row live-indexes
(`SESSION_WORK_INDEX.md`, `session-index/INDEX.md`) carry `^\| ` in their
contract, so `--apply` finds their rows without passing the flag), `--keep <N>`
(force the number of newest entries kept live), `--period YYYY-MM` (archive
period override for deterministic runs).

---

## How it works

- **`--check`** — for every governed file, read its cap from the file's own
  front-matter contract (`cap_lines`/`cap_kb`, D2) and fall back to a built-in
  `filename → cap` registry when the front-matter is absent (the D2 no-clobber
  carry-over case). Measure `wc -l` / `wc -c`. On any breach emit a SYSTEM
  FAILURE block (file, size, cap, remedy command) and **exit non-zero** so
  closeout cannot complete while a governed file is over cap.

- **`--apply <file>`** — move the **oldest contiguous block of whole entries**
  (never splitting an entry) into a dated shard, then either update the
  manifest (`decision-log-INDEX.md`, append-only-log) or the reconciliation
  banner (`N active as of …`, register), write a thin live pointer, and verify
  counts. Heartbeat / thin-register files (`rotation_trigger: none`) are
  check-only — `--apply` refuses them.

Contract source of truth: `PARZIVAL-OVERSIGHT-SOT.md` §14 (caps) and BP-167
Part C (rotation lifecycle). Caps are byte **and** line — either breach fails.

---

## When to use

Invoked by the session-close workflow (`session/close/steps-c/`): step-02
rotates at write (append, then `--apply` if over cap); the enforce-caps gate
step runs `--check` before save so a bloated handoff is never pushed.
