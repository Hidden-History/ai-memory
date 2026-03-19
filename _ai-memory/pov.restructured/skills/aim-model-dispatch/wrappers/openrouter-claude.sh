#!/bin/bash
# openrouter-claude — Claude Code via OpenRouter
# Routes to OpenRouter API endpoint with proper token handling

unset CLAUDECODE

# Read OpenRouter API key from file or env var
if [ -f ~/.openrouter-token ]; then
  OPENROUTER_API_KEY=$(tr -d '\n\r' < ~/.openrouter-token)
elif [ -n "$OPENROUTER_API_KEY" ]; then
  : # Use env var
else
  echo "Error: No OpenRouter API key found. Run: model-dispatch install" >&2
  exit 1
fi

# Set OpenRouter endpoint and auth token
export ANTHROPIC_BASE_URL="https://openrouter.ai/api"
export ANTHROPIC_AUTH_TOKEN="$OPENROUTER_API_KEY"
export ANTHROPIC_API_KEY=""  # Must be explicitly empty per OpenRouter docs

exec claude "$@"
