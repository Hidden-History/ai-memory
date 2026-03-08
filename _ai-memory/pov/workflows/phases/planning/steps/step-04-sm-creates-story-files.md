---
name: 'step-04-sm-creates-story-files'
description: 'Activate SM to create detailed story files for every story in the sprint'
nextStepFile: './step-05-parzival-reviews-sprint.md'
---

# Step 4: SM Creates Story Files

## STEP GOAL
For every story in the sprint, the SM agent creates a detailed story file with all seven required sections. Each story must be self-contained enough that a DEV agent can implement it without ambiguity.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Sprint story list from Step 3, epic files, PRD.md, architecture.md, project-context.md
- Limits: SM creates story files. Parzival reviews in the next step.

## MANDATORY SEQUENCE

### 1. Prepare Story Creation Instruction
Each story file must include seven sections:

1. **Story header** -- Story ID, title, epic reference, sprint assignment, status: ready
2. **User story** -- As a [user type], I want [action], so that [value]
3. **Acceptance criteria** -- From PRD where possible, specific and testable, minimum 3 per story
4. **Technical context** -- Files/modules to create or modify, architectural patterns to follow (cite architecture.md), standards to follow (cite project-context.md), database models (if applicable), API endpoints (if applicable)
5. **Dependencies** -- Stories that must complete first, external systems involved
6. **Out of scope** -- What this story explicitly does NOT include
7. **Implementation notes** -- Guidance from architecture decisions, known edge cases, security considerations

### 2. Dispatch SM via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the SM with the story creation instruction. Run once per story or as a batch.

### 3. Receive Story Files
Receive all story files from the SM.

## CRITICAL STEP COMPLETION NOTE
ONLY when all story files are received, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All sprint stories have complete story files
- All seven sections present in each story
- Technical context references architecture.md and project-context.md
- Acceptance criteria are specific and testable

### FAILURE:
- Missing story files for sprint stories
- Incomplete sections in story files
- Technical context not referencing architecture.md
- Vague acceptance criteria
