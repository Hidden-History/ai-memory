---
name: aim-agent-dispatch
description: Generic agent instruction preparation and activation
---

# Agent Dispatch -- Generic Agent Activation

> **INVOCATION RULE**: Parzival MUST invoke this skill via the Skill tool. NEVER read this file and execute steps manually -- that bypasses validation, schema enforcement, and pipeline routing. Reading is for audit and authoring; invocation is the only sanctioned execution path.

**Purpose**: Prepare instructions for generic agents (no BMAD persona). For BMAD agents, use /aim-bmad-dispatch instead.

---

## Embedded Constraints (Layer 3)

- **EC-02 (moved from Execution phase)**: MUST use the instruction template for every agent dispatch. Story files are planning artifacts -- implementation instructions translate requirements into precise, actionable specifications.
- **GC-11 L3**: ALWAYS use the instruction template for every agent dispatch. Every requirement must cite a project file. Every DONE WHEN criterion must be objectively measurable.

---

## Dispatch Plan Input (v1)

This skill is invoked by `aim-parzival-team-builder` with a structured
Dispatch Plan object. See the `Dispatch Plan Schema` section in
`aim-parzival-team-builder/SKILL.md` for the authoritative definition.

**First action on invocation**: Re-emit the received plan verbatim — no
paraphrase, no field renames, no model-ID shortening. If any key is missing
or malformed, STOP and request a corrected plan from the caller.

**Before routing (Step 4)**: Copy the plan into the downstream invocation.
Fields used by this skill:
- `provider` — routes to Claude path vs. non-Claude path
- `agent` + `agent_id` — sets `AI_MEMORY_AGENT_ID`
- `model` — passed through verbatim
- `task_summary` + `files` + `complexity` — feed the instruction template
- `workspace_root` — verified downstream by the CWD sentinel
- `reviewer_plan` — informs whether a follow-up dispatch will be required

**Never re-derive fields.** Exact model ID and file list propagate unchanged.

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

Check `provider` field from the Dispatch Plan:

**Claude provider (`provider: claude`):**
→ /aim-model-dispatch (MANDATORY next step)
Pass the full Dispatch Plan object plus the assembled instruction.

**Non-Claude provider:**
→ /aim-agent-lifecycle (MANDATORY next step)
Pass the full Dispatch Plan object plus the assembled instruction. Lifecycle
then invokes model-dispatch at its Step 1.

MUST spawn fresh agent for every task — never reuse across roles or stories.
MUST pass the Dispatch Plan verbatim — do NOT paraphrase model IDs or collapse
file lists.

### 5. Dispatch Complete

Agent instruction prepared and routed. Downstream skill handles spawn and activation.

---

## Instruction Template Reference

> **Convention**: All POV skill templates use the `.template.md` extension to distinguish them from step files and other markdown documents.

The full instruction template is at: `templates/agent-instruction.template.md`
