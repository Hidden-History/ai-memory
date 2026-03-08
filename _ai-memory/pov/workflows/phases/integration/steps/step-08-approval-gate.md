---
name: 'step-08-approval-gate'
description: 'Route to approval gate for integration sign-off before Release phase begins'
---

# Step 8: Approval Gate

## STEP GOAL
Route to {workflows_path}/cycles/approval-gate/workflow.md for integration sign-off. On approval, route to WF-RELEASE. This is the terminal step.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Final verification results, integration summary
- Limits: Do not begin Release until approval. Integration approval confirms production-readiness.

## MANDATORY SEQUENCE

### 1. Prepare Integration Approval Package

**Milestone:** [name]
**Sprint(s):** [N]
**Status:** Full test plan passed -- cohesion confirmed -- zero issues

**Integration summary:** Features integrated, stories in scope, test plan results, architecture cohesion status

**Review summary:** DEV issues found and resolved, Architect issues found and resolved, pre-existing issues fixed, fix passes required, final status

**Notable findings:** Significant issues resolved, architecture improvements, pre-existing issues addressed

**Next step: Release Phase**
On approval, begin release process. Deliverables: changelog + rollback plan + deployment sign-off.

**Important:** Integration approval confirms this milestone is production-ready from a technical standpoint.

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- begin Release phase
- **[R] Reject** -- additional review or changes needed
- **[H] Hold** -- need to review or test something first

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md:
   - current_phase: release
   - last_session_summary: "Integration milestone [name] approved. Beginning release."
2. Update sprint-status.yaml: milestone INTEGRATION PASSED
3. Confirm: "Integration approved. Loading WF-RELEASE."
4. Load: {workflows_path}/phases/release/workflow.md
5. Load: {constraints_path}/release/ constraints
6. Drop: {constraints_path}/integration/ constraints

**IF REJECTED:**
- If story-level rework needed: return affected stories to WF-EXECUTION, then re-run full integration
- If scope gaps: create new stories, execute, then return to integration

**IF HELD:** Wait for user.

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step. When approval is received, route to WF-RELEASE.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Approval gate invoked with complete package
- Production-readiness implications communicated
- Correct routing on approval
- Rejection handled with appropriate re-entry

### FAILURE:
- Starting release without approval
- Not communicating production-readiness implications
- Partial re-integration after rejection (must be full)
