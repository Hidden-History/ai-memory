---
name: approval-gate
description: 'User approval protocol. Every completed unit of work passes through this gate. Nothing proceeds on assumption, nothing auto-advances.'
firstStep: './steps/step-01-prepare-package.md'
---

# Approval Gate

**Goal:** Present verified, reviewed, summarized work to the user and receive an explicit decision (Approve, Reject with feedback, or Hold) before anything advances.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files

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
