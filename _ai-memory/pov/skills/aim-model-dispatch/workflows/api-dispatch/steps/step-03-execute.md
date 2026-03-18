---
name: 'step-03-execute'
description: 'Execute Python script to call OpenRouter API'
nextStepFile: './step-04-deliver-result.md'
---

# Step 3: Execute API Call

## STEP GOAL
Run the Python script to make the OpenRouter API call and capture the response.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Model, script path, input from previous steps
- Limits: Do not modify the Python scripts. Handle errors gracefully.

## MANDATORY SEQUENCE

### 1. Prompt Approval (HITL Gate — Image Generation Only)

For **image-generate** tasks, present the final prompt to the user before calling the API:

> **Prompt to send:** "[INPUT_SOURCE]"
> **Model:** [MODEL]
>
> Approve this prompt, or edit it before sending?

Halt and wait for the user's response:
- **User approves** — proceed with INPUT_SOURCE as-is
- **User edits** — record the revised prompt as INPUT_SOURCE
- **User cancels** — abort the workflow

For all other task types (text-generate, image-analyze, audio-process), skip this section.

### 2. Check for OpenRouter API Key

```bash
# Check for API key in environment or token file
if [ -z "$OPENROUTER_API_KEY" ]; then
  if [ -f ~/.openrouter-token ]; then
    OPENROUTER_API_KEY=$(cat ~/.openrouter-token)
  else
    echo "Error: No OpenRouter API key found"
    echo "Set OPENROUTER_API_KEY or run: model-dispatch install"
    exit 1
  fi
fi
```

### 3. Prepare Input for Script

The Python script accepts different input formats based on task type:

**Text generation:**
```bash
INPUT_TEXT="Your prompt here"
```

**Image analysis:**
```bash
INPUT_IMAGE="/path/to/image.png"
```

**Image generation:**
```bash
INPUT_TEXT="Describe the image to generate"
```

**Audio processing:**
```bash
INPUT_AUDIO="/path/to/audio.mp3"
```

### 4. Execute the Python Script and Capture Output

**IMPORTANT:** SKILL_DIR does NOT persist between Bash calls. Set it inline every time.

Run the script once with `--json` and capture the full output:
```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch"
OUTPUT_JSON=$(python3 "${SKILL_DIR}/scripts/openrouter-api/${TASK_TYPE}.py" \
  --model "${MODEL}" \
  --input "${INPUT_SOURCE}" \
  --output "-" \
  --json)

# Verify success
SUCCESS=$(echo "$OUTPUT_JSON" | python3 -c "import sys, json; d=json.load(sys.stdin); print('content' in d or 'model' in d or 'images' in d)")

if [ "$SUCCESS" != "True" ]; then
  echo "API call failed:"
  echo "$OUTPUT_JSON"
  # Do not proceed — report error
fi

# Extract results
OUTPUT_TEXT=$(echo "$OUTPUT_JSON" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('content', '') or d.get('analysis', '') or d.get('transcription', ''))")
TOKEN_USAGE=$(echo "$OUTPUT_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin).get('usage', {}))")

echo "Model: ${MODEL}"
echo "Output: ${OUTPUT_TEXT}"
echo "Token usage: ${TOKEN_USAGE}"
```

The script outputs JSON with this structure:
```json
{
  "model": "model-id",
  "content": "Result text",
  "usage": { "input_tokens": 100, "output_tokens": 50, "total_tokens": 150 }
}
```

## CRITICAL STEP COMPLETION NOTE
ONLY when the script executes successfully and output is captured, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Prompt approved by user (image-generate tasks)
- API key verified
- Python script executed successfully
- Output parsed from JSON
- Token usage captured

### FAILURE:
- Sending image generation prompt without user approval
- API key not found
- Script execution failed (check Python syntax)
- Invalid JSON output
- API call returned error
