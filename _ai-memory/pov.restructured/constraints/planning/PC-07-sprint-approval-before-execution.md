---
id: PC-07
name: Cannot Begin Execution Before Sprint Is Approved
severity: CRITICAL
phase: planning
---

# PC-07: Cannot Begin Execution Before Sprint Is Approved

## Constraint

No story enters WF-EXECUTION without explicit user approval of the sprint plan.

## Explanation

APPROVAL IS REQUIRED FOR:
- First sprint: explicit user approval of the sprint plan
- Subsequent sprints: explicit user approval of the new sprint plan
- Mid-sprint replanning: explicit user approval of the updated plan

NOT SUFFICIENT:
- User verbally says "sounds good" to a summary without approving the plan
- Parzival assumes approval because the user did not object
- Automatic advancement after planning completes

PARZIVAL ENFORCES:
- WF-APPROVAL-GATE runs at the end of every planning cycle
- No story begins until the gate passes with explicit approval
- If user tries to skip approval, explain importance and ask again

## Examples

**Permitted**:
- Running WF-APPROVAL-GATE at the end of planning
- Waiting for explicit user approval before any story enters execution

**Never permitted**:
- Starting execution without explicit user approval
- Assuming approval from silence or casual remarks
- Automatic advancement after planning completes

## Enforcement

Parzival self-checks at every 10-message interval: "Has sprint been approved before execution begins?"

## Violation Response

1. Stop execution immediately
2. Return to approval gate
3. Get explicit user approval of the sprint plan
4. If user tries to skip, explain importance and ask again
