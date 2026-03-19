---
id: release
name: Release Phase Constraints
description: Active only during WF-RELEASE — dropped when Release exits
authority: If any Release constraint conflicts with a global constraint, the global constraint wins
---

# Release Phase Constraints

> **Scope**: Active only during WF-RELEASE
> **Loaded**: When WF-RELEASE begins, alongside global constraints
> **Dropped**: When Release exits
> **Inherits**: All 20 global constraints — these add on top

## Priority Rule

**If any Release constraint conflicts with a global constraint — the global constraint wins.**

Global constraints (GC-01 through GC-20) are always active. The constraints below apply only during WF-RELEASE. When Release exits, these constraints are dropped.

Release is a one-way gate. Once the user signs off, deployment proceeds. The constraints here exist because mistakes at this phase have the highest cost and visibility of any phase in the project.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| RC-01 | Changelog Must Be Accurate and Complete | HIGH |
| RC-02 | Rollback Plan Must Exist and Be Specific | CRITICAL |
| RC-03 | Deployment Checklist Must Be DEV-Verified Before Sign-Off | HIGH |
| RC-04 | Breaking Changes Must Be Explicitly Surfaced to User | CRITICAL |
| RC-05 | Release Cannot Proceed Without Explicit User Sign-Off | CRITICAL |
| RC-06 | Release Notes Must Be Written for the User/Stakeholder Audience | MEDIUM |
| RC-07 | Integration Must Have Passed Before Release Begins | CRITICAL |

## Self-Check Schedule

Run this checklist after every 10 messages during Release:

- RC-01: Is the changelog accurate and complete — every entry traceable?
- RC-02: Does a specific, executable rollback plan exist?
- RC-03: Has the deployment checklist been DEV-verified?
- RC-04: Are breaking changes explicitly surfaced in the sign-off?
- RC-05: Has explicit user sign-off been received before deployment?
- RC-06: Are release notes written for user/stakeholder audience?
- RC-07: Did integration pass before release began?

PLUS all 20 global constraint checks from global/constraints.md

IF ANY CHECK FAILS: Course-correct IMMEDIATELY before continuing.

## Violation Severity Reference

| Constraint | Severity | Immediate Action |
|---|---|---|
| RC-01: Changelog inaccurate or incomplete | HIGH | Return to SM, fix before sign-off |
| RC-02: No specific rollback plan | CRITICAL | Create specific rollback plan before proceeding |
| RC-03: Deployment checklist not DEV-verified | HIGH | Run DEV verification before sign-off |
| RC-04: Breaking changes not surfaced to user | CRITICAL | Add to sign-off presentation explicitly |
| RC-05: Deployment begun without sign-off | CRITICAL | Stop — get explicit user authorization |
| RC-06: Release notes in technical language | MEDIUM | Return to SM for audience-appropriate rewrite |
| RC-07: Release started without integration pass | CRITICAL | Block release — run integration first |
