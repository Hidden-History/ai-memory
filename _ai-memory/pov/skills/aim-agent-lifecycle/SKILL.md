---
name: aim-agent-lifecycle
description: tmux agent lifecycle management for non-Claude providers
---

# Agent Lifecycle -- Non-Claude Provider Agent Management

**Purpose**: Manage tmux-spawned agents for non-Claude providers. Invokes /aim-model-dispatch for tmux spawn, sends instructions via tmux send-keys, monitors via tmux capture-pane, and shuts down via tmux kill-pane. Called by /aim-bmad-dispatch and /aim-agent-dispatch when provider is not Claude.

---

## ENFORCEMENT

This skill is MANDATORY for all non-Claude provider dispatches.
Claude-native agents use the claude-native workflow in /aim-model-dispatch instead.

tmux communication:
- Send instruction: `tmux send-keys`
- Monitor: `tmux capture-pane`
- Shutdown: `tmux send-keys` DA + `tmux kill-pane`

---

## Constraints

Parzival's global constraints (GC-09, GC-10, GC-12) govern review, summaries, and correction loops.
Max 3 correction loops -- escalate to user if unresolved.

---

## Step 1: Spawn Agent

Invoke /aim-model-dispatch with the dispatch plan. Model-dispatch routes to the correct tmux workflow for the provider and spawns the agent.

For BMAD agents, the tmux bmad-dispatch workflow handles two-phase activation (persona command → menu detection → task instruction).

For generic agents, the tmux-dispatch workflow sends the instruction directly.

**Handle clarification requests:**
- Agent asks BEFORE starting: provide clarification with citation. Never guess.
- Agent asks DURING work (blocker): resolve from project files if possible, escalate to user if not.

---

## Step 2: Monitor

Monitor via `tmux capture-pane` periodically.

Intervene if agent works outside scope, makes assumptions, or appears stuck.
Do not interrupt if progressing normally.

---

## Step 3: Accept or Loop

Parzival reviews output per GC-09 and GC-12 constraints.

**Correction loop:** Shutdown current agent (Step 4), spawn FRESH agent via /aim-model-dispatch, send correction instruction. Loop until zero issues or 3 loops reached.

See [templates/agent-correction.template.md](templates/agent-correction.template.md) for correction format.

---

## Step 4: Shutdown

Send `DA` via `tmux send-keys`, wait 3s, then `tmux kill-pane`.

MUST shutdown and spawn fresh for: new tasks, role changes, fix dispatches, re-review passes.
Never reuse an agent across tasks or roles.

Verify no pending work remains. Confirm no orphaned tmux panes.
