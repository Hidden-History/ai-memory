---
name: 'step-02-update-tracking'
description: 'Update all tracking files with session outcomes, with user confirmation for status changes'
nextStepFile: './step-03-create-handoff.md'
---

# Step 2: Update Tracking Files

**Progress: Step 2 of 4** — Next: Create Handoff Document

## STEP GOAL:

Update all tracking files to reflect the session's outcomes. Task status changes require user confirmation. Unlogged decisions and blockers are added to their respective logs.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

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

## Sequence of Instructions (Do not deviate, skip, or optimize)

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
- Append to `{oversight_path}/tracking/decision-log.md` using the standard format
- Include: date, context, options considered, decision, rationale

---

### 3. Log Unlogged Blockers

For any blockers identified in Step 1 that were not yet logged:
- Append to `{oversight_path}/tracking/blockers-log.md` using the standard format
- Include: date, severity, affected task, description, resolution status

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

### 5. Verify Tracking State

After all updates, confirm:
- Task tracker reflects current reality
- Decision log includes all session decisions
- Blockers log includes all session blockers
- Risk register is current (update if user requested)

## CRITICAL STEP COMPLETION NOTE

ONLY when all tracking files are updated and the user has confirmed status changes, load and read fully {nextStepFile}
