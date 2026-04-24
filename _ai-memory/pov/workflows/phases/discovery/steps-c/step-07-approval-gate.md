---
name: 'step-07-approval-gate'
description: 'Route to approval gate for explicit PRD sign-off before Architecture phase begins'
---

# Step 7: Approval Gate

**Final Step — Discovery Complete**

## STEP GOAL:

Route to {workflows_path}/cycles/approval-gate/workflow.md for explicit PRD sign-off. On approval, update project status and route to WF-ARCHITECTURE. This is the terminal step.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Finalized PRD.md, scope summary, key decisions summary
- Focus: Approval gate execution and phase transition to Architecture
- Limits: Do not begin Architecture work until approval is received. Signing off locks scope.
- Dependencies: Complete approval package from Step 6 finalization

- Focus on presenting complete approval package and routing through approval gate
**Behavioral Constraints:**
- FORBIDDEN to begin Architecture work before explicit user approval
- Present scope lock implications clearly before user approves
- All three approval outcomes (Approve/Reject/Hold) must be handled explicitly

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Route to Approval Gate

Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- begin Architecture phase
- **[R] Reject** -- more changes needed
- **[H] Hold** -- need more time to review

---

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

## TERMINATION STEP PROTOCOLS:

- This is the TERMINAL step of the Discovery phase — no nextStepFile exists in this workflow
- On APPROVED: Update project-status.md (phases_complete.discovery: true, current_phase: architecture), update decisions.md with key PRD decisions, load WF-ARCHITECTURE, load architecture constraints, drop discovery constraints
- On REJECTED: Return to step-05-user-review-iteration.md — do not proceed to Architecture
- On HELD: Pause workflow completely — wait for user to resume the approval process; do not load any next step
