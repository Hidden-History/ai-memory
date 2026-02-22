---
description: 'Quick project status check without full session startup'
allowed-tools: Read, Grep, Glob
---

# Quick Status Check

Provide a quick status summary without the full session start protocol.

## Gather Status

Check:
1. `oversight/tracking/task-tracker.md` - Current tasks
2. `oversight/tracking/blockers-log.md` - Active blockers
3. `oversight/tracking/risk-register.md` - High/Critical risks
4. Most recent `oversight/session-logs/SESSION_HANDOFF_*.md` - Last session

## Output Format

```
## Quick Status

**Current Sprint**: [Sprint ID/Name]
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

## Notes
- This is a quick check, not a full session start
- Do not provide recommendations unless asked
- Keep output concise
