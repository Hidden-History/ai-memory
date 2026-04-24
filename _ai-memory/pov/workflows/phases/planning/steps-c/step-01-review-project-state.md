---
name: 'step-01-review-project-state'
description: 'Review the current project state before any planning agent is activated'
nextStepFile: './step-02-retrospective.md'
---

# Step 1: Review Current Project State

**Progress: Step 1 of 7** — Next: Retrospective

## STEP GOAL:

Before activating any agent, Parzival reads the current state to understand what is available, what has changed, and what the sprint planning inputs are.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: sprint-status.yaml (if exists), epics/, architecture.md, PRD.md, decisions.md
- Focus: State assessment only — do not activate agents or modify files
- Limits: Only read and assess. Do not activate agents. Do not modify files.
- Dependencies: None — this is the first step of the planning workflow

- Focus on reading and assessing project state — do not activate agents
**Behavioral Constraints:**
- FORBIDDEN to modify files or activate any agent during state review
- Approach: Systematic read of all project artifacts in specified order
- Must identify first sprint vs subsequent sprint correctly

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Read sprint-status.yaml (if exists)

- Current sprint number
- Stories complete, in-progress, not started
- Carryover stories from previous sprint
- Overall sprint velocity (stories completed per sprint)

---

### 2. Read epics/ Directory

- Which epics have all stories complete?
- Which epics have stories remaining?
- Any stories added or modified since last planning?

---

### 3. Read architecture.md

- Any architecture updates that affect story technical context?
- Any new decisions since last sprint?

---

### 4. Read PRD.md

- Any scope changes approved since last sprint?
- Are priorities still current?

---

### 5. Read decisions.md

- Any decisions made mid-sprint that affect story content?
- Any open questions resolved that affect upcoming stories?

---

### 6. Produce State Summary

- Stories remaining by epic
- Stories completed to date
- Carryover stories from prior sprint (if any)
- Scope changes to incorporate
- Estimated stories available for next sprint

---

### 7. Determine If This Is First Sprint

If sprint-status.yaml does not exist or this is sprint 1: skip retrospective in next step.

## CRITICAL STEP COMPLETION NOTE

ONLY when state review is complete, load and read fully {nextStepFile}
