---
name: review-cycle
description: 'Dev-review loop that enforces quality on every implementation. Cycles until zero legitimate issues remain.'
firstStep: './steps-c/step-01-verify-completeness.md'
---

# Review Cycle

**Goal:** Ensure every piece of implementation work passes a thorough review cycle that does not end until a review pass returns zero legitimate issues.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Cycle Anti-Patterns
These apply across ALL steps in this workflow:
- Never accept a review with known legitimate issues
- Never skip a review pass because "the fixes were simple"
- Never run the review cycle only on new code, not changed code
- Never let DEV self-certify completion without Parzival verification
- Never treat pre-existing issues as out of scope
- Never send partial correction instructions (only some issues)
- Never close the cycle when uncertain issues are unresolved
- Never accept implausible zero-issue reports without scrutiny
- Never count non-issues in the legitimate issue tally

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
