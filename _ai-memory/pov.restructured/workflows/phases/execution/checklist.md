---
name: 'phases-execution-checklist'
description: 'Quality gate rubric for phases-execution'
---

# Phases Execution — Validation Checklist

## Pre-Execution Checks

- [ ] Sprint is approved and sprint-status.yaml exists
- [ ] Story files exist for all sprint stories

## Step Completion Checks

### Step 1: Verify Story Requirements (step-01-verify-story-requirements)
- [ ] Story read in full (all seven sections)
- [ ] Verified against current architecture.md, project-context.md, and PRD.md
- [ ] Outdated references identified and corrected
- [ ] Pre-execution questions resolved

### Step 2: Prepare Instruction (step-02-prepare-instruction)
- [ ] Instruction includes all required sections
- [ ] Every field is specific (not vague)
- [ ] Quality check passes
- [ ] DEV could implement with this instruction alone

### Step 3: Activate DEV (step-03-activate-dev)
- [ ] DEV dispatched through agent-dispatch workflow
- [ ] Clarification questions answered with citations
- [ ] Scope drift caught and corrected
- [ ] Blockers resolved or escalated properly
- [ ] Implementation completion report received

### Step 4: Review Cycle (step-04-review-cycle)
- [ ] Review cycle invoked with all required inputs
- [ ] Red flags monitored during the cycle
- [ ] Non-convergence handled proactively
- [ ] Zero legitimate issues confirmed at exit

### Step 5: Verify Fixes (step-05-verify-fixes)
- [ ] Four-source verification applied to all significant fixes
- [ ] Every source individually checked
- [ ] Final implementation review confirms all criteria satisfied
- [ ] No issues remain before user presentation

### Step 6: Prepare Summary (step-06-prepare-summary)
- [ ] Summary is in Parzival's words (not DEV output copy)
- [ ] All acceptance criteria confirmed satisfied
- [ ] Review cycle metrics are accurate
- [ ] Notable findings are genuinely notable

### Step 7: Approval Gate (step-07-approval-gate)
- [ ] Approval gate invoked with complete package
- [ ] Correct routing after approval (next story vs milestone)
- [ ] Sprint status updated accurately
- [ ] Rejection handled with appropriate routing

## Workflow-Level Checks

- [ ] Story moved to COMPLETE state
- [ ] sprint-status.yaml updated
- [ ] Zero legitimate issues confirmed before approval gate
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT dispatch DEV with outdated story references
- [ ] Did NOT leave ambiguities for DEV to resolve
- [ ] Did NOT send story file directly instead of building an instruction
- [ ] Did NOT include vague file references ("the relevant files")
- [ ] Did NOT run quality check before dispatch
- [ ] Did NOT activate DEV directly instead of through agent-dispatch workflow
- [ ] Did NOT let scope drift pass uncaught
- [ ] Did NOT skip the review cycle
- [ ] Did NOT accept review cycle exit with uncertain issues unresolved
- [ ] Did NOT skip four-source fix verification after review cycle
- [ ] Did NOT copy DEV output into summary
- [ ] Did NOT advance to next story without approval
- [ ] Did NOT miss milestone trigger
- [ ] Did NOT bypass approval gate
- [ ] Did NOT accept DEV's self-certification without review
- [ ] Did NOT: Not verifying against current project state
- [ ] Did NOT: Missing security requirements
- [ ] Did NOT: Vague answers to clarification questions
- [ ] Did NOT: Blockers ignored or left unresolved
- [ ] Did NOT: Not monitoring for red flags
- [ ] Did NOT: Not escalating non-convergence
- [ ] Did NOT: Accepting fixes that fail any source
- [ ] Did NOT: Presenting to user with unverified fixes
- [ ] Did NOT: Not running final implementation review
- [ ] Did NOT: Missing acceptance criteria in status list
- [ ] Did NOT: Inaccurate review cycle metrics
- [ ] Did NOT: Including non-notable items as findings
- [ ] Did NOT: Not updating sprint-status.yaml

_Validated by: Parzival Quality Gate on {date}_
