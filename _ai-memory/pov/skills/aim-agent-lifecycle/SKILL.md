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

**Activation gate (MANDATORY before first instruction):**

**Two-phase activation (GC-20):** send the activation command (e.g. `/bmad-agent-dev`), optionally plus a reporting-routing directive -- stating only where to send the activation reply and to wait for instructions, nothing else -- never the task instruction -- as its own message. Wait for the persona greeting/menu. Send the task instruction as a SEPARATE, follow-up message -- never bundled with activation. Bundling a task instruction into the activation message is a failed process: re-activate cleanly (fresh activation command, wait again), don't patch around it. See GC-20 (`_ai-memory/pov/constraints/global/GC-20-no-instruction-in-activation.md`) for the full rule and rationale.

**Readiness-ack:** before sending any task content, require the teammate to confirm role + CWD + "READY FOR INSTRUCTION" (the BMAD persona greeting + numbered menu satisfies this for BMAD agents).

**Never nudge:** never send a repeat of the activation command. An idle ping or notification means the teammate is working -- wait, don't react. If there is no activation output at all, verify by `tmux capture-pane` -- never by nudging. Only if that confirms a genuine stall -- defined by state, not time, and covering two forms: (a) no activation output AND no sign of in-progress loading/work (no partial persona text, no pane activity since spawn), or (b) activation output appeared but has stopped progressing -- shows a crash-or-error signature (e.g. a render-crash pane) with no persona greeting/menu having appeared, and no further pane activity since. A slow persona load is NOT a stall. When uncertain, inspect again before respawning. Only then spawn a FRESH agent. This governs the activation / idle-notification phase only; a mid-task, diagnosed-stuck status request is a distinct case, not covered by this rule.

**Idle vs. stall:** distinguish a normal between-turn idle (teammate finished its turn, awaiting the next message) from a real stall by checking work-state (git status / files written since spawn). Distinguish a system task-auto-replay (harness re-delivering a prior message) from genuine new direction before re-acting on it.

Do NOT send the task instruction until `tmux capture-pane` shows the teammate's activation output -- BMAD persona greeting plus numbered menu, or an explicit "ready" ack -- not idle, not mid-load. Then send the task as a SEPARATE message (one task per instruction) including an explicit "do not idle until X" plus a concrete numbered step list. If `tmux capture-pane` confirms no genuine activation output (a real stall, not a normal idle/notification), shut down (Step 4) and spawn FRESH. Never instruct an unverified agent.

See `/aim-agent-dispatch`'s Dispatch & Coordination Playbook for the reporting-address convention, spawn-prompt wording, and one-message-then-wait coordination cadence that apply once activation completes.

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
