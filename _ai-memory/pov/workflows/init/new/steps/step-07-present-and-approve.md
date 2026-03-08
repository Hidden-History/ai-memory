---
name: 'step-07-present-and-approve'
description: 'Present the verified baseline to the user and route to approval gate for sign-off before Discovery'
---

# Step 7: Present and Approve

## STEP GOAL
Present the complete project baseline to the user via {workflows_path}/cycles/approval-gate/workflow.md. On approval, update project status and route to WF-DISCOVERY. This is the terminal step of the init-new workflow.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All verified baseline files, complete project foundation summary
- Limits: Do not begin Discovery work until approval is received. Do not skip the approval gate.

## MANDATORY SEQUENCE

### 1. Prepare Approval Package
Build the approval package with the following information:

**Project:** [name]
**Track:** [Quick Flow / Standard Method / Enterprise]
**Status:** Baseline established -- ready to begin Discovery

**Completed items:**
- _ai-memory/ installation verified
- Project baseline files created:
  - project-status.md (project tracking)
  - goals.md (project goals and constraints)
  - project-context.md (stub -- populated in Architecture)
  - decisions.md (decision log -- initialized)
- Claude Code teams session structure established

**Project foundation:**
- Goal: [primary goal]
- Type: [project type]
- Stack: [confirmed decisions / TBD items]
- Constraints: [list or 'none stated']

**Open items for Discovery:**
[List of anything deferred -- to be resolved in Discovery]
[Or: 'None -- all foundation information confirmed']

**Next step on approval:**
Begin WF-DISCOVERY. First action: Activate Analyst for requirements research, then PM for PRD creation. Deliverable: PRD.md -- approved product requirements document.

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md with the prepared package.

Options presented to user:
- **[A] Approve** -- begin Discovery
- **[R] Reject** -- corrections needed
- **[H] Hold** -- user needs to add something first

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md:
   - baseline_complete: true
   - current_phase: discovery
   - last_updated: [current date]
   - last_session_summary: "Baseline established. Beginning Discovery."

2. Confirm to user:
   "Foundation approved. Loading WF-DISCOVERY.
    Activating Analyst agent to begin requirements research."

3. Load: {workflows_path}/phases/discovery/workflow.md
4. Load: {constraints_path}/discovery/ constraints
5. Drop: {constraints_path}/init/ constraints

**IF REJECTED:**
- Receive specific corrections from user
- Return to the appropriate prior step to address corrections
- Re-verify (Step 6) after corrections
- Re-present for approval

**IF HELD:**
- Wait for user to provide additional input
- Incorporate input into baseline files
- Re-verify (Step 6) after changes
- Re-present for approval

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step. When approval is received, route to WF-DISCOVERY. Do not load another step file from this workflow.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Complete approval package presented with all required sections
- Approval gate was invoked (not bypassed)
- User explicitly approved before any Discovery work began
- Project status updated accurately on approval
- Clean handoff to WF-DISCOVERY

### FAILURE:
- Beginning Discovery without explicit user approval
- Bypassing the approval gate
- Not updating project-status.md on approval
- Presenting an incomplete approval package
