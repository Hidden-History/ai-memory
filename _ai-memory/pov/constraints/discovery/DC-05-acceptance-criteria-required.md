---
id: DC-05
name: Every Feature Must Have Acceptance Criteria
severity: HIGH
phase: discovery
---

# DC-05: Every Feature Must Have Acceptance Criteria

## Constraint

No feature is accepted into the PRD without testable, specific acceptance criteria.

## Explanation

ACCEPTANCE CRITERIA MUST BE:
- Specific: describes exact behavior, not general intent
- Testable: can be confirmed as pass/fail
- Complete: covers the primary flow and key edge cases
- Unambiguous: only one interpretation possible

PARZIVAL ENFORCES:
- Review every feature for acceptance criteria
- Return any feature without criteria to PM for completion
- Never approve a PRD with features missing acceptance criteria

## Examples

BAD: "Users can log in"
GOOD: "Users can log in using a valid email and password.
       Login fails with a clear error message for invalid credentials.
       After 5 failed attempts, the account is temporarily locked for 15 minutes."

BAD: "The system is fast"
GOOD: "API responses for all core user actions must complete in under 200ms
       at 95th percentile under normal load (up to 500 concurrent users)."

BAD: "Errors are handled"
GOOD: "All API errors return a structured JSON response with an error code,
       human-readable message, and request ID for debugging."

## Enforcement

Parzival self-checks at every 10-message interval: "Does every feature have acceptance criteria?"

## Violation Response

1. Identify the feature missing acceptance criteria
2. Return to PM with specific instruction to complete criteria
3. Do not approve the PRD until all features have testable acceptance criteria
