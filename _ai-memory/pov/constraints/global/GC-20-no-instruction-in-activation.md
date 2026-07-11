---
id: GC-20
name: No Task Instruction in Activation Message — Activation and Task Instruction Are Separate
severity: HIGH
category: Identity
phase: global
---

# GC-20: NEVER Include a Task Instruction in the BMAD Agent Activation Message

## Rule

When activating a BMAD agent, the activation message MUST NOT contain the task instruction.
It may contain the BMAD activation command (e.g., `/bmad-agent-dev`) plus a reporting-routing
directive — telling the teammate where to send its activation reply — but never the task
itself. The task instruction is sent ONLY after the agent has responded with its menu/greeting
confirming it has fully loaded its persona.

**Bright line for the reporting-routing directive:** it may state ONLY (a) where to send the
activation reply, and (b) to wait for instructions after that. It MUST NOT contain any task,
work item, target, file, or "start on X" content — e.g. "...then start on bug #317 once ready"
is a task instruction, not routing metadata, and is forbidden in the activation message.

## Required Sequence

```
Step 1 — Spawn:     Agent tool with team_name (GC-19)
Step 2 — Activate:  Send activation command + reporting-routing directive
                     (e.g., /bmad-agent-dev + "report your activation reply to <handle>")
                     — never the task
Step 3 — Wait:      Wait for agent menu/greeting — do NOT send task content yet
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

A reporting-routing directive is orchestration metadata (where to reply), not task content —
it does not corrupt persona loading the way a bundled task instruction does.

## Applies To

- Every BMAD agent activation
- Both execution mode and planning mode dispatches
- Re-activations after agent shutdown and respawn

## Scope: Interactive vs. Programmatic Activation

This rule governs **interactive/tmux two-phase activation**, where a pane cannot self-sequence its
own turns -- the activation command and the task instruction MUST be sent as two separate messages
because nothing in the pane enforces order between them.

A **programmatic Agent-tool spawn** whose prompt reads "load the skill/persona, THEN read your
brief/task" satisfies this rule's intent without a second message: the agent runs both steps inside
its own single turn, self-sequencing persona-load before task-processing, so there is no window
where an unloaded persona receives task content. This does not loosen the rule for interactive
activation -- the no-task-in-the-activation-message floor still applies there without exception.

## Self-Check

- GC-20: Am I about to send an activation message that contains task instructions (beyond
  the activation command and an optional reporting-routing directive)? If yes — split into
  two messages: activate (+ routing directive if needed) first, wait for menu, then instruct.
  **Testable form:** does the message contain anything beyond the activation command + a
  where-to-reply/wait directive? If yes, it's a task instruction — split it.

## Violation Response

1. Do not send the combined message
2. Send the activation command (with routing directive if applicable) alone
3. Wait for the agent's menu/greeting response
4. Send the instruction as a follow-up message

## Operational Home

Operationalized as the activation-gate checklist in:
- `_ai-memory/pov/skills/aim-agent-dispatch/SKILL.md` (B4. Verify Activation)
- `_ai-memory/pov/skills/aim-agent-lifecycle/SKILL.md` (Step 1, Activation gate)
