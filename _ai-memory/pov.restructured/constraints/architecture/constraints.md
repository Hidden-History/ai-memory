---
id: architecture
name: Architecture Phase Constraints
description: Active only during WF-ARCHITECTURE — dropped when Architecture exits
authority: If any Architecture constraint conflicts with a global constraint, the global constraint wins
---

# Architecture Phase Constraints

> **Scope**: Active only during WF-ARCHITECTURE
> **Loaded**: When WF-ARCHITECTURE begins, alongside global constraints
> **Dropped**: When Architecture exits
> **Inherits**: All 20 global constraints — these add on top

## Priority Rule

**If any Architecture constraint conflicts with a global constraint — the global constraint wins.**

Global constraints (GC-01 through GC-20) are always active. The constraints below apply only during WF-ARCHITECTURE. When Architecture exits, these constraints are dropped.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| AC-01 | MUST Document Every Tech Decision With Rationale | HIGH |
| AC-02 | CANNOT Choose Stack Without User Approval | HIGH |
| AC-03 | Architecture Must Satisfy ALL PRD Non-Functional Requirements | HIGH |
| AC-04 | Stories CANNOT Be Written Before Architecture Is Approved | CRITICAL |
| AC-05 | Implementation Readiness Check Cannot Be Skipped | CRITICAL |
| AC-06 | No Gold-Plating — Architecture Must Fit Project Scale | MEDIUM |
| AC-07 | Existing Technology Must Be Respected | HIGH |
| AC-08 | project-context.md Must Be Updated With Architecture Decisions | MEDIUM |

## Self-Check Schedule

Run this checklist after every 10 messages during Architecture:

- AC-01: Do all tech decisions have documented rationale?
- AC-02: Has user approved the tech stack choices?
- AC-03: Does architecture address all PRD non-functional requirements?
- AC-04: Are stories being written before architecture approval? (must not be)
- AC-05: Has implementation readiness check been run and passed?
- AC-06: Is there any gold-plating without PRD justification?
- AC-07: Is existing technology being respected (if applicable)?
- AC-08: Has project-context.md been updated with architecture decisions?

PLUS all 20 global constraint checks from global/constraints.md

IF ANY CHECK FAILS: Course-correct IMMEDIATELY before continuing.

## Violation Severity Reference

| Constraint | Severity | Immediate Action |
|---|---|---|
| AC-01: Undocumented tech decision | HIGH | Return to Architect — document with rationale |
| AC-02: Stack chosen without user approval | HIGH | Present to user, get explicit approval |
| AC-03: Non-functional requirement unaddressed | HIGH | Return to Architect — address requirement |
| AC-04: Stories written before architecture approval | CRITICAL | Stop story creation, complete architecture first |
| AC-05: Readiness check skipped | CRITICAL | Run readiness check before exiting |
| AC-06: Gold-plating detected | MEDIUM | Question justification, simplify if unjustified |
| AC-07: Existing tech contradicted without approval | HIGH | Escalate to user, get explicit authorization |
| AC-08: project-context.md not updated | MEDIUM | Update before exiting Architecture phase |
