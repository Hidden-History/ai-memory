---
name: 'step-02-write-handoff'
description: 'Write the handoff document to the session logs directory'
nextStepFile: './step-03-update-index.md'
handoffTemplate: '{project-root}/_ai-memory/pov/templates/session-handoff.template.md'
---

# Step 2: Write Handoff Document

## STEP GOAL
Write the captured state to a handoff file in the session logs directory using the standard handoff format.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All state captured in Step 1
- Limits: Write the handoff file -- do not update tracking files (that is the next step or the closeout workflow's job)

## MANDATORY SEQUENCE

### 1. Load Template (If Available)

If `{handoffTemplate}` exists, use it as the format guide. Otherwise, use the format below.

### 2. Write Handoff File

Create file: `{oversight_path}/session-logs/SESSION_HANDOFF_{date}.md`

Where `{date}` is today's date in YYYY-MM-DD format.

If a handoff file for today already exists, append a time suffix: `SESSION_HANDOFF_{date}_{time}.md`

Use this format:

```markdown
# Session Snapshot

**Date**: [YYYY-MM-DD]
**Time**: [HH:MM or approximate]
**Reason**: [Why this snapshot was created]
**Session Status**: In Progress

---

## Current State

### Active Work
- **Task**: [ID] [Title]
- **Status**: [What has been done so far]
- **Currently doing**: [What is in progress right now]
- **Next step**: [Immediate next action]

### Context That Would Be Lost
[Information from this conversation that future Parzival needs]
- [Important context point 1]
- [Important context point 2]
- [Decisions made in this session]
- [Approaches tried and results]

### Files Being Modified
- `[path]` - [What is being changed and current state]

### Assumptions Currently Active
- [Assumption 1] - [Status: Verified/Unverified]
- [Assumption 2] - [Status: Verified/Unverified]

### Things That Almost Went Wrong
[Near-misses or gotchas discovered this session]

### Open Questions
- [Question that came up but was not resolved]

---

## Recovery Instructions

If this snapshot is being read to recover session state:

1. Current task is [ID]: [Title]
2. We were in the middle of [specific activity]
3. The approach being used is [description]
4. Key files are [list]
5. Next action should be [specific next step]

## What's Working
[Things confirmed working as of this snapshot]

## What's Not Working
[Known issues at this point]

---

*Snapshot created during active session. Session continues.*
```

### 3. Verify Write

Confirm the file was written by reading it back. Verify:
- All captured state is included
- No sections are empty
- Recovery instructions are actionable

## CRITICAL STEP COMPLETION NOTE
ONLY when the handoff file is written and verified, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Handoff file is created at the correct path
- All state from Step 1 is present in the file
- Format follows the template
- File is verified after writing

### FAILURE:
- Writing to the wrong path
- Omitting captured state
- Leaving empty sections
- Not verifying the written file
