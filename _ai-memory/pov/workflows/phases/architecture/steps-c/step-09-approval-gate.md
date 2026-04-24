---
name: 'step-09-approval-gate'
description: 'Route to approval gate for architecture sign-off before Sprint Planning begins'
---

# Step 9: Approval Gate

**Final Step — Architecture Complete**

## STEP GOAL:

Route to {workflows_path}/cycles/approval-gate/workflow.md for architecture sign-off. On approval, update project status and route to WF-PLANNING. This is the terminal step.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Architecture approval summary from Step 8
- Focus: Approval gate invocation and routing to WF-PLANNING on approval
- Limits: Do not begin Planning work until approval is received. Approving locks the technical foundation.
- Dependencies: Step 8 complete — finalization done and approval summary prepared

- Focus on presenting the complete approval package and communicating the technical lock implications
**Behavioral Constraints:**
- FORBIDDEN to begin Planning work before receiving explicit user approval
- Approach: Present package, route through approval gate, handle result and transition cleanly
- Approving locks the technical foundation — this must be communicated clearly before the user decides

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Architecture Approval Package

**Phase:** Architecture
**Outputs:** architecture.md + epics + implementation readiness confirmed
**Status:** All documents reviewed and cohesion confirmed

**Architecture summary:** Stack, API, Auth, Hosting, Key pattern

**Implementation plan:** Epic count, story count, Must Have coverage, readiness check PASSED

**Key decisions locked in:** Top 5-7 decisions with brief rationale

**Known trade-offs:** Trade-offs the user should explicitly accept

**Next phase: Sprint Planning**
On approval, Parzival will activate the SM agent to initialize sprint planning from the approved epics.

**Important:** Approving this locks the technical foundation. Architecture changes after implementation begins require full impact assessment across all in-progress and completed stories.

---

### 2. Route to Approval Gate

Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- begin Sprint Planning
- **[R] Reject** -- changes needed
- **[H] Hold** -- need to review documents first

---

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md:
   - phases_complete.architecture: true
   - current_phase: planning
   - last_updated: [current date]
   - last_session_summary: "Architecture approved. Beginning Sprint Planning."

2. Update decisions.md with final architecture decisions

3. Confirm to user:
   "Architecture approved. Loading WF-PLANNING.
    Activating SM agent to initialize sprint."

4. Load: {workflows_path}/phases/planning/workflow.md
5. Load: {constraints_path}/planning/ constraints
6. Drop: {constraints_path}/architecture/ constraints

**IF REJECTED:**
- Return to step-05 for user review and iteration

**IF HELD:**
- Wait for user to complete review

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — Architecture phase complete on approval
- Update project-status.md: phases_complete.architecture: true, current_phase: planning
- Route to WF-PLANNING via {workflows_path}/phases/planning/workflow.md on approval
- Drop architecture constraints and load planning constraints on transition
