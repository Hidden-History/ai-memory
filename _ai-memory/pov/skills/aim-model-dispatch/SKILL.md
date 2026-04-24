---
name: aim-model-dispatch
description: Select the appropriate LLM model for each agent based on task complexity and role
---

# Model Dispatch -- Model Selection and Provider Routing

**Purpose**: Select the appropriate LLM model and route to the correct provider workflow. Called by /aim-agent-dispatch and /aim-agent-lifecycle.

---

## Model Selection

### By Complexity

| Complexity | Model |
|------------|-------|
| Straightforward / Moderate | Sonnet |
| Significant / Complex / Architectural | Opus |

### Role-Based Defaults

| Agent Role | Default | Override When |
|------------|---------|---------------|
| DEV (implementation) | Sonnet | Opus if architectural changes or complex refactoring |
| DEV (code review) | Sonnet | Opus if reviewing architectural decisions |
| Analyst | Sonnet | Opus if deep architectural analysis |
| PM | Sonnet | Opus if complex domain modeling |
| Architect | Opus | Already at highest tier |
| SM, UX Designer | Sonnet | Standard for all work |
| Generic agent | Sonnet | Opus if task requires deep reasoning |

### Override Rules

1. **User override**: User preference always wins.
2. **Failed fix escalation**: After loop count > 1, consider upgrading to Opus.
3. **Haiku**: Only for simple, high-volume parallel tasks (file scanning, grep-and-report). Never for implementation, review, or planning.
4. **Cost awareness**: Use Opus when reasoning depth justifies the cost, not as default.
5. **Non-Claude providers**: Reasoning tier (Opus/Sonnet/Haiku) maps to equivalent model on the selected provider.

---

## Provider Routing

### Path 1: Claude Native

**MANDATORY** for opus, sonnet, haiku -- use the Claude Code native parallel system.

→ [`workflows/claude-native/workflow.md`]({project-root}/_ai-memory/pov/model-dispatch-framework/workflows/claude-native/workflow.md)

### Path 2: Non-Claude Providers

| Provider | Workflow |
|----------|----------|
| openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow | [`tmux-dispatch`]({project-root}/_ai-memory/pov/model-dispatch-framework/workflows/tmux-dispatch/workflow.md) or [`bmad-dispatch`]({project-root}/_ai-memory/pov/model-dispatch-framework/workflows/bmad-dispatch/workflow.md) |
| api (image/audio/video) | [`api-dispatch`]({project-root}/_ai-memory/pov/model-dispatch-framework/workflows/api-dispatch/workflow.md) |

---

## Framework

All sub-workflows, references, scripts, wrappers, and evals are in:
`{project-root}/_ai-memory/pov/model-dispatch-framework/`
