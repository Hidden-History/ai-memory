---
name: 'phases-discovery-instructions'
description: 'Discovery phase: assess inputs, gather requirements, create PRD with user collaboration and approval'
---

# phases-discovery — Instructions

## Prerequisites

- Parzival oversight session active with the discovery phase loaded
- A new project or feature initiative has been identified requiring formal discovery
- PRD template is accessible at the configured template path
- PM agent (`bmad-bmm-pm`) and Analyst agent (`bmad-bmm-analyst`) are available for dispatching

## Workflow Overview

The discovery phase transforms a raw initiative into a reviewed and approved Product Requirements Document. It begins by assessing any existing inputs (briefs, notes, prior research), then dispatches the Analyst agent to conduct structured research, followed by the PM agent creating the PRD from research outputs.

Parzival reviews the PRD before it reaches the user, checking for completeness and consistency with project constraints. The user reviews and iterates until satisfied, at which point the PRD is finalized and the workflow exits through the approval gate — confirming readiness to advance to the architecture phase.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-assess-existing-inputs.md` | Inventory any existing product briefs, research notes, or prior decisions relevant to the initiative |
| 2 | `step-02-analyst-research.md` | Dispatch Analyst agent to conduct structured discovery research |
| 3 | `step-03-pm-creates-prd.md` | Dispatch PM agent to create the PRD from research outputs |
| 4 | `step-04-parzival-reviews-prd.md` | Parzival reviews the PRD for completeness, consistency, and constraint compliance |
| 5 | `step-05-user-review-iteration.md` | Present PRD to user; iterate based on feedback until user is satisfied |
| 6 | `step-06-prd-finalization.md` | Finalize and lock the PRD; record in tracking |
| 7 | `step-07-approval-gate.md` | Run approval-gate cycle; confirm phase is complete and ready for architecture |

## Key Decisions

- **Research scope**: Analyst determines research breadth based on initiative complexity; Parzival may challenge scope if insufficient
- **PRD completeness gate**: Step 4 enforces that unclear or missing requirements are flagged before the user sees the PRD
- **Phase advancement**: The approval gate at step 7 is the only valid path to exit the discovery phase

## Outputs

- Approved PRD document
- Research notes/artifacts from Analyst agent
- Phase approval logged in tracking

## Exit Conditions

The workflow exits when:
- The PRD has been approved by the user through the approval gate
- Phase completion has been recorded in tracking
