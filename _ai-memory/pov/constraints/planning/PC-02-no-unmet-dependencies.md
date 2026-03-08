---
id: PC-02
name: Cannot Assign a Story With Unmet Dependencies
severity: CRITICAL
phase: planning
---

# PC-02: Cannot Assign a Story With Unmet Dependencies

## Constraint

No story enters a sprint if its dependencies are not complete or also in the same sprint in correct sequence.

## Explanation

DEPENDENCY CHECK FOR EVERY STORY:
- Are all stories this story depends on already complete?
- If not complete: are they in this sprint and sequenced before this story?
- Are any external dependencies (APIs, services) confirmed available?
- Are any infrastructure dependencies (database, auth) in place?

DEPENDENCY VIOLATIONS:
- Story depends on database model not yet created — not ready
- Story depends on auth system not yet implemented — not ready
- Story depends on API endpoint in another story not yet in sprint — not ready

HOW TO HANDLE:
- Move dependent story to next sprint
- Add the prerequisite story to current sprint first
- Sequence stories within sprint correctly

PARZIVAL ENFORCES:
- Check dependency chain for every story before sprint assignment
- sprint-status.yaml must reflect correct sequencing
- Never allow a story to start that has unresolved dependencies

## Examples

**Permitted**:
- A story whose dependencies are all complete
- A story whose dependencies are in the same sprint and sequenced before it

**Never permitted**:
- A story with dependencies that are incomplete and not in the current sprint
- Starting a story before its prerequisite stories are complete

## Enforcement

Parzival self-checks at every 10-message interval: "Do all sprint stories have their dependencies met?"

## Violation Response

1. Identify the unmet dependency
2. Either move the dependent story to next sprint or add the prerequisite to current sprint
3. Ensure correct sequencing in sprint-status.yaml
4. Never allow a story to start with unresolved dependencies
