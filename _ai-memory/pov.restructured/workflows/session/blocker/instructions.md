---
name: 'session-blocker-instructions'
description: 'Blocker analysis: capture, diagnose root cause, propose resolution options, log to blockers tracker'
---

# session-blocker — Instructions

## Prerequisites

- An active Parzival oversight session
- `blockers-log.md` exists in the oversight workspace
- The blocker to be captured has been described by the user or identified by Parzival

## Workflow Overview

Session-blocker captures, analyzes, and logs a blocker that is impeding progress. The workflow structures the blocker with a unique BLK-ID, determines whether it can be resolved immediately or requires escalation, and records the outcome in the blockers log.

Parzival drives the analysis — identifying the blocker type, affected work, possible resolution paths, and recommended action. The user decides on resolution approach. The blocker is always logged regardless of whether it is resolved in-session, ensuring no blocker is lost.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-capture-blocker.md` | Capture the blocker details: description, affected story/phase, blocker type, and severity |
| 2 | `step-02-analyze-and-resolve.md` | Analyze root cause, identify resolution options, present recommendation to user |
| 3 | `step-03-log-blocker.md` | Assign BLK-ID, write entry to `blockers-log.md`, update sprint status if applicable |

## Key Decisions

- **Resolution vs. escalation**: Parzival recommends whether the blocker can be resolved now or must be escalated/deferred
- **BLK-ID assignment**: IDs are sequential; Parzival reads existing log to determine next available ID
- **Sprint impact**: If the blocker affects sprint capacity, `sprint-status.yaml` must be updated

## Outputs

- Blocker entry written to `blockers-log.md` with assigned BLK-ID
- Resolution recommendation presented to user
- Sprint status updated if the blocker affects the active sprint

## Exit Conditions

The workflow exits when:
- The blocker has been logged in `blockers-log.md` with a BLK-ID
- The user has acknowledged the log entry
