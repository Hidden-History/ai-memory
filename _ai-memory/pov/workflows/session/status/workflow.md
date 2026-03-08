---
name: session-status
description: 'Quick project status check without full session startup. Reads tracking files and presents concise summary.'
firstStep: null  # Single-step workflow — executes inline within this file
---

# Session Status

**Goal:** Provide a fast, read-only status snapshot so the user can see where the project stands without committing to a full session start.

---

## WORKFLOW ARCHITECTURE

This is a **single-step workflow** -- no step files are needed. The entire workflow executes within this file.

### Execution Rules
1. **READ ONLY**: This workflow reads tracking files but writes nothing
2. **CONCISE OUTPUT**: Present the status in the defined format, nothing more
3. **NO RECOMMENDATIONS**: Do not provide suggestions unless the user asks
4. **NO SESSION START**: This does NOT initialize a session -- use `{workflows_path}/session/start/workflow.md` for that

### Anti-Patterns
- Do not start loading full session context (handoffs, risk registers, etc.)
- Do not provide recommendations or next-step suggestions unprompted
- Do not modify any files
- Do not treat this as a session start

---

## MANDATORY SEQUENCE

### 1. Read Tracking Files

Read the following files. If any file does not exist, note it as "Not found" in the output.

1. `{oversight_path}/SESSION_WORK_INDEX.md` -- current session state
2. `{oversight_path}/tracking/task-tracker.md` -- task statuses
3. `{oversight_path}/tracking/blockers-log.md` -- active blockers
4. `{oversight_path}/tracking/risk-register.md` -- high/critical risks

### 2. Find Last Session

From SESSION_WORK_INDEX or the most recent `{oversight_path}/session-logs/SESSION_HANDOFF_*.md` file, extract:
- Date of last session
- Topic/focus of last session
- Outcome of last session

### 3. Compile and Present Status

Present using this exact format:

```
## Quick Status

**Current Sprint**: [Sprint ID/Name or "No active sprint"]
**Active Tasks**: [Count]

### In Progress
| Task | Status | Assignee |
|------|--------|----------|
| [ID]: [Title] | [Status] | [Who] |

### Blockers ([Count] Active)
- [BLK-ID]: [Brief description] - [Severity]

### Risks ([Count] High/Critical)
- [RISK-ID]: [Brief description] - [Status]

### Last Session
- **Date**: [Date]
- **Topic**: [What was worked on]
- **Outcome**: [Result]

---
Need details on anything specific?
```

---

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All available tracking files were read
- Status is accurate and reflects current file contents
- Output is concise and follows the defined format
- No recommendations were given unless asked

### FAILURE:
- Skipping tracking files that exist
- Providing inaccurate status information
- Giving unsolicited recommendations
- Modifying any files during status check
- Treating this as a full session start
