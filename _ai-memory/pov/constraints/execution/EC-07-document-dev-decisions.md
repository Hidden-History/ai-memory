---
id: EC-07
name: Implementation Decisions Made by DEV Must Be Reviewed and Documented
severity: MEDIUM
phase: execution
---

# EC-07: Implementation Decisions Made by DEV Must Be Reviewed and Documented

## Constraint

Any decision DEV makes during implementation that was not specified in the instruction must be reviewed and documented.

## Explanation

IMPLEMENTATION DECISIONS INCLUDE:
- Choosing between two valid approaches not specified in architecture
- Naming a file, class, or function not specified in the instruction
- Structuring code in a way not specified in project-context.md
- Adding a dependency not specified in the instruction
- Handling an edge case in a way not specified in the story

REVIEW CRITERIA FOR DEV DECISIONS:
- Does the decision align with architecture.md patterns?
- Does the decision align with project-context.md standards?
- Is the decision consistent with similar decisions elsewhere in codebase?
- Would this decision need to be replicated in similar stories?

IF DECISION IS ALIGNED:
- Accept the decision
- Document in decisions.md if it sets a precedent
- Update project-context.md if it becomes a new standard

IF DECISION CONFLICTS:
- It is a legitimate issue — add to review cycle fix list
- Provide specific fix guidance aligned with project standards

PARZIVAL ENFORCES:
- During review cycle, look for undocumented implementation decisions
- Every decision that sets a precedent gets documented
- No silent decisions that become undocumented architecture drift

## Examples

**Permitted**:
- Accepting an aligned DEV decision and documenting it in decisions.md
- Flagging a conflicting DEV decision as a legitimate issue in the review cycle

**Never permitted**:
- Ignoring DEV decisions that were not specified in the instruction
- Allowing undocumented decisions to become silent architecture drift

## Enforcement

Parzival self-checks at every 10-message interval: "Have DEV implementation decisions been reviewed and documented?"

## Violation Response

1. Identify the undocumented implementation decision
2. Review against architecture.md and project-context.md
3. If aligned, document in decisions.md (if precedent-setting)
4. If conflicting, add to review cycle fix list
