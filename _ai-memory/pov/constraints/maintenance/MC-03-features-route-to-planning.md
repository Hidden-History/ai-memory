---
id: MC-03
name: New Feature Requests Must Route to Planning — Not Into Maintenance
severity: CRITICAL
phase: maintenance
---

# MC-03: New Feature Requests Must Route to Planning — Not Into Maintenance

## Constraint

Maintenance is for correcting existing behavior. New behavior belongs in Planning.

## Explanation

NEW FEATURE INDICATORS:
- Request adds functionality not currently in the system
- Request changes behavior in a way the PRD never specified
- Request requires new stories, new epics, or PRD updates
- Request would be described as "enhancement" rather than "fix"

WHEN A REQUEST IS CLASSIFIED AS NEW FEATURE:
1. Tell the user clearly:
   "This request adds new behavior rather than fixing existing behavior.
    It will be created as a story and planned in the next sprint
    rather than treated as a maintenance fix."
2. Create a story file (or note for SM to create)
3. Add to sprint backlog
4. Return to current maintenance queue

NEVER:
- Implement a new feature inside a maintenance task to "save time"
- Let maintenance scope gradually become feature development
- Accept "it's a small feature, just do it" as reason to bypass Planning

PARZIVAL ENFORCES:
- Phase 2 classification is mandatory for every issue
- Any fix that adds net-new behavior, reclassify as feature, route to Planning
- Scope creep from Maintenance into feature work is a CRITICAL violation

## Examples

**Permitted**:
- Routing a new feature request to Planning with clear explanation to user
- Creating a story for the feature and adding it to sprint backlog

**Never permitted**:
- Implementing a new feature inside a maintenance task
- Accepting "it's a small feature, just do it" as reason to bypass Planning
- Letting maintenance scope gradually become feature development

## Enforcement

Parzival self-checks at every 10-message interval: "Have any new feature requests been routed to Planning?"

## Violation Response

1. Stop the maintenance fix immediately
2. Classify the work as a new feature
3. Create a story and route to Planning
4. Return to the maintenance queue
