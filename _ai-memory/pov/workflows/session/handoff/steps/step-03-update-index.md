---
name: 'step-03-update-index'
description: 'Update the SESSION_WORK_INDEX with a reference to the new handoff and confirm to the user'
---

# Step 3: Update Index and Confirm

## STEP GOAL
Add a reference to the new handoff in the SESSION_WORK_INDEX and confirm to the user that the snapshot is complete. The session continues after this.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The handoff file path and content from Step 2
- Limits: Update the index and confirm -- do not end the session

## MANDATORY SEQUENCE

### 1. Update SESSION_WORK_INDEX

Add or update entry in `{oversight_path}/SESSION_WORK_INDEX.md`:

```markdown
### [YYYY-MM-DD]: [Brief Topic] (Snapshot)
- **Task**: [Task title]
- **Task ID**: [ID]
- **Status**: In Progress
- **Progress**: [One sentence on current state]
- **Snapshot**: `session-logs/SESSION_HANDOFF_{date}.md`
```

### 2. Confirm to User

Present:

```
State snapshot created: `{oversight_path}/session-logs/SESSION_HANDOFF_{date}.md`
Index updated: `{oversight_path}/SESSION_WORK_INDEX.md`

Session continues. This snapshot can be used to:
- Recover if context degrades
- Resume if session is interrupted
- Reference what has been established so far

Continue with current work?
```

### 3. Session Continues

This is NOT a session end. The session continues after the snapshot.
- Do not run closeout procedures
- Do not update task statuses
- Do not ask about documentation updates
- Resume working on whatever was in progress

## CRITICAL STEP COMPLETION NOTE
This is a **terminal step**. The workflow is complete once the index is updated and the user is informed. Work resumes based on user direction.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- SESSION_WORK_INDEX is updated with a reference to the snapshot
- User is informed of the snapshot location
- Session continues normally after the snapshot

### FAILURE:
- Not updating the SESSION_WORK_INDEX
- Treating this as a session end
- Running closeout procedures after a snapshot
- Not confirming the snapshot to the user
