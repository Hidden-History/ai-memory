---
name: 'step-02-select-model-and-script'
description: 'Present model options to user, select Python script for the task'
nextStepFile: './step-03-execute.md'
---

# Step 2: Select Model and Python Script

## STEP GOAL
Choose the appropriate OpenRouter model and corresponding Python script based on the task classification. If the user did not specify a model, present options and wait for their choice before proceeding.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Task type and input from step-01
- Limits: Do not execute the script yet — only select model and script path.

## MANDATORY SEQUENCE

### 1. Select Python Script

SKILL_DIR must be resolved inline in every Bash call — it does NOT persist between calls:
```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && python3 "${SKILL_DIR}/scripts/openrouter-api/[script].py" [args]
```

| Task Type | Script (relative to SKILL_DIR) |
|---|---|
| image-analyze | `scripts/openrouter-api/image-analyze.py` |
| image-generate | `scripts/openrouter-api/image-generate.py` |
| audio-process | `scripts/openrouter-api/audio-process.py` |

### 2. Check for Explicit Model

If the user already specified a model in their request (e.g., "use dall-e-3", "with gpt-4o"), record that model and skip to section 6.

If MODEL is empty (user did not specify), proceed to section 3.

### 3. Map Task Type to Category

| Task Type | Category |
|---|---|
| image-analyze | `vision` |
| image-generate | `image-gen` |
| audio-process | `audio` |

### 4. Present Model Options to User

Run the live model query:
```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && python3 "${SKILL_DIR}/scripts/openrouter-api/list-models.py" --category [category] --query "[user's task description]" --limit 10
```

Show the user:
1. The live model list from the query above
2. The recommended default for their task type:

| Task Type | Default Model | Notes |
|---|---|---|
| image-analyze | `anthropic/claude-sonnet-4-6` | Best vision model |
| image-generate | `openai/gpt-5-image` | High quality |
| audio-process | `openai/whisper-1` | Standard |

**Fallback:** If the list-models.py script fails (path error, API error), present only the static defaults table above.

### 5. Wait for User Model Choice

Present the recommendation and ask:
> "Recommended: **[default-model]**. Accept this model, or pick a different one from the list above?"

Halt and wait. Do not proceed without the user's explicit response. Do not interpret silence as approval. Record their choice as MODEL.

### 6. Validate Model Availability

The selected model must be available on OpenRouter. Check if the model ID matches known patterns:
- `anthropic/*` — Available
- `openai/*` — Available
- `google/*` — Available
- `meta-llama/*` — Available
- `mistralai/*` — Available
- `black-forest-labs/*` — Available

If model not found in catalog, inform the user and suggest the default from the table in section 4.

### 7. Record Selection

Store these values:
- **MODEL**: The resolved model ID (confirmed by user or explicitly specified)
- **SCRIPT_PATH**: The full path to the Python script
- **OUTPUT_FILE**: Temporary output file path (`/tmp/api-result-${RANDOM}.txt`)

## CRITICAL STEP COMPLETION NOTE
ONLY when model is confirmed by user (section 5) or was explicitly specified (section 2), AND model and script are selected and recorded, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Model options presented to user (when not pre-specified)
- User explicitly confirmed model choice
- Python script path resolved
- Model validated against catalog
- All selection values recorded

### FAILURE:
- Proceeding without user confirmation when no model was specified
- Silently picking a default model without presenting options
- Model not available on OpenRouter
- Script path does not exist
- Proceeding without model selection
