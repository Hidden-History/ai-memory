---
name: 'step-02-select-model'
description: 'Present image-analyze model options to user'
nextStepFile: './step-03-execute.md'
---

# Step 2: Select Model

## STEP GOAL
Choose model for image-analyze. If user did not specify, present options and wait for confirmation.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Task type and input from step-01
- Limits: Do not execute the script yet — only select model and record selection.

## MANDATORY SEQUENCE

### 1. Check for Explicit Model

If the user already specified a model, record it as MODEL and skip to section 4.

### 2. Present Model Options

Run live query:
```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && \
python3 "${SKILL_DIR}/scripts/openrouter-api/list-models.py" \
  --category vision --query "${INPUT_SOURCE}" --limit 10
```

Default if live query fails:

| Model ID | Notes |
|---|---|
| `anthropic/claude-sonnet-4-6` | Best vision model (recommended) |
| `openai/gpt-4o` | Strong vision, good reasoning |
| `google/gemini-2.5-pro` | Excellent multimodal |
| `anthropic/claude-opus-4-6` | Highest quality, slower |

### 3. Wait for User Model Choice

> "Recommended: **anthropic/claude-sonnet-4-6**. Accept this model, or pick a different one?"

Halt and wait. Do not proceed without the user's explicit response. Do not interpret silence as approval. Record confirmed choice as MODEL.

### 4. Record Selection

- **MODEL**: Confirmed model ID
- **SCRIPT**: `image-analyze.py`
- **SCRIPT_PATH**: Resolved at execution time via SKILL_DIR inline
- **ANALYSIS_PROMPT**: The user's analytical question extracted from the original task description (e.g., "What text appears in this image?"). If no specific question was stated, leave unset — the script defaults to "Describe this image in detail".

## CRITICAL STEP COMPLETION NOTE
ONLY when model is confirmed, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Model options presented to user (when not pre-specified)
- User explicitly confirmed model choice
- Python script name recorded
- All selection values stored

### FAILURE:
- Proceeding without user confirmation when no model was specified
- Silently picking a default model without presenting options
- Proceeding without model selection
