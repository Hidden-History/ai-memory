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
