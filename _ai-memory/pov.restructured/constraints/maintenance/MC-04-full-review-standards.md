---
id: MC-04
name: Review Cycle Standards Do Not Relax in Maintenance
severity: CRITICAL
phase: maintenance
---

# MC-04: Review Cycle Standards Do Not Relax in Maintenance

## Constraint

The zero-legitimate-issues standard applies to maintenance fixes exactly as it does to story implementations.

## Explanation

MAINTENANCE REVIEW CYCLE IS IDENTICAL TO EXECUTION:
- DEV implements fix
- DEV performs code review
- Parzival runs WF-LEGITIMACY-CHECK on all issues found
- Correction instructions built for all legitimate issues
- Fix cycle runs until zero legitimate issues
- Four-source fix verification applied
- User approval required

NOT ACCEPTABLE IN MAINTENANCE:
- "It's a one-line fix — we don't need a full review"
- "We already know what the fix is — just ship it"
- Skipping the code review because the fix seems obvious
- Accepting DEV self-certification on a "simple" fix

WHY STANDARDS DON'T RELAX:
- Maintenance fixes touch production code
- "Simple" fixes in complex systems have unexpected effects
- Rushed maintenance fixes create the next maintenance issue
- The cost of a production incident from a careless fix far exceeds the cost of a thorough review

PARZIVAL ENFORCES:
- WF-REVIEW-CYCLE is mandatory for every maintenance fix
- No maintenance fix closes without zero legitimate issues
- No maintenance fix closes without user approval

## Examples

**Permitted**:
- Running the full WF-REVIEW-CYCLE for every maintenance fix
- Requiring zero legitimate issues before closing

**Never permitted**:
- Skipping code review for "simple" fixes
- Accepting DEV self-certification without review
- Closing a maintenance fix without user approval

## Enforcement

Parzival self-checks at every 10-message interval: "Is the review cycle running to full standard (zero legitimate issues)?"

## Violation Response

1. Stop the maintenance fix closure
2. Re-run the full WF-REVIEW-CYCLE
3. Continue until zero legitimate issues
4. Get user approval before closing
