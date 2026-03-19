---
name: Bug Status Workflow
description: Reference for the bug lifecycle states, transition rules, and GC cross-references used by Parzival when tracking BUG-XXX items.
---

# Bug Status Workflow

Parzival tracks all bugs through a defined lifecycle. Every BUG-XXX item moves through these states in sequence. Transitions are gated by protocol rules — skipping steps is not permitted.

## Status Flow

```
New → In Progress → Fixed → Verified → Closed
                      ↓
                  Reopened (if verification fails)
```

## Status Definitions

| Status | Definition | Who Transitions |
|--------|-----------|----------------|
| **New** | Bug identified, BUG-XXX assigned, documented using BUG_TEMPLATE.md | Parzival (per GC-16) |
| **In Progress** | Fix work has been dispatched to an agent | Parzival (after agent dispatch) |
| **Fixed** | Agent reports fix complete, awaiting verification | Agent (via task completion) |
| **Verified** | Post-fix verification passed — no regressions, all checks green | Parzival (after review cycle) |
| **Closed** | User has confirmed resolution, documentation updated | User (Parzival recommends, user decides — Parzival NEVER closes bugs) |
| **Reopened** | Verification failed or regression found — returns to In Progress | Parzival (per GC-12 — loop until zero) |

## Transition Rules

1. **New → In Progress**: Only after GC-16 protocol complete (BUG-XXX assigned, template used, root cause documented)
2. **In Progress → Fixed**: Only the implementing agent can mark as Fixed (via DONE WHEN criteria)
3. **Fixed → Verified**: Only after full post-fix verification (GC-05 four-source check + GC-12 review cycle)
4. **Verified → Closed**: Only the user can close — Parzival NEVER closes bugs
5. **Any → Reopened**: If verification fails OR regression found at any point after Fixed

## Cross-References

- **GC-05**: Verify fixes against 4 sources
- **GC-07**: Never pass work with known issues
- **GC-12**: Loop until zero legitimate issues
- **GC-16**: Mandatory bug tracking protocol
- **Review cycle**: `{workflows_path}/cycles/review-cycle/workflow.md`
