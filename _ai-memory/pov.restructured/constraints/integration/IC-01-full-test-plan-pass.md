---
id: IC-01
name: Test Plan Must Be Created and Fully Executed Before Integration Exits
severity: CRITICAL
phase: integration
---

# IC-01: Test Plan Must Be Created and Fully Executed Before Integration Exits

## Constraint

Integration cannot exit without a written test plan that is 100% passed.

## Explanation

TEST PLAN REQUIREMENTS:
- Created from PRD requirements for this milestone
- Covers all Must Have features in the integration scope
- Covers all integration points (component-to-component, external)
- Covers non-functional requirements (performance, security)
- Covers regression — existing functionality must still work
- Every test has: specific input, expected outcome, pass/fail criteria

100% PASS MEANS:
- Every test item is executed
- Every test item passes
- No test item is skipped, deferred, or marked "good enough"

NOT ACCEPTABLE:
- "Mostly passing" with some failures noted for later
- Test plan items skipped because "it's obviously working"
- Test pass/fail based on DEV's verbal confirmation without execution
- Partial test plan ("we tested the main flows")

PARZIVAL ENFORCES:
- Phase 2 creates the test plan before any review begins
- Test plan is provided to DEV as part of Phase 3 instruction
- After every fix pass: full test plan re-executed
- Integration does not exit until all items explicitly show PASS

## Examples

**Permitted**:
- A complete test plan covering all milestone features, integration points, and non-functional requirements
- Exiting integration only after every test item shows PASS

**Never permitted**:
- Exiting with "mostly passing" results
- Skipping test items because "it's obviously working"
- Accepting DEV's verbal confirmation without execution

## Enforcement

Parzival self-checks at every 10-message interval: "Is the test plan created and being fully executed?"

## Violation Response

1. Identify the skipped or failing test plan items
2. If items are failing, add to fix list, fix cycle continues
3. If items were skipped, return to DEV for execution
4. Do not advance to Release with any untested or failing items
