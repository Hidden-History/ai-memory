---
name: 'step-01-resolve-task'
description: 'Analyze task, present model options, and prepare dispatch plan for tmux dispatch'
nextStepFile: './step-02-launch-pane.md'
---

# Step 1: Resolve Task and Configure Dispatch Plan

## STEP GOAL
Analyze the user's task description to determine which backend (claude/openrouter/ollama/gemini/deepseek/groq/cerebras/mistral/openai/vertex-ai/siliconflow) and model to use, producing a dispatch plan for subsequent steps. If the user did not specify a model, present options and wait for their choice before proceeding.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps
- Use holistic judgment on user intent, not just keyword matching

## CONTEXT BOUNDARIES
- Available context: User's task description, any explicitly mentioned backend or model
- Limits: Do not create panes or send commands yet — this step is configuration only.
- **Backend skip:** If BACKEND was already set by route/step-01 (standard SKILL.md activation path),
  use that value directly and skip Section 1. Only run Section 1 if activating this workflow directly
  without the routing step.

## MANDATORY SEQUENCE

### 1. Extract Backend Indicator

Check user input for backend specification:

**Explicit backend keywords (highest priority):**
- "dispatch to claude" / "use claude" / "claude-dispatch" → `claude`
- "dispatch to openrouter" / "use openrouter" / "300 models" → `openrouter`
- "dispatch to ollama" / "use ollama" / "remote model" → `ollama`
- "dispatch to gemini" / "use gemini" / "google model" → `gemini`
- "dispatch to deepseek" / "use deepseek" → `deepseek`
- "dispatch to groq" / "use groq" / "llama on groq" → `groq`
- "dispatch to cerebras" / "use cerebras" / "fast inference" → `cerebras`
- "dispatch to mistral" / "use mistral" / "codestral" → `mistral`
- "dispatch to openai" / "use openai" / "gpt-4o" / "o1" → `openai`
- "dispatch to vertex-ai" / "use vertex-ai" / "vertex ai" / "google vertex" → `vertex-ai`
- "dispatch to siliconflow" / "use siliconflow" / "silicon flow" → `siliconflow`

**No backend specified** → Default to `claude` (native Anthropic)

### 2. Check for Explicit Model

If the user already specified a model in their request (e.g., "use qwen3-coder-next:cloud", "with gpt-4o"), record that model and skip to section 5.

If no model was specified, proceed to section 3.

### 3. Present Model Options to User

Follow the model selection procedure in `references/model-selection-guide.md`:
- Detect task category using the category table
- Present backend-appropriate model options
- Run live query for openrouter (SKILL_DIR inline in every Bash call)

### 4. Wait for User Model Choice

Follow the confirmation gate in `references/model-selection-guide.md`. Halt and wait for
explicit user confirmation. Record confirmed choice as MODEL.

### 5. Determine Wrapper Command

| Backend | Wrapper Command |
|---|---|
| claude | `claude-dispatch` (or `claude` if wrapper unavailable) |
| openrouter | `provider-dispatch openrouter` |
| ollama | `provider-dispatch ollama` |
| gemini | `gemini` (native Gemini CLI — uses Google account auth, not API key) |
| deepseek | `provider-dispatch deepseek` |
| groq | `provider-dispatch groq` |
| cerebras | `provider-dispatch cerebras` |
| mistral | `provider-dispatch mistral` |
| openai | `provider-dispatch openai` |
| vertex-ai | `provider-dispatch vertex-ai` |
| siliconflow | `provider-dispatch siliconflow` |
| (any other provider) | `provider-dispatch <provider-name>` |

**CLAUDE WRAPPER:** The wrapper should unset CLAUDECODE and ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN to guarantee native Anthropic API routing.

**GEMINI CLI:** Gemini uses its own native CLI (`gemini`) rather than routing through Claude Code. This uses the user's Google account/plan (not the Gemini API free tier). The `gemini` command must be installed via `npm install -g @google/gemini-cli`. Model selection and authentication are handled by the Gemini CLI itself. When BACKEND is `gemini`, set WRAPPER_CMD to `gemini` and skip model confirmation — the Gemini CLI manages its own model selection interactively.

### 6. Record Dispatch Plan

Store these values:
- **BACKEND**: claude, openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow, or any configured provider
- **PROVIDER**: Same as BACKEND value (used to construct `provider-dispatch ${PROVIDER}` for non-claude backends)
- **WRAPPER_CMD**: The command to launch Claude (e.g., `claude-dispatch` or `provider-dispatch gemini`)
- **MODEL**: The model ID confirmed by user (e.g., `glm-5:cloud`, or empty for native claude)
- **TASK_INPUT**: The user's task description
- **TASK_FOLLOW_UP**: Any additional input expected later (empty if not known)

### 7. Validate Dispatch Plan

Confirm:
- Backend is one of: claude, openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow, or a configured provider
- Wrapper command exists or can be executed
- Model is confirmed by user or was explicitly specified in request

## CRITICAL STEP COMPLETION NOTE
ONLY when model is confirmed by user (section 4) or was explicitly specified (section 2), AND the dispatch plan is fully prepared with all values recorded, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Backend correctly identified from user intent
- Model options presented to user (when not pre-specified)
- User explicitly confirmed model choice
- Wrapper command resolved for selected backend
- All dispatch plan values recorded
- Plan validated before proceeding

### FAILURE:
- Proceeding without user confirmation when no model was specified
- Silently picking a default model without presenting options
- Ambiguous backend specification without clear default
- Proceeding without complete dispatch plan
