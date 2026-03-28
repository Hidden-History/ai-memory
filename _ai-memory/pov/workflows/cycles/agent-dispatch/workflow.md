---
name: agent-dispatch
description: 'Agent dispatch and lifecycle management. Defines how Parzival activates, instructs, monitors, and closes agents.'
firstStep: './steps-c/step-01-prepare-instruction.md'
---

# Agent Dispatch

**Goal:** Define exactly how Parzival activates, instructs, monitors, and closes agents -- the operational backbone of every agent interaction.

**Layered Execution:** This cycle is the core execution mechanism. It is invoked by phase workflows and session commands. For team design (multi-agent parallel work), use the aim-parzival-team-builder skill first, which produces context blocks that feed into this cycle.

**MANDATORY Orchestration Pipeline (GC-21) -- every dispatch MUST follow this sequence:**
1. **TeamCreate** → create team + shared task list (MUST)
2. **aim-parzival-team-builder** → design team structure or fast path for single agent (MUST)
3. **aim-bmad-dispatch** OR **aim-agent-dispatch** → select agent, prepare instruction (MUST)
4. **aim-model-dispatch** → select model (MUST)
5. **Agent tool spawn** → team_name + name + mode: "acceptEdits" from project root (MUST)
6. **aim-agent-lifecycle** → send, monitor, review, accept/loop, shutdown, summary (MUST)

Skipping any step is a GC-21 violation. These are not optional consultations.

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

### Common Dispatch Errors

| Error | Prevention |
|---|---|
| Sending vague instruction | Always complete the full instruction template before dispatching |
| Combining multiple tasks in one instruction | One task per instruction -- always |
| Activating wrong agent | Consult the aim-bmad-dispatch skill for agent role selection |
| Accepting partial output | Review all DONE WHEN criteria before accepting |
| Passing raw agent output to user | Always prepare summary -- never copy-paste agent output |
| Running agents without project file verification | Complete instruction checklist before every dispatch |
| Starting new task before prior one is fully accepted | One active task per agent at a time |

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
