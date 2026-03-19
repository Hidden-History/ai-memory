#!/bin/bash
# provider-dispatch — Dynamic Claude Code wrapper for any configured provider
# Reads ~/.config/claude-code-router/providers.json and sets env vars per provider
#
# Usage: provider-dispatch <provider-name> [claude args...]
#   provider-dispatch gemini
#   provider-dispatch deepseek --model deepseek-reasoner

set -euo pipefail

PROVIDER="${1:-}"

# Show help for -h / --help / no args
if [ -z "$PROVIDER" ] || [ "$PROVIDER" = "-h" ] || [ "$PROVIDER" = "--help" ]; then
  echo "Usage: provider-dispatch <provider> [claude args...]" >&2
  echo "" >&2
  echo "Examples:" >&2
  echo "  provider-dispatch openrouter" >&2
  echo "  provider-dispatch ollama --model glm-5:cloud" >&2
  echo "  provider-dispatch gemini --model gemini-2.0-flash" >&2
  echo "" >&2
  echo "Available providers: $(jq -r '.providers | keys[]' \
    "${HOME}/.config/claude-code-router/providers.json" 2>/dev/null | tr '\n' ' ')" >&2
  echo "" >&2
  echo "To add a provider: run install.sh and select the provider." >&2
  [ -z "$PROVIDER" ] && exit 1 || exit 0
fi
shift  # Remove provider arg, pass rest to claude

CONFIG_FILE="${HOME}/.config/claude-code-router/providers.json"
if [ ! -f "$CONFIG_FILE" ]; then
  echo "Error: providers.json not found at $CONFIG_FILE" >&2
  echo "Run: model-dispatch install" >&2
  exit 1
fi

# Extract provider config
BASE_URL=$(jq -r ".providers[\"${PROVIDER}\"].baseUrl // empty" "$CONFIG_FILE")
KEY_FILE=$(jq -r ".providers[\"${PROVIDER}\"].keyFile // empty" "$CONFIG_FILE")
EMPTY_API_KEY=$(jq -r ".providers[\"${PROVIDER}\"].emptyApiKey // false" "$CONFIG_FILE")

if [ -z "$BASE_URL" ]; then
  echo "Error: Provider '${PROVIDER}' not configured in ${CONFIG_FILE}" >&2
  echo "Run: model-dispatch install" >&2
  exit 1
fi

# Expand ~ in keyFile path
KEY_FILE="${KEY_FILE/#\~/$HOME}"

# Read API token
API_TOKEN=""
if [ -n "$KEY_FILE" ] && [ -f "$KEY_FILE" ]; then
  API_TOKEN=$(tr -d '\n\r' < "$KEY_FILE")
elif [ -n "$KEY_FILE" ]; then
  echo "Error: Token file not found: ${KEY_FILE}" >&2
  echo "Run: model-dispatch install" >&2
  exit 1
fi

# Set Claude Code env vars
unset CLAUDECODE
export ANTHROPIC_BASE_URL="$BASE_URL"
export ANTHROPIC_AUTH_TOKEN="$API_TOKEN"

# OpenRouter requires ANTHROPIC_API_KEY to be explicitly empty
if [ "$EMPTY_API_KEY" = "true" ]; then
  export ANTHROPIC_API_KEY=""
fi

exec claude "$@"
