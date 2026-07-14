---
name: 'session-start-instructions'
description: 'Session start protocol: load context, compile status, present recommendation, wait for direction'
---
> **Note**: This file is a BMAD module summary. The authoritative execution path is `workflow.md` → step files (firstStep/nextStepFile chain). If this summary conflicts with step file content, the step files are canonical.

# session-start — Instructions

## Prerequisites

- Parzival is activated as the oversight agent for this session
- `oversight_path` (the POV workspace) is accessible
- `/aim-parzival-bootstrap` skill is available for Qdrant retrieval

## Workflow Overview

Session-start initializes a Parzival oversight session by loading all relevant context, compiling a status report, and presenting it to the user before waiting for direction. This workflow is the entry point for every Parzival-managed work session and must complete fully before any execution begins.

The workflow follows a layered initialization: first loading project context files and triggering the Parzival bootstrap (for Qdrant-backed memory retrieval). It then compiles a structured status report from tracking files and presents it with a recommended next action, waiting for the user to confirm direction before anything proceeds.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-load-context.md` | Load all project tracking files and establish the current session baseline |
| 1b | `step-01b-parzival-bootstrap.md` | (Parzival only) Trigger `/aim-parzival-bootstrap` for L1–L4 Qdrant memory retrieval |
| 2 | `step-02-compile-status.md` | Synthesize loaded context into a structured status report with active sprint, open blockers, and pending decisions |
| 3 | `step-03-present-and-wait.md` | Present the status report and Parzival's recommendation to the user; halt for direction |

## Key Decisions

- **Bootstrap trigger**: Whether to run the Parzival bootstrap (step-01b) depends on whether Parzival is operating as the oversight agent; skip for other agents
- **Constraint injection**: Behavioral constraints are loaded at Parzival activation (GC-01 through GC-22 always active). No dedicated constraint-injection step is required during session-start.
- **Recommendation framing**: Parzival must always present a specific recommendation with reasoning, never just "what would you like to do?"

## Outputs

- Compiled status report presented to the user
- Parzival bootstrap memory loaded (when applicable)
- Behavioral constraints active for the session (loaded at activation, not session-start)

## Exit Conditions

The workflow exits when:
- The status report has been presented to the user
- Parzival's recommendation for next action has been stated
- The user has been asked for direction and the workflow halts to await their response
