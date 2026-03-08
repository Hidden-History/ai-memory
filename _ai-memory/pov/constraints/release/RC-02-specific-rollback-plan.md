---
id: RC-02
name: Rollback Plan Must Exist and Be Specific
severity: CRITICAL
phase: release
---

# RC-02: Rollback Plan Must Exist and Be Specific

## Constraint

A rollback plan is required for every release. "We'll figure it out" is not a rollback plan.

## Explanation

ROLLBACK PLAN MUST INCLUDE:
- Specific rollback trigger conditions (not "if something goes wrong")
- Specific rollback steps (not "revert the deployment")
- Specific database rollback steps (if migrations are included)
- Explicit identification of any irreversible changes
- Impact statement if rollback is needed after irreversible changes
- Realistic time estimate for rollback

NOT ACCEPTABLE:
- "Rollback: revert to previous version"
- "Database: restore backup if needed"
- Rollback plan that omits irreversible migration steps
- Rollback plan without specific commands or steps

IRREVERSIBLE CHANGES REQUIRE SPECIAL HANDLING:
- Explicitly named in rollback plan
- User must see them in the sign-off presentation
- Database backup must be included as a pre-deployment step
- Impact of proceeding past this point must be stated

PARZIVAL ENFORCES:
- Rollback plan is reviewed in Phase 6 against the specificity checklist
- Vague rollback plans, return to Phase 4 for revision
- Irreversible changes, must appear in sign-off presentation with impact statement
- No release proceeds without a specific, executable rollback plan

## Examples

**Permitted**:
- A rollback plan with specific trigger conditions, specific steps, specific database rollback steps, and time estimates
- Irreversible changes explicitly named with impact statements

**Never permitted**:
- "Rollback: revert to previous version"
- "Database: restore backup if needed"
- Omitting irreversible migration steps from the rollback plan

## Enforcement

Parzival self-checks at every 10-message interval: "Does a specific, executable rollback plan exist?"

## Violation Response

1. Identify the vague or missing rollback plan elements
2. Return to Phase 4 for revision
3. Ensure irreversible changes appear in sign-off presentation
4. No release proceeds without a specific, executable rollback plan
