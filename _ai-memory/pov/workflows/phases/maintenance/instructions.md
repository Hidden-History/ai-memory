---
name: 'phases-maintenance-instructions'
description: 'Maintenance phase: triage issue, classify legitimacy, diagnose, dispatch fix, review cycle, approve'
---

# phases-maintenance — Instructions

## Prerequisites

- Parzival oversight session active
- A maintenance issue has been reported (bug, regression, performance degradation, or operational concern)
- Analyst agent (`bmad-bmm-analyst`) is available for diagnosis
- Dev agent (`bmad-bmm-dev`) is available for fix implementation

## Workflow Overview

The maintenance phase handles post-release issues through a structured triage-to-fix cycle. The issue is triaged on arrival, classified by type and severity, and diagnosed by the Analyst agent to determine root cause. A targeted maintenance task is created, the Dev agent implements the fix, Parzival triggers a review cycle, and the fix is approved through the approval gate.

Maintenance is scoped to a single issue per workflow run. The classification step determines whether the issue warrants an immediate hotfix or can be scheduled for the next sprint.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-triage-issue.md` | Capture the issue report and assess initial severity and urgency |
| 2 | `step-02-classify-issue.md` | Classify the issue type (bug / regression / performance / operational) and priority level |
| 3 | `step-03-analyst-diagnosis.md` | Dispatch Analyst agent to investigate root cause and determine fix scope |
| 4 | `step-04-create-maintenance-task.md` | Create the maintenance task file with acceptance criteria for the fix |
| 5 | `step-05-dev-implements-fix.md` | Dispatch Dev agent to implement the fix per the maintenance task |
| 6 | `step-06-review-cycle.md` | Trigger review-cycle on the fix; verify it resolves the issue without regressions |
| 7 | `step-07-approval-gate.md` | Run approval-gate cycle; confirm the fix is approved and ready to release |

## Key Decisions

- **Hotfix vs. sprint scheduling**: Classification at step 2 determines urgency — critical issues become hotfixes, lower-priority items are queued for the next sprint
- **Root cause requirement**: The Analyst diagnosis at step 3 must identify root cause, not just symptoms — fixes that address only symptoms are flagged
- **Scope containment**: Maintenance tasks must not expand into feature work; scope creep is flagged by Parzival

## Outputs

- Maintenance task file with root cause and acceptance criteria
- Fix implemented and reviewed
- Issue closure documented in tracking
- Fix approval logged

## Exit Conditions

The workflow exits when:
- The fix has been approved through the approval gate
- Issue status is updated in tracking as resolved
