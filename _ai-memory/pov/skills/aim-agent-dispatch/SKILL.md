---
name: aim-agent-dispatch
description: Generic agent instruction preparation and activation -- Layer 3a
---

# Agent Dispatch -- Generic Agent Activation (Layer 3a)

**Purpose**: Activate and instruct generic agents (no BMAD persona, no BMAD activation commands). For BMAD agents with personas and activation commands, use aim-bmad-dispatch instead.

---

## Embedded Constraints (Layer 3)

- **EC-02 (moved from Execution phase)**: MUST use the instruction template for every agent dispatch. Story files are planning artifacts -- implementation instructions translate requirements into precise, actionable specifications.
- **GC-11 L3**: ALWAYS use the instruction template for every agent dispatch. Every requirement must cite a project file. Every DONE WHEN criterion must be objectively measurable.

---

## When to Use This Skill

Use aim-agent-dispatch when:
- The agent does NOT need a BMAD persona (no /bmad-agent-bmm-* activation)
- The agent is a generic worker spawned for a specific task
- Examples: code-reviewer agent, verify-implementation agent, skill-creator agent

Use aim-bmad-dispatch instead when:
- The agent IS a BMAD agent (Analyst, PM, Architect, DEV, SM, UX Designer)
- The agent requires persona activation via /bmad-agent-bmm-* commands

---

## Dispatch Process

### 1. Determine if BMAD Activation Needed
- If the task requires a BMAD agent role (Analyst, PM, Architect, DEV, SM, UX Designer) -- route to aim-bmad-dispatch
- If the task uses a generic agent -- continue here

### 2. Prepare Instruction Using Template
Build the instruction using the instruction template (`templates/agent-instruction.template.md`):

- **TASK**: Single, specific, unambiguous description. One task per instruction.
- **CONTEXT**: Relevant background -- only what is necessary.
- **REQUIREMENTS**: Cited project files and sections (PRD, architecture, standards, story criteria)
- **SCOPE**: Explicit IN SCOPE and OUT OF SCOPE lists
- **OUTPUT EXPECTED**: Exactly what the agent should produce (file names, formats, contents)
- **DONE WHEN**: Measurable, specific criteria the agent can self-assess
- **STANDARDS TO FOLLOW**: Specific coding standards, patterns, naming conventions
- **IF YOU ENCOUNTER A BLOCKER**: Stop and report immediately. Do not guess.

### 3. Verify Instruction Quality
Before dispatching, verify the instruction is:
- Complete (all template sections filled)
- Unambiguous (could not be interpreted multiple ways)
- Scoped (clear IN and OUT boundaries)
- Cited (every requirement references a project file)
- Measurable (DONE WHEN criteria are objectively verifiable)

IF ANY CHECK FAILS: fix the instruction before proceeding.

### 4. Select Model
Consult aim-model-dispatch for the appropriate model based on task complexity and agent role.

### 5. Spawn Agent as Teammate
Spawn the agent as a teammate in parallel using the Agent tool with `team_name`:
- Use `team_name` parameter to add agent to the team
- Set `AI_MEMORY_AGENT_ID` environment variable
- Use the model from Step 4
- Spawn multiple teammates in the same turn for parallel execution
- Start with fresh context (no contamination from prior tasks)

**Non-Claude provider**: When the user specifies a non-Claude provider, delegate the terminal launch to the model-dispatch skill.

### 6. Hand Off to aim-agent-lifecycle
After the agent is spawned and confirmed ready, proceed with aim-agent-lifecycle for steps 4-9 (send instruction, monitor, review, accept/loop, shutdown, summary).

---

## Instruction Template Reference

> **Convention**: All POV skill templates use the `.template.md` extension to distinguish them from step files and other markdown documents.

The full instruction template is at: `templates/agent-instruction.template.md`
