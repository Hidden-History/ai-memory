---
name: 'step-01-load-context'
description: 'Load all session context from oversight tracking files and most recent handoff'
nextStepFile: './step-01b-parzival-bootstrap.md'
---

# Step 1: Load Context

## STEP GOAL
Load all relevant project context so Parzival has a complete picture of the current state before compiling a status report.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All files under `{oversight_path}/`
- Limits: Read only -- do not modify any files during context loading

## MANDATORY SEQUENCE

### 1. Read Session Work Index
Read `{oversight_path}/SESSION_WORK_INDEX.md` to understand the current project state and most recent session entry.

If the file does not exist, note this as a first-session scenario and proceed with available files.

### 2. Read Most Recent Handoff
Find and read the most recent `{oversight_path}/session-logs/SESSION_HANDOFF_*.md` file (sorted by date in filename).

Extract:
- Date and topic of last session
- What was accomplished
- What was in progress
- Recommended next steps
- Open questions

If no handoff files exist, note this as a first-session scenario.

### 3. Read Task Tracker
Read `{oversight_path}/tracking/task-tracker.md` to understand:
- Current sprint and its tasks
- Status of each task (backlog, doing, blocked, review, done)
- Any tasks that were in-progress at last session end

### 4. Read Blockers Log
Read `{oversight_path}/tracking/blockers-log.md` to identify:
- Any active (unresolved) blockers
- Severity of each active blocker
- Impact on current work

### 5. Read Risk Register
Read `{oversight_path}/tracking/risk-register.md` to identify:
- High or critical risks
- Any risks that have changed status since last session

### 6. Compile Loaded Context
Organize the loaded information into these categories:
- **Last session**: date, topic, outcome
- **Current task**: ID, title, status
- **Blockers**: count and brief descriptions
- **Risks**: count of high/critical, brief descriptions
- **Continuation point**: where work should resume

## CRITICAL STEP COMPLETION NOTE
ONLY when all available context files have been read, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All existing context files were read in full
- Missing files were noted but did not block execution
- Context is organized by category for status compilation
- No files were modified

### FAILURE:
- Skipping context files that exist
- Failing to note missing files
- Modifying any files during context load
- Proceeding before reading all available files
