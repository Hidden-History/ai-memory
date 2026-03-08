---
name: 'step-02-retrospective'
description: 'Run sprint retrospective for subsequent sprints before planning begins (skip for first sprint)'
nextStepFile: './step-03-sm-sprint-planning.md'
---

# Step 2: Retrospective (Subsequent Sprints Only)

## STEP GOAL
For every sprint after the first, run a retrospective before planning begins. The retrospective informs the next sprint's scope, sizing, and approach.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: sprint-status.yaml, completed story files, state summary from Step 1
- Limits: Retrospective runs on the completed sprint. Does not modify the next sprint.

## MANDATORY SEQUENCE

### 1. Check If Retrospective Should Run

**RUN when:**
- A sprint has fully closed (all stories approved or explicitly dropped)
- User has confirmed the sprint is done

**SKIP when:**
- This is the very first sprint (nothing to retrospect)
- User explicitly skips ("let us just plan the next sprint")
- Mid-sprint replanning (retrospective runs at sprint close, not mid-sprint)

**IF SKIPPING:** Proceed directly to {nextStepFile}

### 2. Prepare Retrospective Instruction
SM must cover:
1. What was completed this sprint (stories done)
2. What was not completed (carryover or dropped -- with reason)
3. Issues or blockers encountered during the sprint
4. Patterns in review cycles (many passes = story too complex?)
5. Velocity: stories planned vs. stories completed
6. Recommended adjustments for next sprint: story sizing, dependency sequencing, scope

### 3. Dispatch SM via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the SM with the retrospective instruction.

### 4. Review Retrospective Output
Parzival reviews for:
- Are carryover stories explained (not just listed)?
- Are velocity numbers accurate?
- Are recommendations specific and actionable?
- Are recurring issues identified?
- Do recommendations inform the upcoming sprint plan?

### 5. Present Retrospective Summary to User
Present before planning begins:
"Sprint [N] retrospective complete.
 Completed: [N] stories
 Carryover: [N] stories -- [brief reason]
 Key finding: [most important observation]
 Recommendation for next sprint: [specific recommendation]

 Ready to begin planning Sprint [N+1]?"

Wait for user acknowledgment before proceeding.

## CRITICAL STEP COMPLETION NOTE
Whether retrospective ran or was skipped, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Retrospective ran for subsequent sprints
- Correctly skipped for first sprint
- Velocity data is accurate
- Recommendations are specific and inform next sprint
- User acknowledged before planning begins

### FAILURE:
- Skipping retrospective without justification
- Running retrospective for first sprint
- Accepting vague recommendations
- Not presenting to user before planning
