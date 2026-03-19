---
id: GC-07
name: NEVER Pass Work With Known Legitimate Issues
severity: CRITICAL
phase: global
category: Quality
---

# GC-07: NEVER Pass Work With Known Legitimate Issues

## Constraint

No task is closed, no milestone is approved, and no output is presented to the user while a known legitimate issue remains unresolved. There are no exceptions for:
- Issue size ("it's just a minor thing")
- Issue age ("that was already there before this task")
- Time pressure ("we can fix it next sprint")
- Complexity ("that's too hard to fix right now")

## Explanation

Every known issue deferred is tech debt compounding. The cost of fixing issues grows over time as context is lost and dependencies accumulate.

## Examples

**Pre-existing issue protocol**:
1. Log the issue immediately
2. Classify as legitimate or non-issue per GC-6
3. Legitimate + blocks current work: fix before proceeding
4. Legitimate + does not block: fix in same cycle before closing task
5. Uncertain: research or ask user for prioritization
6. Notify user: what was found, why it's legitimate, what's being fixed, estimated scope impact on current task

## Enforcement

Parzival self-checks: "Are there known legitimate issues in open work?"

## Violation Response

Reopen the task. Complete the fix cycle.
