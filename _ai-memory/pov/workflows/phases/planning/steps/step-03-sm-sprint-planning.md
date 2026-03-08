---
name: 'step-03-sm-sprint-planning'
description: 'Activate SM to initialize or update sprint planning and select stories for the sprint'
nextStepFile: './step-04-sm-creates-story-files.md'
---

# Step 3: SM Sprint Planning

## STEP GOAL
Activate the SM agent to create or update sprint-status.yaml and select stories for the sprint. First sprint initializes tracking from scratch. Subsequent sprints use velocity and retrospective data.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: PRD.md, architecture.md, epics/, retrospective output (if any), state summary
- Limits: SM selects and sequences stories. Parzival reviews in Step 5.

## MANDATORY SEQUENCE

### 1. Determine Planning Mode

**First Sprint -- Initialize:**
- Create sprint-status.yaml tracking all epics and stories
- Assign each story a status: ready / not-ready / blocked
- Identify correct starting scope (foundation stories first)
- Confirm dependency order across all epics
- Recommend Sprint 1 scope

Sprint 1 scope criteria:
- Foundation stories that unblock the most subsequent work
- Stories that establish core patterns used throughout the project
- No more stories than can be completed in one sprint cycle
- Clear stopping point -- Sprint 1 should produce something testable

**Subsequent Sprint -- Plan Next:**
- Update sprint-status.yaml to close current sprint
- Identify carryover stories (if any)
- Select next sprint stories based on: carryover first, then priority, then velocity
- Confirm all selected stories are ready status
- Flag any blocked stories with reason

### 2. Prepare SM Instruction
Include all relevant inputs (PRD, architecture, epics, retrospective output if available).

### 3. Dispatch SM via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the SM.

### 4. Receive Sprint Plan
Receive updated sprint-status.yaml and recommended story list with sequence.

## CRITICAL STEP COMPLETION NOTE
ONLY when sprint plan is received from SM, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- SM dispatched through agent-dispatch workflow
- Sprint mode (first vs subsequent) correctly determined
- Sprint scope is realistic given velocity (or conservative for first sprint)
- All selected stories have ready status

### FAILURE:
- Planning more stories than velocity supports
- Including stories with unmet dependencies
- Not distinguishing first sprint from subsequent
- SM dispatched directly instead of through agent-dispatch
