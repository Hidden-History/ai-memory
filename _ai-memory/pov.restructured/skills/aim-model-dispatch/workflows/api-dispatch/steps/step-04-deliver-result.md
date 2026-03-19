---
name: 'step-04-deliver-result'
description: 'Format and deliver API result to user'
nextStepFile: null
---

# Step 4: Deliver Result

## STEP GOAL
Format the API response and deliver it to the user, optionally injecting into the team lead inbox.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: API output and token usage from step-03
- Limits: Do not make additional API calls. Deliver what was generated.

## MANDATORY SEQUENCE

### 1. Format Output by Type

**Text output (most common):**
```bash
echo "=== API Result ==="
echo "Model: ${MODEL}"
echo "Output:"
echo "${OUTPUT_TEXT}"
```

**Image generation (URLs):**
```bash
# image-generate.py returns a JSON object with an "images" array of {url, revised_prompt}
# Extract and display image URLs
echo "$OUTPUT_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for i, img in enumerate(data.get('images', [])):
    print(f'Image {i+1}: {img[\"url\"]}')
    if img.get('revised_prompt'):
        print(f'Revised prompt: {img[\"revised_prompt\"]}')
"
```

**Image analysis (text description):**
```bash
echo "=== Image Analysis ==="
echo "Model: ${MODEL}"
echo "Description:"
echo "${OUTPUT_TEXT}"
```

**Audio transcription:**
```bash
echo "=== Audio Transcription ==="
echo "Model: ${MODEL}"
echo "Transcription:"
echo "${OUTPUT_TEXT}"
```

### 2. Show Token Usage

```bash
echo ""
echo "=== Token Usage ==="
echo "${TOKEN_USAGE}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Input: {d.get(\"input_tokens\", 0)}, Output: {d.get(\"output_tokens\", 0)}, Total: {d.get(\"total_tokens\", 0)}')"
```

### 3. Deliver to User

**Direct delivery (most common):**
- Output is already displayed in terminal
- Include any relevant metadata (token usage, model)

**Inbox injection (if in team context):**
```bash
TEAM_DIR=$(ls -td ~/.claude/teams/*/config.json 2>/dev/null | head -1 | xargs dirname 2>/dev/null)
if [ -n "$TEAM_DIR" ]; then
  INBOX="${TEAM_DIR}/inboxes/team-lead.json"
  RESULT_MESSAGE="Model: ${MODEL}\n\nOutput:\n${OUTPUT_TEXT}\n\nToken Usage: ${TOKEN_USAGE}"
  SKILL_DIR="$(pwd)/.claude/skills/model-dispatch"
  python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
    --inbox "$INBOX" \
    --from "api-dispatch" \
    --message "$RESULT_MESSAGE" \
    --color "green"
  echo "Result injected to team lead inbox."
fi
```

### 4. Handle Output Too Long

If output exceeds terminal display:
```bash
# Save to file for user to inspect
echo "${OUTPUT_TEXT}" > /tmp/api-result-output.txt
echo "Output saved to /tmp/api-result-output.txt"
```

### 5. Final Summary

```bash
echo ""
echo "=== Complete ==="
echo "API dispatch complete. Check output above or in inbox."
```

## CRITICAL STEP COMPLETION NOTE
This is the final step. The workflow is complete when the result has been formatted and delivered to the user (or inbox).

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Output formatted appropriately by type
- Token usage displayed
- Result delivered (terminal output or inbox injection)
- Long output saved to file if needed

### FAILURE:
- Output truncated without saving to file
- No delivery to user or inbox
- Incorrect formatting for output type
