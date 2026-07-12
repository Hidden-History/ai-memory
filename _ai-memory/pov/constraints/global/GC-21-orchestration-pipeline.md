---
id: GC-21
name: ALWAYS Follow Mandatory Team Orchestration Pipeline
severity: CRITICAL
category: Identity
phase: global
---

# GC-21: ALWAYS Follow Mandatory Team Orchestration Pipeline

## Rule

Every agent dispatch — no exceptions, no inline shortcuts — MUST follow the full orchestration
pipeline. Parzival MUST invoke /aim-parzival-team-builder as the mandatory entry point.
Loading an inline summary instead of invoking the actual skill is a GC-21 violation.

## Mandatory Pipeline

**Mandatory entry: /aim-parzival-team-builder**
Collects provider, model, and agent type. Follow its output (preset, fast path, or full design).
Routes to /aim-agent-dispatch (handles both BMAD and generic agents -- BMAD routing is within the skill).

**Claude provider path:**
/aim-parzival-team-builder → /aim-agent-dispatch → /aim-model-dispatch → claude-native workflow

**Non-Claude provider path:**
/aim-parzival-team-builder → /aim-agent-dispatch → /aim-agent-lifecycle → /aim-model-dispatch → tmux workflow

**Fresh agent per task** — never reuse an agent across roles or stories. One story per SM (shutdown
after each). Review loop uses fresh reviewer agents.

**Note on aim-agent-lifecycle**: Lifecycle is MANDATORY for non-Claude (tmux) dispatches only. The Claude-native path (Agent tool) does not use aim-agent-lifecycle — lifecycle management is handled natively by the Claude Code agent framework.

## Why This Matters

The orchestration pipeline ensures correct model selection, memory tracking (AI_MEMORY_AGENT_ID),
quality gates, and lifecycle management. Bypassing it creates untracked agents that skip lifecycle
management and produce output without proper review gates.

## Applies To

Every agent activation — BMAD agents (dev, pm, architect, sm, analyst, ux, qa, tech-writer,
quick-flow-solo-dev) AND generic agents (code-reviewer, verify-implementation, etc.). All dispatch
modes: execution (one-shot) and planning (relay protocol).

## Self-Check

- GC-21: Have I dispatched any agent without following the full orchestration pipeline? If yes — stop, restart from the missed step.

## Violation Response

1. Stop dispatch immediately
2. Identify which step was skipped and which provider path applies (Claude-native or non-Claude/tmux)
3. **Claude-native path**: Restart from missed step — full pipeline: aim-parzival-team-builder → aim-agent-dispatch → aim-model-dispatch → claude-native workflow (Agent tool). No aim-agent-lifecycle required.
4. **Non-Claude (tmux) path**: Restart from missed step — full pipeline: aim-parzival-team-builder → aim-agent-dispatch → aim-agent-lifecycle (MUST load before spawn) → aim-model-dispatch (spawn called from lifecycle Step 4). Never spawn a tmux agent without lifecycle loaded.
5. Resume only after the missed step is properly executed
