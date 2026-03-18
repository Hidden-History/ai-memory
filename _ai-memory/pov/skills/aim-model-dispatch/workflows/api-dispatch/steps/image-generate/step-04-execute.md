---
name: 'step-04-execute'
description: 'Execute image-generate Python script to call OpenRouter API'
nextStepFile: './step-05-deliver.md'
---

# Step 4: Execute API Call

## STEP GOAL
Run the Python script to call the API and capture the response.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Model, script name, approved INPUT_SOURCE from previous steps
- Limits: Do not modify the Python scripts. Handle errors gracefully.

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
OUTPUT_JSON=$(python3 "${SKILL_DIR}/scripts/openrouter-api/image-generate.py" \
  --model "${MODEL}" \
  --input "${INPUT_SOURCE}" \
  --output "-" \
  --json)

SUCCESS=$(echo "$OUTPUT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(bool(d.get('images')))
")

if [ "$SUCCESS" != "True" ]; then
  echo "API call failed:"
  echo "$OUTPUT_JSON"
  # Do not proceed — report error
fi
```

### 3. Parse Output

```bash
OUTPUT_URLS=$(echo "$OUTPUT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
images = d.get('images', [])
for img in images:
    print(img.get('url', ''))
")
OUTPUT_REVISED_PROMPTS=$(echo "$OUTPUT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
images = d.get('images', [])
for img in images:
    rp = img.get('revised_prompt', '')
    print(rp if rp else '')
")
TOKEN_USAGE=$(echo "$OUTPUT_JSON" | python3 -c "
import sys, json
print(json.dumps(json.load(sys.stdin).get('usage', {})))
")
```

- **OUTPUT_URLS**: One URL per line from the images array
- **OUTPUT_REVISED_PROMPTS**: Revised prompt per image (if provided by the model)
- **TOKEN_USAGE**: Usage object from the API response

## CRITICAL STEP COMPLETION NOTE
ONLY when script executes successfully and output parsed, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- API key verified
- Python script executed successfully
- OUTPUT_URLS populated from images array
- Token usage captured

### FAILURE:
- API key not found
- Script execution failed (check Python syntax)
- Invalid JSON output
- API call returned error
- No images returned when images were expected
