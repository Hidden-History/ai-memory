---
id: planning
name: Planning Phase Constraints
description: Active only during WF-PLANNING — dropped when Planning exits
authority: If any Planning constraint conflicts with a global constraint, the global constraint wins
---

# Planning Phase Constraints

> **Scope**: Active only during WF-PLANNING
> **Loaded**: When WF-PLANNING begins, alongside global constraints
> **Dropped**: When Planning exits
> **Inherits**: All 12 global constraints — these add on top

## Priority Rule

**If any Planning constraint conflicts with a global constraint — the global constraint wins.**

Global constraints (GC-1 through GC-12) are always active. The constraints below apply only during WF-PLANNING. When Planning exits, these constraints are dropped.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| PC-01 | Tasks Must Be Broken to Single-Responsibility Units | HIGH |
| PC-02 | Cannot Assign a Story With Unmet Dependencies | CRITICAL |
| PC-03 | Story Files Must Be Implementation-Ready Before Sprint Starts | HIGH |
| PC-04 | Retrospective Must Run Before Subsequent Sprint Planning | MEDIUM |
| PC-05 | Sprint Scope Must Be Realistic Given Project Velocity | MEDIUM |
| PC-06 | Architecture.md Must Be Used as Technical Context for All Stories | HIGH |
| PC-07 | Cannot Begin Execution Before Sprint Is Approved | CRITICAL |
| PC-08 | Carryover Stories Are Included First in Next Sprint | MEDIUM |

## Self-Check Schedule

Run this checklist after every 10 messages during Planning:

- PC-01: Are all stories single-responsibility units?
- PC-02: Do all sprint stories have their dependencies met?
- PC-03: Are all story files implementation-ready?
- PC-04: Did retrospective run before this sprint planning (if not first sprint)?
- PC-05: Is sprint scope realistic given project velocity?
- PC-06: Does every story's technical context cite architecture.md specifically?
- PC-07: Has sprint been approved before execution begins?
- PC-08: Are carryover stories included first in this sprint?

PLUS all 12 global constraint checks from global/constraints.md

IF ANY CHECK FAILS: Course-correct IMMEDIATELY before continuing.

## Violation Severity Reference

| Constraint | Severity | Immediate Action |
|---|---|---|
| PC-01: Oversized story not split | HIGH | Return to SM to split before sprint starts |
| PC-02: Story with unmet dependencies in sprint | CRITICAL | Remove from sprint or resolve dependency first |
| PC-03: Story not implementation-ready | HIGH | Return to SM with specific gaps to fill |
| PC-04: Subsequent sprint planned without retrospective | MEDIUM | Run retrospective before finalizing plan |
| PC-05: Sprint scope exceeds realistic velocity | MEDIUM | Flag to user, recommend reduction |
| PC-06: Story technical context lacks architecture citations | HIGH | Return to SM with specific sections to cite |
| PC-07: Execution started before sprint approval | CRITICAL | Stop execution, return to approval gate |
| PC-08: Carryover stories not prioritized | MEDIUM | Update sprint plan to include carryover first |
