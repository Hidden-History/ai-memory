---
id: IC-03
name: All Milestone Stories Must Be Complete Before Integration Begins
severity: HIGH
phase: integration
---

# IC-03: All Milestone Stories Must Be Complete Before Integration Begins

## Constraint

Integration cannot begin with incomplete stories in its scope.

## Explanation

COMPLETE MEANS:
- Story implementation approved by user (through WF-APPROVAL-GATE)
- Zero legitimate issues confirmed in story review cycle
- All acceptance criteria explicitly satisfied
- Story marked COMPLETE in sprint-status.yaml

NOT COMPLETE:
- Story in IN-REVIEW state (review still running)
- Story in PENDING-APPROVAL state (awaiting user approval)
- Story in BLOCKED state
- Story with known deferred issues

WHY:
- Integration verifies that completed stories work together
- An incomplete story will fail integration tests
- Running integration on incomplete stories wastes the review cycle
- It gives a false signal that integration issues are integration problems when they are actually story completion problems

PARZIVAL ENFORCES:
- Phase 1 checks sprint-status.yaml for all milestone stories
- Any incomplete story, resolve story completion first
- Only then begin integration scope definition

## Examples

**Permitted**:
- Starting integration only after all milestone stories are marked COMPLETE
- Resolving incomplete stories before beginning integration

**Never permitted**:
- Starting integration with stories in IN-REVIEW or PENDING-APPROVAL state
- Starting integration with BLOCKED stories in scope
- Starting integration with known deferred issues

## Enforcement

Parzival self-checks at every 10-message interval: "Are all milestone stories confirmed complete before integration began?"

## Violation Response

1. Stop integration
2. Check sprint-status.yaml for all milestone stories
3. Resolve any incomplete stories first
4. Resume integration only after all stories are COMPLETE
