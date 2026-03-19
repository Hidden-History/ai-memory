#!/bin/bash
# usage-report.sh — OpenRouter usage aggregation via API
# Shows cost by model for current billing period
#
# Usage: usage-report.sh [token-file] [start-date]
#   token-file: Path to OpenRouter API token (default: ~/.openrouter-token)
#   start-date: Filter from date (ISO format, default: first of current month)

set -uo pipefail

TOKEN_FILE="${1:-$HOME/.openrouter-token}"
START_DATE="${2:-$(date +%Y-%m-01)}"

# Read API key
if [ ! -f "$TOKEN_FILE" ]; then
  echo "Error: API token file not found: $TOKEN_FILE" >&2
  echo "Run: echo YOUR_KEY > $TOKEN_FILE && chmod 600 $TOKEN_FILE" >&2
  exit 1
fi

OPENROUTER_API_KEY=$(tr -d '\n\r' < "$TOKEN_FILE")
if [ -z "$OPENROUTER_API_KEY" ]; then
  echo "Error: API token is empty" >&2
  exit 1
fi

# Fetch usage from OpenRouter API
# https://openrouter.ai/docs/api-reference#get-/activity
echo "Fetching usage from $START_DATE..."
echo ""

USAGE=$(curl -s -N \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  "https://openrouter.ai/api/v1/activity?since=${START_DATE}T00:00:00Z" 2>/dev/null)

if [ -z "$USAGE" ]; then
  echo "Error: Empty response from OpenRouter API" >&2
  exit 1
fi

# Check for API errors
if echo "$USAGE" | jq -e '.error' >/dev/null 2>&1; then
  ERROR_MSG=$(echo "$USAGE" | jq -r '.error.message // "Unknown error"' 2>/dev/null)
  echo "Error from OpenRouter: $ERROR_MSG" >&2
  exit 1
fi

# Aggregate costs by model
echo "=== OpenRouter Usage Report ==="
echo "Period: ${START_DATE} to $(date +%Y-%m-%d)"
echo ""
echo "Usage breakdown by model:"

while IFS=$'\t' read -r model requests cost; do
  printf "%-40s %6s requests  $%.6f\n" "$model" "$requests" "$cost"
done < <(echo "$USAGE" | jq -r '
  .data // [] |
  group_by(.model_id) |
  map({
    model: .[0].model_id,
    total_requests: (map(.total_requests) | add),
    total_cost: (map(.total_cost) | add)
  }) |
  sort_by(.total_cost) |
  reverse |
  .[] |
  "\(.model)\t\(.total_requests)\t\(.total_cost)"
' 2>/dev/null) || {
  echo "Error: Failed to parse usage data" >&2
  echo ""
  echo "Raw response:"
  echo "$USAGE" | head -c 500
  exit 1
}

echo ""
echo "=== Summary ==="

TOTAL_COST=$(echo "$USAGE" | jq '[.data // [] | .[].total_cost] | add // 0' 2>/dev/null || echo "0")
TOTAL_REQUESTS=$(echo "$USAGE" | jq '[.data // [] | .[].total_requests] | add // 0' 2>/dev/null || echo "0")
TOTAL_TOKENS=$(echo "$USAGE" | jq '[.data // [] | .[].total_tokens] | add // 0' 2>/dev/null || echo "0")

echo "Total requests: $TOTAL_REQUESTS"
echo "Total tokens: $TOTAL_TOKENS"
echo "Total cost: $(printf '%.6f\n' $TOTAL_COST)"
