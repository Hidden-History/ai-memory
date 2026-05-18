---
name: 'step-08-shutdown-teammate'
description: 'Gracefully shut down the teammate when the task is fully complete and output is accepted'
nextStepFile: './step-09-prepare-summary.md'
---

# Step 8: Shut Down Teammate

**Progress: Step 8 of 9** — Next: Prepare User Summary

## STEP GOAL:

When an agent's task is fully complete and output is accepted, gracefully shut down the teammate using SendMessage with type "shutdown_request". Clean up all active agent sessions appropriately.

**Scope:**
- Available context: The accepted output, the active teammate, the session state
- Focus: Teammate lifecycle management only — do not begin dispatch summary
- Limits: Only shut down teammates whose tasks are fully complete. Never shut down a teammate mid-task.
- Dependencies: Accepted output from step-07 and task_id for dispatch log update

- Focus on clean teammate lifecycle — shut down or confirm keep-active decision for each teammate
**Behavioral Constraints:**
- FORBIDDEN to shut down a teammate while a task is still in progress
- Approach: Verify task completion status before any shutdown action
- No orphaned teammates — all teammates must be explicitly handled at session end

## Sequence

### 1. Determine Shutdown or Keep Active

**Shut down teammate when:**
- Agent task is fully complete and accepted
- Agent is no longer needed for current phase
- Session is ending

**Keep teammate active when:**
- Agent is waiting for Parzival's review decision within the SAME task (step-06/step-07 loop)

MUST shutdown and spawn fresh for: new tasks, role changes, fix dispatches after review, re-review passes. Never reuse an agent across tasks or roles (GC-21).

---

### 2. Send Shutdown Request

When shutting down:
- Use SendMessage with type: "shutdown_request" to gracefully shut down the teammate
- Wait for confirmation that shutdown completed cleanly
- Verify no pending work remains with the teammate

---

### 3. Lifecycle Rules

**NEVER:**
- Leave a teammate active with a pending failed task
- Run a new task with a teammate that has unresolved prior output
- Shut down a teammate while a task is still in progress
- Leave teammates active when the session is ending

---

### 4. Clean Up

- Verify the teammate has been shut down
- Update the dispatch log with final status
- Confirm no orphaned teammates remain

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the teammate is appropriately handled (shut down or confirmed to remain active for upcoming work), load and read fully {nextStepFile}
