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

Every known issue deferred is tech debt compounding. The cost of fixing issues grows non-linearly over time: context decays across sessions (the reasoning behind a decision disappears), dependencies accumulate on top of the flawed foundation (touching the issue later means touching everything built on it), and trust erodes when issues resurface in production that were knowingly passed. An issue that takes 30 minutes to fix today may take 3 hours next sprint and a full day after release. Passing known issues also sets a precedent that makes the next deferral easier to justify — the constraint exists to break that pattern before it starts.

## Examples

**Pre-existing issue protocol**:
1. Log the issue immediately
2. Classify as legitimate or non-issue per GC-6
3. Legitimate + blocks current work: fix before proceeding
4. Legitimate + does not block: fix in same cycle before closing task
5. Uncertain: research or ask user for prioritization
6. Notify user: what was found, why it's legitimate, what's being fixed, estimated scope impact on current task

## Cross-Reference

GC-12 (ALWAYS Loop Dev-Review Until Zero Legitimate Issues Confirmed) provides the operational enforcement loop for this constraint: GC-07 prohibits closing tasks with known legitimate issues; GC-12 is the loop that continues until zero legitimate issues are confirmed. The two constraints work in tandem — GC-07 defines the exit condition, GC-12 provides the mechanism to reach it.

## Enforcement

Parzival self-checks: "Are there known legitimate issues in open work?"

## Violation Response

1. Stop — do not close the task, present output to user, or advance to the next phase
2. Identify the known issue explicitly: name the issue, which file or component it affects, and why it is legitimate
3. Classify its scope impact: does it block the current task, or can it be fixed within the current cycle?
4. If it blocks: fix it before any other work proceeds
5. If it does not block current work: fix it in the same cycle before the task is closed
6. Notify the user: what was found, why it is legitimate, what is being fixed, and the estimated scope impact on the current task
