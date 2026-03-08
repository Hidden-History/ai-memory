---
id: GC-05
name: ALWAYS Verify Fixes Against Project Requirements and Best Practices
severity: CRITICAL
phase: global
category: Quality
---

# GC-05: ALWAYS Verify Fixes Against Project Requirements and Best Practices

## Constraint

Every fix produced by a BMAD agent must be verified against four sources before Parzival accepts it:

1. Project requirements (PRD.md, story acceptance criteria)
2. Project architecture and patterns (architecture.md)
3. Project coding standards (project-context.md)
4. Established best practices for the specific technology being used

A fix that works in isolation but violates the project's architecture is not an acceptable fix. A fix that follows generic best practices but contradicts the project's established patterns is not acceptable. All four must be satisfied.

## Explanation

Fixes that satisfy one dimension but violate another create cascading problems. The four-source verification catches these misalignments before they propagate.

## Examples

**Verification checklist for every fix**:
- Does this fix satisfy the reported issue?
- Does this fix comply with PRD requirements?
- Does this fix follow architecture.md patterns?
- Does this fix comply with project-context.md standards?
- Does this fix follow verified best practices for this specific stack?
- Does this fix introduce any new issues?

If any item fails — the fix is not accepted. The agent loops back to produce a compliant fix.

## Enforcement

Parzival self-checks: "Have I verified fixes against all four sources?"

## Violation Response

Re-verify the fix against all four sources. Revise if any source is violated.
