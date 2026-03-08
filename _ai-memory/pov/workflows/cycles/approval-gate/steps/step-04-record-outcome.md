---
name: 'step-04-record-outcome'
description: 'Record the approval outcome and phase-specific exit requirements verification'
---

# Step 4: Record the Outcome

## STEP GOAL
Regardless of the user's response, the outcome is recorded in the standard format. For phase-level approvals, verify phase-specific exit requirements are met before recording.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The user's response, the processing result from step-03, the approval type, phase-specific exit requirements
- Limits: Record factually. This is the terminal step.

## MANDATORY SEQUENCE

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

### 3. Finalize
The approval record is complete. Route to the next workflow as determined in step-03.

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step of the approval gate workflow. When the outcome is recorded and phase exit requirements are verified (if applicable), return to the routing determined in step-03.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Approval record is complete with all fields
- Phase exit requirements verified for phase-level approvals
- Routing matches the determination from step-03

### FAILURE:
- Incomplete approval record
- Phase approval recorded without verifying exit requirements
- Routing does not match step-03 determination
