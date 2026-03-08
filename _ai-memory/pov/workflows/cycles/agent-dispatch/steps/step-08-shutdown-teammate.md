---
name: 'step-08-shutdown-teammate'
description: 'Gracefully shut down the teammate when the task is fully complete and output is accepted'
nextStepFile: './step-09-prepare-summary.md'
---

# Step 8: Shut Down Teammate

## STEP GOAL
When an agent's task is fully complete and output is accepted, gracefully shut down the teammate using SendMessage with type "shutdown_request". Clean up all active agent sessions appropriately.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The accepted output, the active teammate, the session state
- Limits: Only shut down teammates whose tasks are fully complete. Never shut down a teammate mid-task.

## MANDATORY SEQUENCE

### 1. Determine Shutdown or Keep Active

**Shut down teammate when:**
- Agent task is fully complete and accepted
- Agent is no longer needed for current phase
- Session is ending

**Keep teammate active when:**
- Agent will be needed again within the same session
- Agent is in a review-fix loop and will be called back

### 2. Send Shutdown Request
When shutting down:
- Use SendMessage with type: "shutdown_request" to gracefully shut down the teammate
- Wait for confirmation that shutdown completed cleanly
- Verify no pending work remains with the teammate

### 3. Lifecycle Rules
**NEVER:**
- Leave a teammate active with a pending failed task
- Run a new task with a teammate that has unresolved prior output
- Shut down a teammate while a task is still in progress
- Leave teammates active when the session is ending

### 4. Clean Up
- Verify the teammate has been shut down
- Update the dispatch log with final status
- Confirm no orphaned teammates remain

## CRITICAL STEP COMPLETION NOTE
ONLY when the teammate is appropriately handled (shut down or confirmed to remain active for upcoming work), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Teammate shut down gracefully after task completion
- No pending work left with the teammate
- Dispatch log updated
- No orphaned teammates

### FAILURE:
- Shutting down teammate mid-task
- Leaving teammate active with pending failed task
- Not cleaning up teammates at session end
- Running new tasks with unresolved prior output
