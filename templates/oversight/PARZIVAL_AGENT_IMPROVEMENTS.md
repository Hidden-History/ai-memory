# Parzival Agent Improvements

This document tracks general improvements to Parzival agent behaviors that apply across all projects.

## Session Behaviors

### Session Startup Protocol

1. Check `PROJECT_STANDARDS.yaml` index exists
2. Verify `sprint-status.yaml` matches recent git log
3. Check this improvements file for actionable items
4. Load standards selectively based on task context

### During Work Protocol

1. Load only standards relevant to current task (~350 tokens each)
2. Check component-specific rules before recommendations
3. Escalate to user when project-specific knowledge needed

### Session Closeout Protocol

1. Verify documentation matches reality (no drift)
2. Update improvements file with lessons learned
3. Update standards if new patterns established

---

## Active Improvements

| ID | Improvement | Priority | Status | Added |
|----|-------------|----------|--------|-------|
| - | No active improvements | - | - | - |

## Priority Legend

| Priority | Meaning |
|----------|---------|
| **P0** | Critical - fix immediately |
| **P1** | High - fix soon |
| **P2** | Medium - nice to have |
| **P3** | Low - future consideration |

---

## Improvement Template

When adding a new improvement:

```markdown
| IMP-XXX | [Brief description] | P[0-3] | Open | [YYYY-MM-DD] |
```

### Details for IMP-XXX

**Problem**: [What issue was observed]
**Solution**: [What should be done differently]
**Applies to**: [Which agents/workflows affected]

---

## Completed Improvements

| ID | Improvement | Completed |
|----|-------------|-----------|
| - | None yet | - |

---

*Last reviewed: [DATE]*
