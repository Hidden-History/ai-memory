---
id: maintenance
name: Maintenance Phase Constraints
description: Active only during WF-MAINTENANCE — dropped when Maintenance routes to another phase
authority: If any Maintenance constraint conflicts with a global constraint, the global constraint wins
---

# Maintenance Phase Constraints

> **Scope**: Active only during WF-MAINTENANCE
> **Loaded**: When WF-MAINTENANCE begins, alongside global constraints
> **Dropped**: When Maintenance routes to Planning or Execution
> **Inherits**: All 20 global constraints — these add on top

## Priority Rule

**If any Maintenance constraint conflicts with a global constraint — the global constraint wins.**

Global constraints (GC-01 through GC-20) are always active. The constraints below apply only during WF-MAINTENANCE. When Maintenance routes to Planning or Execution, these constraints are dropped.

Maintenance is the most scope-unstable phase. Issues arrive reactively. Fixes seem simple but often are not. The constraints here exist to prevent the most common maintenance failure modes: scope expansion, rushed reviews, and undocumented changes.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| MC-01 | Every Issue Must Be Triaged Before Any Fix Begins | HIGH |
| MC-02 | Maintenance Fixes Are Strictly Scoped — No Scope Expansion | HIGH |
| MC-03 | New Feature Requests Must Route to Planning — Not Into Maintenance | CRITICAL |
| MC-04 | Review Cycle Standards Do Not Relax in Maintenance | CRITICAL |
| MC-05 | One Issue Per Maintenance Task — No Bundling | MEDIUM |
| MC-06 | CHANGELOG.md Must Be Updated for Every Approved Fix | MEDIUM |
| MC-07 | CRITICAL and HIGH Fixes Must Have a Deployment Plan Before Closing | HIGH |
| MC-08 | Queued Issues Are Prioritized by Severity — Always | MEDIUM |

## Self-Check Schedule

Run this checklist after every 10 messages during Maintenance:

- MC-01: Has every issue been triaged before fix work began?
- MC-02: Is the current fix staying within defined scope?
- MC-03: Have any new feature requests been routed to Planning?
- MC-04: Is the review cycle running to full standard (zero legitimate issues)?
- MC-05: Is each issue in its own separate task?
- MC-06: Has CHANGELOG.md been updated for all approved fixes?
- MC-07: Do CRITICAL/HIGH fixes have a deployment plan before closing?
- MC-08: Are queued issues being addressed in severity order?

PLUS all 20 global constraint checks from global/constraints.md

IF ANY CHECK FAILS: Course-correct IMMEDIATELY before continuing.

## Violation Severity Reference

| Constraint | Severity | Immediate Action |
|---|---|---|
| MC-01: Fix started without triage | HIGH | Stop fix, run triage, confirm scope |
| MC-02: Fix scope expanded beyond issue | HIGH | Revert out-of-scope changes, create separate task |
| MC-03: New feature implemented as maintenance fix | CRITICAL | Stop, create story, route to Planning |
| MC-04: Review cycle standard relaxed | CRITICAL | Re-run full review cycle to zero issues |
| MC-05: Multiple issues bundled in one task | MEDIUM | Separate tasks unless technically inseparable |
| MC-06: CHANGELOG.md not updated after approval | MEDIUM | Update immediately, before next session |
| MC-07: CRITICAL/HIGH approved without deployment plan | HIGH | Create deployment plan before deployment |
| MC-08: Lower priority work done ahead of higher priority | MEDIUM | Reorder queue, address higher priority first |
