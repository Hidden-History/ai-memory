---
name: 'init-existing-instructions'
description: 'Existing project onboarding: read files, audit state, identify branch (active/legacy/paused/handoff), establish baseline'
---

# init-existing — Instructions

## Prerequisites

- An existing project with prior history (commits, documentation, or prior oversight records) is being brought under Parzival oversight
- The project directory is accessible
- Analyst agent (`bmad-bmm-analyst`) is available for the audit
- AI Memory installation (`~/.ai-memory`) must be accessible

## Workflow Overview

The init-existing workflow onboards a project that already has history into Parzival oversight. Unlike init-new, it must first understand the existing state before creating any baseline files. The Analyst agent audits the project, Parzival identifies the project's situation branch, an appropriate baseline is established, the understanding is verified, and the result is presented to the user for approval.

Four situation branches are supported, each handled by a dedicated branch step file in the `branches/` directory: **Branch A** (Active Mid-Sprint) for projects already in active development, **Branch B** (Legacy/Undocumented) for projects with little formal process, **Branch C** (Paused/Restarting) for projects returning after a hiatus, and **Branch D** (Handoff from Team) for projects transferring from another team.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-read-existing-files.md` | Read and inventory all existing project files: docs, specs, git history summary, and any prior oversight records |
| 2 | `step-02-run-analyst-audit.md` | Dispatch Analyst agent to audit the project state and produce a structured findings report |
| 3 | `step-03-identify-branch.md` | Identify which of the four situation branches applies; load the corresponding branch step file |
| 4 | `step-04-establish-baseline.md` | Create baseline tracking files calibrated to the project's identified state and branch |
| 5 | `step-05-verify-understanding.md` | Verify that the baseline accurately reflects actual project state; surface any gaps |
| 6 | `step-06-present-and-approve.md` | Present the baseline and situation summary to the user for review and approval |

## Key Decisions

- **Branch identification**: Step 3 selects one of four branches (A/B/C/D) — the branch drives how the baseline is structured in step 4
- **Analyst audit scope**: The audit covers code, documentation, git history, and any prior planning artifacts — it is comprehensive, not superficial
- **Baseline calibration**: For Branch B (legacy) and Branch C (paused), baselines must reflect actual state, not ideal state

## Outputs

- Situation branch identified (A, B, C, or D)
- Analyst audit report
- Calibrated Parzival oversight baseline created
- Baseline approved by user

## Exit Conditions

The workflow exits when:
- The user has approved the baseline in step 6
- The project is ready for its first session-start under Parzival oversight
