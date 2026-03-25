---
name: 'session-handoff-instructions'
description: 'Mid-session handoff: capture state snapshot for cross-session continuity'
---

# session-handoff — Instructions

## Prerequisites

- An active Parzival oversight session
- `SESSION_WORK_INDEX.md` exists in the oversight workspace
- A reason to capture state has occurred (pre-risky operation, progress milestone, context degradation risk)

## Workflow Overview

Session-handoff creates a mid-session state snapshot to preserve context without ending the session. It is distinct from session-close, which is the full end-of-session protocol. After a handoff is created, the session continues normally.

The handoff captures the current state of all active work, decisions in progress, and context that would be lost if the session ended unexpectedly. It writes a timestamped handoff document and updates the SESSION_WORK_INDEX so future sessions can recover from this snapshot.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-capture-state.md` | Gather current work state: active stories, open blockers, recent decisions, context that would be lost |
| 2 | `step-02-write-handoff.md` | Write the handoff document using the session-handoff template; include recovery instructions |
| 3 | `step-03-update-index.md` | Add the handoff file reference to `SESSION_WORK_INDEX.md` |

## Key Decisions

- **Handoff vs. closeout**: This workflow is for mid-session snapshots only; use `session/close` to end a session
- **Recovery instructions**: Every handoff must include explicit recovery steps — never vague descriptions
- **Context specificity**: "Working on stuff" is not acceptable; every item must be named and described

## Outputs

- Handoff document written to the oversight workspace (timestamped)
- `SESSION_WORK_INDEX.md` updated with handoff reference
- Session continues after completion

## Exit Conditions

The workflow exits when:
- The handoff document has been written
- `SESSION_WORK_INDEX.md` has been updated
- The session continues (no closeout occurs)
