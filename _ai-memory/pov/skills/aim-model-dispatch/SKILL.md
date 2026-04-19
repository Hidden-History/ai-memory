---
name: aim-model-dispatch
description: Select the appropriate LLM model for each agent based on task complexity and role
---

# Model Dispatch -- Model Selection and Provider Routing

> **INVOCATION RULE**: Parzival MUST invoke this skill via the Skill tool. NEVER read this file and execute steps manually -- that bypasses pre-spawn model validation, CWD sentinel checks, and wrapper resolution. Reading is for audit and authoring; invocation is the only sanctioned execution path.

**Purpose**: Select the appropriate LLM model and route to the correct provider workflow. Called by /aim-bmad-dispatch, /aim-agent-dispatch, and /aim-agent-lifecycle.

---

## Dispatch Plan Input (v1)

This skill receives a structured Dispatch Plan from the upstream dispatch
skill. Authoritative schema is defined in `aim-parzival-team-builder/SKILL.md`
under `Dispatch Plan Schema`.

**First action on invocation**: Re-emit the received plan verbatim. If a key
is missing or the `model` field is empty when the plan requires a concrete
model (non-Claude providers always require a concrete `model`), STOP and
return a plan-validation error to the caller.

### Pre-Spawn Validation Gates (run in order)

Gates 2 (model catalog check) and 3 (wrapper availability) apply to non-Claude provider paths only. Claude-native does not require catalog validation (the Anthropic API rejects invalid model names) or wrapper check (uses Agent tool directly via Claude Code).

1. **CWD Sentinel** — Verify workspace root by co-presence of `_ai-memory/`,
   `_bmad/`, and `oversight/`. See workflow files under `workflows/` for the
   bash implementation. `workspace_root` from the Dispatch Plan is the
   expected path.
2. **Model catalog check** — For `provider: ollama`, grep
   `references/models-ollama.md` for the exact `model` string. For `provider:
   openrouter`, grep `references/models-openrouter.md`. Fail-fast on miss with
   the catalog path in the error message.
3. **Wrapper availability** — Verify the backend wrapper exists on PATH.

Gates 1–3 run before tmux pane creation; Gate 1 also runs before Agent spawn for Claude-native. A failed gate aborts the dispatch without consuming a pane slot or teammate slot.

---

## Model Selection Criteria

### Default Mapping by Complexity

| Complexity | Model | Reasoning |
|------------|-------|-----------|
| Straightforward | Sonnet | Fast, cost-effective for clear tasks |
| Moderate | Sonnet | Good balance for most work |
| Significant | Opus | Deeper reasoning for complex coordination |
| Complex/architectural | Opus | Full reasoning depth required |

### Role-Based Defaults

| Agent Role | Default Model | Override When |
|------------|---------------|---------------|
| DEV (implementation) | Sonnet | Opus if architectural changes or complex refactoring |
| DEV (code review) | Sonnet | Opus if reviewing architectural decisions |
| Analyst (research) | Sonnet | Opus if deep architectural analysis |
| PM (PRD creation) | Sonnet | Opus if complex domain modeling |
| Architect (design) | Opus | Already at highest tier |
| SM (sprint planning) | Sonnet | Opus if complex dependency resolution |
| UX Designer | Sonnet | Standard for all UX work |
| Generic agent | Sonnet | Opus if task requires deep reasoning |

### Override Rules

1. **User override**: The user can override any model selection. User preference always wins.
2. **Failed fix escalation**: After a failed correction loop (loop count > 1), consider upgrading to Opus for deeper reasoning on the fix.
3. **Haiku**: Only for simple, high-volume parallel tasks (e.g., file scanning, simple grep-and-report). Never for implementation, review, or planning.
4. **Cost awareness**: Opus costs significantly more than Sonnet. Use it when the reasoning depth justifies the cost, not as a default.
5. **Non-Claude providers**: When the user specifies a provider (e.g., "use openrouter", "use ollama"), the model-dispatch skill handles provider selection, model ID resolution, and terminal launch. aim-model-dispatch still determines the reasoning tier (Opus/Sonnet/Haiku) which maps to the equivalent model on the selected provider.

---

## Two Provider Paths

### Path 1: Claude Native (MANDATORY for Claude models)

**MANDATORY**: When using opus, sonnet, or haiku, ALWAYS use the claude-native workflow.
**MANDATORY**: Use Claude Code native teammates in parallel system built into Claude Code.

