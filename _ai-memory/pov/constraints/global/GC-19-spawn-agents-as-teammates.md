---
id: GC-19
name: Spawn Agents as Teammates — Never as Standalone Subagents
severity: HIGH
category: Identity
phase: global
---

# GC-19: ALWAYS Spawn BMAD Agents as Teammates Using the Agent Tool With team_name

## Rule

When dispatching any BMAD agent, Parzival MUST spawn the agent as a teammate using the Agent
tool with the `team_name` parameter. Standalone subagent dispatches (Agent tool without
`team_name`) are FORBIDDEN for BMAD agent work.

## Required Pattern

```
Agent tool:
  team_name: [descriptive name for the team/task]
  model: [appropriate model for the role]
  [activation and instruction as separate messages — see GC-20]
```

## Forbidden Pattern

- Agent tool called WITHOUT `team_name` (standalone subagent)
- Direct invocation that bypasses the teammate lifecycle
- Any dispatch that does not allow SendMessage for follow-up communication

## Why This Matters

Standalone subagent dispatches lack the Edit and Write tool permissions required for
implementation work. Without `team_name`, Parzival cannot send follow-up instructions,
relay user confirmations, or manage the agent lifecycle (monitor → review → shutdown).
The teammate pattern is required for the full BMAD dispatch protocol to function correctly.

Reference: MEMORY.md — "Use Teammates Not Subagents" (PM #185 lesson).

## Applies To

- Every BMAD agent activation: bmad-bmm-dev, bmad-bmm-pm, bmad-bmm-architect, bmad-bmm-sm,
  bmad-bmm-analyst, bmad-bmm-ux, bmad-bmm-quick-dev, and any future BMAD agents
- All dispatch modes: execution (one-shot) and planning (relay protocol)

## Self-Check

- GC-19: Am I about to spawn a BMAD agent WITHOUT a team_name? If yes — stop and add team_name.

## Violation Response

1. Do not complete the subagent dispatch
2. Restart the agent activation using Agent tool with team_name
3. Note: any output from a standalone dispatch must be discarded — permissions were insufficient
