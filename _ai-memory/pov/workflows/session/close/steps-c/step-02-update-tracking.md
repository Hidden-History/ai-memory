---
name: 'step-02-update-tracking'
description: 'Update all tracking files with session outcomes, with user confirmation for status changes'
nextStepFile: './step-02b-update-plan.md'
---

# Step 2: Update Tracking Files

**Progress: Step 2 of 6** — Next: Update Active Plan

## STEP GOAL:

Update all tracking files to reflect the session's outcomes. Task status changes require user confirmation. Unlogged decisions and blockers are added to their respective logs.

**Scope:**
- Available context: Session summary from Step 1, tracking files at `{oversight_path}/tracking/`
- Focus: Tracking file updates only — do not create handoff document yet
- Limits: All task status changes require user confirmation before executing
- Dependencies: Session summary from Step 1 is required

- Focus on updating tracking files with confirmed status changes
**Behavioral Constraints:**
- FORBIDDEN to update task status without explicit user confirmation
- Approach: Present proposed changes, wait for confirmation, then execute
- Unlogged decisions and blockers must be added even if no task status changes occur

## Sequence

### 0. Pre-condition: Verify Handoff Template Exists (TD-520 / TD-500)

Before composing any tracking updates, confirm the handoff template exists at
its canonical location. The template is the binding site for the TD-500
empirical commits-ahead capture mandate; if it is missing, session-close MUST
NOT silently proceed down a fallback path that would produce a handoff lacking
the Branch State block.

Check: `_ai-memory/pov/templates/session-handoff.template.md` exists.

**If missing — HALT session-close** with the explicit error:

> Handoff template missing — cannot enforce TD-500 empirical commits-ahead
> capture. Restore template before continuing:
> `_ai-memory/pov/templates/session-handoff.template.md`.

Do NOT degrade to a fallback path. Do NOT auto-recover. Operator must restore
the template (e.g., `git checkout _ai-memory/pov/templates/session-handoff.template.md`
or re-run installer) before resuming session-close.

This is a defensive check — the failure has not been observed in current
builds, but template-bound enforcement is a future-self trap. The same check
fires again at step-03 entry as a belt-and-suspenders safeguard against
workflow refactors that bypass step-02.

---

### 1. Request Task Status Updates

For each task that was worked on, present the proposed update:

```
### Task Status Updates

| Task | Current Status | Proposed Status | Reason |
|------|---------------|-----------------|--------|
| [ID]: [Title] | [current] | [proposed] | [what happened] |

Approve these status updates? (y/n, or specify changes)
```

Wait for user confirmation. Only update `{oversight_path}/tracking/task-tracker.md` with approved changes.

---

### 2. Log Unlogged Decisions

For any decisions identified in Step 1 that were not yet logged:
- **Prepend** at the TOP of the `## Decisions` section (newest-first) of `{oversight_path}/tracking/decision-log.md` using the standard format — the seed contract and the `aim-tracking-rotate` skill both require newest-at-top; appending at the bottom would cause rotation to archive the newest decisions
- Include: date, context, options considered, decision, rationale

**Rotate at write**: after prepending, if `decision-log.md` is over its cap,
rotate the oldest entries out of the live file in this same close:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --apply {oversight_path}/tracking/decision-log.md \
  --oversight-root {oversight_path}
```

This archives the oldest contiguous block to a dated shard and updates the
`decision-log-INDEX.md` manifest in the same close — chronology preserved,
by-id lookup intact. (The Step 4 gate re-checks; rotating here keeps it green.)

---

### 3. Log Unlogged Blockers

`blockers-log.md` is a **register**: the live file holds **OPEN blockers only**,
plus a reconciliation banner (`{N} active as of PM #{X}`). It is not an
append-only diary of resolved items.

For blockers identified in Step 1:
- Append any newly-open blocker using the standard format (date, severity, affected task, description, resolution status)
- When a blocker was resolved this session, **MOVE** it out of the live file to the dated archive — do not leave resolved entries inline
- Update the reconciliation banner count to the number of blockers still open

**Fix at write**: if the live file is over cap after the update, use `--fix` to
archive the whole file verbatim and rewrite a lean index + pointer:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --fix {oversight_path}/tracking/blockers-log.md \
  --oversight-root {oversight_path}
```

---

### 4. Request Documentation Updates

Ask the user:

```
### Documentation Updates

Any of these needed?
- [ ] New decisions to add to the decision log? (beyond those just logged)
- [ ] New risks to add to the risk register?
- [ ] Updates to main project documentation?

Your input?
```

Wait for user response. Execute any requested documentation updates.

---

### 5. Reconcile the Bug / Tech-Debt INDEX

Run the tracking-freshness skill so the bug and tech-debt `INDEX.md` files are
reconciled against the current `bugs/*.md` and `tech-debt/*.md` records before
the session closes:

/aim-tracking-freshness --check

- Reports `INDEX files are fully in sync` → note it and proceed.
- Reports any divergence, missing-from-INDEX, orphan row, missing INDEX file, or
  skipped / no-status record → present the summary to the user; on confirmation
  run `/aim-tracking-freshness --write` to regenerate the INDEX files, then
  re-run `--check` to confirm sync.

This applies to `bugs/INDEX.md` + `tech-debt/INDEX.md` the same close-time
discipline already applied to `SESSION_WORK_INDEX.md`. Skipping it is the drift
root-caused in `oversight/tracking/RCA-tracking-system-drift-PM296.md` (RC-1).

---

### 6. Overwrite the project-status.md Heartbeat

`project-status.md` is the machine-routing heartbeat Parzival reads at every
session start. **This close step owns its write** — one datum, one home.
Overwrite it in place from the session's final state (do not append; do not
narrate). Keep it within its 60-line / 6-KB cap; the narrative belongs in the
handoff + `SESSION_WORK_INDEX.md`, never here.

Overwrite `{oversight_path}/project-status.md` from the heartbeat schema:

```yaml
current_phase: {discovery|architecture|planning|execution|integration|release|maintenance}
current_sprint: {n|null}
active_task: {path|null}
baseline_complete: {true|false}
phases_complete:
  discovery: {true|false}
  architecture: {true|false}
  planning_initialized: {true|false}
key_files:
  prd: {path|null}
  architecture: {path|null}
  project_context: {path|null}
live_record: oversight/SESSION_WORK_INDEX.md
last_session_summary: "{≤200 chars — date + PM# + what shipped/blocked/next}"
open_issues: {count}
```

The contract front-matter + field schema are the source of truth in the
`project-status.md` template seed (and `references/workflow-map-details.md`
§"project-status.md Schema") — mirror it exactly.

---

### 7. Verify Tracking State

After all updates, confirm:
- Task tracker reflects current reality
- Decision log includes all session decisions (rotated if over cap; manifest updated)
- Blockers log holds open items only + an accurate reconciliation banner
- Risk register is current (update if user requested)
- Bug/TD INDEX reconciled and in sync (per section 5)
- `project-status.md` heartbeat overwritten in place with the session's final state

## CRITICAL STEP COMPLETION NOTE

ONLY when all tracking files are updated and the user has confirmed status changes, load and read fully {nextStepFile}
