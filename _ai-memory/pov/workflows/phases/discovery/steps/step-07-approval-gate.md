---
name: 'step-07-approval-gate'
description: 'Route to approval gate for explicit PRD sign-off before Architecture phase begins'
---

# Step 7: Approval Gate

## STEP GOAL
Route to {workflows_path}/cycles/approval-gate/workflow.md for explicit PRD sign-off. On approval, update project status and route to WF-ARCHITECTURE. This is the terminal step.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Finalized PRD.md, scope summary, key decisions summary
- Limits: Do not begin Architecture work until approval is received. Signing off locks scope.

## MANDATORY SEQUENCE

### 1. Prepare Discovery Approval Package

**Phase:** Discovery
**Output:** PRD.md
**Status:** PRD complete and reviewed -- ready for sign-off

**Scope summary:**
- Must Have features: [count and brief list]
- Should Have: [count and brief list]
- Nice to Have: [count and brief list]
- Explicitly out of scope: [key exclusions]

**Key decisions locked in:**
[What signing off commits to -- scope, priorities, success metrics]

**Open questions:**
[Any remaining or 'None -- all questions resolved']

**Next phase: Architecture**
On approval, Parzival will activate the Architect agent to design the technical architecture based on this PRD. Deliverable: architecture.md.

**Important:** Signing off on this PRD locks in scope. Changes after this point require a formal scope change that will be assessed for impact on architecture and timeline.

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- begin Architecture phase
- **[R] Reject** -- more changes needed
- **[H] Hold** -- need more time to review

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md:
   - phases_complete.discovery: true
   - current_phase: architecture
   - last_updated: [current date]
   - last_session_summary: "PRD approved. Beginning Architecture phase."

2. Update decisions.md with key PRD decisions

3. Confirm to user:
   "PRD approved. Loading WF-ARCHITECTURE.
    Activating Architect agent to design technical architecture."

4. Load: {workflows_path}/phases/architecture/workflow.md
5. Load: {constraints_path}/architecture/ constraints
6. Drop: {constraints_path}/discovery/ constraints

**IF REJECTED:**
- Return to step-05 for additional user review and iteration

**IF HELD:**
- Wait for user to complete review
- Resume approval process when ready

## SCOPE CHANGE PROTOCOL (POST-APPROVAL)

If the user requests a scope change after PRD approval, follow this protocol:

1. **Capture the change request** — document exactly what is being requested
2. **Impact assessment** — evaluate how the change affects:
   - Existing PRD requirements (additions, modifications, removals)
   - Architecture decisions already made (if in Architecture phase)
   - Stories already written or in progress (if in Planning/Execution)
   - Timeline and sprint scope
3. **Classify the change**:
   - **Minor**: Does not affect architecture or existing stories -> update PRD, note the change
   - **Moderate**: Affects architecture or multiple stories -> requires Architect review and re-assessment
   - **Major**: Fundamentally changes project direction -> requires full re-planning from affected phase
4. **Present assessment to user** with recommendation and tradeoffs
5. **Get explicit user approval** before implementing any scope change

This protocol applies even after PRD sign-off. Scope changes are allowed but must be assessed, not silently absorbed.

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step. When approval is received, route to WF-ARCHITECTURE. Do not load another step file from this workflow.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Approval gate invoked with complete package
- Scope implications clearly communicated
- User explicitly approved before Architecture work began
- Project status updated accurately
- Clean handoff to WF-ARCHITECTURE

### FAILURE:
- Beginning Architecture without explicit approval
- Not communicating scope lock implications
- Bypassing the approval gate
- Not updating project-status.md
