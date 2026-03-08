---
id: IN-05
name: Establish Baseline Before Entering Any Phase Workflow
severity: CRITICAL
phase: init
---

# IN-05: Establish Baseline Before Entering Any Phase Workflow

## Constraint

Init must establish a complete, verified baseline before transitioning to any phase workflow. The baseline includes: project state captured, oversight structure created, tracking files initialized, and first phase identified and confirmed with user.

## Explanation

Phase workflows assume a stable baseline exists. If init transitions prematurely, phase workflows operate on incomplete state, leading to missing tracking, lost context, and incorrect constraint loading.

## Examples

**Baseline requirements** (all must be satisfied):
- project-status.md created with initial phase set
- Oversight directory structure verified (tracking files exist)
- SESSION_WORK_INDEX.md created or updated with current state
- First session handoff document created (captures init state)
- User has explicitly confirmed the target phase
- All applicable phase constraints loaded and verified

**Never**:
- Skip baseline creation to "get started faster"
- Assume the user wants a specific phase without asking
- Transition to a phase workflow with incomplete tracking

## Enforcement

Init workflow must verify all baseline requirements in its final step before invoking the WORKFLOW-MAP router.

## Violation Response

1. Stop before phase transition
2. Complete all missing baseline items
3. Re-verify baseline
4. Only then transition to phase workflow
