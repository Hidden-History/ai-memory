---
name: 'step-03-execute'
description: 'Execute image-analyze Python script to call OpenRouter API'
nextStepFile: './step-04-deliver.md'
---

# Step 3: Execute API Call

## STEP GOAL
Run the Python script to call the API and capture the response.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Model, script name, input from previous steps
- Limits: Do not modify the Python scripts. Handle errors gracefully.
- ANALYSIS_PROMPT: The user's analytical question or task description (e.g., "What objects are in this image?"). If not captured from the user's task description in step-01, defaults to "Describe this image in detail".

## MANDATORY SEQUENCE

### 1. Check for API Key (OpenRouter)

```bash
if [ -z "$OPENROUTER_API_KEY" ]; then
  if [ -f ~/.openrouter-token ]; then
    OPENROUTER_API_KEY=$(cat ~/.openrouter-token)
  else
    echo "Error: No OpenRouter API key. Run: model-dispatch install"
    exit 1
  fi
fi
```

### 2. Execute Script

```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch"
OUTPUT_JSON=$(python3 "${SKILL_DIR}/scripts/openrouter-api/image-analyze.py" \
  --model "${MODEL}" \
  --input "${INPUT_SOURCE}" \
  --prompt "${ANALYSIS_PROMPT:-Describe this image in detail}" \
  --output "-" \
  --json)

SUCCESS=$(echo "$OUTPUT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('analysis' in d)
")

if [ "$SUCCESS" != "True" ]; then
  echo "API call failed:"
  echo "$OUTPUT_JSON"
  # Do not proceed — report error
fi
```

### 3. Parse Output

```bash
OUTPUT_TEXT=$(echo "$OUTPUT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('analysis', ''))
")
TOKEN_USAGE=$(echo "$OUTPUT_JSON" | python3 -c "
import sys, json
print(json.dumps(json.load(sys.stdin).get('usage', {})))
")
```

- **OUTPUT_TEXT**: The analysis/description text from the model
- **TOKEN_USAGE**: Usage object from the API response

## CRITICAL STEP COMPLETION NOTE
ONLY when script executes successfully and output parsed, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- API key verified
- Python script executed successfully
- OUTPUT_TEXT populated from analysis key
- Token usage captured

### FAILURE:
- API key not found
- Script execution failed (check Python syntax)
- Invalid JSON output
- API call returned error
- OUTPUT_TEXT is empty when content was expected
