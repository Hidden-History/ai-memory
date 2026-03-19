---
name: 'init-new-instructions'
description: 'New project initialization: gather info, define goals, create baseline files, establish oversight structure'
---

# init-new — Instructions

## Prerequisites

- A new project is being brought under Parzival oversight for the first time
- AI Memory installation (`~/.ai-memory`) is accessible and configured
- The project directory exists and is accessible
- No existing Parzival oversight workspace (`_ai-memory/pov/`) is present in the project

## Workflow Overview

The init-new workflow establishes a complete Parzival oversight baseline for a brand-new project. It gathers essential project information, validates it, verifies the AI Memory installation is functional, creates all baseline tracking and oversight files, establishes the initial agent team configuration, and verifies the completed baseline before presenting it to the user for approval.

This workflow runs exactly once per project — at the moment Parzival is first activated for a project. It must complete fully before any session-start or phase workflow can be used.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-gather-project-info.md` | Collect project name, repository path, tech stack, and initial team configuration |
| 2 | `step-02-validate-and-clarify.md` | Validate gathered information; surface and resolve any ambiguities before proceeding |
| 3 | `step-03-verify-installation.md` | Verify that AI Memory is installed, Qdrant is reachable, and required skills are available |
| 4 | `step-04-create-baseline-files.md` | Create all oversight baseline files: `SESSION_WORK_INDEX.md`, `sprint-status.yaml`, `blockers-log.md`, `decision-log.md` |
| 5 | `step-05-establish-teams.md` | Configure the initial BMAD agent team structure for this project |
| 6 | `step-06-verify-baseline.md` | Verify all created files are well-formed and accessible |
| 7 | `step-07-present-and-approve.md` | Present the completed baseline to the user for review and approval |

## Key Decisions

- **Installation verification**: Step 3 surfaces any AI Memory configuration issues before files are created; a non-functional installation does not block baseline creation but is noted
- **Baseline completeness**: All four tracking files must be created in step 4 — partial baseline is not accepted
- **Team configuration**: Step 5 establishes the project's default agent teams; these can be revised later but must be initialized here

## Outputs

- Complete Parzival oversight workspace created (`_ai-memory/pov/`)
- Four baseline tracking files created and populated
- Agent team configuration established
- Baseline presented to and approved by user

## Exit Conditions

The workflow exits when:
- The user has approved the baseline in step 7
- The project is ready for its first session-start
