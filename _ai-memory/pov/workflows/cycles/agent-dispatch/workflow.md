---
name: agent-dispatch
description: 'Agent dispatch and lifecycle management. Defines how Parzival activates, instructs, monitors, and closes agents.'
firstStep: './steps-c/step-01-prepare-instruction.md'
---

# Agent Dispatch

**Goal:** Define exactly how Parzival activates, instructs, monitors, and closes agents -- the operational backbone of every agent interaction.

**Layered Execution:** This cycle is the core execution mechanism. It is invoked by phase workflows and session commands. For team design (multi-agent parallel work), use the aim-parzival-team-builder skill first, which produces context blocks that feed into this cycle.

**MANDATORY Orchestration Pipeline (GC-21) -- follow the path that matches your provider:**

**Claude-native path:**
1. **aim-parzival-team-builder** → design team structure or fast path for single agent [MANDATORY]
2. **aim-agent-dispatch** → select agent, prepare instruction (handles both BMAD and generic) [MANDATORY]
3. **aim-model-dispatch** → select model + spawn via the `Agent` tool [MANDATORY]
4. Claude-native framework handles lifecycle — **aim-agent-lifecycle is NOT used on this path**

**Non-Claude (tmux) path:**
1. **aim-parzival-team-builder** → design team structure or fast path for single agent [MANDATORY]
2. **aim-agent-dispatch** → select agent, prepare instruction (handles both BMAD and generic) [MANDATORY]
3. **aim-agent-lifecycle** → MUST load before spawn — mandatory for tmux path only [MANDATORY]
4. **aim-model-dispatch** → select model + tmux spawn with AI_MEMORY_AGENT_ID [MANDATORY]

Skipping any step on the active path is a GC-21 CRITICAL violation. These are not optional consultations.
**aim-agent-lifecycle is tmux-only — do NOT load it for Claude-native dispatches.**

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Common Dispatch Errors

| Error | Prevention |
|---|---|
| Sending vague instruction | Always complete the full instruction template before dispatching |
| Combining multiple tasks in one instruction | One task per instruction -- always |
| Activating wrong agent | Consult the aim-agent-dispatch skill for agent role selection (BMAD routing within) |
| Accepting partial output | Review all DONE WHEN criteria before accepting |
| Passing raw agent output to user | Always prepare summary -- never copy-paste agent output |
| Running agents without project file verification | Complete instruction checklist before every dispatch |
| Starting new task before prior one is fully accepted | One active task per agent at a time |
| Pre-reading the dispatched agent's skill or workflow files | FORBIDDEN — provide target + minimal context; the agent's skill defines requirements and approach |
| Sending full instruction template to a BMAD skill-driven agent | Use lightweight form for skill-driven agents — detailed requirements and standards are the skill's job |
| Asking BMAD agent to "state your planned approach" | First SendMessage asks "what do you recommend and why?" — let the skill drive the approach, not Parzival's prescription |

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
