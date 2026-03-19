---
name: 'phases-architecture-checklist'
description: 'Quality gate rubric for phases-architecture'
---

# Phases Architecture — Validation Checklist

## Pre-Execution Checks

- [ ] PRD.md is approved and exists at the correct location
- [ ] Discovery phase is complete (user approval recorded)

## Step Completion Checks

### Step 1: Assess Inputs (step-01-assess-inputs)
- [ ] PRD.md read in full (not summarized from Discovery)
- [ ] All relevant project files read
- [ ] Pre-architecture ambiguities resolved before Architect activation
- [ ] Answers documented in appropriate files

### Step 2: Architect Designs (step-02-architect-designs)
- [ ] Architect dispatched through agent-dispatch workflow
- [ ] All eight sections requested in the instruction
- [ ] Track-appropriate depth specified
- [ ] Architecture draft received without presenting to user

### Step 3: UX Design (step-03-ux-design)
- [ ] Correct decision made about whether UX design is needed
- [ ] If activated, UX Designer dispatched through agent-dispatch workflow
- [ ] If UI-heavy project, design artifacts reference PRD acceptance criteria
- [ ] If skipped, clear justification recorded

### Step 4: Parzival Reviews Architecture (step-04-parzival-reviews-architecture)
- [ ] All five checklists run completely
- [ ] Issues batched into single correction instruction
- [ ] Corrected architecture re-reviewed from scratch
- [ ] Architecture passes all checks before user sees it

### Step 5: User Review Iteration (step-05-user-review-iteration)
- [ ] Architecture presented with cascading-change warning
- [ ] Every piece of feedback addressed
- [ ] Impact assessment performed for each change
- [ ] Corrections batched and re-reviewed
- [ ] User explicitly confirmed satisfaction

### Step 6: PM Creates Epics and Stories (step-06-pm-creates-epics-stories)
- [ ] PM received both PRD and architecture as inputs
- [ ] Stories reference architecture decisions for technical context
- [ ] Every PRD Must Have feature has a story
- [ ] Stories do not span component boundaries
- [ ] Parzival reviewed before proceeding

### Step 7: Readiness Check (step-07-readiness-check)
- [ ] Readiness check covered all three document sets
- [ ] NOT READY gaps were individually addressed and re-checked
- [ ] READY assessment was verified by Parzival (not just accepted)
- [ ] All document sets are cohesive

### Step 8: Finalize (step-08-finalize)
- [ ] All files verified at correct locations
- [ ] project-context.md updated with confirmed architecture
- [ ] decisions.md updated with architecture decisions
- [ ] project-status.md tracking files updated
- [ ] Approval summary is complete

### Step 9: Approval Gate (step-09-approval-gate)
- [ ] Approval gate invoked with complete package
- [ ] Technical lock implications clearly communicated
- [ ] User explicitly approved
- [ ] Project status updated
- [ ] Clean handoff to WF-PLANNING

## Workflow-Level Checks

- [ ] architecture.md exists at the correct location
- [ ] Epics and stories are created and reviewed
- [ ] Readiness check passed for all three document sets
- [ ] User approved exit to Planning phase
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT activate Architect with unresolved ambiguities
- [ ] Did NOT rely on summaries instead of reading PRD.md
- [ ] Did NOT present architecture to user before Parzival review
- [ ] Did NOT specify fewer than eight required sections in Architect instruction
- [ ] Did NOT gold-plate beyond project scale
- [ ] Did NOT dispatch Architect directly instead of through agent-dispatch
- [ ] Did NOT activate UX Designer for API-only projects
- [ ] Did NOT skip UX design for a UI-heavy project without justification
- [ ] Did NOT send corrections piecemeal
- [ ] Did NOT fail to assess cascade impact of user changes
- [ ] Did NOT write stories without architecture as input
- [ ] Did NOT skip the readiness check
- [ ] Did NOT accept NOT READY without fixing gaps
- [ ] Did NOT allow undocumented architecture decisions
- [ ] Did NOT begin Planning without explicit approval
- [ ] Did NOT treat architecture as fixed when a major PRD requirement is missed
- [ ] Did NOT: Not checking for existing codebase constraints
- [ ] Did NOT: UX Designer dispatched directly instead of through agent-dispatch
- [ ] Did NOT: Not re-reviewing after corrections
- [ ] Did NOT: Skipping any checklist
- [ ] Did NOT: Dismissing user feedback
- [ ] Did NOT: Stories that span component boundaries
- [ ] Did NOT: PRD features without corresponding stories
- [ ] Did NOT: Accepting READY without Parzival verification
- [ ] Did NOT: Leaving contradictions between documents
- [ ] Did NOT: Files at wrong locations
- [ ] Did NOT: project-context.md not updated
- [ ] Did NOT: Incomplete approval summary
- [ ] Did NOT: Not communicating technical lock implications

_Validated by: Parzival Quality Gate on {date}_
