---
name: 'phases-maintenance-checklist'
description: 'Quality gate rubric for phases-maintenance'
---

# Phases Maintenance — Validation Checklist

## Pre-Execution Checks

- [ ] Issue is reported with sufficient detail to triage
- [ ] Maintenance phase is active (project has been released)

## Step Completion Checks

### Step 1: Triage Issue (step-01-triage-issue)
- [ ] Issue fully understood before any action
- [ ] Severity correctly assigned based on impact
- [ ] Triage summary produced with all fields
- [ ] Queue management applied if multiple issues

### Step 2: Classify Issue (step-02-classify-issue)
- [ ] Decision tree applied honestly
- [ ] New features correctly identified and routed (not treated as maintenance fixes)
- [ ] Maintenance scope stays tight
- [ ] Classification reasoning documented

### Step 3: Analyst Diagnosis (step-03-analyst-diagnosis)
- [ ] Correct decision made about whether diagnosis is needed
- [ ] Diagnosis produces specific root cause and actionable fix
- [ ] Risk assessment included
- [ ] Related issues identified

### Step 4: Create Maintenance Task (step-04-create-maintenance-task)
- [ ] Task document has all required sections
- [ ] Fix scope is tight (not expanding into refactor)
- [ ] Acceptance criteria are specific
- [ ] Fix protocol matches severity
- [ ] Out of scope is explicit

### Step 5: DEV Implements Fix (step-05-dev-implements-fix)
- [ ] DEV dispatched through agent-dispatch workflow
- [ ] One issue per dispatch
- [ ] Fix stays within defined scope
- [ ] Related issues reported (not fixed)
- [ ] Test results included in report

### Step 6: Review Cycle (step-06-review-cycle)
- [ ] Review cycle invoked with correct inputs
- [ ] Same standards applied as execution phase (no relaxed standards)
- [ ] Zero legitimate issues at exit
- [ ] Pre-existing issues handled normally

### Step 7: Approval Gate (step-07-approval-gate)
- [ ] Approval gate invoked with complete package
- [ ] Deployment recommendation matches severity
- [ ] CHANGELOG.md updated for approved fixes
- [ ] Queue management applied for multiple issues
- [ ] Patch release triggered when appropriate

## Workflow-Level Checks

- [ ] Issue classified correctly (maintenance vs new feature)
- [ ] Fix deployed only after user approval
- [ ] CHANGELOG.md updated
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT start fixing before triaging
- [ ] Did NOT assign incorrect severity
- [ ] Did NOT treat new features as maintenance fixes
- [ ] Did NOT expand maintenance scope without user approval
- [ ] Did NOT skip Analyst diagnosis for complex or unclear bugs
- [ ] Did NOT accept vague root cause ("something is broken")
- [ ] Did NOT write fix scope that expands into refactor
- [ ] Did NOT combine multiple issues in one DEV dispatch
- [ ] Did NOT allow DEV to implement beyond defined scope
- [ ] Did NOT allow DEV to fix related issues instead of reporting them
- [ ] Did NOT relax review cycle standards because "it is just a small fix"
- [ ] Did NOT deploy without approval
- [ ] Did NOT skip updating CHANGELOG.md after fixes
- [ ] Did NOT silently defer LOW priority issues indefinitely
- [ ] Did NOT approve a CRITICAL fix without a deployment plan
- [ ] Did NOT: Vague triage ('it is broken')
- [ ] Did NOT: Not managing queue priority
- [ ] Did NOT: Fix recommendation addresses symptom not cause
- [ ] Did NOT: Missing acceptance criteria
- [ ] Did NOT: No testing requirements
- [ ] Did NOT: Wrong fix protocol for severity
- [ ] Did NOT: No test results in report
- [ ] Did NOT: Not handling pre-existing issues found during review
- [ ] Did NOT: Not checking issue queue after fix

_Validated by: Parzival Quality Gate on {date}_
