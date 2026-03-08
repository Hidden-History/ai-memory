---
name: 'step-07-approval-gate'
description: 'Route to approval gate for story sign-off, then advance to next story or milestone'
---

# Step 7: Approval Gate

## STEP GOAL
Route to {workflows_path}/cycles/approval-gate/workflow.md for story sign-off. On approval, advance to the next story or trigger milestone/integration check. This is the terminal step per story, but the execution workflow loops back to step-01 for each subsequent story.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Story completion summary, sprint-status.yaml, remaining stories
- Limits: Do not advance until user approves. Do not skip approval gate.

## MANDATORY SEQUENCE

### 1. Prepare Story Approval Package

**Story:** [Story ID] -- [Title]
**Sprint:** [N]
**Status:** Zero legitimate issues -- all criteria satisfied

**Completed:** Plain language description of what was built

**Review summary:** Passes, issues found, fixed, pre-existing fixed. All acceptance criteria satisfied.

**Notable fixes (if applicable):** Significant issues resolved

**Next step:**
- Remaining in sprint: [N] stories
- Next story: [Story ID] -- [Title]
- OR: Sprint milestone reached -- ready for Integration phase

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- proceed to next story
- **[R] Reject** -- feedback needed
- **[H] Hold** -- pause before next story

### 3. Handle Approval Result

**IF APPROVED -- Next Story:**
1. Update sprint-status.yaml: [Story ID] = complete, active_task = [Next Story ID]
2. Update project-status.md: active_task, open_issues, last_session_summary
3. Load next story -- return to step-01 with new story file

**IF APPROVED -- Milestone Hit:**
Milestone is hit when all stories for a feature set are complete, sprint is complete, or a defined checkpoint is reached.
1. Update sprint-status.yaml: sprint complete or milestone reached
2. Update project-status.md: current_phase = integration
3. Confirm to user: "Sprint milestone reached. Loading WF-INTEGRATION."
4. Load: {workflows_path}/phases/integration/workflow.md
5. Load: {constraints_path}/integration/ constraints
6. Drop: {constraints_path}/execution/ constraints

**IF REJECTED:**
1. Classify feedback per approval gate rejection protocol
2. Route:
   - Quality issue: re-enter review cycle (step-04)
   - Requirements mismatch: update instruction, re-enter step-02
   - Scope change: assess impact, update story if confirmed, re-execute
3. Confirm understanding before acting

**IF HELD:**
- Pause execution
- Wait for user to resume

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step per story. For next story: loop back to step-01. For milestone: route to WF-INTEGRATION.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Approval gate invoked with complete package
- Correct routing after approval (next story vs milestone)
- Sprint status updated accurately
- Rejection handled with appropriate routing

### FAILURE:
- Advancing to next story without approval
- Missing milestone trigger
- Not updating sprint-status.yaml
- Bypassing approval gate
