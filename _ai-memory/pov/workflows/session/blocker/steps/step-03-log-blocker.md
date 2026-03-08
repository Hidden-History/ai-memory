---
name: 'step-03-log-blocker'
description: 'Log the blocker and chosen resolution to the blockers tracking file'
---

# Step 3: Log Blocker

## STEP GOAL
Record the blocker, analysis, and chosen resolution (or deferral) in the blockers log for cross-session visibility. If this is a new failure pattern, note it for the failure pattern library.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Blocker details from Step 1, analysis and user decision from Step 2
- Limits: Log the facts -- do not editorialize or add commentary

## MANDATORY SEQUENCE

### 1. Write Blocker Entry

Append to `{oversight_path}/tracking/blockers-log.md`:

```markdown
### BLK-[ID]: [Brief Title]
- **Date**: [YYYY-MM-DD]
- **Severity**: [Critical/High/Medium/Low]
- **Affected Task**: [Task ID]
- **Description**: [Specific description from Step 1]
- **Root Cause**: [From Step 2 analysis]
- **Confidence**: [Verified/Informed/Inferred/Uncertain]
- **Resolution**: [Option chosen by user, or "Deferred"]
- **Status**: [Open/Resolved/Deferred]
```

### 2. Update Failure Pattern Library (If Applicable)

If this blocker represents a new pattern not already in the failure pattern library:
- Note that `{oversight_path}/learning/failure-pattern-library.md` should be updated with:
  - Pattern description
  - How it was detected
  - Resolution that worked
- If the file does not exist, skip this substep

### 3. Confirm Logging

Present confirmation to the user:

```
Blocker logged: BLK-[ID] in `{oversight_path}/tracking/blockers-log.md`
Severity: [severity]
Status: [Open/Resolved/Deferred]

[If new pattern]: Consider updating failure pattern library with this issue.

Continue with current work?
```

## CRITICAL STEP COMPLETION NOTE
This is a **terminal step**. The workflow is complete once the blocker is logged and confirmed. Work continues based on user direction.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Blocker is logged with all required fields
- Entry accurately reflects the captured details and user's chosen resolution
- User is informed of the logged entry
- New patterns are flagged for the failure pattern library

### FAILURE:
- Logging incomplete or vague blocker information
- Logging a resolution the user did not choose
- Failing to append to the blockers log file
- Skipping the confirmation step
