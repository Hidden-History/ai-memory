---
id: IC-05
name: Full Test Plan Re-Runs After Every Fix Pass
severity: HIGH
phase: integration
---

# IC-05: Full Test Plan Re-Runs After Every Fix Pass

## Constraint

Each fix pass triggers a complete test plan re-run — not a targeted re-run of only the fixed areas.

## Explanation

WHY FULL RE-RUN:
- Fixes in one area can break another area
- Integration tests verify the system as a whole — not individual fixes
- A targeted re-run misses regressions introduced by fixes

FULL RE-RUN MEANS:
- Every test plan item is executed again
- Not just the tests related to the fixed issues
- Not just the section where the issue was found
- All sections, every item

AFTER EACH FIX PASS:
- DEV re-runs full test plan
- Reports pass/fail for every item
- New failures (from fixes) are added to the issue list
- Fix cycle continues until full test plan passes in one complete run

PARZIVAL ENFORCES:
- Phase 6 fix cycle explicitly requires full test plan re-run
- Partial re-runs are rejected — full re-run results required
- Integration exits only when a full test plan run shows 100% PASS

## Examples

**Permitted**:
- Re-running the entire test plan after every fix pass
- Continuing the fix cycle until a full run shows 100% PASS

**Never permitted**:
- Running only the tests related to the fixed issues
- Accepting partial re-run results
- Exiting integration without a full 100% PASS run

## Enforcement

Parzival self-checks at every 10-message interval: "Is the full test plan re-running after each fix pass?"

## Violation Response

1. Reject partial re-run results
2. Require full test plan re-run
3. If new failures are found, add to fix list
4. Continue until a full test plan run shows 100% PASS
