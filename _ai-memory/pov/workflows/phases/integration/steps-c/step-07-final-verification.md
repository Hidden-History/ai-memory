---
name: 'step-07-final-verification'
description: 'Final verification pass confirming zero issues, test plan passed, and cohesion confirmed'
nextStepFile: './step-08-approval-gate.md'
---

# Step 7: Final Verification Pass

**Progress: Step 7 of 8** — Next: Approval Gate

## STEP GOAL:

When fix cycle reports zero issues and all test plan items pass, run a final verification to confirm everything is clean before presenting to the user.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Fix cycle results, test plan results, cohesion check results
- Focus: Final verification only — no new fixes or changes in this step
- Limits: If any check fails, return to fix cycle.
- Dependencies: Fix cycle completion from Step 6 (or Step 5 if zero issues found)

- Confirm zero issues, all test plan items pass, and cohesion confirmed before approval gate
**Behavioral Constraints:**
- FORBIDDEN to proceed to approval gate with any unresolved items or unverified checks
- Approach: Three-area verification against all prior step results
- If any check fails, return to step-06 — do not proceed

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Verify DEV Review Results

- Zero legitimate issues confirmed across all milestone stories
- All test plan items confirmed PASS
- No test plan items skipped or deferred
- All pre-existing issues found during integration are fixed

---

### 2. Verify Architect Results

- Cohesion: CONFIRMED (or re-confirmed after fixes)
- All architectural violations from Step 4 are resolved
- No new architectural concerns introduced by fixes

---

### 3. Parzival Verification

- All acceptance criteria for all milestone stories confirmed satisfied
- All PRD Must Have features for this milestone are implemented
- No known legitimate issues remain anywhere in milestone scope
- Four-source verification applied to all significant fixes
- decisions.md updated with any new decisions

---

### 4. Handle Failures

**IF ALL PASS:** Proceed to approval gate.
**IF ANY FAIL:** Return to step-06 fix cycle.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all verification checks pass, will you then read fully and follow: `{nextStepFile}` to begin the approval gate.
