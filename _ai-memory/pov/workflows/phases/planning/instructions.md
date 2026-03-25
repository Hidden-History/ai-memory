---
name: 'phases-planning-instructions'
description: 'Planning phase: review state, run retrospective, dispatch SM for sprint setup, create stories, approve'
---

# phases-planning — Instructions

## Prerequisites

- Approved architecture and epics/stories from the architecture phase
- Sprint Master agent (`bmad-bmm-sm`) is available
- `sprint-status.yaml` is accessible for update
- Prior sprint retrospective data is available (if this is not the first sprint)

## Workflow Overview

The planning phase prepares the next sprint for execution. It begins by reviewing current project state and running a retrospective on the previous sprint (if one exists), then dispatches the Sprint Master agent to plan the sprint and create story files. Parzival reviews the sprint plan before it reaches the user.

The user reviews and approves the sprint plan. Once approved, the sprint status is updated and the workflow exits through the approval gate — confirming readiness to begin execution.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-review-project-state.md` | Review current sprint status, open blockers, and available stories to inform planning |
| 2 | `step-02-retrospective.md` | Run retrospective on the previous sprint to surface lessons (skip for first sprint) |
| 3 | `step-03-sm-sprint-planning.md` | Dispatch Sprint Master agent to select stories and plan the sprint |
| 4 | `step-04-sm-creates-story-files.md` | Sprint Master creates individual story files for all stories in the sprint |
| 5 | `step-05-parzival-reviews-sprint.md` | Parzival reviews sprint plan for feasibility, dependency conflicts, and constraint compliance |
| 6 | `step-06-user-review-approval.md` | Present sprint plan to user; collect approval or revision requests |
| 7 | `step-07-approval-gate.md` | Run approval-gate cycle; confirm sprint is ready for execution |

## Key Decisions

- **Retrospective applicability**: Step 2 is skipped only for the very first sprint; it runs for all subsequent sprints
- **Story file completeness**: Step 4 must produce one file per story before step 5 can proceed
- **Parzival review**: Step 5 checks capacity, dependencies, and constraint alignment — not cosmetic review

## Outputs

- Sprint plan with selected stories and assignments
- Individual story files created for all sprint stories
- `sprint-status.yaml` updated with new sprint state
- Phase approval logged in tracking

## Exit Conditions

The workflow exits when:
- The sprint plan has been approved through the approval gate
- All story files are created and accessible
- `project-status.md` reflects the new sprint
