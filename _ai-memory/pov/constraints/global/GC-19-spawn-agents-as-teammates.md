---
id: GC-19
name: ALWAYS Spawn Agents via Approved Dispatch Path (tmux or Claude-native)
severity: HIGH
category: Identity
phase: global
---

# GC-19: ALWAYS Spawn Agents via Approved Dispatch Path (tmux or Claude-native)

## Rule

When dispatching any agent (BMAD or generic), Parzival MUST use one of the two approved
dispatch paths. AI_MEMORY_AGENT_ID is mandatory on all paths for cross-session memory tracking.

## Approved Paths

### Claude provider path (Claude Code Agent Teams)

Spawn via the Agent tool with a unique agent `name` field serving as AI_MEMORY_AGENT_ID; the team
forms automatically and this session is the lead.
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 must be enabled in settings.

```
Agent: subagent_type=[agent-type], name=[ai-memory-agent-id]
  [BMAD agents: the spawn prompt loads the persona via the Skill tool — `Use the Skill tool to load bmad-{name}`, never a bare `/bmad-*`; two-phase activation]
```

### Non-Claude provider path (tmux)

Spawn via aim-model-dispatch tmux workflow with AI_MEMORY_AGENT_ID as an environment variable.
Applies to openrouter, ollama, gemini, deepseek, and any non-Claude backend.

```
tmux spawn via aim-model-dispatch:
  AI_MEMORY_AGENT_ID: [unique agent identity — e.g., dev-2.5, review-s-2.5, sm-sprint1]
  Backend: [openrouter/ollama/gemini/etc. — determined by model-dispatch]
  Wrapper: [provider-dispatch — determined by model-dispatch]
  [BMAD agents: two-phase activation — persona command → wait for menu → workflow command]
```

Both paths are valid. The correct path is determined by aim-parzival-team-builder based on
the configured provider.

## Forbidden Pattern

- Spawning any agent without AI_MEMORY_AGENT_ID set
- Spawning without a unique agent name / AI_MEMORY_AGENT_ID (bypasses Claude-native tracking)
- Spawning outside tmux on non-Claude paths (bypassing aim-model-dispatch)
- Skipping aim-agent-lifecycle after spawn on non-Claude paths (lifecycle is [ALWAYS-MANDATORY-4])

## Why This Matters

AI_MEMORY_AGENT_ID enables cross-session memory accumulation — the same agent identity
working on the same domain across sessions builds domain-specific expertise in Qdrant.
Both paths ensure the lifecycle is managed and output is tracked for review.

## Applies To

- Every agent activation: BMAD agents (dev, pm, architect, sm, analyst, ux, qa, tech-writer,
  quick-flow-solo-dev) AND generic agents (code-reviewer, verify-implementation, etc.)
- All dispatch modes: execution (one-shot) and planning (relay protocol)

## Self-Check

- GC-19: Am I about to spawn an agent outside an approved dispatch path or without AI_MEMORY_AGENT_ID? If yes — stop and fix.

## Violation Response

1. Do not complete the dispatch
2. Identify the correct path based on provider (Claude → Agent Teams, non-Claude → tmux)
3. Restart the agent activation via the correct approved path with AI_MEMORY_AGENT_ID set
4. Any output from an unapproved dispatch must be re-verified — memory was not accumulated
