---
name: 'step-05-receive-fixes'
description: 'Verify DEV fix report, confirm each fix addresses root cause, check for new issues, then re-run legitimacy checks'
nextStepFile: './step-03-process-review-report.md'
---

# Step 5: Receive Fix Report and Re-Review

## STEP GOAL
After DEV applies fixes and re-reviews, Parzival verifies each fix, checks for new issues introduced by fixes, and runs WF-LEGITIMACY-CHECK again on the updated review report. This step loops back to step-03 for re-processing.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: DEV's fix report, DEV's re-review report, prior pass correction instruction, all prior pass records
- Limits: Do not trust DEV's self-assessment alone — Parzival reads each fix and verifies independently

## MANDATORY SEQUENCE

### 1. Receive Fix Report from DEV
Wait for DEV to report back with:
- Confirmation that each issue was fixed
- How each fix was implemented
- DEV's own re-review result after fixes

### 2. Verify Each Fix
For each fix reported by DEV:
- Was the specific issue actually fixed? Read the fix — do not trust DEV's self-assessment alone
- Does the fix address the root cause, not just the symptom?
- Does the fix comply with project requirements? Apply GC-5 four-source verification
- Did the fix introduce any new issues? New issues from fixes are legitimate issues
- Did DEV stay within fix scope? Only the listed issues should have been touched. Flag any changes outside fix scope

### 3. Check Uncertain Issue Status
- Are all uncertain issues still correctly held (not touched without resolution)?
- Have any uncertain issues been resolved since the correction instruction was sent?
- If resolved: classify per WF-LEGITIMACY-CHECK result and add to appropriate list

### 4. Update Cycle Tracking
Record this pass in the cycle tracking data:
- Pass number
- Issues found in re-review
- New issues introduced by fixes
- Issues resolved from prior pass
- Issues still open
- Uncertain issues resolved

### 5. Route to Re-Processing
The DEV re-review produces a new report. This report must be processed through step-03 again:
- Route back to {nextStepFile} (step-03-process-review-report)
- Step-03 will run WF-LEGITIMACY-CHECK on ALL issues in the new report
- This includes: unresolved prior issues, new issues from fixes, additional pre-existing issues surfaced during fixing
- The cycle continues until the report is clean

## CRITICAL STEP COMPLETION NOTE
ONLY when fix verification is complete and cycle tracking is updated, load and read fully {nextStepFile} to re-process the updated review report.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every fix was independently verified by Parzival (not just DEV's claim)
- Fix scope compliance was checked
- New issues introduced by fixes were identified
- Uncertain issues were correctly tracked
- Cycle tracking record was updated
- Re-review report routed back to step-03 for full processing

### FAILURE:
- Trusting DEV's self-assessment without independent verification
- Missing new issues introduced by fixes
- Allowing changes outside fix scope to pass
- Touching uncertain issues without resolution
- Skipping cycle tracking update
- Not routing back to step-03 for re-processing
