---
name: 'phases-integration-checklist'
description: 'Quality gate rubric for phases-integration'
---

# Phases Integration — Validation Checklist

## Pre-Execution Checks

- [ ] All milestone stories are marked COMPLETE in sprint-status.yaml
- [ ] DEV implementation artifacts are available

## Step Completion Checks

### Step 1: Establish Scope (step-01-establish-scope)
- [ ] All milestone stories confirmed complete
- [ ] Integration points specifically identified
- [ ] Known risks documented
- [ ] Scope is comprehensive (not a spot check)

### Step 2: Prepare Test Plan (step-02-prepare-test-plan)
- [ ] All four test plan sections are populated
- [ ] Tests are specific (not generic)
- [ ] Every Must Have feature has test coverage
- [ ] Integration points have explicit boundary tests
- [ ] Pass criteria are defined

### Step 3: DEV Full Review (step-03-dev-full-review)
- [ ] DEV reviewed all seven areas
- [ ] Test plan items executed with clear pass/fail
- [ ] Issues reported with specific locations
- [ ] Dispatched through agent-dispatch workflow

### Step 4: Architect Cohesion (step-04-architect-cohesion)
- [ ] All six cohesion areas reviewed
- [ ] Clear CONFIRMED or ISSUES FOUND verdict
- [ ] Issues documented with architectural basis
- [ ] Dispatched through agent-dispatch workflow

### Step 5: Review Findings (step-05-review-findings)
- [ ] All findings from both sources classified
- [ ] Integration-specific rules applied
- [ ] Consolidated fix list built with clear priorities
- [ ] Correct routing based on whether fixes are needed

### Step 6: Fix Cycle (step-06-fix-cycle)
- [ ] Fixes routed correctly by type
- [ ] Cross-component fixes verified together
- [ ] Architecture decisions documented before implementation
- [ ] Test plan re-run after every fix pass
- [ ] All test plan items pass at exit

### Step 7: Final Verification (step-07-final-verification)
- [ ] All three verification areas checked
- [ ] Zero issues confirmed from all sources
- [ ] All test plan items passed
- [ ] Cohesion confirmed
- [ ] Four-source verification applied

### Step 8: Approval Gate (step-08-approval-gate)
- [ ] Approval gate invoked with complete package
- [ ] Production-readiness implications communicated
- [ ] Correct routing on approval
- [ ] Rejection handled with appropriate re-entry

## Workflow-Level Checks

- [ ] All test plan items passed
- [ ] Zero issues from DEV review and Architect cohesion
- [ ] User approved for release
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT run integration as a spot check on a few files
- [ ] Did NOT skip the test plan and just run a code review
- [ ] Did NOT use generic test descriptions ("verify it works")
- [ ] Did NOT dispatch DEV directly instead of through agent-dispatch
- [ ] Did NOT skip Architect cohesion check
- [ ] Did NOT accept vague cohesion assessment
- [ ] Did NOT dispatch Architect directly instead of through agent-dispatch
- [ ] Did NOT fail to apply integration-specific classification rules
- [ ] Did NOT classify test failures as anything other than CRITICAL
- [ ] Did NOT implement without resolving architecture questions
- [ ] Did NOT exit fix cycle with test failures remaining
- [ ] Did NOT accept partial test plan pass
- [ ] Did NOT start release before integration approval
- [ ] Did NOT accept "mostly passing" test plan
- [ ] Did NOT: Missing milestone stories from scope
- [ ] Did NOT: Not identifying integration points
- [ ] Did NOT: Ignoring known risks from development
- [ ] Did NOT: Missing test plan sections
- [ ] Did NOT: Must Have features without test coverage
- [ ] Did NOT: No pass criteria defined
- [ ] Did NOT: Not executing test plan items
- [ ] Did NOT: Vague issue descriptions
- [ ] Did NOT: Not providing DEV review report as context
- [ ] Did NOT: Missing findings from either source
- [ ] Did NOT: Routing to fix cycle with zero issues
- [ ] Did NOT: Not re-running test plan after fixes
- [ ] Did NOT: Verifying cross-component fixes in isolation
- [ ] Did NOT: Proceeding with unverified items
- [ ] Did NOT: Not re-confirming cohesion after fixes
- [ ] Did NOT: Not communicating production-readiness implications
- [ ] Did NOT: Partial re-integration after rejection

_Validated by: Parzival Quality Gate on {date}_
