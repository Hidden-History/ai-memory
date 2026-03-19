---
id: MC-05
name: One Issue Per Maintenance Task — No Bundling
severity: MEDIUM
phase: maintenance
---

# MC-05: One Issue Per Maintenance Task — No Bundling

## Constraint

Each maintenance issue gets its own task, its own DEV dispatch, and its own review cycle.

## Explanation

WHY SEPARATE TASKS:
- Multiple issues combined in one fix create entangled code changes
- Entangled changes make code review harder and less effective
- If one fix needs to be reverted, bundled fixes get reverted together
- Separate tasks produce separate, reviewable, reversible units of work

EXCEPTION — CRITICAL BUNDLING:
- If two CRITICAL issues are deeply interrelated (fixing one requires fixing the other to maintain system consistency), bundle them
- Document explicitly why they are bundled
- Review covers both as a single unit
- Requires user acknowledgment of the bundling

WHAT "RELATED" DOES NOT MEAN:
- Same file or module — each gets a separate fix
- Same feature area — each gets a separate fix
- Same root cause — fix root cause in one task, verify all symptoms are resolved in the same review
- Fixes that seem logically connected — still separate unless technically impossible to fix independently

PARZIVAL ENFORCES:
- One MAINT-[N] task per issue
- One DEV dispatch per maintenance task
- Related issues identified during a fix, new tasks, not bundled

## Examples

**Permitted**:
- One task per issue with its own DEV dispatch and review cycle
- Bundling only CRITICAL interrelated issues with explicit documentation and user acknowledgment

**Never permitted**:
- Bundling multiple issues in one task because they are in the same file
- Bundling issues because they are in the same feature area

## Enforcement

Parzival self-checks at every 10-message interval: "Is each issue in its own separate task?"

## Violation Response

1. Identify the bundled issues
2. Separate into individual maintenance tasks
3. Each gets its own DEV dispatch and review cycle
4. Exception only for technically inseparable CRITICAL issues (with documentation)
