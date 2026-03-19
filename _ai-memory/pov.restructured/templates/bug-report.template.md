---
name: "bug-report"
description: "Standard bug report format for tracking issues found during task execution and review cycles"
---

## BUG-{number}: {title}

| Field | Value |
|-------|-------|
| **ID** | BUG-{number} |
| **Severity** | {severity: Critical / High / Medium / Low} |
| **Status** | {status: New / In Progress / Fixed / Verified / Closed / Reopened} |
| **Found During** | {task_id} / {phase} |
| **Found By** | {agent_or_reviewer} |
| **Date Found** | {date} |
| **Related Issues** | {linked_bugs_decisions_tasks} |

### Description
{description — what is wrong, with specific observable behavior}

### Reproduction Steps
1. {step_1}
2. {step_2}
3. {step_n}

**Expected**: {expected_behavior}
**Actual**: {actual_behavior}

### Evidence
{file paths, test output, error messages, screenshots — concrete proof}

### Root Cause
{root_cause — why it happens, not just what happens}

### Fix
{fix_description — what was changed and why}

### Verification
- [ ] Fix addresses root cause (not just symptoms)
- [ ] No regressions introduced
- [ ] Related functionality still works
- [ ] Evidence of fix: {test_output_or_file_check}

**Verified By**: {verifier}
**Verification Date**: {date}

---

### Bug ID Convention
Assign sequential IDs: BUG-001, BUG-002, etc. Check `{oversight_path}/bugs/` for the highest existing ID before assigning.

### Status Workflow
```
New → In Progress → Fixed → Verified → Closed
                      ↓
                  Reopened (if verification fails) → In Progress
```

### Severity Guide
- **Critical**: System down, data loss, security vulnerability
- **High**: Major feature broken, no workaround
- **Medium**: Feature degraded, workaround exists
- **Low**: Cosmetic, minor inconvenience
