---
name: aim-model-dispatch
description: Select the appropriate LLM model for each agent based on task complexity and role
---

# Model Dispatch -- Model Selection for Agent Activation

**Purpose**: Select the appropriate LLM model for each agent based on task complexity and agent role. Called by aim-agent-dispatch and aim-bmad-dispatch before agent activation.

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

## Usage

When preparing an agent dispatch, determine the model:

1. Assess the task complexity (Straightforward / Moderate / Significant / Complex)
2. Check the agent role default from the table above
3. Apply any override rules that match
4. Return the model parameter value: `"sonnet"`, `"opus"`, or `"haiku"`

For Claude-native agents, the model value is passed as the `model` parameter to the Agent tool when spawning teammates. When a non-Claude provider is specified by the user, the model tier informs provider model selection — defer to the model-dispatch skill for provider routing and terminal launch.

---

## Decision Log

When selecting a model other than the role default, document:
- Why the override was applied
- Which override rule triggered
- Expected benefit of the higher/lower model

---

## Supporting Resources

### Sub-Workflows
- [api-dispatch](workflows/api-dispatch/workflow.md) — OpenRouter direct API dispatch for multimodal tasks (image, audio, video generation)
- [bmad-dispatch](workflows/bmad-dispatch/workflow.md) — Two-phase BMAD agent dispatch via tmux panes with backend-aware wrappers
- [route](workflows/route/step-01-resolve-backend.md) — Task classification and backend routing (claude/openrouter/ollama/gemini/etc.)
- [tmux-dispatch](workflows/tmux-dispatch/workflow.md) — Generic tmux dispatch for any backend, launches Claude Code in tmux pane

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
