---
description: 'Execute Parzival session closeout with handoff creation'
allowed-tools: Read, Grep, Glob, Write, Edit, TaskCreate, TaskUpdate, TaskList
---

# Session Closeout Protocol

Execute the Parzival session end protocol.

## Task Tracking (Optional)

For complex closeouts with many completed items, use task tracking:

```
TaskCreate(subject="Session closeout", activeForm="Creating session handoff")
TaskUpdate(status="in_progress")
# ... create handoff, update index, etc ...
TaskUpdate(status="completed")
```

---

## Step 1: Create Session Handoff

Create file: `oversight/session-logs/SESSION_HANDOFF_[TODAY'S DATE].md`

Required content:
```markdown
# Session Handoff: [Primary Topic]

**Date**: [YYYY-MM-DD]
**Session Duration**: [Approximate time]

## Executive Summary
[2-3 sentences: What was accomplished, current state, what's next]

## Work Completed
- [Task ID]: [Description of what was done]
- [Include all completed items with IDs]

## Current Status
- **Active Task**: [ID] [Title] - [Status]
- **Blockers**: [List or "None"]
- **In Progress**: [What's partially done]

## Issues Encountered
[For each issue:]
- **Issue**: [Description]
- **Resolution**: [How it was resolved OR "Pending"]
- **Learning**: [What to remember for next time]

## Files Modified
- `[path/to/file]` - [What changed]
- [List all modified files]

## Decisions Made
- [Decision]: [Rationale]
- [List any decisions from this session]

## Next Steps (Recommended)
1. [Most important next action]
2. [Second priority]
3. [Third priority]

## Open Questions
- [Any unresolved questions]
- [Things that need user's input]

## Context for Future Parzival
[Anything a new Claude instance would need to know that isn't captured above.
Write as if the reader has never seen this project.]

---
*Handoff created by Parzival session closeout protocol*
```

## Step 2: Update Session Work Index

Add entry to `oversight/SESSION_WORK_INDEX.md`:
```markdown
### [YYYY-MM-DD]: [Brief Topic]
- **Task:** [Task title]
- **Task ID:** [ID]
- **Status:** [In Progress/Complete/Blocked]
- **Progress:** [One sentence on what was accomplished]
- **Handoff:** `session-logs/SESSION_HANDOFF_[DATE].md`
```

## Step 3: Request Task Updates

Ask user:
- "Should I update task [ID] status to [suggested status]?"
- For completed tasks: "Mark [ID] as done?"
- For new items: "Create task for [discovered item]?"

Wait for responses before proceeding.

## Step 4: Request Documentation Updates

Ask user:
- "Any decisions to add to decisions log?"
- "Any new risks identified?"
- "Update main documentation with today's progress?"

Wait for responses.

## Step 5: Final Confirmation

```
## Session Closeout Complete

**Handoff**: `session-logs/SESSION_HANDOFF_[DATE].md`
**Index Updated**: check

### Summary
- [Key accomplishments]
- [Current state]
- [Recommended next steps]

### Checklist
- [x] Handoff document created
- [x] Session work index updated
- [ ] Task status updates: [Pending your approval]
- [ ] Documentation updates: [Pending your approval]

Ready for next session. Anything else before we close?
```
