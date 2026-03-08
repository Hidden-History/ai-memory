---
name: 'step-02-update-tracking'
description: 'Update all tracking files with session outcomes, with user confirmation for status changes'
nextStepFile: './step-03-create-handoff.md'
---

# Step 2: Update Tracking Files

## STEP GOAL
Update all tracking files to reflect the session's outcomes. Task status changes require user confirmation. Unlogged decisions and blockers are added to their respective logs.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Session summary from Step 1, tracking files at `{oversight_path}/tracking/`
- Limits: All task status changes require user confirmation before executing

## MANDATORY SEQUENCE

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

### 2. Log Unlogged Decisions

For any decisions identified in Step 1 that were not yet logged:
- Append to `{oversight_path}/tracking/decision-log.md` using the standard format
- Include: date, context, options considered, decision, rationale

### 3. Log Unlogged Blockers

For any blockers identified in Step 1 that were not yet logged:
- Append to `{oversight_path}/tracking/blockers-log.md` using the standard format
- Include: date, severity, affected task, description, resolution status

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

### 5. Verify Tracking State

After all updates, confirm:
- Task tracker reflects current reality
- Decision log includes all session decisions
- Blockers log includes all session blockers
- Risk register is current (update if user requested)

## CRITICAL STEP COMPLETION NOTE
ONLY when all tracking files are updated and the user has confirmed status changes, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Task status changes are confirmed by the user before executing
- All unlogged decisions and blockers are added
- User is asked about documentation updates
- Tracking files accurately reflect the session outcome

### FAILURE:
- Updating task status without user confirmation
- Skipping unlogged decisions or blockers
- Not asking about documentation updates
- Leaving tracking files in an inconsistent state
