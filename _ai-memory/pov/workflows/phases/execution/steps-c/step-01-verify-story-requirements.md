---
name: 'step-01-verify-story-requirements'
description: 'Read and verify the current story against architecture, standards, and PRD before any agent is activated'
nextStepFile: './step-02-prepare-instruction.md'
---

# Step 1: Read and Verify Story Requirements

**Progress: Step 1 of 7** — Next: Prepare DEV Implementation Instruction

## STEP GOAL:

Before any agent is activated, Parzival reads and verifies the story thoroughly against current project state. Ensure story references are current and no ambiguities exist.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Current story file, architecture.md, project-context.md, PRD.md
- Focus: Verification only — do not activate agents or begin implementation
- Limits: Only verify. Do not activate agents. Do not begin implementation.
- Dependencies: None — this is the first step of the execution workflow

- Focus only on verification — do not activate agents or begin implementation
**Behavioral Constraints:**
- FORBIDDEN to dispatch any agent before verification completes
- Approach: Systematic verification against all four source files
- If story requires update, route to SM before proceeding

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Read Complete Story File

Read all seven sections:
- User story -- is the goal clear and specific?
- Acceptance criteria -- are all criteria testable?
- Technical context -- references current architecture.md?
- Technical context -- references current project-context.md?
- Dependencies -- all confirmed complete?
- Out of scope -- explicit?
- Story size -- appropriate for one implementation session?

---

### 2. Verify Against architecture.md

- Do referenced patterns still reflect current architecture?
- Have any architecture decisions changed since story was written?
- Are referenced files/modules still named correctly?

---

### 3. Verify Against project-context.md

- Do referenced standards still reflect current project-context?
- Have any standards been updated since story was written?

---

### 4. Verify Against PRD.md

- Do acceptance criteria match PRD requirements?
- Has the PRD been updated since story was written?

---

### 5. Handle Story Updates Needed

If story requires update before execution:
- Identify specific updates needed
- Return to SM via {workflows_path}/cycles/agent-dispatch/workflow.md with correction instruction
- SM updates story file
- Parzival re-reviews
- Then proceed to Step 2

---

### 6. Resolve Pre-Execution Questions

- Is there anything DEV would need to guess?
- Is there any ambiguity in acceptance criteria?
- Are there edge cases not covered?
- Are there security considerations not addressed?

If YES to any: resolve using project files or ask user.
If NO: proceed to instruction preparation.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN story verification passes with no issues, will you then read fully and follow: `{nextStepFile}` to begin instruction preparation.
