---
id: PC-08
name: Carryover Stories Are Included First in Next Sprint
severity: MEDIUM
phase: planning
---

# PC-08: Carryover Stories Are Included First in Next Sprint

## Constraint

Stories not completed in a sprint carry over to the next sprint with priority.

## Explanation

CARRYOVER STORY HANDLING:
- Identified in retrospective (not completed in prior sprint)
- Entered in next sprint BEFORE selecting new stories
- Reason for carryover documented (too large / blocked / deprioritized)
- Story file reviewed for currency — still matches current architecture?

IF CARRYOVER STORY IS NO LONGER VALID:
- Story has been superseded by architectural changes — update story first
- Story's dependency is now resolved — confirm and update
- Story is no longer required — remove from sprint, note in PRD if scope change

PARZIVAL ENFORCES:
- Review sprint-status.yaml for carryover from prior sprint
- Carryover stories enter next sprint plan before new stories
- Do not drop carryover stories without user acknowledgment

## Examples

**Permitted**:
- Including carryover stories first in next sprint plan
- Updating carryover stories to match current architecture before including them
- Dropping a carryover story with explicit user acknowledgment

**Never permitted**:
- Ignoring carryover stories when planning next sprint
- Dropping carryover stories without user acknowledgment
- Adding new stories before carryover stories are accounted for

## Enforcement

Parzival self-checks at every 10-message interval: "Are carryover stories included first in this sprint?"

## Violation Response

1. Review sprint-status.yaml for carryover from prior sprint
2. Add carryover stories to next sprint plan before new stories
3. If carryover story is no longer valid, get user acknowledgment before dropping
