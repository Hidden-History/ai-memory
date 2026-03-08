---
name: 'step-04-report-results'
description: 'Present the verification report with overall status, detailed results, and recommendation'
---

# Step 4: Report Verification Results

## STEP GOAL
Present the complete verification report to the user with all check results, a summary, and a recommendation. The user makes the approval decision.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All check results from Step 3
- Limits: Parzival validates and recommends -- the user approves or rejects

## MANDATORY SEQUENCE

### 1. Determine Overall Status

Based on check results:
- **PASSED**: All checks are PASS or N/A (zero FAIL, zero UNCERTAIN)
- **FAILED**: One or more checks are FAIL
- **PARTIAL**: No FAIL checks, but one or more UNCERTAIN checks

### 2. Present Verification Report

Use this exact format:

```
## Verification Report

**Work Item**: [Description]
**Checklist Used**: [Verification type]
**Date**: [YYYY-MM-DD]

---

### Overall Status: [PASSED / FAILED / PARTIAL]

### Checks Performed

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | [Check description] | PASS | [Evidence or note] |
| 2 | [Check description] | FAIL | [What failed and why] |
| 3 | [Check description] | UNCERTAIN | [What is unclear] |

### Summary
- **Passed**: [X] of [Y] checks
- **Failed**: [X] checks
- **Uncertain**: [X] checks
- **N/A**: [X] checks
```

### 3. Detail Failed Checks (If Any)

For each FAIL result:
```
### Failed Checks Detail

**[Check Name]**
- Expected: [What should have been true]
- Actual: [What was found]
- Impact: [Why this matters]
- Suggested Fix: [How to address]
```

### 4. Present Assessment and Recommendation

```
### Assessment

[Overall assessment of the work item's readiness]

**Confidence**: [Verified/Informed]

### Recommendation

[One of:]
- "All checks passed. Recommend approval."
- "Minor issues found. Recommend approval with noted caveats."
- "Significant issues found. Recommend addressing [specific items] before approval."
- "Critical issues found. Do not approve until resolved."

---
**Decision needed**: Do you approve this work item?
```

### 5. Wait for User Decision

- Do NOT approve on behalf of the user
- If the user requests re-verification after fixes, restart from Step 3 with the same checklist
- Record the user's decision for session records

### 6. Log Verification Result

After the user decides, note the verification outcome:
- Work item verified: [yes/no]
- Date: [YYYY-MM-DD]
- Result: [PASSED/FAILED/PARTIAL]
- User decision: [Approved/Rejected/Deferred]

## CRITICAL STEP COMPLETION NOTE
This is a **terminal step**. The workflow is complete once the user has made their approval decision.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Report is presented in the defined format
- All check results are included
- Failed checks have detailed explanations with suggested fixes
- Recommendation is proportional to findings
- User makes the approval decision
- Verification outcome is recorded

### FAILURE:
- Omitting check results from the report
- Approving without user's explicit decision
- Presenting a recommendation that contradicts the findings
- Not detailing failed checks
- Skipping the user decision step
