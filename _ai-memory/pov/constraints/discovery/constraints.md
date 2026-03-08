---
id: discovery
name: Discovery Phase Constraints
description: Active only during WF-DISCOVERY — dropped when Discovery exits
authority: If any Discovery constraint conflicts with a global constraint, the global constraint wins
---

# Discovery Phase Constraints

> **Scope**: Active only during WF-DISCOVERY
> **Loaded**: When WF-DISCOVERY begins, alongside global constraints
> **Dropped**: When Discovery exits
> **Inherits**: All 12 global constraints — these add on top

## Priority Rule

**If any Discovery constraint conflicts with a global constraint — the global constraint wins.**

Global constraints (GC-1 through GC-12) are always active. The constraints below are specific to the Discovery phase and add additional rules that apply only while WF-DISCOVERY is running. When Discovery exits, these constraints are dropped.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| DC-01 | MUST Produce a PRD Before Exiting Discovery | CRITICAL |
| DC-02 | CANNOT Exit Without Explicit User Sign-off on Scope | CRITICAL |
| DC-03 | ALL Requirements Must Be Sourced — No Invented Requirements | HIGH |
| DC-04 | Requirements Must Be Implementation-Free | HIGH |
| DC-05 | Every Feature Must Have Acceptance Criteria | HIGH |
| DC-06 | Out of Scope Must Be Explicitly Stated | MEDIUM |
| DC-07 | Open Questions Must Be Resolved Before Architecture | HIGH |
| DC-08 | Analyst Research Must Precede PM When Input Is Thin | MEDIUM |

## Self-Check Schedule

Run this checklist after every 10 messages during Discovery:

- DC-01: Is the PRD on track to be complete? Any missing sections?
- DC-02: Have I asked for explicit user approval (not assumed it)?
- DC-03: Are there any invented requirements in the PRD?
- DC-04: Are there implementation details in the PRD?
- DC-05: Does every feature have acceptance criteria?
- DC-06: Is there an explicit out-of-scope section?
- DC-07: Are there unresolved requirements questions still open?
- DC-08: Did I check input quality before activating PM?

PLUS all 12 global constraint checks from global/constraints.md

IF ANY CHECK FAILS: Course-correct IMMEDIATELY before continuing.

## Violation Severity Reference

| Constraint | Severity | Immediate Action |
|---|---|---|
| DC-01: Exited Discovery without approved PRD | CRITICAL | Return to Discovery, complete PRD |
| DC-02: Advanced without explicit user sign-off | CRITICAL | Return to approval gate, get explicit sign-off |
| DC-03: PRD contains invented requirements | HIGH | Remove unsourced requirements, confirm with user |
| DC-04: PRD contains implementation details | HIGH | Remove implementation details, note for Architecture |
| DC-05: Feature missing acceptance criteria | HIGH | Return to PM, complete criteria |
| DC-06: No out-of-scope section | MEDIUM | Return to PM, add explicit exclusions |
| DC-07: Open requirements questions unresolved | HIGH | Resolve before routing to Architecture |
| DC-08: PM activated without sufficient input | MEDIUM | Pause PM, run Analyst first |
