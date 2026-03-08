---
name: 'step-06-review-cycle'
description: 'Route to review cycle for maintenance fix verification -- same standards as execution'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: Review Cycle

## STEP GOAL
Route to {workflows_path}/cycles/review-cycle/workflow.md with the maintenance task as the specification. Same standards as execution -- no relaxation because "it is just a bug fix."

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Maintenance task document, DEV fix report, regression test specs
- Limits: Zero legitimate issues is still the exit condition. No shortcuts for maintenance.

## MANDATORY SEQUENCE

### 1. Prepare Review Cycle Inputs
Provide to {workflows_path}/cycles/review-cycle/workflow.md:
- Maintenance task document (acceptance criteria)
- DEV fix implementation
- Specific regression tests to verify

### 2. Invoke Review Cycle
Load and execute {workflows_path}/cycles/review-cycle/workflow.md.

Important notes for maintenance review:
- Same standards as Execution -- no relaxation
- Zero legitimate issues still the exit condition
- Pre-existing issues found during fix review are classified normally
- Fix-introduced issues are classified and fixed before close
- Maintenance fixes often touch fragile, previously-unreviewed code
- Additional pre-existing issues are expected -- handle normally
- A sloppy maintenance fix creates the next maintenance issue

### 3. Receive Clean Review Summary
Review cycle exits with zero legitimate issues and clean summary.

## CRITICAL STEP COMPLETION NOTE
ONLY when review cycle exits with zero legitimate issues, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Review cycle invoked with correct inputs
- Same standards applied as execution phase
- Zero legitimate issues at exit
- Pre-existing issues handled normally

### FAILURE:
- Relaxing standards for "just a bug fix"
- Accepting review exit with remaining issues
- Not handling pre-existing issues found during review
- Rushing through review
