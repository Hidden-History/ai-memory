---
name: 'session-status-checklist'
description: 'Quality gate rubric for session-status'
---

# Session Status — Validation Checklist

## Pre-Execution Checks

- [ ] At least one tracking file exists at the oversight path
- [ ] Workflow is being used for a quick status check, not a full session start

## Step Completion Checks

### Inline Step: Read Tracking Files
- [ ] SESSION_WORK_INDEX.md was read (or noted as "Not found")
- [ ] task-tracker.md was read (or noted as "Not found")
- [ ] blockers-log.md was read (or noted as "Not found")
- [ ] risk-register.md was read (or noted as "Not found")

### Inline Step: Find Last Session
- [ ] Date of last session extracted from SESSION_WORK_INDEX or latest handoff file
- [ ] Topic/focus of last session identified
- [ ] Outcome of last session identified

### Inline Step: Compile and Present Status
- [ ] All available tracking files were read
- [ ] Status is accurate and reflects current file contents
- [ ] Output is concise and follows the defined format
- [ ] No recommendations were given unless asked

## Workflow-Level Checks

- [ ] Status output uses the exact defined format
- [ ] No files were modified during status check
- [ ] Workflow treated as read-only throughout

## Anti-Pattern Checks

- [ ] Did NOT skip tracking files that exist
- [ ] Did NOT provide inaccurate status information
- [ ] Did NOT give unsolicited recommendations
- [ ] Did NOT modify any files during status check
- [ ] Did NOT treat this as a full session start
- [ ] Did NOT load full session context (handoffs, risk registers) beyond required tracking files

_Validated by: Parzival Quality Gate on {date}_
