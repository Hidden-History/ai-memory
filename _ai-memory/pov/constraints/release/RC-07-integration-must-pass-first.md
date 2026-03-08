---
id: RC-07
name: Integration Must Have Passed Before Release Begins
severity: CRITICAL
phase: release
---

# RC-07: Integration Must Have Passed Before Release Begins

## Constraint

Release cannot run without a passed and approved integration gate.

## Explanation

PASSED INTEGRATION MEANS:
- WF-INTEGRATION completed with full test plan pass
- Architect cohesion check returned CONFIRMED
- Zero legitimate issues across all milestone stories
- User approved integration (WF-APPROVAL-GATE passed)

THIS CANNOT BE BYPASSED BY:
- "We trust the stories were done well"
- "We're in a hurry to ship"
- "The changes are small enough that integration isn't needed"
- User request to skip integration

PARZIVAL ENFORCES:
- Phase 1 of WF-RELEASE confirms integration approval on record
- If integration was not run, block release, run integration first
- Release is downstream of integration — not parallel to it

## Examples

**Permitted**:
- Starting release only after integration has fully passed with user approval
- Blocking release when integration has not been run

**Never permitted**:
- Starting release without a passed integration gate
- Bypassing integration because "the changes are small"
- Running release in parallel with integration

## Enforcement

Parzival self-checks at every 10-message interval: "Did integration pass before release began?"

## Violation Response

1. Block release immediately
2. Confirm integration status
3. If integration was not run, run it first
4. Release cannot proceed until integration has fully passed
