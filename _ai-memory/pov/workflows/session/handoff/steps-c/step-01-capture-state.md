---
name: 'step-01-capture-state'
description: 'Capture the current session state including active work, context, and open questions'
nextStepFile: './step-02-write-handoff.md'
---

# Step 1: Capture Current State

**Progress: Step 1 of 3** — Next: Write Handoff Document

## STEP GOAL:

Capture a complete snapshot of the current session state: what is done, what is in progress, what is blocked, and what context would be lost if the session ended.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Current conversation context, task tracker at `{oversight_path}/tracking/task-tracker.md`, files being modified
- Focus: State capture and documentation only — do not write the handoff file yet
- Limits: Do not query Qdrant, do not activate agents, do not modify any project files — read-only state capture
- Dependencies: None — this is the first step of the session-handoff workflow

- Focus only on capturing session state — do not write the handoff file yet
**Behavioral Constraints:**
- FORBIDDEN to skip any state category or provide vague descriptions
- Approach: Systematic state capture with specific, verifiable detail
- "Context that would be lost" section must be substantive — this is the most critical capture

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Capture Active Work State

Document:
- **Current task**: ID, title, status
- **What has been completed** this session: specific items with evidence
- **What is currently in progress**: exactly what is being worked on right now
- **What is the immediate next step**: the very next action to take

---

### 2. Capture Context That Would Be Lost

This is the most critical section. Document anything from this conversation that a future Parzival instance would need but would not know from files alone:
- Decisions made during this session (that are not yet logged)
- Approaches tried and their results
- Assumptions currently active (and whether verified or unverified)
- Things that almost went wrong (near-misses, gotchas)
- Understanding gained about the codebase or problem space

---

### 3. Capture File State

List every file that:
- Was modified during this session (and what changed)
- Is currently being modified (and what the current state is)
- Is planned for modification (but not yet touched)

---

### 4. Capture Open Questions

Document:
- Unresolved questions that came up during the session
- Items that need user input but have not been addressed
- Uncertainties about the approach being taken

---

### 5. Capture Recovery Instructions

Write specific instructions for resuming work:
1. What task to resume
2. What was being done when the snapshot was taken
3. What approach is being used
4. What key files to examine
5. What the next action should be

---

### 6. Capture Working/Not Working State

- **What is working**: Items confirmed working as of this snapshot
- **What is not working**: Known issues at this point

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all state categories have been captured, will you then read fully and follow: `{nextStepFile}` to begin writing the handoff document.
