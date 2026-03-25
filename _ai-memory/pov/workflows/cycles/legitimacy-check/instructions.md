---
name: 'cycles-legitimacy-check-instructions'
description: 'Issue classification: read issue, check project files, classify LEGITIMATE/NON-ISSUE/UNCERTAIN, record, prioritize'
---

# cycles-legitimacy-check — Instructions

## Prerequisites

- An issue has been surfaced during code review, audit, or maintenance that requires classification
- Project files (architecture, specifications, oversight docs) are accessible for citation during classification
- The issue is described clearly enough for classification

## Workflow Overview

The legitimacy-check cycle classifies issues surfaced during code review, audit, or maintenance into LEGITIMATE, NON-ISSUE, or UNCERTAIN before any fix action is taken. It reads the issue, checks it against project files, applies formal classification criteria with project file citations, records the classification, and assigns a priority level.

This cycle prevents misclassified issues from entering the execution pipeline and ensures no issue is skipped or assumed. It is invoked whenever an issue is surfaced that has not yet been classified.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-read-issue.md` | Read and understand the incoming issue in full |
| 2 | `step-02-check-project-files.md` | Cross-reference the issue against project files (architecture, specs, standards) to gather citations |
| 3 | `step-03-classify-issue.md` | Classify the issue: LEGITIMATE (must fix) / NON-ISSUE (document, do not fix) / UNCERTAIN (trigger research protocol) |
| 4 | `step-04-record-classification.md` | Record the classification with criteria basis and project file citations |
| 5 | `step-05-assign-priority.md` | Assign priority level (CRITICAL/HIGH/MEDIUM/LOW) for LEGITIMATE issues |

## Key Decisions

- **Classification authority**: Parzival classifies using formal criteria (A1-A8, B1-B4, C1-C5); classification must be grounded in project file citations, not opinion
- **Pre-existing issues**: Pre-existing issues are not exempt from legitimacy — if they meet any Category A criterion, they are LEGITIMATE regardless of age
- **UNCERTAIN handling**: When project files do not clearly address an issue, it is classified UNCERTAIN and routed to the research protocol — guessing is forbidden

## Outputs

- Priority assigned for LEGITIMATE issues (CRITICAL/HIGH/MEDIUM/LOW)
- NON-ISSUE items documented with criteria basis
- UNCERTAIN items routed to research protocol

## Exit Conditions

The workflow exits when:
- The issue has been classified in step 3
- The classification has been recorded in step 4
- Priority has been assigned in step 5
