---
name: 'cycles-review-cycle-checklist'
description: 'Quality gate rubric for cycles-review-cycle'
---

# Cycles Review Cycle — Validation Checklist

## Pre-Execution Checks

- [ ] Implementation output is available for review
- [ ] DONE WHEN criteria from the original instruction are accessible

## Step Completion Checks

### Step 1: Verify Completeness (step-01-verify-completeness)
- [ ] Every DONE WHEN criterion has been verified individually
- [ ] Implementation output has been read in full, not skimmed
- [ ] Incomplete implementations are returned to DEV with specific direction
- [ ] Only complete implementations proceed to code review

### Step 2: Trigger Code Review (step-02-trigger-code-review)
- [ ] Code review instruction includes all files in scope
- [ ] Code review instruction cites specific project requirements
- [ ] DEV review covers all required areas
- [ ] Complete review report received before proceeding

### Step 3: Process Review Report (step-03-process-review-report)
- [ ] Every issue in the report was read and classified individually
- [ ] WF-LEGITIMACY-CHECK ran for every single issue
- [ ] Uncertain issues triggered WF-RESEARCH-PROTOCOL
- [ ] Pre-existing issues were classified and included (not deferred)
- [ ] Zero-issue reports on complex tasks were questioned

### Step 4: Build Correction Instruction (step-04-build-correction-instruction)
- [ ] All legitimate issues included in one instruction
- [ ] Issues organized by priority (CRITICAL → HIGH → MEDIUM → LOW)
- [ ] Each issue has location, problem, required fix, and basis
- [ ] Non-issues documented but excluded from fix list
- [ ] Uncertain issues held separately with status

### Step 5: Receive Fixes (step-05-receive-fixes)
- [ ] Every fix was independently verified by Parzival (not just DEV's claim)
- [ ] Fix scope compliance was checked
- [ ] New issues introduced by fixes were identified
- [ ] Uncertain issues were correctly tracked
- [ ] Cycle tracking record was updated
- [ ] Re-review report routed back to step-03 for full processing

### Step 6: Cycle Tracking (step-06-cycle-tracking)
- [ ] Every pass is recorded with accurate counts
- [ ] Priority breakdowns are tracked for legitimate issues
- [ ] New issues from fixes are counted separately
- [ ] Pre-existing fixes are counted separately
- [ ] Data is available for the approval gate summary

### Step 7: Exit Cycle (step-07-exit-cycle)
- [ ] Every exit condition was individually verified
- [ ] Cannot-exit conditions were explicitly checked
- [ ] Review cycle summary is complete and accurate
- [ ] Summary is written in Parzival's words (not copied from DEV output)
- [ ] Clean handoff to WF-APPROVAL-GATE

## Workflow-Level Checks

- [ ] Zero legitimate issues confirmed at cycle exit
- [ ] No uncertain issues remain unresolved
- [ ] Cycle tracking data is complete and accurate
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT trigger code review on incomplete implementation
- [ ] Did NOT skim output instead of reading in full
- [ ] Did NOT send vague incompleteness instructions
- [ ] Did NOT: Proceeding despite failed completeness checks
- [ ] Did NOT omit files from the review scope
- [ ] Did NOT: Not citing specific requirements to review against
- [ ] Did NOT: Proceeding before receiving complete review report
- [ ] Did NOT skip classification for any issue
- [ ] Did NOT classify multiple issues together in batch
- [ ] Did NOT rely on DEV's severity instead of independent classification
- [ ] Did NOT defer pre-existing legitimate issues
- [ ] Did NOT accept implausible zero-issue reports without scrutiny
- [ ] Did NOT send partial correction instruction (only some issues)
- [ ] Did NOT include non-issues in the fix list
- [ ] Did NOT: Not organizing by priority
- [ ] Did NOT: Missing location or basis for any issue
- [ ] Did NOT: Sending fix instructions for uncertain issues before resolution
- [ ] Did NOT trust DEV's self-assessment without independent verification
- [ ] Did NOT miss new issues introduced by fixes
- [ ] Did NOT allow changes outside fix scope to pass
- [ ] Did NOT: Touching uncertain issues without resolution
- [ ] Did NOT: Skipping cycle tracking update
- [ ] Did NOT: Not routing back to step-03 for re-processing
- [ ] Did NOT exit with unresolved legitimate issues
- [ ] Did NOT exit with pending uncertain issues
- [ ] Did NOT copy DEV output into the summary
- [ ] Did NOT accept review exit with remaining issues
- [ ] Did NOT skip review cycle because "the fixes were simple"
- [ ] Did NOT: Missing pass records
- [ ] Did NOT: Not distinguishing pre-existing fixes from current-task fixes

_Validated by: Parzival Quality Gate on {date}_
