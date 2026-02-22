---
description: 'Create a handoff document mid-session (state snapshot)'
argument-hint: '[optional: specific focus or reason for snapshot]'
allowed-tools: Read, Grep, Glob, Write
---

# Mid-Session Handoff (State Snapshot)

Create a handoff document without ending the session. Useful for:
- Long sessions where context might degrade
- Before attempting risky operations
- When significant progress milestone reached
- Periodic state preservation

## Input
Context/reason: $ARGUMENTS

## Create State Snapshot

Create file: `oversight/session-logs/SESSION_SNAPSHOT_[TODAY]_[TIME].md`

```markdown
# Session Snapshot

**Date**: [YYYY-MM-DD]
**Time**: [HH:MM]
**Reason**: [Why this snapshot was created]
**Session Status**: In Progress

---

## Current State

### Active Work
- **Task**: [ID] [Title]
- **Status**: [What's been done so far]
- **Currently doing**: [What's in progress right now]
- **Next step**: [Immediate next action]

### Context That Would Be Lost
[Information from this conversation that future Parzival needs]
- [Important context point 1]
- [Important context point 2]
- [Decisions made in this session]
- [Approaches tried and results]

### Files Being Modified
- `[path]` - [What's being changed and current state]

### Assumptions Currently Active
- [Assumption 1] - [Status: Verified/Unverified]
- [Assumption 2] - [Status: Verified/Unverified]

### Things That Almost Went Wrong
[Near-misses or gotchas discovered this session]

### Open Questions
- [Question that came up but wasn't resolved]

---

## Recovery Instructions

If this snapshot is being read to recover session state:

1. Current task is [ID]: [Title]
2. We were in the middle of [specific activity]
3. The approach being used is [description]
4. Key files are [list]
5. Next action should be [specific next step]

## What's Working
[Things that are confirmed working as of this snapshot]

## What's Not Working
[Known issues at this point]

---

*Snapshot created during active session. Session continues.*
```

## After Creating Snapshot

```
State snapshot created: `session-logs/SESSION_SNAPSHOT_[timestamp].md`

Session continues. This snapshot can be used to:
- Recover if context degrades
- Resume if session is interrupted
- Reference what we've established so far

Continue with current work?
```

## Note

This is NOT a session end. The session continues after the snapshot.
For session end, use `/parzival-closeout` instead.
