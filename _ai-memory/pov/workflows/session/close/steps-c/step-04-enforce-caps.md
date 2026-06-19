---
name: 'step-04-enforce-caps'
description: 'Enforce oversight-file caps before save; block closeout while any governed file is over cap'
nextStepFile: './step-05-save-and-confirm.md'
---

# Step 4: Enforce Oversight-File Caps

**Progress: Step 4 of 5** — Next: Save and Confirm

## STEP GOAL:

Run the cap-enforcement gate so closeout cannot declare complete — or push a
bloated handoff to Qdrant — while any governed oversight file is over its cap.
The handoff has just been written (Step 3); this gate runs after it and before
the Qdrant save (Step 5).

**Scope:**
- Available context: handoff from Step 3, tracking updated in Step 2
- Focus: cap enforcement only — Qdrant save is the next step
- Limits: a breach BLOCKS closeout until rotated; do not skip, do not save over a breach
- Dependencies: handoff written (Step 3) and tracking rotated (Step 2)

**Behavioral Constraints:**
- FORBIDDEN to proceed to Step 5 while `--check` reports a breach
- Approach: run the gate, rotate any over-cap file with the surfaced remedy, re-run until clean

## Sequence

### 1. Run the Enforcement Gate

Invoke the `aim-tracking-rotate` gate against the oversight root:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --check \
  --oversight-root {oversight_path}
```

The gate reads each governed file's cap from its own front-matter contract,
falling back to the built-in `filename → cap` registry when front-matter is
absent. Caps are byte **and** line — either breach fails.

- **Exit 0 (PASS)** → all governed files within cap. Note it and proceed.
- **Exit non-zero (FAIL)** → the gate prints a SYSTEM FAILURE block per
  over-cap file (file, size, cap, remedy command). Closeout is BLOCKED.

### 2. Rotate Any Over-Cap File

For each SYSTEM FAILURE block, run the remedy command it printed.

For `decision-log.md` (the verified id-H3 append-only-log) the remedy is
`--apply`:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --apply {over_cap_file} \
  --oversight-root {oversight_path}
```

This moves the oldest contiguous block of whole entries into a dated archive
shard, updates the `decision-log-INDEX.md` manifest, and writes a thin live
pointer — chronology preserved.

For a table-row / multi-table register or live-index (`blockers-log.md`,
`risk-register.md`, `SESSION_WORK_INDEX.md`, `session-index/INDEX.md`) the gate
**REFUSES** `--apply` (field-aware safe rotation deferred to TD-655). Use `--fix`
instead — it archives the whole file verbatim and rewrites a lean index + pointer:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --fix {over_cap_file} \
  --oversight-root {oversight_path}
```

For a heartbeat or non-rotatable register (`project-status.md`, `task-tracker.md`),
use `--fix` — it archives-whole-verbatim for non-rotatable registers, and refreshes
the template front-matter for heartbeats:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --fix {over_cap_file} \
  --oversight-root {oversight_path}
```

If `--fix` reports that a heartbeat body is still over cap after the front-matter
refresh, trim the body by hand, then re-run.

### 3. Re-Run Until Clean

Re-run the Step 1 `--check` command. Repeat rotate → re-check until it reports
PASS. Only a clean gate may advance to Step 5.

## CRITICAL STEP COMPLETION NOTE

ONLY when `--check` reports PASS (all governed files within cap), load and read fully {nextStepFile}
