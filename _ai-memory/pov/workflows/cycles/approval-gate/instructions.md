---
name: 'cycles-approval-gate-instructions'
description: 'User approval gate: prepare package, present summary, process response, record outcome'
---

# cycles-approval-gate — Instructions

## Prerequisites

- Work has been completed and is ready for user review
- The item being approved has defined acceptance criteria or completion criteria
- The calling workflow has assembled the approval package

## Workflow Overview

The approval-gate cycle is the standard mechanism for presenting completed work to the user and collecting an explicit approval or rejection decision. It is called at the end of phase workflows and major execution milestones.

The cycle packages the work for presentation, presents it clearly to the user with Parzival's recommendation, processes the user's response (approve, reject, or request changes), and records the outcome in tracking. Approval gates are never bypassed — all significant work decisions require explicit user approval.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-prepare-package.md` | Assemble the approval package: work artifacts, summary, and Parzival's recommendation |
| 2 | `step-02-present-to-user.md` | Present the approval package to the user; halt and await explicit response |
| 3 | `step-03-process-response.md` | Process the user's decision: approve, reject, or request specific changes |
| 4 | `step-04-record-outcome.md` | Record the approval outcome in the appropriate tracking file |

## Key Decisions

- **No self-approval**: Parzival never approves its own work — the user response in step 2 is always required
- **Rejection handling**: Rejection returns control to the calling workflow with the user's feedback as input
- **Changes vs. rejection**: A "request changes" response loops back to the calling workflow, not a full rejection

## Outputs

- Explicit user approval or rejection recorded
- Outcome logged in tracking

## Exit Conditions

The workflow exits when:
- The user has provided an explicit decision (approve / reject / request changes)
- The outcome has been recorded in step 4
- For phase-level approvals, phase-specific exit requirements have been verified before the outcome is recorded
