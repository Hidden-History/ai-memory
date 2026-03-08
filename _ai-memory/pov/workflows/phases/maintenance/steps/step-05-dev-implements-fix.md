---
name: 'step-05-dev-implements-fix'
description: 'Activate DEV to implement the maintenance fix within the defined scope'
nextStepFile: './step-06-review-cycle.md'
---

# Step 5: DEV Implements Fix

## STEP GOAL
Activate the DEV agent to implement the fix as specified in the maintenance task. Scope is tightly defined -- implement only what is listed. Report but do not fix related issues.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Maintenance task document, architecture.md, project-context.md
- Limits: DEV implements only the defined fix. Related issues are reported, not fixed. One issue per dispatch.

## MANDATORY SEQUENCE

### 1. Prepare DEV Fix Instruction
Include:
- Issue description from maintenance task
- Root cause
- Fix required: specific files, specific changes, patterns to follow
- Acceptance criteria (from maintenance task)
- Testing steps:
  1. Reproduce original issue first
  2. Apply fix
  3. Confirm resolved against acceptance criteria
  4. Run regression tests
  5. Verify no new issues in related areas
- Out of scope: explicit exclusions
- Security check (if applicable)
- Report back with: confirmation, files modified, test results, related issues identified

### 2. Apply Hotfix vs Standard Fix Protocol

**HOTFIX (CRITICAL severity — production down or data at risk):**
- Skip staging — fix directly in production flow
- Accelerate review cycle — one focused pass
- Deploy immediately after approval (no sprint planning)
- Document hotfix in CHANGELOG.md as patch release
- Post-hotfix: create story for proper regression test coverage

**STANDARD FIX (HIGH / MEDIUM / LOW):**
- Normal review cycle applies
- No expedited handling
- Fix goes through full review cycle
- Deploy with next release or as a patch depending on severity

### 3. Dispatch DEV via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate DEV. One issue per dispatch -- never combine multiple issues.

### 4. Receive Fix Report
DEV reports:
- Original issue resolved: [yes/no]
- Files modified
- Test results
- Related issues identified (not fixed)

## CRITICAL STEP COMPLETION NOTE
ONLY when DEV reports fix complete, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- DEV dispatched through agent-dispatch workflow
- One issue per dispatch
- Fix stays within defined scope
- Related issues reported (not fixed)
- Test results included in report

### FAILURE:
- Combining multiple issues in one dispatch
- DEV implementing beyond defined scope
- DEV fixing related issues instead of reporting
- No test results in report
