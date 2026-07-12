---
name: 'step-01-prepare-instruction'
description: 'Prepare a complete, verified instruction before activating any agent'
nextStepFile: './step-02-spawn-agent.md'
instructionTemplate: '{skills_path}/aim-agent-dispatch/templates/agent-instruction.template.md'
---

# Step 1: Prepare the Instruction

**Progress: Step 1 of 9** — Next: Spawn Agent

## STEP GOAL:

Before creating any team or spawning any agent, Parzival prepares a complete, verified instruction. No agent is activated until the instruction is ready and verified against project files.

**Scope:**
- Available context: Current task/story, project files (PRD.md, architecture.md, project-context.md, story files), scope definition
- Focus: Instruction preparation only — do not activate agents or create teams
- Limits: Do not activate any agent at this stage. This step is instruction preparation only.
- Dependencies: Current task/story definition and relevant project files must be available

**Behavioral Constraints:**
- FORBIDDEN to activate or spawn any agent before instruction passes all checklist items
- FORBIDDEN to pre-read or load the dispatched agent's skill or workflow files — those are the agent's tools, not Parzival's to summarize or replicate
- For BMAD/skill-driven agents: use the lightweight instruction form (section 2b) — provide target + context only; do NOT populate REQUIREMENTS, STANDARDS, or step-by-step guidance from the agent's skill domain
- Approach: Systematic verification against project files before writing instruction
- Every requirement in the instruction must cite a specific project file and section

## Sequence

### 1. Complete the Instruction Checklist

Before constructing the instruction, verify:
- **Agent type (do first):** Is this a BMAD skill-driven agent? → YES: use lightweight form in section 2b. NO (generic agent): use full template in section 2a.
- Have I identified the correct agent for this task? (see Agent Selection Guide in workflow.md)
- Have I read the relevant project files for this task?
- Is every requirement cited with a specific file and section?
- Is the scope clearly defined -- what is IN and what is OUT?
- Are the completion criteria specific and measurable?
- Is the instruction unambiguous -- could it be interpreted multiple ways?
- Have I verified this instruction does not contradict any project decisions?

IF ANY CHECK FAILS: fix the instruction before proceeding.

---

### 2a. Full Instruction Form (Generic Agents)

Using skills/aim-agent-dispatch/templates/agent-instruction.template.md, construct the instruction containing:
- **TASK:** Single, specific, unambiguous description. One task per instruction.
- **CONTEXT:** Relevant background -- only what is necessary. Do not dump entire project history.
- **REQUIREMENTS:** Cited project files and sections (PRD, architecture, standards, story criteria)
- **SCOPE:** Explicit IN SCOPE and OUT OF SCOPE lists
- **OUTPUT EXPECTED:** Exactly what the agent should produce (file names, formats, contents)
- **DONE WHEN:** Measurable, specific criteria the agent can self-assess
- **STANDARDS TO FOLLOW:** Specific coding standards, patterns, naming conventions
- **IF YOU ENCOUNTER A BLOCKER:** Stop and report immediately. Do not guess.

---

### 2b. Lightweight Instruction Form (BMAD / Skill-Driven Agents)

For BMAD skill-driven agents — the skill defines requirements, standards, and approach. Provide:
- **TASK:** Single, specific, unambiguous description. One task per instruction.
- **CONTEXT:** Only what the agent cannot get from project files. Be minimal.
- **TARGET:** What to produce (file names, formats, key outputs)
- **DONE WHEN:** Measurable criteria the agent can self-assess

Do NOT include REQUIREMENTS, SCOPE breakdowns, or STANDARDS — those are the skill's domain. Over-instruction undermines the skill's guidance and wastes tokens. Step-04 sends this as a recommendation request, not a full work order.

---

### 3. Verify Instruction Quality

Read the complete instruction through. Verify it is:
- **Complete** — form-appropriate section coverage:
  - For §2a (full form, generic agents): all 8 sections present — TASK, CONTEXT, REQUIREMENTS, SCOPE, OUTPUT EXPECTED, DONE WHEN, STANDARDS TO FOLLOW, BLOCKER PROTOCOL.
  - For §2b (lightweight form, BMAD / skill-driven agents): all 4 sections present — TASK, CONTEXT, TARGET, DONE WHEN — and NO REQUIREMENTS / SCOPE / STANDARDS sections (those belong to the skill).
- **Unambiguous** — could not be interpreted multiple ways.
- **Scoped** — §2a has explicit IN SCOPE / OUT OF SCOPE lists; §2b conveys scope via TARGET precision.
- **Cited** — every requirement references a project file.
- **Measurable** — DONE WHEN criteria are objectively verifiable.

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the instruction passes all checklist items and quality verification, load and read fully {nextStepFile}
