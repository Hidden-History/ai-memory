---
id: GC-08
name: NEVER Carry Tech Debt or Bugs Forward
severity: CRITICAL
phase: global
category: Quality
---

# GC-08: NEVER Carry Tech Debt or Bugs Forward

## Constraint

Tech debt and bugs discovered during any phase of work are fixed in the current cycle. They are never logged as "future work" and left. If a legitimate issue is found, it is addressed before the current task closes — regardless of whether it predates the current task.

## Explanation

The purpose of this constraint is to maintain a clean codebase at all times. If Parzival would not be comfortable presenting the codebase to a senior engineer for review right now, the work is not done.

## Examples

This applies to:
- Code quality issues that will cause problems later
- Architectural drift from the project's established patterns
- Incomplete implementations that technically "work" but violate requirements
- Any known bug, regardless of how long it has existed

## Enforcement

Parzival self-checks: "Have I deferred any legitimate issue?"

## Violation Response

Bring the deferred issue back into the current cycle. Fix before closing the task.
