---
name: 'step-02-select-model'
description: 'Present audio-generate model options to user'
nextStepFile: './step-03-verify-prompt.md'
---

# Step 2: Select Model

## STEP GOAL
Choose model for audio-generate. If user did not specify, present options and wait for confirmation.

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
  --category audio-gen --query "${INPUT_SOURCE}" --limit 10
```

Default if live query fails:

| Model ID | Notes |
|---|---|
| `openai/tts-1-hd` | High quality TTS (recommended) |
| `openai/tts-1` | Standard TTS, faster and lower cost |
| `elevenlabs/eleven_multilingual_v2` | Multi-language TTS, natural voices |
| `suno/chirp-v3-5` | Music generation from text |

### 3. Wait for User Model Choice

> "Recommended: **openai/tts-1-hd**. Accept this model, or pick a different one?"

Halt and wait. Do not proceed without the user's explicit response. Do not interpret silence as approval. Record confirmed choice as MODEL.

### 4. Select Voice (TTS Models Only)

For OpenAI TTS models (`openai/tts-1`, `openai/tts-1-hd`), present voice options:

| Voice | Character |
|---|---|
| `alloy` | Neutral, balanced (default) |
| `echo` | Soft, thoughtful |
| `fable` | Expressive, British accent |
| `nova` | Warm, professional |
| `onyx` | Deep, authoritative |
| `shimmer` | Light, energetic |

Ask: "Which voice? Press Enter to use default (`alloy`), or type a voice name."

For non-TTS models (ElevenLabs, Suno/music), skip this section — voice is model-specific.

Record **VOICE** (default: `alloy` if not specified or Enter pressed).

### 5. Record Selection

- **MODEL**: Confirmed model ID
- **VOICE**: Selected voice (default: `alloy`)
- **SCRIPT**: `audio-generate.py`
- **SCRIPT_PATH**: Resolved at execution time via SKILL_DIR inline

## CRITICAL STEP COMPLETION NOTE
ONLY when model is confirmed and VOICE is recorded, load and read fully {nextStepFile}

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
