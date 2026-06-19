---
class: register
read_path: section-anchored
owns: "pointer to live sprint/task state"
cap_lines: 60
cap_kb: 4.5
rotation_trigger: none
archive_target: N/A
index_file: N/A
reconciliation: "thin pointer, never re-grow"
---
# Task Tracker

**Last Updated**: [DATE]

> Thin pointer — never re-grow. Holds only the current-sprint pointer and the
> naming convention. Detailed task tables live in the sprint tooling, not here.

---

## Current Sprint

| Field | Value |
|-------|-------|
| Sprint | [Sprint Name/ID] |
| Goal | [One sentence] |
| Status | In Progress / Complete / Blocked |
| Active task | [TASK-### or pointer] |

---

## Naming Convention

- Tasks: `TASK-###` (sequential)
- Blockers: `BLK-###` (sequential)
- Risks: `RSK-###` (sequential)
- Decisions: `DEC-###` (sequential)
