---
name: 'step-07-exit-cycle'
description: 'Verify all exit conditions are met, prepare the review cycle summary, and hand off to WF-APPROVAL-GATE'
---

# Step 7: Exit the Cycle

## STEP GOAL
Verify that all exit conditions are met (zero legitimate issues across all passes, all uncertain issues resolved, all fixes verified), prepare the review cycle summary for WF-APPROVAL-GATE, and hand off. This is the terminal step of the review cycle.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All pass records, all classification records, the final clean review report, the complete implementation
- Limits: Do not re-open the cycle once exit is confirmed. Do not advance without verifying every exit condition.

## MANDATORY SEQUENCE

### 1. Verify Exit Conditions
DEV review has returned: "Code review complete -- zero issues found"

Parzival verifies ALL of the following:
- All legitimate issues from all prior passes are resolved
- All uncertain issues are resolved (researched or user-decided)
- No new issues introduced by fixes remain unaddressed
- Fix verification passed for all applied fixes

### 2. Confirm Cannot-Exit Conditions Are Clear
The cycle CANNOT exit if ANY of the following are true:
- Any legitimate issue from any pass remains unresolved
- Any uncertain issue is still pending without a resolution path
- Any fix verification check failed
- DEV's zero-issues claim is implausible given complexity (request second look)
- Pre-existing issues were found but not yet addressed

If any cannot-exit condition is true, return to step-03 for re-processing.

### 3. Prepare Review Cycle Summary
Build the handoff summary for WF-APPROVAL-GATE:

```
REVIEW CYCLE COMPLETE -- Ready for approval

Task:              [task/story name]
Total passes:      [N]
Total issues found: [N across all passes]
  Legitimate fixed: [N]
  Non-issues:       [N] (documented, excluded)
  Pre-existing fixed: [N]

Fix verification:  All fixes verified against project requirements
Zero issues:       Confirmed -- DEV review pass [N] returned clean

IMPLEMENTATION SUMMARY:
  [What was built -- in Parzival's words, not DEV's]
  [Key decisions made during implementation if any]
  [Files created or modified]

ISSUES RESOLVED (notable ones):
  [Any significant issues found and fixed -- worth the user knowing about]

READY FOR: User approval
```

### 4. Hand Off to WF-APPROVAL-GATE
- Review cycle is COMPLETE
- Proceed to WF-APPROVAL-GATE with the prepared summary
- Do not re-open the cycle

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step. When exit conditions are verified and the summary is prepared, hand off to WF-APPROVAL-GATE. Do not load another step file.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every exit condition was individually verified
- Cannot-exit conditions were explicitly checked
- Review cycle summary is complete and accurate
- Summary is written in Parzival's words, not copied from DEV output
- Clean handoff to WF-APPROVAL-GATE

### FAILURE:
- Exiting with unresolved legitimate issues
- Exiting with pending uncertain issues
- Exiting without verifying all fixes
- Copying DEV output into the summary instead of writing Parzival's own summary
- Re-opening the cycle after confirmed exit
