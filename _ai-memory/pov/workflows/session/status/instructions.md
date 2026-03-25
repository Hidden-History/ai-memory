---
name: 'session-status-instructions'
description: 'Quick status check: read project state and present current phase, task, blockers, and risks'
---

# session-status — Instructions

## Prerequisites

- Parzival oversight workspace exists at the configured `oversight_path`
- Four tracking files are accessible:
  - `SESSION_WORK_INDEX.md`
  - `sprint-status.yaml` (or equivalent sprint tracking file)
  - `blockers-log.md`
  - `decision-log.md`

## Workflow Overview

Session-status is a lightweight inline workflow — it has no step files. The entire logic executes in a single sequence without loading separate step files. It reads four tracking files, identifies the last session from the work index, compiles a Quick Status block, and presents it. No session is started, no files are modified.

This workflow is used when the user needs a fast project orientation without triggering a full session-start initialization. It is intentionally minimal: read, summarize, present. It does not load Qdrant memory, does not inject constraints, and does not ask the user for direction afterward.

## Step Summary

| Step | File | Purpose |
|------|--------|---------|
| 1 | Inline (`workflow.md`) | Read `SESSION_WORK_INDEX.md` to find the last completed session |
| 2 | Inline (`workflow.md`) | Read sprint tracking, blockers-log, and decision-log to extract current state |
| 3 | Inline (`workflow.md`) | Compile and present Quick Status block (sprint state, open blockers, pending decisions, last session summary) |

## Key Decisions

- **No file modifications**: This workflow is read-only; no tracking files are updated
- **No session initialization**: Does not start a session, load bootstrap memory, or inject constraints
- **Graceful degradation**: If any tracking file is missing, present available data and note the gap

## Outputs

- Quick Status block presented inline (sprint state, open blockers count, pending decisions, last session reference)

## Exit Conditions

The workflow exits when:
- The Quick Status block has been displayed to the user
- No further prompts or questions are asked
