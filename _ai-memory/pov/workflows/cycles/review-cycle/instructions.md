---
name: 'cycles-review-cycle-instructions'
description: 'Review cycle: verify completeness, adversarial review, classify issues, correct, track cycles, exit when zero issues'
---

# cycles-review-cycle — Instructions

## Prerequisites

- Code or artifact has been produced by a Dev or other implementation agent
- The code reviewer agent configuration is available
- The work being reviewed has defined acceptance criteria

## Workflow Overview

The review-cycle drives a structured code/artifact review loop: verify the submission is complete, trigger an adversarial code review, process the findings, instruct the Dev agent on required corrections, receive the fixes, track cycle counts, and exit when review criteria are met.

The cycle enforces that review findings are addressed before work advances. It tracks how many review cycles have occurred to flag if an agent is failing to converge. The cycle exits cleanly when findings are resolved or the calling workflow accepts a deferred-findings state.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-verify-completeness.md` | Verify the submitted work is complete enough for review (no placeholder code, no partial stubs) |
| 2 | `step-02-trigger-code-review.md` | Dispatch code reviewer agent for adversarial review of the submitted work |
| 3 | `step-03-process-review-report.md` | Read and triage the review report; classify findings as blocking vs. advisory |
| 4 | `step-04-build-correction-instruction.md` | Compose correction instruction for the Dev agent addressing all blocking findings |
| 5 | `step-05-receive-fixes.md` | Receive Dev agent's corrected output |
| 6 | `step-06-cycle-tracking.md` | Increment cycle counter; flag if cycle count exceeds threshold |
| 7 | `step-07-exit-cycle.md` | Confirm all blocking findings resolved; exit cycle and return to calling workflow |

## Key Decisions

- **Completeness gate**: Step 1 returns incomplete work to the Dev agent before review is triggered — partial work is never reviewed
- **Blocking vs. advisory**: Only blocking findings require correction before exit; advisory findings are noted but do not block
- **Cycle threshold**: If the cycle count exceeds the configured threshold (typically 3), Parzival escalates to the user

## Outputs

- Reviewed and corrected work artifact
- Review report with finding classifications
- Cycle count recorded in tracking

## Exit Conditions

The workflow exits when:
- All blocking review findings have been resolved
- All uncertain issues have been resolved (classified or routed to research protocol)
- Cannot-exit conditions have been verified clear
- Review cycle summary has been prepared and handed off to WF-APPROVAL-GATE
