---
id: MC-08
name: Queued Issues Are Prioritized by Severity — Always
severity: MEDIUM
phase: maintenance
---

# MC-08: Queued Issues Are Prioritized by Severity — Always

## Constraint

Multiple maintenance issues must be addressed in severity order.

## Explanation

PRIORITY ORDER:
CRITICAL > HIGH > MEDIUM > LOW

WITHIN SAME SEVERITY:
- Older issues before newer issues (FIFO at same severity)
- User-reported production impact before internal findings

PRIORITY OVERRIDE:
- A new CRITICAL issue always interrupts lower-severity active work
- Pause current fix at a clean stopping point
- Document pause in project-status.md
- Begin CRITICAL fix immediately

NOT ACCEPTABLE:
- Working on LOW priority fixes while HIGH issues are queued
- "We'll get to the HIGH issue next session"
- Letting MEDIUM/LOW queue grow indefinitely

PARZIVAL ENFORCES:
- Issue queue is maintained and visible in project-status.md
- New issues are triaged and inserted in priority order
- At session start in Maintenance: check queue, confirm priority order
- User is informed of queue state and any priority decisions

## Examples

**Permitted**:
- Addressing CRITICAL issues before HIGH, HIGH before MEDIUM, etc.
- Interrupting LOW priority work for a new CRITICAL issue
- FIFO ordering within the same severity level

**Never permitted**:
- Working on LOW fixes while HIGH issues are queued
- Deferring HIGH issues to "next session"
- Letting the MEDIUM/LOW queue grow indefinitely without attention

## Enforcement

Parzival self-checks at every 10-message interval: "Are queued issues being addressed in severity order?"

## Violation Response

1. Check the issue queue for priority order
2. Reorder if lower-priority work is being done ahead of higher-priority
3. Pause current work at a clean stopping point if a higher-priority issue exists
4. Document the pause and begin the higher-priority fix
