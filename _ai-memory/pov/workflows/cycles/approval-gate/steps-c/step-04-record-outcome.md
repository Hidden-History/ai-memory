---
name: 'step-04-record-outcome'
description: 'Record the approval outcome and phase-specific exit requirements verification'
---

# Step 4: Record the Outcome

**Final Step — Approval Gate Complete**

## STEP GOAL:

Regardless of the user's response, the outcome is recorded in the standard format. For phase-level approvals, verify phase-specific exit requirements are met before recording.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The user's response, the processing result from step-03, the approval type, phase-specific exit requirements
- Focus: Accurate recording and exit verification only — do not begin new workflows
- Limits: Record factually. This is the terminal step.
- Dependencies: Routing determination from step-03

- Record the outcome accurately and completely for all approval types
**Behavioral Constraints:**
- FORBIDDEN to skip exit requirement verification for phase-level approvals
- Approach: Factual, complete recording — no interpretation
- For phase approvals, all exit requirements must be verified before closing

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Record Approval Outcome

```
APPROVAL RECORD
Type:      [Task / Phase / Decision]
Item:      [task name, phase name, or decision topic]
Presented: [session marker]
Response:  [APPROVED / REJECTED / HOLD]
Feedback:  [user's feedback if rejected -- verbatim if possible]
Action:    [what Parzival did in response]
Routed to: [next workflow]
```

---

### 2. Verify Phase Exit Requirements (Phase Approvals Only)

For phase-level approvals, verify the specific exit requirements are met:

**Discovery -> Architecture:**
- PRD.md is approved as written
- Scope is correct -- features in, features out
- Success criteria are agreed upon
- Ready to proceed to architecture design

**Architecture -> Planning:**
- architecture.md is approved
- Tech stack decisions are accepted
- Epics are approved and correctly scoped
- Implementation readiness check passed
- Ready to begin sprint planning

**Planning -> Execution:**
- Sprint plan is approved
- Story priorities are correct
- Ready to begin implementation

**Execution -> Integration (Milestone):**
- All milestone tasks are complete and approved
- Ready to begin integration and full QA

**Integration -> Release:**
- Full test plan passed
- All modules integrate cleanly
- Zero open legitimate issues
- Ready to begin release process

**Release -> Maintenance:**
- Changelog is accurate and complete
- Rollback plan exists and is understood
- Release is approved to ship
- Maintenance mode acknowledged

---

### 3. Finalize

The approval record is complete. Route to the next workflow as determined in step-03.

---

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — approval gate workflow is complete
- Update tracking files with the recorded outcome
- Route to the next workflow as determined in step-03
- Mark the approval gate cycle as complete in project-status.md
