---
description: 'Run verification protocol on completed work'
argument-hint: '<work item to verify> [checklist type: story|code|production]'
allowed-tools: Read, Grep, Glob, Bash, TaskCreate, TaskUpdate, TaskList
---

# Verification Protocol

Run verification checks on completed work item.

## Task Tracking

Use task tracking for multi-check verification:

```
1. TaskCreate(subject="Verify [work item]", activeForm="Running verification")
2. TaskUpdate(status="in_progress")
3. For each checklist section:
   - TaskCreate(subject="Check [section]", activeForm="Verifying [section]")
   - Execute checks → TaskUpdate(status="completed")
4. Final report includes verification task status
```

---

## Input
Work item: $ARGUMENTS

## Determine Checklist

Based on the work item type, select appropriate checklist:
- Story completion: `oversight/verification/checklists/story-complete.md`
- Code review: `oversight/verification/checklists/code-review.md`
- Production readiness: `oversight/verification/checklists/production-ready.md`
- Best practices: `oversight/verification/checklists/best-practices.md`

If checklist type specified in arguments, use that one.

## Verification Process

For each item in the checklist:
1. Execute the check (read files, run commands, inspect code)
2. Record PASS or FAIL
3. For failures, document specific issue
4. Note evidence for each check

## Output Format

```
## Verification Report

**Work Item**: [Description]
**Checklist Used**: [Which checklist]
**Date**: [Today's date]

---

### Overall Status: [PASSED | FAILED | PARTIAL]

### Checks Performed

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | [Check description] | PASS | [Evidence or note] |
| 2 | [Check description] | PASS | [Evidence or note] |
| 3 | [Check description] | FAIL | [What failed and why] |
| 4 | [Check description] | UNCERTAIN | [Partial/uncertain] |

### Summary
- **Passed**: [X] of [Y] checks
- **Failed**: [X] checks
- **Uncertain**: [X] checks

### Failed Checks Detail

**[Check Name]**
- Expected: [What should have been true]
- Actual: [What was found]
- Impact: [Why this matters]
- Suggested Fix: [How to address]

[Repeat for each failed check]

### Issues Found

| # | Issue | Severity | Recommendation |
|---|-------|----------|----------------|
| 1 | [Description] | [High/Medium/Low] | [What to do] |

### Parzival's Assessment

[Overall assessment of the work item's readiness]

**Confidence**: [Verified/Informed]

### Recommendation

[One of:]
- "All checks passed. Recommend approval."
- "Minor issues found. Recommend approval with noted caveats."
- "Significant issues found. Recommend addressing [X] before approval."
- "Critical issues found. Do not approve until resolved."

---
**Decision needed**: Do you approve this work item? [Or specify what needs to happen first]
```

## Important

- Parzival VALIDATES, user APPROVES
- All approvals require user's explicit decision
- Document findings regardless of outcome
- If uncertain about any check, mark as UNCERTAIN and explain
