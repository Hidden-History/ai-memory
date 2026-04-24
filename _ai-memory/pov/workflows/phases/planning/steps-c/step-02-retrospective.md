---
name: 'step-02-retrospective'
description: 'Run sprint retrospective for subsequent sprints before planning begins (skip for first sprint)'
nextStepFile: './step-03-sm-sprint-planning.md'
---

# Step 2: Retrospective (Subsequent Sprints Only)

**Progress: Step 2 of 7** — Next: SM Sprint Planning

## STEP GOAL:

For every sprint after the first, run a retrospective before planning begins. The retrospective informs the next sprint's scope, sizing, and approach.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: sprint-status.yaml, completed story files, state summary from Step 1
- Focus: Retrospective on completed sprint only — do not modify or plan the next sprint
- Limits: Retrospective runs on the completed sprint. Does not modify the next sprint.
- Dependencies: State summary from Step 1

- Focus on retrospective for the completed sprint — do not plan the next sprint yet
**Behavioral Constraints:**
- FORBIDDEN to run retrospective for first sprint or skip without justification
- Approach: Evidence-based retrospective using sprint-status.yaml and story files
- User must acknowledge retrospective findings before planning begins

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Check If Retrospective Should Run

**RUN when:**
- A sprint has fully closed (all stories approved or explicitly dropped)
- User has confirmed the sprint is done

**SKIP when:**
- This is the very first sprint (nothing to retrospect)
- User explicitly skips ("let us just plan the next sprint")
- Mid-sprint replanning (retrospective runs at sprint close, not mid-sprint)

**IF SKIPPING:** Proceed directly to {nextStepFile}

---

### 2. Prepare Retrospective Instruction

SM must cover:
1. What was completed this sprint (stories done)
2. What was not completed (carryover or dropped -- with reason)
3. Issues or blockers encountered during the sprint
4. Patterns in review cycles (many passes = story too complex?)
5. Velocity: stories planned vs. stories completed
6. Recommended adjustments for next sprint: story sizing, dependency sequencing, scope
7. DORA-analog process metrics (derive from sprint-status.yaml and story review records):
   - **Review-cycle count per story**: total review passes per story before approval — stories requiring >2 cycles flag scope ambiguity or instruction gaps
   - **Reopened-task rate**: count of stories returned to in-progress after being marked done — every reopened story requires a root-cause note
   - **Rework rate**: stories requiring significant revision (>30% of delivered content redone) — signals misalignment in requirements, instructions, or acceptance criteria

---

### 3. Dispatch SM via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the SM with the retrospective instruction.

---

### 4. Review Retrospective Output

Parzival reviews for:
- Are carryover stories explained (not just listed)?
- Are velocity numbers accurate?
- Are recommendations specific and actionable?
- Are recurring issues identified?
- Are DORA-analog metrics reported (review-cycle count, reopened-task rate, rework rate)?
- Do recommendations inform the upcoming sprint plan?

---

### 5. Present Retrospective Summary to User

Present before planning begins:
"Sprint [N] retrospective complete.
 Completed: [N] stories
 Carryover: [N] stories -- [brief reason]
 Process metrics: avg review cycles [N], reopened tasks [N], rework rate [N%]
 Key finding: [most important observation]
 Recommendation for next sprint: [specific recommendation]

 Ready to begin planning Sprint [N+1]?"

Wait for user acknowledgment before proceeding.

## CRITICAL STEP COMPLETION NOTE

Whether retrospective ran or was skipped, load and read fully {nextStepFile}
