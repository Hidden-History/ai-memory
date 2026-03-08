---
id: AC-04
name: Stories CANNOT Be Written Before Architecture Is Approved
severity: CRITICAL
phase: architecture
---

# AC-04: Stories CANNOT Be Written Before Architecture Is Approved

## Constraint

Epics and stories are created after architecture — never before.

## Explanation

WHY THIS IS CRITICAL:
- Stories without architecture lack accurate technical context
- Developers (DEV agents) will fill gaps with guesses
- Architecture decisions change story boundaries
- A story written pre-architecture may span the wrong component boundaries, causing rework when architecture is finalized

SEQUENCE IS NON-NEGOTIABLE:
1. PRD approved (Discovery)
2. Architecture designed and reviewed
3. User approves architecture
4. PM creates epics and stories using architecture as input
5. Readiness check validates cohesion

PARZIVAL ENFORCES:
- PM is NOT activated for story creation until architecture.md is reviewed by Parzival and approved by user
- If PM begins stories prematurely, stop immediately
- Any stories created before architecture approval are invalid and must be recreated after approval

## Examples

**Permitted**:
- Creating stories after architecture is reviewed by Parzival and approved by user
- Using architecture as input for story creation

**Never permitted**:
- Activating PM for story creation before architecture approval
- Keeping stories created before architecture approval (they must be recreated)

## Enforcement

Parzival self-checks at every 10-message interval: "Are stories being written before architecture approval? (must not be)"

## Violation Response

1. Stop story creation immediately
2. Complete architecture review and approval first
3. Any pre-architecture stories are invalid — recreate after approval
