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

**Ownership boundary**: rotate owns append-only-log + register archival. It does
NOT touch `bugs/INDEX.md` or `tech-debt/INDEX.md` — those generated files and
their `CLOSED.md` shards are owned by `aim-tracking-freshness`.

**`--apply` support (and the TD-655 limitation)**: `--check` enforces the cap on
**every** governed file, but `--apply` auto-rotation is shipped only for the
id-H3 append-only log it was verified against:

| File | `--apply` | Why |
|------|-----------|-----|
| `tracking/decision-log.md` | ✅ supported | `### DEC-…` id-H3 entries, newest-first; archives the oldest into a dated shard + manifest |
| `tracking/blockers-log.md` | ⛔ refused → TD-655 | "Active Blockers" table + `### BLK-` detail H3 + "Resolved Blockers" table — archiving the H3 details orphans the matching table rows |
| `tracking/risk-register.md` | ⛔ refused → TD-655 | table rows under `### Critical/High/Medium/Low` severity headers — the H3 boundary is a severity header, not a record |
| `SESSION_WORK_INDEX.md` | ⛔ refused → TD-655 | four distinct tables (Active Task / Last 5 Sessions / Active Blockers / High Priority Risks); a bare `^\| ` match sheds rows from the wrong table, and the last-5 window is hand-managed |
| `session-index/INDEX.md` | ⛔ refused → TD-655 | `### [Month YYYY]` H3 sections + Current-Year and Archive tables (mixed) |

For a ⛔ file, `--apply` makes **no changes** and exits non-zero with a manual
remedy; rotate it by hand (move resolved/oldest rows into its archive
table/shard). Field-aware safe auto-rotation for table-under-severity registers
and multi-table live-indexes is deferred to **TD-655**. The refusal is enforced
by rel-path (`MANUAL_ROTATION_FILES`), so a future cap-contract seed cannot
re-enable an unsafe `--apply`.

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
id-prefixed H3 default `^### [A-Z]{2,4}-`), `--keep <N>` (force the number of
newest entries kept live), `--period YYYY-MM` (archive period override for
deterministic runs).

---

## How it works

- **`--check`** — for every governed file, read its cap from the file's own
  front-matter contract (`cap_lines`/`cap_kb`, D2) and fall back to a built-in
  `filename → cap` registry when the front-matter is absent (the D2 no-clobber
  carry-over case). Measure `wc -l` / `wc -c`. On any breach emit a SYSTEM
  FAILURE block (file, size, cap, remedy command) and **exit non-zero** so
  closeout cannot complete while a governed file is over cap.

- **`--apply <file>`** — move the **oldest contiguous block of whole entries**
  (never splitting an entry) into a dated shard, then update the manifest
  (`decision-log-INDEX.md`, append-only-log), write a thin live pointer, and
  verify counts. An archived entry whose id already exists in the shard with **identical** content is treated as a safe replay and skipped (so an interrupted `--apply` can be re-run idempotently); if the id matches with **different** content, `--apply` refuses — exiting non-zero with the colliding id(s), leaving the live file and shard untouched — so a body is never silently overwritten or dropped. Heartbeat / thin-register files (`rotation_trigger: none`) are
  check-only, and the table-under-severity registers / multi-table live-indexes
  are deferred to TD-655 (see the support table above) — `--apply` refuses both
  non-destructively.

Contract source of truth: `PARZIVAL-OVERSIGHT-SOT.md` §14 (caps) and BP-167
Part C (rotation lifecycle). Caps are byte **and** line — either breach fails.

---

## When to use

Invoked by the session-close workflow (`session/close/steps-c/`): step-02
rotates at write (append, then `--apply` if over cap); the enforce-caps gate
step runs `--check` before save so a bloated handoff is never pushed.
