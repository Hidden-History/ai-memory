---
id: integration
name: Integration Phase Constraints
description: Active only during WF-INTEGRATION — dropped when Integration exits
authority: If any Integration constraint conflicts with a global constraint, the global constraint wins
---

# Integration Phase Constraints

> **Scope**: Active only during WF-INTEGRATION
> **Loaded**: When WF-INTEGRATION begins, alongside global constraints
> **Dropped**: When Integration exits
> **Inherits**: All 20 global constraints — these add on top

## Priority Rule

**If any Integration constraint conflicts with a global constraint — the global constraint wins.**

Global constraints (GC-01 through GC-20) are always active. The constraints below apply only during WF-INTEGRATION. When Integration exits, these constraints are dropped.

Integration is a milestone gate. The constraints here are stricter than Execution because integration failures have wider blast radius — a problem found here affects everything downstream.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| IC-01 | Test Plan Must Be Created and Fully Executed Before Integration Exits | CRITICAL |
| IC-02 | Architect Cohesion Check Is Mandatory | CRITICAL |
| IC-03 | All Milestone Stories Must Be Complete Before Integration Begins | HIGH |
| IC-04 | Integration Issues Cannot Be Deferred to Next Sprint | CRITICAL |
| IC-05 | Full Test Plan Re-Runs After Every Fix Pass | HIGH |
| IC-06 | DEV Integration Review Covers All Files in Milestone Scope | HIGH |
| IC-07 | Security Full-Flow Verification Is Required for All Applicable Integrations | CRITICAL |

## Self-Check Schedule

Run this checklist after every 10 messages during Integration:

- IC-01: Is the test plan created and being fully executed?
- IC-02: Has the Architect cohesion check been run or scheduled?
- IC-03: Are all milestone stories confirmed complete before integration began?
- IC-04: Are all integration issues being fixed (none silently deferred)?
- IC-05: Is the full test plan re-running after each fix pass?
- IC-06: Does the DEV review cover all files in full milestone scope?
- IC-07: Is security full-flow verification included for applicable integrations?

PLUS all 20 global constraint checks from global/constraints.md

IF ANY CHECK FAILS: Course-correct IMMEDIATELY before continuing.

## Violation Severity Reference

| Constraint | Severity | Immediate Action |
|---|---|---|
| IC-01: Integration exited without full test plan pass | CRITICAL | Return to Phase 6 — all tests must pass |
| IC-02: Architect cohesion check skipped | CRITICAL | Run Architect check before advancing |
| IC-03: Integration started with incomplete stories | HIGH | Complete all stories, then restart integration |
| IC-04: Integration issue silently deferred | CRITICAL | Classify issue, fix or get explicit user deferral |
| IC-05: Only partial test re-run after fixes | HIGH | Re-run full test plan — reject partial results |
| IC-06: DEV review scoped to partial files | HIGH | Expand review scope to full milestone files |
| IC-07: Security full-flow skipped for applicable integration | CRITICAL | Add security full-flow to test plan, execute it |
