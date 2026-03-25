---
name: 'session-verify-instructions'
description: 'Verification protocol: determine type, select template, run checks, present pass/fail report'
---

# session-verify — Instructions

## Prerequisites

- An active Parzival oversight session
- Completed work exists that is being verified (story, code, or production artifact)
- Relevant acceptance criteria or verification checklist exists for the work type

## Workflow Overview

Session-verify runs a structured verification on completed work to ensure it meets defined criteria before the user is asked for approval. Parzival executes all checks; the user approves or rejects the result. The workflow supports three verification types — story, code, and production — each using a different checklist template.

The workflow first determines the verification type, then loads the appropriate checklist, executes each check systematically, and presents a full report. Uncertain checks are never marked as PASS; incomplete or ambiguous items are flagged. The user is never bypassed — Parzival verifies, the user approves.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-determine-type.md` | Identify verification type (story / code / production) and the work being verified |
| 2 | `step-02-load-checklist.md` | Load the appropriate checklist template for the identified type |
| 3 | `step-03-execute-checks.md` | Run each checklist item systematically; mark PASS / FAIL / SKIP with evidence |
| 4 | `step-04-report-results.md` | Present full verification report; ask user for approval or rejection decision |

## Key Decisions

- **Type selection**: The three types are mutually exclusive; never combine in a single run
- **Check integrity**: Uncertain checks are FAIL or SKIP, never PASS — no rounding up
- **Approval gate**: The report is always presented to the user; Parzival never self-approves

## Outputs

- Completed verification report (PASS/FAIL/SKIP per checklist item)
- Approval decision requested from user

## Exit Conditions

The workflow exits when:
- All checklist items have been evaluated
- The verification report has been presented to the user
- The user has been asked for their approval or rejection decision
