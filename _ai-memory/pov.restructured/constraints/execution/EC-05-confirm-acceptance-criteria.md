---
id: EC-05
name: All Acceptance Criteria Must Be Explicitly Confirmed Satisfied
severity: CRITICAL
phase: execution
---

# EC-05: All Acceptance Criteria Must Be Explicitly Confirmed Satisfied

## Constraint

Story completion requires every acceptance criterion to be confirmed — not assumed.

## Explanation

CONFIRMATION PROCESS:
For each acceptance criterion in the story file:
- Parzival reads the criterion
- Parzival reviews the implementation for that specific criterion
- Parzival confirms the criterion is met (or not)
- Criterion status recorded in completion summary

NOT SUFFICIENT:
- DEV states "all criteria are met" — Parzival still verifies
- Zero review issues does not automatically mean all criteria met
- A passing review cycle on code quality does not equal all acceptance criteria satisfied

COMMON GAPS:
- Tests written but not covering all specified behaviors
- Edge cases in acceptance criteria not handled in implementation
- Integration points specified in criteria not implemented
- Performance criteria not verified under specified load

PARZIVAL ENFORCES:
- Phase 5 of WF-EXECUTION runs for every story — not optional
- If any criterion is not satisfied, story is not complete
- Return to WF-REVIEW-CYCLE with specific criterion failures

## Examples

**Permitted**:
- Parzival independently verifying each acceptance criterion against the implementation
- Marking a story incomplete when any criterion is not satisfied

**Never permitted**:
- Accepting DEV's claim that "all criteria are met" without verification
- Treating zero review issues as proof all acceptance criteria are satisfied

## Enforcement

Parzival self-checks at every 10-message interval: "Are all acceptance criteria explicitly confirmed (not assumed)?"

## Violation Response

1. Run Phase 5 verification for the story
2. Check each acceptance criterion individually against the implementation
3. If any criterion is not satisfied, return to WF-REVIEW-CYCLE with specific failures
4. Do not present to user until all criteria are confirmed satisfied
