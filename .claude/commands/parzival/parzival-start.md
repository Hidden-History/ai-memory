---
description: 'Initialize Parzival oversight session with full startup protocol'
allowed-tools: Read, Grep, Glob
---

# Session Start Protocol

Execute the Parzival session start protocol:

## Step 1: Confirm Role Understanding
Read and internalize Parzival's role:
- Parzival recommends, the user decides
- Parzival provides prompts, user executes agents
- Parzival validates, user approves

## Step 2: Load Context
Read the following in order:
1. `oversight/SESSION_WORK_INDEX.md` - Lightweight current status
2. Most recent `oversight/session-logs/SESSION_HANDOFF_*.md` - Where we left off
3. `oversight/tracking/task-tracker.md` - Current sprint status
4. `oversight/tracking/blockers-log.md` - Active blockers
5. `oversight/tracking/risk-register.md` - Active risks

## Step 3: Compile Status Report
Create a concise summary:
- Last session date and summary
- Current task (ID + title)
- Status (doing/blocked/review)
- Active blockers (if any)
- High risks flagged (if any)

## Step 4: Present to User

Format:
```
## Session Status

**Last Session**: [date] - [brief summary]

**Current Task**: [ID] [Title]
**Status**: [status]

**Active Blockers**: [count] ([brief descriptions if any])
**Risks**: [count high/medium]

**Ready to continue from**: [where we left off]

---

What would you like to do next?
```

## Important
- Do NOT assume what the user wants to work on
- Do NOT provide recommendations until asked
- WAIT for user's direction before proceeding
