---
name: 'step-07-approval-gate'
description: 'Route to approval gate for sprint plan sign-off before Execution begins'
---

# Step 7: Approval Gate

## STEP GOAL
Route to {workflows_path}/cycles/approval-gate/workflow.md for sprint plan sign-off. On approval, update project status and route to WF-EXECUTION. This is the terminal step.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Approved sprint plan, all story files
- Limits: Do not begin execution until approval is received.

## MANDATORY SEQUENCE

### 1. Prepare Sprint Approval Package

**Sprint:** [N]
**Stories:** [count] stories ready for implementation
**Status:** All story files reviewed and implementation-ready

**Sprint scope:** Story list in execution order

**Key dependencies:** Cross-story dependencies or 'Stories are independent'

**First story:** On approval, begin [Story 1 ID and title]. DEV agent will be activated with the story file as instruction.

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- begin implementation
- **[R] Reject** -- changes needed
- **[H] Hold** -- need to review story files first

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md:
   - phases_complete.planning_initialized: true (first sprint)
   - current_phase: execution
   - current_sprint: [N]
   - active_task: [Story 1 ID and file path]
   - last_updated: [current date]
   - last_session_summary: "Sprint [N] approved. Beginning Story [1]."

2. Confirm to user:
   "Sprint [N] approved. Loading WF-EXECUTION.
    Starting Story [1]: [title]"

3. Load: {workflows_path}/phases/execution/workflow.md
4. Load: {constraints_path}/execution/ constraints
5. Drop: {constraints_path}/planning/ constraints
6. Begin WF-EXECUTION with Story 1

**IF REJECTED:** Return to step-06 for changes.
**IF HELD:** Wait for user review.

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step. When approval is received, route to WF-EXECUTION.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Approval gate invoked with complete package
- First story clearly identified
- User explicitly approved before execution began
- Project status updated
- Clean handoff to WF-EXECUTION

### FAILURE:
- Starting execution without approval
- Not identifying first story
- Bypassing approval gate
