---
id: GC-19
name: Spawn ALL Agents via tmux with AI_MEMORY_AGENT_ID
severity: HIGH
category: Identity
phase: global
---

# GC-19: ALWAYS Spawn ALL Agents via tmux with AI_MEMORY_AGENT_ID

## Rule

When dispatching any agent (BMAD or generic), Parzival MUST spawn the agent via
aim-model-dispatch tmux workflow with a unique AI_MEMORY_AGENT_ID set as an environment
variable. AI_MEMORY_AGENT_ID is mandatory for cross-session memory tracking.

## Required Pattern

```
tmux spawn via aim-model-dispatch:
  AI_MEMORY_AGENT_ID: [unique agent identity — e.g., dev-2.5, review-s-2.5, sm-sprint1]
  Backend: [claude/openrouter/ollama/etc. — determined by model-dispatch]
  Wrapper: [claude-dispatch or provider-dispatch — determined by model-dispatch]
  [BMAD agents: two-phase activation — persona command → wait for menu → workflow command]
```

## Forbidden Pattern

- Spawning any agent without AI_MEMORY_AGENT_ID set
- Spawning outside tmux (bypassing aim-model-dispatch)
- Skipping aim-agent-lifecycle after spawn (lifecycle is [ALWAYS-MANDATORY-4])

## Why This Matters

AI_MEMORY_AGENT_ID enables cross-session memory accumulation — the same agent identity
working on the same domain across sessions builds domain-specific expertise in Qdrant.
tmux enables full Claude Code CLI sessions where BMAD skills work correctly. The lifecycle
requires a known agent identity for tracking, review, and shutdown.

## Applies To

- Every agent activation: BMAD agents (dev, pm, architect, sm, analyst, ux, qa, tech-writer,
  quick-flow-solo-dev) AND generic agents (code-reviewer, verify-implementation, etc.)
- All dispatch modes: execution (one-shot) and planning (relay protocol)

## Self-Check

- GC-19: Am I about to spawn an agent WITHOUT AI_MEMORY_AGENT_ID or outside tmux? If yes — stop and fix.

## Violation Response

1. Do not complete the dispatch
2. Restart the agent activation via aim-model-dispatch tmux with AI_MEMORY_AGENT_ID set
3. Note: any output from an untracked dispatch must be re-verified — memory was not accumulated
