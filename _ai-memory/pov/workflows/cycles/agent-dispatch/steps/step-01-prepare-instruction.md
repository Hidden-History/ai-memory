---
name: 'step-01-prepare-instruction'
description: 'Prepare a complete, verified instruction before activating any agent'
nextStepFile: './step-02-create-team.md'
instructionTemplate: '../templates/agent-instruction.md'
---

# Step 1: Prepare the Instruction

## STEP GOAL
Before creating any team or spawning any agent, Parzival prepares a complete, verified instruction. No agent is activated until the instruction is ready and verified against project files.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Current task/story, project files (PRD.md, architecture.md, project-context.md, story files), scope definition
- Limits: Do not activate any agent at this stage. This step is instruction preparation only.

## MANDATORY SEQUENCE

### 1. Complete the Instruction Checklist
Before constructing the instruction, verify:
- Have I identified the correct agent for this task? (see Agent Selection Guide in workflow.md)
- Have I read the relevant project files for this task?
- Is every requirement cited with a specific file and section?
- Is the scope clearly defined -- what is IN and what is OUT?
- Are the completion criteria specific and measurable?
- Is the instruction unambiguous -- could it be interpreted multiple ways?
- Have I verified this instruction does not contradict any project decisions?

IF ANY CHECK FAILS: fix the instruction before proceeding.

### 2. Build the Instruction
Using {instructionTemplate}, construct the instruction containing:
- **TASK:** Single, specific, unambiguous description. One task per instruction.
- **CONTEXT:** Relevant background -- only what is necessary. Do not dump entire project history.
- **REQUIREMENTS:** Cited project files and sections (PRD, architecture, standards, story criteria)
- **SCOPE:** Explicit IN SCOPE and OUT OF SCOPE lists
- **OUTPUT EXPECTED:** Exactly what the agent should produce (file names, formats, contents)
- **DONE WHEN:** Measurable, specific criteria the agent can self-assess
- **STANDARDS TO FOLLOW:** Specific coding standards, patterns, naming conventions
- **IF YOU ENCOUNTER A BLOCKER:** Stop and report immediately. Do not guess.

### 3. Verify Instruction Quality
Read the complete instruction through. Verify it is:
- Complete (all template sections filled)
- Unambiguous (could not be interpreted multiple ways)
- Scoped (clear IN and OUT boundaries)
- Cited (every requirement references a project file)
- Measurable (DONE WHEN criteria are objectively verifiable)

## CRITICAL STEP COMPLETION NOTE
ONLY when the instruction passes all checklist items and quality verification, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Instruction checklist is fully completed
- Every requirement cites a specific project file and section
- Scope is explicitly defined (IN and OUT)
- DONE WHEN criteria are specific and measurable
- Instruction is unambiguous

### FAILURE:
- Proceeding to agent activation with incomplete instruction
- Missing project file citations
- Vague or missing scope definition
- Unmeasurable completion criteria
- Ambiguous task description
