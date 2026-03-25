---
name: 'session-handoff-checklist'
description: 'Quality gate rubric for session-handoff'
---

# Session Handoff — Validation Checklist

## Pre-Execution Checks

- [ ] Session is ongoing (not being closed — use session/close for closeout)
- [ ] A state snapshot is needed mid-session

## Step Completion Checks

### Step 1: Capture State (step-01-capture-state)
- [ ] All state categories are captured with specific detail
- [ ] "Context that would be lost" section is substantive (not empty or vague)
- [ ] Recovery instructions are specific enough for a cold start
- [ ] File state is accurate and complete

### Step 2: Write Handoff (step-02-write-handoff)
- [ ] Handoff file is created at the correct path
- [ ] All state from Step 1 is present in the file
- [ ] Format follows the template
- [ ] File is verified after writing

### Step 3: Update Index (step-03-update-index)
- [ ] SESSION_WORK_INDEX is updated with a reference to the snapshot
- [ ] User is informed of the snapshot location
- [ ] Session continues normally after the snapshot

## Workflow-Level Checks

- [ ] Handoff file exists at the correct path
- [ ] SESSION_WORK_INDEX references the new handoff
- [ ] Session was not treated as ended
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT write to the wrong path
- [ ] Did NOT omit captured state from the file
- [ ] Did NOT leave empty sections
- [ ] Did NOT use vague descriptions ("working on stuff")
- [ ] Did NOT leave "context that would be lost" section empty or minimal
- [ ] Did NOT write recovery instructions that require existing conversation context
- [ ] Did NOT fail to verify the written file
- [ ] Did NOT omit file state information
- [ ] Did NOT skip updating SESSION_WORK_INDEX
- [ ] Did NOT treat this as a session end
- [ ] Did NOT run closeout procedures after a snapshot
- [ ] Did NOT fail to confirm the snapshot to the user

_Validated by: Parzival Quality Gate on {date}_
