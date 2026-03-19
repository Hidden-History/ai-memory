---
name: 'phases-execution-instructions'
description: 'Execution phase: verify story requirements, dispatch dev, run review cycle, approve completed task'
---

# phases-execution — Instructions

## Prerequisites

- An approved sprint plan with story files from the planning phase
- Dev agent (`bmad-bmm-dev`) is available for dispatching
- The story to be executed has acceptance criteria defined in its story file

## Workflow Overview

The execution phase drives the implementation of a single story from the active sprint. Parzival verifies story requirements are complete and unambiguous before dispatching the Dev agent with a precise implementation instruction. The agent implements the story, Parzival triggers a review cycle, and any required fixes are verified before the story is summarized and presented for approval.

This workflow is run once per story. The pattern repeats for each story in the sprint until all stories are completed and the sprint is ready for integration.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-verify-story-requirements.md` | Confirm the story file is complete, acceptance criteria are unambiguous, and no blocking dependencies exist |
| 2 | `step-02-prepare-instruction.md` | Compose the implementation instruction for the Dev agent |
| 3 | `step-03-activate-dev.md` | Dispatch Dev agent via the agent-dispatch cycle with the prepared instruction |
| 4 | `step-04-review-cycle.md` | Trigger review-cycle on the Dev agent's output; surface findings |
| 5 | `step-05-verify-fixes.md` | Verify that all review findings have been addressed |
| 6 | `step-06-prepare-summary.md` | Compile story completion summary including changes made, tests status, and any deferred items |
| 7 | `step-07-approval-gate.md` | Run approval-gate cycle; confirm story is complete and ready for integration |

## Key Decisions

- **Pre-dispatch verification**: Step 1 must pass before any agent is dispatched — ambiguous requirements are never sent to Dev
- **Fix loop**: Steps 4–5 repeat until all review findings are resolved or explicitly deferred by the user
- **Per-story scope**: This workflow executes for one story at a time; multi-story execution requires multiple runs

## Outputs

- Implemented story code committed to the feature branch
- Review cycle findings documented
- Story completion summary
- Story approval logged in tracking

## Exit Conditions

The workflow exits when:
- The story has been approved through the approval gate
- Story status in `sprint-status.yaml` is updated to complete
