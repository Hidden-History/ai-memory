---
id: GC-20
name: No Instruction in Activation Message — Activation and Instruction Are Separate
severity: HIGH
category: Identity
phase: global
---

# GC-20: NEVER Include the Task Instruction in the BMAD Agent Activation Message

## Rule

When activating a BMAD agent, the activation command and the task instruction MUST be sent
as separate messages. The activation message contains ONLY the BMAD activation command
(e.g., `/bmad-agent-bmm-dev`). The instruction is sent ONLY after the agent has responded
with its menu/greeting confirming it has fully loaded its persona.

## Required Sequence

```
Step 1 — Spawn:     Agent tool with team_name (GC-19)
Step 2 — Activate:  Send activation command ONLY (e.g., /bmad-agent-bmm-dev)
Step 3 — Wait:      Wait for agent menu/greeting — do NOT send anything yet
Step 4 — Instruct:  Send task instruction as a separate message
```

## Forbidden Pattern

- Combining activation command and task instruction in a single message
- Sending any task content before the agent has displayed its greeting/menu
- Assuming the agent is ready without waiting for its confirmation response

## Why This Matters

BMAD agents must load their full persona, skills, and workflow context during the activation
step. Sending instructions before this loading completes causes the agent to operate with
incomplete configuration. The greeting/menu response is the agent's signal that it is ready
to receive instructions. This applies equally to execution mode (one-shot instruction) and
planning mode (relay protocol — where the workflow selection is also sent separately).

## Applies To

- Every BMAD agent activation
- Both execution mode and planning mode dispatches
- Re-activations after agent shutdown and respawn

## Self-Check

- GC-20: Am I about to send an activation command that also contains task instructions?
  If yes — split into two messages: activate first, wait for menu, then instruct.

## Violation Response

1. Do not send the combined message
2. Send the activation command alone
3. Wait for the agent's menu/greeting response
4. Send the instruction as a follow-up message
