---
name: approval-gate
description: 'User approval protocol. Every completed unit of work passes through this gate. Nothing proceeds on assumption, nothing auto-advances.'
firstStep: './steps-c/step-01-prepare-package.md'
---

# Approval Gate

**Goal:** Present verified, reviewed, summarized work to the user and receive an explicit decision (Approve, Reject with feedback, or Hold) before anything advances.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Presentation Rules (Apply Across All Steps)
**Always:**
- Write summaries in Parzival's own words -- never copy agent output
- Be specific -- name files, features, decisions concretely
- Include review stats -- passes, issues found, issues fixed
- State the recommended next step with specifics
- Wait for explicit approval before advancing
- Confirm understanding before acting on rejection feedback
- Update project-status.md after every approval response

**Never:**
- Present raw agent output as the summary
- Assume approval -- always wait for explicit response
- Stack multiple decisions into one presentation
- Advance to next step while waiting for approval
- Mark a task complete without going through this gate
- Skip this gate because "the user will obviously approve"
- Interpret silence as approval
- Present more than one decision at a time

### When This Gate Triggers
- **Task Level:** After WF-REVIEW-CYCLE exits cleanly (most frequent)
- **Phase Level:** After Discovery, Architecture, Integration, Release milestones
- **Decision Points:** Mid-workflow decisions, blocker escalations, scope change requests

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
