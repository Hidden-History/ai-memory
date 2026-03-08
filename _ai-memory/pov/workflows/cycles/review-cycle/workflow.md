---
name: review-cycle
description: 'Dev-review loop that enforces quality on every implementation. Cycles until zero legitimate issues remain.'
firstStep: './steps/step-01-verify-completeness.md'
---

# Review Cycle

**Goal:** Ensure every piece of implementation work passes a thorough review cycle that does not end until a review pass returns zero legitimate issues.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files

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
