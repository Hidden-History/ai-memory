---
id: execution
name: Execution Phase Constraints
description: Active only during WF-EXECUTION -- dropped when Execution exits
authority: If any Execution constraint conflicts with a global constraint, the global constraint wins
---

# Execution Phase Constraints

> **Scope**: Active only during WF-EXECUTION
> **Loaded**: When WF-EXECUTION begins, alongside global constraints
> **Dropped**: When Execution exits (to Planning or Integration)
> **Inherits**: All 20 global constraints -- these add on top

## Priority Rule

**If any Execution constraint conflicts with a global constraint -- the global constraint wins.**

Global constraints (GC-01 through GC-20) are always active. The constraints below apply only during WF-EXECUTION. When Execution exits (to Planning or Integration), these constraints are dropped.

Execution is the most constraint-dense phase because it is the most frequent. Every story runs through this phase. Every constraint here is non-negotiable.

## Constraint Summary

| ID | Name | Severity |
|----|------|----------|
| EC-01 | MUST Verify Story Requirements Against Current Project Files Before Proceeding | CRITICAL |
| EC-03 | CANNOT Generate a Fix Instruction Without a Review Result | HIGH |
| EC-04 | Story Scope Cannot Expand During Execution Without User Approval | HIGH |
| EC-05 | All Acceptance Criteria Must Be Explicitly Confirmed Satisfied | CRITICAL |
| EC-06 | DEV Cannot Self-Certify Completion -- Parzival Verifies | CRITICAL |
| EC-07 | Implementation Decisions Must Be Reviewed and Documented | MEDIUM |
| EC-08 | Security Requirements Must Be Addressed for All Applicable Stories | CRITICAL |
| EC-09 | Sprint Status Must Be Updated After Every Story State Transition | MEDIUM |
| EC-10 | Observability Requirements for New Code | HIGH |

**Note**: EC-02 (Use Instruction Template) has been moved to the aim-agent-dispatch skill as a Layer 3 constraint. It applies during agent dispatch, not as a phase constraint.

## Self-Check Schedule

Run this checklist after every 10 messages during Execution:

- EC-01: Did I verify story requirements against current project files?
- EC-03: Are fix instructions based on review results only?
- EC-04: Has story scope stayed within defined boundaries?
- EC-05: Are all acceptance criteria explicitly confirmed (not assumed)?
- EC-06: Did I verify completion claims independently?
- EC-07: Have implementation decisions been reviewed and documented?
- EC-08: Have security requirements been addressed for applicable stories?
- EC-09: Is sprint-status.yaml current after every state transition?
- EC-10: Does the current story involve new scripts, services, or features? If yes, have I included observability requirements in agent instructions?

PLUS all 20 global constraint checks from global/constraints.md

IF ANY CHECK FAILS: Course-correct IMMEDIATELY before continuing.

## Violation Severity Reference

| Constraint | Severity | Immediate Action |
|---|---|---|
| EC-01: Story proceeded without verification | CRITICAL | Stop execution, verify story, update if needed |
| EC-03: Fix instruction without review result | HIGH | Retract fix, wait for review result |
| EC-04: Story scope expanded without approval | HIGH | Revert out-of-scope work, create new story |
| EC-05: Acceptance criteria not explicitly confirmed | CRITICAL | Run Phase 5 verification before user presentation |
| EC-06: Self-certification accepted without verification | CRITICAL | Run full verification cycle regardless |
| EC-07: Undocumented implementation decision | MEDIUM | Review decision, document if precedent-setting |
| EC-08: Security requirements skipped | CRITICAL | Run security checklist, fix all gaps |
| EC-09: sprint-status.yaml not updated on transition | MEDIUM | Update immediately, verify accuracy |
| EC-10: New code without observability requirements | HIGH | Add observability checklist to agent instructions, verify compliance |
