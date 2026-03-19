---
name: 'phases-architecture-instructions'
description: 'Architecture phase: assess inputs, dispatch architect, create epics and stories, readiness check'
---

# phases-architecture — Instructions

## Prerequisites

- An approved PRD from the discovery phase
- Architect agent (`bmad-bmm-architect`) is available
- UX Designer agent (`bmad-bmm-ux-designer`) is available (if UI work is in scope)
- PM agent (`bmad-bmm-pm`) is available for epics/stories creation

## Workflow Overview

The architecture phase translates an approved PRD into a technical architecture and an organized set of epics and stories ready for sprint planning. The Architect agent designs the system architecture, the UX Designer creates interface designs (if applicable), and Parzival reviews the combined output for technical coherence and alignment with the PRD.

After user review and iteration, the PM agent breaks down the architecture into epics and stories. A readiness check verifies that planning can proceed, the architecture is finalized, and the approval gate confirms the phase is complete before advancing to planning.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-assess-inputs.md` | Review approved PRD and identify architecture constraints, integrations, and scope |
| 2 | `step-02-architect-designs.md` | Dispatch Architect agent to produce system architecture document |
| 3 | `step-03-ux-design.md` | Dispatch UX Designer agent for interface design (skip if no UI scope) |
| 4 | `step-04-parzival-reviews-architecture.md` | Parzival reviews architecture for completeness, PRD alignment, and technical soundness |
| 5 | `step-05-user-review-iteration.md` | Present architecture to user; iterate until satisfied |
| 6 | `step-06-pm-creates-epics-stories.md` | Dispatch PM agent to decompose architecture into epics and user stories |
| 7 | `step-07-readiness-check.md` | Verify all architecture artifacts are complete and planning can proceed |
| 8 | `step-08-finalize.md` | Finalize and lock all architecture documents; record in tracking |
| 9 | `step-09-approval-gate.md` | Run approval-gate cycle; confirm phase is complete and ready for planning |

## Key Decisions

- **UX scope**: Step 3 is skipped when no user interface work is in scope for the initiative
- **Architecture review depth**: Parzival's step 4 review is not advisory — identified gaps must be resolved before the user sees the design
- **Epics/stories dependency**: Step 6 only proceeds after the user has approved the architecture in step 5

## Outputs

- Approved architecture document
- UX design artifacts (when in scope)
- Epics and user stories created and stored
- Phase approval logged in tracking

## Exit Conditions

The workflow exits when:
- The architecture and all artifacts have been approved through the approval gate
- Epics and stories are created and ready for sprint planning
- Phase completion has been recorded in tracking
