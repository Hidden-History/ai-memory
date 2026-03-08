---
name: agent-dispatch
description: 'Agent dispatch and lifecycle management via Claude Code teams. Defines how Parzival activates, instructs, monitors, and closes BMAD agents.'
firstStep: './steps/step-01-prepare-instruction.md'
---

# Agent Dispatch

**Goal:** Define exactly how Parzival activates, instructs, monitors, and closes BMAD agents via Claude Code teams -- the operational backbone of every agent interaction.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files

### Agent Selection Guide
When multiple agents could handle a task:

| Task Type | Correct Agent | Wrong Agent |
|---|---|---|
| Research current codebase state | Analyst | Architect |
| Create or update PRD | PM | Analyst |
| Break down features into stories | PM | SM |
| Design system architecture | Architect | PM |
| Check if implementation is ready | Architect | DEV |
| Plan and initialize a sprint | SM | PM |
| Create individual story files | SM | PM |
| Write code / implement a story | DEV | Any other |
| Review implemented code | DEV | Architect |
| Design user flows and screens | UX Designer | PM |

### Agent Combination Sequences
Some phases require agents in sequence:

- **Discovery phase:** Analyst (research) -> PM (PRD creation)
- **Architecture phase:** Architect (design) -> PM (epics/stories) -> Architect (readiness check)
- **Execution cycle:** DEV (implement) -> DEV (code review) -> [loop if issues] -> DEV (re-review)
- **Integration phase:** DEV (full review) -> Architect (cohesion check)
- **Release phase:** SM (retrospective) -> PM or Analyst (documentation update)

### Common Dispatch Errors

| Error | Prevention |
|---|---|
| Sending vague instruction | Always complete the full instruction template before dispatching |
| Combining multiple tasks in one instruction | One task per instruction -- always |
| Activating wrong agent | Use the Agent Selection Guide above |
| Accepting partial output | Review all DONE WHEN criteria before accepting |
| Passing raw agent output to user | Always prepare summary -- never copy-paste agent output |
| Running agents without project file verification | Complete instruction checklist before every dispatch |
| Starting new task before prior one is fully accepted | One active task per agent at a time |

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
