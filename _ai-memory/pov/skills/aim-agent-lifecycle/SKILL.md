---
name: aim-agent-lifecycle
description: tmux agent lifecycle management for non-Claude providers
allowed-tools: Bash
---

# Agent Lifecycle -- Non-Claude Provider Agent Management

**Purpose**: Manage tmux-spawned agents for non-Claude providers. Invokes /aim-model-dispatch for tmux spawn, sends instructions via tmux send-keys, monitors via tmux capture-pane, and shuts down via tmux kill-pane. Called by /aim-agent-dispatch when provider is not Claude.

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

**Pre-spawn sentinel gate (MANDATORY -- re-run before EVERY spawn):** assert the current directory is the workspace root by confirming co-presence of `_ai-memory/`, `_bmad/`, and `oversight/` (CLAUDE.md workspace-root sentinel) -- `test -d _ai-memory && test -d _bmad && test -d oversight`. On FAIL, **ABORT the spawn** ("CWD drift -- not at workspace root; return to root before spawning") and do NOT invoke /aim-model-dispatch. CWD drifts across Bash calls, so re-run before each spawn, not once per session.

**Agent Teams prerequisite gate (MANDATORY before the first parallel-team spawn):** run the shared **fire-only-if-missing** preflight -- `bash _ai-memory/pov/skills/aim-model-dispatch/scripts/lib/preflight_agent_teams.sh`. Silent + exit 0 -> prerequisites satisfied, proceed. Any stderr + exit 1 -> `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is missing or `teammateMode` is a non-team mode; **ABORT the spawn**, relay the script's exact remediation to the user, and re-run once fixed. Same guard runs in the `/aim-model-dispatch` claude-native workflow, so both dispatch paths enforce the identical prerequisites.

Invoke /aim-model-dispatch with the dispatch plan. Model-dispatch routes to the correct tmux workflow for the provider and spawns the agent.

For BMAD agents, the tmux bmad-dispatch workflow handles two-phase activation (persona command → menu detection → task instruction).

For generic agents, the tmux-dispatch workflow sends the instruction directly.

**Activation gate (MANDATORY — two-phase, GC-20):** launch the agent in a fresh pane with
`--allowedTools`, then activate with `tmux send-keys` — the live `/bmad-<role>` command into the pane
(bare slash is correct here: the pane is a fresh interactive session, so the command activates the
persona directly). Wait for the greeting/menu via `tmux capture-pane`; idle output is NOISE (no nudges).
Then send the task with a SEPARATE `tmux send-keys` — never bundled with activation. /aim-model-dispatch
(bmad-dispatch) performs these steps; do not hand-roll them. Idle-is-noise, one-message-then-wait,
cold-verify acceptance, and state-based stall/respawn are the shared Dispatch & Coordination Playbook in
`/aim-agent-dispatch` — follow it; the tmux difference is that activation, task delivery, and inspection
all use `tmux send-keys` / `tmux capture-pane` (no `mode`, no Skill-tool-load, no SendMessage).

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
