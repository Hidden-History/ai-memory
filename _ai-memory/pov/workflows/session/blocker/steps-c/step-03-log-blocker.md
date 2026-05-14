---
name: 'step-03-log-blocker'
description: 'Log the blocker and chosen resolution to the blockers tracking file'
---

# Step 3: Log Blocker

**Final Step — Blocker Analysis Complete**

## STEP GOAL:

Record the blocker, analysis, and chosen resolution (or deferral) in the blockers log for cross-session visibility. If this is a new failure pattern, note it for the failure pattern library.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Blocker details from Step 1, analysis and user decision from Step 2
- Focus: Logging the blocker accurately — no further analysis
- Limits: Log the facts — do not editorialize or add commentary
- Dependencies: Blocker record from Step 1 and user's chosen resolution from Step 2

- Focus on accurate logging of blocker, analysis, and user's chosen resolution
**Behavioral Constraints:**
- FORBIDDEN to editorialize or add commentary beyond the facts
- Approach: Factual, structured logging with full field completion
- Flag new patterns for the failure pattern library

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Update Failure Pattern Library (If Applicable)

If this blocker represents a new pattern not already in the failure pattern library:
- Note that `{oversight_path}/learning/failure-pattern-library.md` should be updated with:
  - Pattern description
  - How it was detected
  - Resolution that worked
- If the file does not exist, skip this substep

---

### 3. Confirm Logging

Present confirmation to the user:

```
Blocker logged: BLK-[ID] in `{oversight_path}/tracking/blockers-log.md`
Severity: [severity]
Status: [Open/Resolved/Deferred]

[If new pattern]: Consider updating failure pattern library with this issue.

Continue with current work?
```

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Append blocker entry to blockers-log.md with all required fields before confirming
- Flag new failure patterns for the failure pattern library if applicable
- Present confirmation to user and await their direction to continue work
