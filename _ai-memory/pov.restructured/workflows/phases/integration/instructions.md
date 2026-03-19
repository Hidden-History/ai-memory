---
name: 'phases-integration-instructions'
description: 'Integration phase: establish scope, cross-story review, architect cohesion check, fix cycle, approve'
---

# phases-integration — Instructions

## Prerequisites

- All stories in the sprint have been completed through the execution phase
- Dev agent (`bmad-bmm-dev`) is available for full review and fix implementation
- Architect agent (`bmad-bmm-architect`) is available for cohesion review
- Feature branch is in a state ready for integration testing

## Workflow Overview

The integration phase verifies that all sprint stories work correctly together before the sprint's work is approved for release consideration. It establishes the integration scope, prepares a test plan, dispatches the Dev agent for a full cross-story review, and the Architect agent for architectural cohesion assessment.

Review findings are surfaced to Parzival and the user, a fix cycle is triggered for any issues, and a final verification confirms all integration criteria are met. The workflow exits through the approval gate confirming sprint integration is complete.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-establish-scope.md` | Define integration scope: which stories are being integrated and what cross-story interfaces exist |
| 2 | `step-02-prepare-test-plan.md` | Create the integration test plan covering cross-story interactions and regression concerns |
| 3 | `step-03-dev-full-review.md` | Dispatch Dev agent for a full code review across all sprint stories |
| 4 | `step-04-architect-cohesion.md` | Dispatch Architect agent to assess architectural cohesion of the integrated sprint |
| 5 | `step-05-review-findings.md` | Compile and triage findings from Dev and Architect reviews; present to user |
| 6 | `step-06-fix-cycle.md` | Dispatch Dev agent to implement fixes for all required findings |
| 7 | `step-07-final-verification.md` | Verify all fixes are in place and integration criteria are met |
| 8 | `step-08-approval-gate.md` | Run approval-gate cycle; confirm sprint integration is complete and ready for release |

## Key Decisions

- **Finding triage**: Not all findings require fixing before approval — Parzival and user triage which are blocking vs. deferred
- **Fix loop**: Steps 6–7 may repeat if verification finds remaining issues
- **Scope boundary**: Integration only covers the current sprint's stories; it does not re-test prior sprints

## Outputs

- Integration test plan
- Consolidated review findings from Dev and Architect agents
- All blocking findings resolved
- Sprint integration approved and logged in tracking

## Exit Conditions

The workflow exits when:
- All blocking findings have been resolved
- Final verification has passed
- Sprint integration has been approved through the approval gate
