---
name: 'step-04-sm-creates-story-files'
description: 'Activate SM to create detailed story files for every story in the sprint'
nextStepFile: './step-05-parzival-reviews-sprint.md'
---

# Step 4: SM Creates Story Files

**Progress: Step 4 of 7** — Next: Parzival Reviews Sprint Plan and Story Files

## STEP GOAL:

For every story in the sprint, the SM agent creates a detailed story file with all seven required sections. Each story must be self-contained enough that a DEV agent can implement it without ambiguity.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Sprint story list from Step 3, epic files, PRD.md, architecture.md, project-context.md
- Focus: Story file creation via SM dispatch — Parzival reviews in the next step
- Limits: SM creates story files. Parzival reviews in the next step.
- Dependencies: Sprint story list from Step 3

- Focus on dispatching SM to create story files — do not review stories yet
**Behavioral Constraints:**
- FORBIDDEN to dispatch SM directly — must use agent-dispatch workflow
- Approach: Provide SM with complete story creation instruction including all 7 required sections
- Stories must be self-contained enough for DEV agent to implement without ambiguity

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Story Creation Instruction

Each story file must include seven sections:

1. **Story header** -- Story ID, title, epic reference, sprint assignment, status: ready
2. **User story** -- As a [user type], I want [action], so that [value]
3. **Acceptance criteria** -- From PRD where possible, specific and testable, minimum 3 per story
4. **Technical context** -- Files/modules to create or modify, architectural patterns to follow (cite architecture.md), standards to follow (cite project-context.md), database models (if applicable), API endpoints (if applicable)
5. **Dependencies** -- Stories that must complete first, external systems involved
6. **Out of scope** -- What this story explicitly does NOT include
7. **Implementation notes** -- Guidance from architecture decisions, known edge cases, security considerations

---

### 2. Dispatch SM via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the SM with the story creation instruction. Run once per story or as a batch.

---

### 3. Receive Story Files

Receive all story files from the SM.

## CRITICAL STEP COMPLETION NOTE

ONLY when all story files are received, load and read fully {nextStepFile}
