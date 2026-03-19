---
name: 'session-close-instructions'
description: 'Session closeout: summarize work, update tracking, create handoff, confirm next steps'
---

# session-close — Instructions

## Prerequisites

- An active Parzival oversight session that is ready to end
- All in-progress work has reached a stable stopping point
- Tracking files (`SESSION_WORK_INDEX.md`, `sprint-status.yaml`, `blockers-log.md`) are accessible

## Workflow Overview

Session-close is the full end-of-session protocol. It summarizes session work, updates all tracking documents, creates a final handoff document for context continuity, and attempts to save the session to Qdrant memory before the user confirms closure.

Unlike session-handoff (which is a mid-session snapshot), session-close formally ends the session. All tracking is updated to reflect the session's outcomes, ensuring the next session can start with accurate state. A Qdrant save is attempted but session close is never blocked by Qdrant unavailability.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-summarize-session.md` | Compile a summary of all work completed, decisions made, and blockers encountered this session |
| 2 | `step-02-update-tracking.md` | Update `SESSION_WORK_INDEX.md`, `sprint-status.yaml`, and `blockers-log.md` with session outcomes |
| 3 | `step-03-create-handoff.md` | Write the session closeout handoff document using the handoff template |
| 4 | `step-04-save-and-confirm.md` | Attempt Qdrant save via `/parzival-save-handoff`; confirm session closure with the user |

## Key Decisions

- **Qdrant save**: Attempted but not blocking — if skills are unavailable, close the session anyway
- **Tracking completeness**: All three tracking files must be updated before closure; none are optional
- **Handoff quality**: Recovery instructions must be specific enough for the next session to resume without context loss

## Outputs

- Session summary document
- Updated tracking files (`SESSION_WORK_INDEX.md`, `sprint-status.yaml`, `blockers-log.md`)
- Closeout handoff document written
- Qdrant save attempted

## Exit Conditions

The workflow exits when:
- All tracking files have been updated
- The handoff document has been written
- The Qdrant save has been attempted (success or graceful skip)
- The user has confirmed session closure
