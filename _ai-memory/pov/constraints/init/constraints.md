---
id: init
name: Init Phase Constraints
description: Active during project initialization workflows (WF-INIT-NEW, WF-INIT-EXISTING)
authority: These constraints supplement global constraints during init phase
---

# Init Phase Constraints

> **Scope**: Active during WF-INIT-NEW and WF-INIT-EXISTING workflows
> **Loaded**: When init workflow is activated
> **Authority**: Supplements global constraints. If conflict, global wins.

## Priority Rule

**If any Init constraint conflicts with a global constraint — the global constraint wins.**

Global constraints (GC-01 through GC-22) are always active. The constraints below are specific to the Init phase and add additional rules that apply only while WF-INIT-NEW or WF-INIT-EXISTING is running. When Init exits, these constraints are dropped.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| IN-01 | Verify Project Structure Before Proceeding | HIGH |
| IN-02 | Detect and Report Existing Project State Accurately | HIGH |
| IN-03 | Confirm User Intent Before Creating or Modifying Project Files | CRITICAL |
| IN-04 | Validate AI-Memory Installation Completeness | HIGH |
| IN-05 | Establish Baseline Before Entering Any Phase Workflow | CRITICAL |
