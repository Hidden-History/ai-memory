---
name: 'step-02-compile-status'
description: 'Compile all loaded context into a structured session status report'
nextStepFile: './step-03-present-and-wait.md'
---

# Step 2: Compile Status Report

## STEP GOAL
Take the context loaded in Step 1 and compile it into a structured status report ready for presentation to the user.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All context loaded and organized in Step 1
- Limits: Compile status facts only -- recommendations are added in Step 3 based on this compiled data

## MANDATORY SEQUENCE

### 1. Determine Session Continuity
Based on the loaded context, classify this session:
- **Continuation**: Previous handoff exists, work was in progress
- **Fresh start**: No handoff exists, or previous work was completed
- **Recovery**: Previous session ended unexpectedly (no handoff, but work was in progress)

### 2. Build Status Fields

Compile each field from the loaded context:

**Last Session**:
- Date: from handoff or SESSION_WORK_INDEX
- Summary: 1-sentence description of what was accomplished

**Current Task**:
- ID: from task-tracker (the task marked as "doing" or most recently active)
- Title: task title
- Status: doing / blocked / review / backlog

**Active Blockers**:
- Count of unresolved blockers
- Brief description of each (1 line per blocker)

**Risks**:
- Count of high/critical risks
- Brief description of each (1 line per risk)

**Continuation Point**:
- Where work should resume based on handoff "Next Steps" or current task status

### 3. Identify Gaps or Anomalies

Flag if:
- Task tracker shows a task as "doing" but handoff says it was completed
- Blockers reference tasks that are marked as done
- Risk register has not been updated recently
- Any tracking file was missing

Note these as items to mention during presentation, not as recommendations.

### 4. Format the Report

Structure the compiled data using the presentation format defined in the next step. Do not present yet -- just prepare the content.

## CRITICAL STEP COMPLETION NOTE
ONLY when the status report is fully compiled, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All loaded context is reflected in the status report
- Status fields are factual, not interpretive
- Anomalies are noted without recommendations
- Report is ready for presentation

### FAILURE:
- Omitting loaded context from the report
- Adding recommendations or opinions to the compiled report
- Presenting the report before it is fully compiled
- Ignoring anomalies between tracking files
