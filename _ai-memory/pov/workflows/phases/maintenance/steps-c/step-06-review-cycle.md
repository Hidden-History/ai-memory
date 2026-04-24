---
name: 'step-06-review-cycle'
description: 'Route to review cycle for maintenance fix verification -- same standards as execution'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: Review Cycle

**Progress: Step 6 of 7** — Next: Approval Gate

## STEP GOAL:

Route to `{workflows_path}/cycles/review-cycle/workflow.md` with the maintenance task as the specification. Same standards as execution -- no relaxation because "it is just a bug fix."

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Maintenance task document, DEV fix report, regression test specs
- Focus: Review cycle invocation and monitoring — same standards as execution
- Limits: Zero legitimate issues is the exit condition. No shortcuts for maintenance.
- Dependencies: DEV fix report from Step 5

- Focus on invoking review cycle with correct inputs and same standards as execution
**Behavioral Constraints:**
- FORBIDDEN to relax review standards because "it is just a bug fix"
- Approach: Zero legitimate issues is still the exit condition — no shortcuts
- Pre-existing issues found during fix review are handled normally

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Review Cycle Inputs

Provide to `{workflows_path}/cycles/review-cycle/workflow.md`:
- Maintenance task document (acceptance criteria)
- DEV fix implementation
- Specific regression tests to verify

---

### 2. Invoke Review Cycle

Load and execute `{workflows_path}/cycles/review-cycle/workflow.md`.

Important notes for maintenance review:
- Same standards as Execution -- no relaxation
- Zero legitimate issues still the exit condition
- Pre-existing issues found during fix review are classified normally
- Fix-introduced issues are classified and fixed before close
- Maintenance fixes often touch fragile, previously-unreviewed code
- Additional pre-existing issues are expected -- handle normally
- A sloppy maintenance fix creates the next maintenance issue

---

### 3. Receive Clean Review Summary

Review cycle exits with zero legitimate issues and clean summary.

## CRITICAL STEP COMPLETION NOTE

ONLY when review cycle exits with zero legitimate issues, load and read fully `{nextStepFile}`
