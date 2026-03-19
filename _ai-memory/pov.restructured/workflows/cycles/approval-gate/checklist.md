---
name: 'cycles-approval-gate-checklist'
description: 'Quality gate rubric for cycles-approval-gate'
---

# Cycles Approval Gate — Validation Checklist

## Pre-Execution Checks

- [ ] Work requiring user approval is ready for presentation
- [ ] Approval type (task, phase milestone, or decision) is identified

## Step Completion Checks

### Step 1: Prepare Package (step-01-prepare-package)
- [ ] Package contains all five sections
- [ ] Written in Parzival's own words
- [ ] Quality check passes all items
- [ ] Appropriate format identified for the approval type
- [ ] Next step loaded only after quality check passes

### Step 2: Present to User (step-02-present-to-user)
- [ ] Correct format used for the approval type
- [ ] One approval presented at a time
- [ ] User provided explicit response before proceeding
- [ ] Pushback handled gracefully while maintaining the gate

### Step 3: Process Response (step-03-process-response)
- [ ] User response correctly identified and classified
- [ ] Reject feedback fully understood and confirmed before acting
- [ ] project-status.md updated after every response
- [ ] Hold acknowledged immediately with clear instructions for resuming
- [ ] Pending approvals flagged for re-presentation at next session start

### Step 4: Record Outcome (step-04-record-outcome)
- [ ] Approval record is complete with all fields
- [ ] Phase exit requirements verified for phase-level approvals
- [ ] Routing matches the determination from step-03
- [ ] project-status.md updated with workflow completion

## Workflow-Level Checks

- [ ] User gave explicit response (not silence)
- [ ] Outcome recorded in project-status.md
- [ ] Routing to next workflow matches user's decision
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT copy agent output instead of writing a summary
- [ ] Did NOT present with missing package sections
- [ ] Did NOT include unverified claims
- [ ] Did NOT proceed to step-02 without a complete, verified package
- [ ] Did NOT stack multiple decisions in one presentation
- [ ] Did NOT use wrong format for the approval type
- [ ] Did NOT proceed without explicit user response
- [ ] Did NOT interpret silence as approval
- [ ] Did NOT skip the gate entirely
- [ ] Did NOT assume understanding of rejection feedback without confirming
- [ ] Did NOT fail to update project-status.md
- [ ] Did NOT start work while approval is pending
- [ ] Did NOT interpret ambiguous response as approval
- [ ] Did NOT fail to re-present pending approvals at session start
- [ ] Did NOT record an incomplete approval record
- [ ] Did NOT record phase approval without verifying exit requirements
- [ ] Did NOT route incorrectly after processing the response

_Validated by: Parzival Quality Gate on {date}_
