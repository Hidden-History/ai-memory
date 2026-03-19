---
name: 'phases-discovery-checklist'
description: 'Quality gate rubric for phases-discovery'
---

# Phases Discovery — Validation Checklist

## Pre-Execution Checks

- [ ] Init phase is complete and baseline files exist
- [ ] Project goals and user inputs are available

## Step Completion Checks

### Step 1: Assess Existing Inputs (step-01-assess-existing-inputs)
- [ ] All available inputs were read in full (not skimmed)
- [ ] Scenario classification is based on specific assessment of input quality
- [ ] Decision to skip or require research is justified
- [ ] No agents were activated prematurely

### Step 2: Analyst Research (step-02-analyst-research)
- [ ] Analyst dispatched through agent-dispatch workflow (not directly)
- [ ] All six research areas covered
- [ ] Research is organized, not raw notes
- [ ] Gaps and open questions explicitly identified
- [ ] User questions resolved before proceeding to PRD

### Step 3: PM Creates PRD (step-03-pm-creates-prd)
- [ ] PM dispatched through agent-dispatch workflow
- [ ] All required PRD sections were requested in the instruction
- [ ] Track-appropriate depth was specified
- [ ] PRD draft received without presenting to user

### Step 4: Parzival Reviews PRD (step-04-parzival-reviews-prd)
- [ ] All four checklists run completely
- [ ] Issues batched into a single correction instruction (not piecemeal)
- [ ] Corrected PRD re-reviewed from scratch
- [ ] PRD passes all checks before user sees it

### Step 5: User Review Iteration (step-05-user-review-iteration)
- [ ] PRD presented with clear review guidance
- [ ] Every piece of user feedback was addressed
- [ ] Corrections batched (not piecemeal)
- [ ] Updated PRD re-reviewed by Parzival before re-presenting
- [ ] Iteration continued until user expressed satisfaction

### Step 6: PRD Finalization (step-06-prd-finalization)
- [ ] Final review passed with zero issues
- [ ] All user feedback confirmed incorporated
- [ ] PRD saved at correct location
- [ ] Project status updated
- [ ] Approval package is prepared with all required sections

### Step 7: Approval Gate (step-07-approval-gate)
- [ ] Approval gate invoked with complete package
- [ ] Scope implications clearly communicated
- [ ] User explicitly approved before Architecture work began
- [ ] Project status updated accurately
- [ ] Clean handoff to WF-ARCHITECTURE

## Workflow-Level Checks

- [ ] PRD exists at the correct location with all required sections
- [ ] User approved exit to Architecture phase
- [ ] No open questions remain unresolved
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT skip input assessment and go straight to research
- [ ] Did NOT classify as Scenario A when input was actually thin
- [ ] Did NOT activate agents before assessment was complete
- [ ] Did NOT skip research when input is thin
- [ ] Did NOT accept invented requirements from PM
- [ ] Did NOT dispatch Analyst directly instead of through agent-dispatch
- [ ] Did NOT resolve user questions before PRD creation
- [ ] Did NOT present PRD to user before Parzival review
- [ ] Did NOT specify all required PRD sections in the PM instruction
- [ ] Did NOT use the wrong track workflow
- [ ] Did NOT send corrections piecemeal to PM
- [ ] Did NOT re-review after corrections
- [ ] Did NOT run all four checklists during Parzival review
- [ ] Did NOT assume user is satisfied without explicit confirmation
- [ ] Did NOT dismiss user feedback
- [ ] Did NOT re-review updated PRD with Parzival before re-presenting
- [ ] Did NOT skip the final PRD review
- [ ] Did NOT update project-status.md after finalization
- [ ] Did NOT prepare a complete approval package
- [ ] Did NOT begin Architecture without explicit user approval
- [ ] Did NOT bypass the approval gate
- [ ] Did NOT communicate scope lock implications to the user
- [ ] Did NOT update project-status.md after approval
- [ ] Did NOT move to Architecture with open questions unresolved
- [ ] Did NOT accept vague acceptance criteria
- [ ] Did NOT include implementation details in requirements

_Validated by: Parzival Quality Gate on {date}_
