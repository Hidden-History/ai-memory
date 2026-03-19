---
id: EC-09
name: Sprint Status Must Be Updated After Every Story State Transition
severity: MEDIUM
phase: execution
---

# EC-09: Sprint Status Must Be Updated After Every Story State Transition

## Constraint

sprint-status.yaml is the authoritative source of sprint state and must always be current.

## Explanation

UPDATE SPRINT-STATUS.YAML WHEN:
- Story moves from READY to IN-PROGRESS (DEV dispatched)
- Story moves from IN-PROGRESS to IN-REVIEW (implementation complete)
- Story moves from IN-REVIEW to PENDING-APPROVAL (zero issues confirmed)
- Story moves from PENDING-APPROVAL to COMPLETE (user approved)
- Story moves to BLOCKED (unresolved blocker)
- Story moves to ON-HOLD (user requested hold)

ALSO UPDATE project-status.md:
- active_task field reflects current story
- open_issues count is current
- last_session_summary captures current state

WHY:
- If a session ends mid-story, Parzival must be able to pick up exactly where things left off from project-status.md alone
- Without current status, next session starts with incorrect state
- Accurate status prevents duplicate work and missed steps

PARZIVAL ENFORCES:
- Status update is the first action after every state transition
- Never transition a story state without updating sprint-status.yaml
- End of session: verify sprint-status.yaml reflects exact current state

## Examples

**Permitted**:
- Updating sprint-status.yaml immediately after every story state transition
- Verifying sprint-status.yaml at end of session

**Never permitted**:
- Transitioning a story state without updating sprint-status.yaml
- Ending a session without verifying sprint-status.yaml reflects current state

## Enforcement

Parzival self-checks at every 10-message interval: "Is sprint-status.yaml current after every state transition?"

## Violation Response

1. Update sprint-status.yaml immediately with correct state
2. Verify accuracy against actual story state
3. Also update project-status.md active_task and open_issues
