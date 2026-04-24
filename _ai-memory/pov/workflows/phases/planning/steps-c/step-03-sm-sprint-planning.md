---
name: 'step-03-sm-sprint-planning'
description: 'Define sprint planning scope and dispatch SM via agent-dispatch cycle'
nextStepFile: './step-04-sm-creates-story-files.md'
---

# Step 3: SM Sprint Planning

**Progress: Step 3 of 7** — Next: SM Creates Story Files

## STEP GOAL:

Define the sprint planning scope and dispatch the SM agent via the agent-dispatch cycle to create or update sprint-status.yaml and select stories for the sprint. First sprint initializes tracking from scratch. Subsequent sprints use velocity and retrospective data.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: PRD.md, architecture.md, epics/, retrospective output (if any), state summary
- Focus: Sprint scope definition and SM dispatch — story file creation happens in the next step
- Limits: SM selects and sequences stories. Parzival reviews in Step 5.
- Dependencies: State summary from Step 1, retrospective output from Step 2 (if applicable)

- Focus on defining sprint scope and dispatching SM — do not create story files yet
**Behavioral Constraints:**
- FORBIDDEN to dispatch SM directly — must use agent-dispatch workflow
- Approach: Determine planning mode (first vs subsequent), then dispatch SM with full context
- Sprint scope must be realistic given velocity; carryover stories come first

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Determine Planning Mode

**Parzival's Responsibility (Layer 1)**

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

---

### 2. Prepare SM Instruction

**Parzival's Responsibility (Layer 1)**

Include all relevant inputs (PRD, architecture, epics, retrospective output if available).

---

### 3. Dispatch SM via Agent Dispatch

**Execution (via agent-dispatch cycle)**

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the SM.

---

### 4. Receive Sprint Plan

**Parzival's Responsibility (Layer 1)**

Receive updated sprint-status.yaml and recommended story list with sequence.

## CRITICAL STEP COMPLETION NOTE

ONLY when sprint plan is received from SM, load and read fully {nextStepFile}
