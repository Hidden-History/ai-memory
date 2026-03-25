---
name: 'step-02-update-tracking'
description: 'Update all tracking files with session outcomes, with user confirmation for status changes'
nextStepFile: './step-03-create-handoff.md'
---

# Step 2: Update Tracking Files

**Progress: Step 2 of 4** — Next: Create Handoff Document

## STEP GOAL:

Update all tracking files to reflect the session's outcomes. Task status changes require user confirmation. Unlogged decisions and blockers are added to their respective logs.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on updating tracking files with confirmed status changes
- 🚫 FORBIDDEN to update task status without explicit user confirmation
- 💬 Approach: Present proposed changes, wait for confirmation, then execute
- 📋 Unlogged decisions and blockers must be added even if no task status changes occur

## EXECUTION PROTOCOLS:

- 🎯 Present task status update table and wait for user confirmation before executing
- 💾 Record all approved changes to tracking files immediately after confirmation
- 📖 Load next step only after all tracking files are updated and user has confirmed
- 🚫 FORBIDDEN to modify any tracking file without user approval

## CONTEXT BOUNDARIES:

- Available context: Session summary from Step 1, tracking files at `{oversight_path}/tracking/`
- Focus: Tracking file updates only — do not create handoff document yet
- Limits: All task status changes require user confirmation before executing
- Dependencies: Session summary from Step 1 is required

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Task status changes are confirmed by the user before executing
- All unlogged decisions and blockers are added
- User is asked about documentation updates
- Tracking files accurately reflect the session outcome

### ❌ SYSTEM FAILURE:

- Updating task status without user confirmation
- Skipping unlogged decisions or blockers
- Not asking about documentation updates
- Leaving tracking files in an inconsistent state

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
