#!/bin/bash
# statusline.sh — OpenRouter pane statusline for tmux
# Outputs: MODEL COST/tokens for current session
#
# Usage: statusline.sh <pane-id> [token-file]
#   pane-id: tmux pane ID (e.g., %123)
#   token-file: Path to OpenRouter API token (default: ~/.openrouter-token)

set -uo pipefail

PANE_ID="${1:?Usage: statusline.sh <pane-id> [token-file]}"
TOKEN_FILE="${2:-$HOME/.openrouter-token}"
SIGNAL_FILE="/tmp/model-dispatch-signal-${PANE_ID}"

# Check if session is complete
if [ -f "$SIGNAL_FILE" ]; then
  SIGNAL_CONTENT=$(cat "$SIGNAL_FILE" 2>/dev/null || echo "")
  if echo "$SIGNAL_CONTENT" | grep -q "^DONE"; then
    echo "✓ complete"
    exit 0
  fi
fi

# Read API key
if [ ! -f "$TOKEN_FILE" ]; then
  echo "? no-token"
  exit 1
fi

OPENROUTER_API_KEY=$(tr -d '\n\r' < "$TOKEN_FILE")
if [ -z "$OPENROUTER_API_KEY" ]; then
  echo "? empty-token"
  exit 1
fi

# Fetch current session usage
USAGE=$(curl -s -N \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  "https://openrouter.ai/api/v1/session?pane=${PANE_ID}" 2>/dev/null || echo "")

if [ -z "$USAGE" ]; then
  echo "? loading..."
  exit 0
fi

# Parse response
# Expected format: {"model": "anthropic/claude-3-5-sonnet", "tokens": 1234, "cost": 0.00456}
MODEL=$(echo "$USAGE" | jq -r '.model // "unknown"' 2>/dev/null)
TOKENS=$(echo "$USAGE" | jq -r '.tokens // 0' 2>/dev/null)
COST=$(echo "$USAGE" | jq -r '.cost // 0' 2>/dev/null)

# Format cost
COST_FMT=$(printf "%.6f" "$COST")

# Output statusline
# Format: claude-sonnet-4 1.2k tokens $0.0042
if [ "$MODEL" != "unknown" ] && [ "$TOKENS" != "null" ] && [ "$TOKENS" -gt 0 ] 2>/dev/null; then
  echo "${MODEL} ${TOKENS}t \$$COST_FMT"
else
  echo "? running..."
fi
