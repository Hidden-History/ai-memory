---
name: 'step-07-final-verification'
description: 'Final verification pass confirming zero issues, test plan passed, and cohesion confirmed'
nextStepFile: './step-08-approval-gate.md'
---

# Step 7: Final Verification Pass

## STEP GOAL
When fix cycle reports zero issues and all test plan items pass, run a final verification to confirm everything is clean before presenting to the user.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Fix cycle results, test plan results, cohesion check results
- Limits: If any check fails, return to fix cycle.

## MANDATORY SEQUENCE

### 1. Verify DEV Review Results
- Zero legitimate issues confirmed across all milestone stories
- All test plan items confirmed PASS
- No test plan items skipped or deferred
- All pre-existing issues found during integration are fixed

### 2. Verify Architect Results
- Cohesion: CONFIRMED (or re-confirmed after fixes)
- All architectural violations from Step 4 are resolved
- No new architectural concerns introduced by fixes

### 3. Parzival Verification
- All acceptance criteria for all milestone stories confirmed satisfied
- All PRD Must Have features for this milestone are implemented
- No known legitimate issues remain anywhere in milestone scope
- Four-source verification applied to all significant fixes
- decisions.md updated with any new decisions

### 4. Handle Failures
**IF ALL PASS:** Proceed to approval gate.
**IF ANY FAIL:** Return to step-06 fix cycle.

## CRITICAL STEP COMPLETION NOTE
ONLY when all verification checks pass, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All three verification areas checked
- Zero issues confirmed from all sources
- All test plan items passed
- Cohesion confirmed
- Four-source verification applied

### FAILURE:
- Proceeding with unverified items
- Accepting partial test plan pass
- Not re-confirming cohesion after fixes
