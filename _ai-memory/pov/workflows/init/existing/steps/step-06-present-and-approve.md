---
name: 'step-06-present-and-approve'
description: 'Present the complete onboarding audit to the user and route to approval gate for sign-off'
---

# Step 6: Present and Approve

## STEP GOAL
Present the complete project audit results to the user via {workflows_path}/cycles/approval-gate/workflow.md. On approval, update project status and route to the correct phase workflow. This is the terminal step of the init-existing workflow.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All verified findings, updated baseline files, confirmed exit route
- Limits: Do not begin any phase work until approval is received. Do not skip the approval gate.

## MANDATORY SEQUENCE

### 1. Prepare Onboarding Approval Package
Build the approval package with:

**Project:** [name]
**Branch:** [A: Active Mid-Sprint / B: Legacy / C: Restarting / D: Handoff]
**Status:** Project state understood -- ready to confirm and proceed

**Project state:**
- Current phase: [phase]
- Active task: [task name or 'None']
- Sprint status: [summary or 'N/A']
- Overall health: [Green / Yellow / Red -- from Analyst assessment]

**Key findings:**
[3-7 most important findings from the audit -- specific, not vague]

**Issues identified:**
[Legitimate issues found during audit]
[Or: 'No legitimate issues found during audit']

**Baseline files status:**
- project-status.md: [Updated / Created]
- goals.md: [Updated / Created / Pre-existing confirmed]
- project-context.md: [Updated / Created / Stub]
- decisions.md: [Updated / Created]

**Open questions (if any):**
[Unresolved questions needing user input]
[Or: 'None -- all gaps resolved during audit']

**Recommended next step:**
- Route to: [workflow name]
- Reason: [why this is the correct next workflow]
- First action: [what Parzival will do immediately after approval]

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md with the prepared package.

Options:
- **[A] Approve** -- proceed as recommended
- **[R] Reject** -- corrections or different direction needed
- **[H] Hold** -- user needs to review something first

### 3. Handle Approval Result

**IF APPROVED:**
Route based on confirmed branch and project state:

- Branch A (Active Mid-Sprint): Load WF-EXECUTION + execution constraints
- Branch B (Legacy -- no PRD): Load WF-DISCOVERY + discovery constraints
- Branch B (Legacy -- PRD exists, no architecture): Load WF-ARCHITECTURE + architecture constraints
- Branch B (Legacy -- both exist): Load WF-PLANNING + planning constraints
- Branch C (Paused -- sprint valid): Load WF-EXECUTION + execution constraints
- Branch C (Paused -- sprint needs reassessment): Load WF-PLANNING + planning constraints
- Branch D (Handoff): Load appropriate phase workflow based on confirmed state

For ALL exits:
1. Update project-status.md with confirmed current state
2. Confirm route to user before loading next workflow
3. Drop {constraints_path}/init/ constraints
4. Load new phase constraint files

**IF REJECTED:**
- Receive specific corrections
- Return to appropriate step to address
- Re-verify and re-present

**IF HELD:**
- Wait for user input
- Address any additional items
- Re-verify and re-present

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step. When approval is received, route to the correct phase workflow. Do not load another step file from this workflow.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Complete approval package presented with all sections
- Approval gate was invoked (not bypassed)
- Correct phase workflow loaded based on audit findings
- Project status updated accurately on approval
- Clean handoff to the correct phase

### FAILURE:
- Beginning phase work without explicit user approval
- Routing to the wrong phase workflow
- Not updating project-status.md on approval
- Bypassing the approval gate
