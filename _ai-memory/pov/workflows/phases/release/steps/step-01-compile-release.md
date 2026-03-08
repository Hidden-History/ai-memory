---
name: 'step-01-compile-release'
description: 'Compile the complete picture of what is changing in this release'
nextStepFile: './step-02-create-changelog.md'
---

# Step 1: Compile What Is Being Released

## STEP GOAL
Before any release artifact is created, compile the complete picture of what is changing. Read all sources and produce a comprehensive release summary.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: sprint-status.yaml, story files, integration findings, PRD.md, architecture.md
- Limits: Only compile. Do not create artifacts yet.

## MANDATORY SEQUENCE

### 1. Verify Sprint Completion
From sprint-status.yaml:
- All stories confirmed complete
- No stories in IN-PROGRESS or IN-REVIEW state

### 2. Read All Completed Story Files
For each story:
- What feature/behavior does it implement?
- What files were created or modified?
- Any implementation decisions that affect behavior?

### 3. Read Integration Findings
From WF-INTEGRATION:
- Pre-existing issues fixed during integration
- Architectural improvements made
- Notable behavior changes from test results

### 4. Read PRD for Coverage
- Which PRD requirements are fulfilled by this release?
- Which requirements remain for future releases?

### 5. Read Architecture Deployment Section
- Deployment process for this stack
- Environment variables or config changes needed
- Database migrations required
- Infrastructure changes required

### 6. Produce Release Summary
Compile:
- Features being released (each with one-line description)
- Changes to existing behavior
- Files changed (created count, modified count)
- Database changes (migrations, schema changes, data migrations)
- Configuration changes (new env vars, changed config, infrastructure)
- PRD coverage (requirements fulfilled, requirements remaining)

## CRITICAL STEP COMPLETION NOTE
ONLY when release summary is compiled, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All stories read (not summarized from memory)
- Changes to existing behavior explicitly identified
- Database and configuration changes captured
- PRD coverage documented

### FAILURE:
- Compiling from memory instead of reading story files
- Missing behavior changes to existing features
- Not identifying database migrations
- Not checking PRD coverage
