#!/bin/bash
set -euo pipefail
# claude-dispatch — Guaranteed native Anthropic Claude Code
# Clears all proxy env vars to ensure direct Anthropic API routing

# Unset proxy/override env vars to ensure native routing
unset CLAUDECODE
unset ANTHROPIC_BASE_URL
unset ANTHROPIC_AUTH_TOKEN
# Do NOT unset ANTHROPIC_API_KEY — native Claude needs it

exec claude "$@"
