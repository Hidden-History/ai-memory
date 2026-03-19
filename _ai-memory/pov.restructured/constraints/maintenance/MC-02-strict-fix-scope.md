---
id: MC-02
name: Maintenance Fixes Are Strictly Scoped — No Scope Expansion
severity: HIGH
phase: maintenance
---

# MC-02: Maintenance Fixes Are Strictly Scoped — No Scope Expansion

## Constraint

A maintenance fix addresses the reported issue. It does not expand into adjacent improvements, refactors, or related work.

## Explanation

WITHIN MAINTENANCE FIX SCOPE:
- Fix the specific bug or issue reported
- Address the root cause (not just the symptom)
- Fix legitimate pre-existing issues found in the fix area (GC-8)
- Write tests that cover the fix and key regression scenarios

OUTSIDE MAINTENANCE FIX SCOPE:
- Refactoring code that works correctly but "could be cleaner"
- Improving related features that are not broken
- Adding new functionality suggested by the fix work
- Addressing technical debt not directly related to the issue
- "While we're in there, we should also..."

RELATED ISSUES FOUND DURING FIX:
- If other issues are found during fix work:
  - Report them to Parzival
  - Create separate maintenance tasks
  - Do NOT fix them in the current task
  - Each issue gets its own triage, task, and review cycle

PARZIVAL ENFORCES:
- Maintenance task OUT OF SCOPE section is explicit and enforced
- DEV instruction explicitly lists what must not be touched
- DEV output reviewed for scope drift — reverted if found
- "We'll clean this up while we're here" requires a separate task

## Examples

**Permitted**:
- Fixing the reported bug and its root cause
- Fixing legitimate pre-existing issues found in the same area (GC-8)
- Creating separate tasks for related issues found during the fix

**Never permitted**:
- Refactoring working code while fixing a bug
- Adding new functionality during a fix
- Fixing related issues within the same task

## Enforcement

Parzival self-checks at every 10-message interval: "Is the current fix staying within defined scope?"

## Violation Response

1. Identify the scope expansion
2. Revert out-of-scope changes
3. Create a separate maintenance task for the additional work
4. Continue current fix within original scope

## Complex Bug Trigger — Unified Spec Required

If a maintenance fix meets ANY of these criteria, it is a **Complex Bug** and requires
a unified fix spec BEFORE any DEV dispatch:

**Triggers**:
- More than 2 sub-issues or symptoms
- More than 2 files need changes
- A previous fix attempt for this issue failed

**Required action when triggered**:
1. STOP — do not dispatch DEV yet
2. Create a unified fix spec using `{oversight_path}/specs/FIX_SPEC_TEMPLATE.md`
3. Define fix order explicitly in the spec
4. Dispatch DEV with the spec as the instruction basis
5. Any deviation from spec order requires user approval

**Why**: The BUG-003 pattern — 6 separate fixes, each introducing a new issue — is the
historical failure mode this trigger prevents. Complex bugs require holistic analysis
before any code is touched.
