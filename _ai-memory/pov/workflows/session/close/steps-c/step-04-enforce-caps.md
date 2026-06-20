---
name: 'step-04-enforce-caps'
description: 'Enforce oversight-file caps before save; block closeout while any governed file is over cap'
nextStepFile: './step-05-save-and-confirm.md'
---

# Step 4: Enforce Oversight-File Caps

**Progress: Step 4 of 5** — Next: Save and Confirm

## STEP GOAL:

Run the cap-enforcement gate so closeout cannot declare complete — or push a
bloated handoff to Qdrant — while any governed file is over its cap. The gate
spans BOTH domains: the **oversight** classes (`aim-tracking-rotate`) AND the
**sanctum** identity classes (`aim-lore-hygiene` — CREED/PERSONA/LORE/BOND/
MEMORY), so creep like the PERSONA `## Evolution Log` is caught automatically.
The handoff has just been written (Step 3); this gate runs after it and before
the Qdrant save (Step 5).

**Scope:**
- Available context: handoff from Step 3, tracking updated in Step 2
- Focus: cap enforcement only — Qdrant save is the next step
- Limits: a breach in EITHER gate BLOCKS closeout until fixed; do not skip, do not save over a breach
- Dependencies: handoff written (Step 3) and tracking rotated (Step 2)

**Behavioral Constraints:**
- FORBIDDEN to proceed to Step 5 while EITHER `--check` reports a breach
- Approach: run both gates, fix any over-cap file with the surfaced remedy, re-run until both clean

## Sequence

### 1. Run the Oversight Enforcement Gate

Invoke the `aim-tracking-rotate` gate against the oversight root:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --check \
  --oversight-root {oversight_path}
```

The gate reads each governed file's cap from its own front-matter contract,
falling back to the built-in `filename → cap` registry when front-matter is
absent. Caps are byte **and** line — either breach fails.

- **Exit 0 (PASS)** → all governed oversight files within cap. Note it and proceed.
- **Exit non-zero (FAIL)** → the gate prints a SYSTEM FAILURE block per
  over-cap file (file, size, cap, remedy command). Closeout is BLOCKED.

### 1b. Run the Sanctum Enforcement Gate

Invoke the `aim-lore-hygiene` gate against the sanctum directory
(`{project-root}/_ai-memory/sanctum/{agent_id}/`, e.g. `.../sanctum/parzival/`):

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-lore-hygiene/scripts/lore_hygiene.py \
  --check \
  {project-root}/_ai-memory/sanctum/{agent_id}/
```

This is **read-only** (it never mutates a sanctum file). It checks every governed
sanctum class against its A2 cap: CREED/BOND (line+KB, check-only), LORE/MEMORY
(line+KB, compact — **size is reporting-only**, prints a WARNING but never blocks
closeout per A2: full files stay on disk and rotation is tag-driven), and PERSONA
(`## Evolution Log` kept to the last 10 entries).

- **Exit 0 (PASS)** → no blocking breach (any over-size LORE/MEMORY is a WARNING
  only). Note it and proceed.
- **Exit non-zero (FAIL)** → a SYSTEM FAILURE block per over-cap file with its
  remedy. Closeout is BLOCKED. **Identity files (CREED/PERSONA/LORE/BOND) are a
  STOP-GATE**: a relocation that moves real identity content needs Will +
  Parzival approval of the proposed diff before `--apply` (do not auto-apply).

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

### 3. Re-Run Until Both Clean

Re-run the Step 1 (oversight) AND Step 1b (sanctum) `--check` commands. Repeat
fix → re-check until BOTH report PASS. Only when both gates are clean may you
advance to Step 5.

## CRITICAL STEP COMPLETION NOTE

ONLY when BOTH `--check` gates report PASS (all governed oversight AND sanctum
files within cap), load and read fully {nextStepFile}
