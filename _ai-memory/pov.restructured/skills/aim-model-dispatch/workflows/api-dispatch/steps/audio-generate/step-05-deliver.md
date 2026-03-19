---
name: 'step-05-deliver'
description: 'Format and deliver generated audio URL to user'
nextStepFile: null
---

# Step 5: Deliver Result

## STEP GOAL
Format the API response and deliver it to the user, optionally injecting into the team lead inbox.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: OUTPUT_AUDIO_URL and TOKEN_USAGE from step-04
- Limits: Do not make additional API calls. Deliver what was generated.

## MANDATORY SEQUENCE

### 1. Format Output

```bash
echo "=== Generated Audio ==="
echo "Model: ${MODEL}"
echo "URL: ${OUTPUT_AUDIO_URL}"
```

### 2. Show Token Usage

```bash
echo ""
echo "=== Token Usage ==="
echo "${TOKEN_USAGE}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Input: {d.get(\"input_tokens\", 0)}, Output: {d.get(\"output_tokens\", 0)}, Total: {d.get(\"total_tokens\", 0)}')
"
```

### 3. Deliver to User

**Direct delivery (most common):**
- Output is already displayed in terminal
- Include any relevant metadata (token usage, model)

**Inbox injection (if in team context):**
```bash
TEAM_DIR=$(ls -td ~/.claude/teams/*/config.json 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
if [ -n "$TEAM_DIR" ]; then
  INBOX="${TEAM_DIR}/inboxes/team-lead.json"
  RESULT_MESSAGE="Model: ${MODEL}\n\nGenerated Audio URL: ${OUTPUT_AUDIO_URL}\n\nToken Usage: ${TOKEN_USAGE}"
  SKILL_DIR="$(pwd)/.claude/skills/model-dispatch"
  python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
    --inbox "$INBOX" \
    --from "api-dispatch" \
    --message "$RESULT_MESSAGE" \
    --color "green"
  echo "Result injected to team lead inbox."
fi
```

### 4. Final Summary

```bash
echo ""
echo "=== Complete ==="
echo "Audio generation complete."
```

## CRITICAL STEP COMPLETION NOTE
This is the final step. The workflow is complete when the result has been formatted and delivered to the user (or inbox).

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Output formatted with === Generated Audio === header
- Model displayed
- OUTPUT_AUDIO_URL displayed
- Token usage shown
- Result delivered (terminal output or inbox injection)

### FAILURE:
- No URL displayed
- No delivery to user or inbox
- Missing header or model info in output
