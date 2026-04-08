---
name: aim-agent-dispatch
description: Generic agent instruction preparation and activation
---

# Agent Dispatch -- Generic Agent Activation

**Purpose**: Prepare instructions for generic agents (no BMAD persona). For BMAD agents, use /aim-bmad-dispatch instead.

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

### 4. Route Based on Provider

Check provider from the dispatch plan:

**Claude provider:**
→ /aim-model-dispatch (MANDATORY next step)
Pass: instruction, AI_MEMORY_AGENT_ID, model from dispatch plan.

**Non-Claude provider:**
→ /aim-agent-lifecycle (MANDATORY next step)
Pass: instruction, AI_MEMORY_AGENT_ID, provider, model from dispatch plan.

MUST spawn fresh agent for every task — never reuse across roles or stories.

### 5. Dispatch Complete

Agent instruction prepared and routed. Downstream skill handles spawn and activation.

---

## Instruction Template Reference

> **Convention**: All POV skill templates use the `.template.md` extension to distinguish them from step files and other markdown documents.

The full instruction template is at: `templates/agent-instruction.template.md`