→ [claude-native](workflows/claude-native/workflow.md)

### Path 2: Non-Claude Providers

**MANDATORY**: For all other providers, route to the appropriate tmux workflow:

| Provider | Workflow |
|----------|----------|
| openrouter | [tmux-dispatch](workflows/tmux-dispatch/workflow.md) or [bmad-dispatch](workflows/bmad-dispatch/workflow.md) |
| ollama | [tmux-dispatch](workflows/tmux-dispatch/workflow.md) or [bmad-dispatch](workflows/bmad-dispatch/workflow.md) |
| gemini | [tmux-dispatch](workflows/tmux-dispatch/workflow.md) or [bmad-dispatch](workflows/bmad-dispatch/workflow.md) |
| deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow | [tmux-dispatch](workflows/tmux-dispatch/workflow.md) or [bmad-dispatch](workflows/bmad-dispatch/workflow.md) |
| api (image/audio/video) | [api-dispatch](workflows/api-dispatch/workflow.md) |

Model-dispatch is invoked by /aim-agent-lifecycle for non-Claude providers. The tmux workflow runs and returns to lifecycle for agent management.

---

## Decision Log

When selecting a model other than the role default, document:
- Why the override was applied
- Which override rule triggered
- Expected benefit of the higher/lower model

---

## Supporting Resources

### Sub-Workflows
- [claude-native](workflows/claude-native/workflow.md) — Claude Code teammate spawn via Agent tool + SendMessage
- [tmux-dispatch](workflows/tmux-dispatch/workflow.md) — Generic tmux dispatch for non-Claude providers
- [bmad-dispatch](workflows/bmad-dispatch/workflow.md) — Two-phase BMAD agent dispatch via tmux panes
- [api-dispatch](workflows/api-dispatch/workflow.md) — OpenRouter direct API dispatch for multimodal tasks

### Reference
- [agent-reference](references/agent-reference.md) — Internal technical reference for executing agents
- [bmad-agents](references/bmad-agents.md) — BMAD agent command reference and activation details
- [model-selection-guide](references/model-selection-guide.md) — Shared model selection reference for dispatch workflows
- [models-claude](references/models-claude.md) — Available Claude models via OpenRouter and native Anthropic API
- [models-ollama](references/models-ollama.md) — Available Ollama cloud models for dispatch
- [models-openrouter](references/models-openrouter.md) — Top OpenRouter models organized by category
- [providers](references/providers.md) — Canonical provider list for model-dispatch
- [setup-guide](references/setup-guide.md) — Complete installation and setup guide
- [user-guide](references/user-guide.md) — End-user guide for dispatching tasks to remote models

### Scripts
- [install.sh](scripts/install.sh) — Interactive installer for model-dispatch (all providers)
- [validate-setup.sh](scripts/validate-setup.sh) — Pre-flight checks for all configured providers
- [auto-approve-hook.sh](scripts/auto-approve-hook.sh) — PermissionRequest hook for auto-approving dispatched agents
- [auto-reply-monitor.sh](scripts/auto-reply-monitor.sh) — Signal + diff-based idle detection with permission dialog forwarding
- [on-complete.sh](scripts/on-complete.sh) — Write signal file when Claude Code session completes
- [inbox-inject.py](scripts/inbox-inject.py) — Inject messages into a Claude Code teammate inbox
- [usage-report.sh](scripts/usage-report.sh) — OpenRouter usage and cost aggregation via API
- [statusline.sh](scripts/statusline/statusline.sh) — OpenRouter pane statusline for tmux (model, cost, tokens)
- [openrouter-api/](scripts/openrouter-api/) — Python scripts for direct OpenRouter API calls (image/audio/video generate, analyze, list-models)

### Wrappers
- [claude-dispatch.sh](wrappers/claude-dispatch.sh) — Native Anthropic Claude Code wrapper (clears proxy env vars)
- [openrouter-claude.sh](wrappers/openrouter-claude.sh) — Claude Code via OpenRouter with proper token handling
- [provider-dispatch.sh](wrappers/provider-dispatch.sh) — Dynamic wrapper for any configured provider
- [install-wrappers.sh](wrappers/install-wrappers.sh) — Install model-dispatch wrappers to ~/.local/bin

### Logs
- [logs/](logs/) — Runtime log output directory (currently empty; reserved for dispatch execution logs)

### Evals
- [evals.json](evals/evals.json) — Skill evaluation test cases
