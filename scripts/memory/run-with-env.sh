#!/usr/bin/env bash
# Run memory scripts with proper environment variables
# Usage: ./scripts/memory/run-with-env.sh <script.py> [args...]
#
# Loads env vars using secrets-first / env-fallback dual-source pattern (BUG-292 fix):
#   1. docker/.env.secrets (chmod 600) — PP-1/PP-2 secret-class keys (QDRANT_API_KEY, GITHUB_TOKEN)
#   2. docker/.env (fallback) — non-secret config and legacy pre-BUG-277 installs
# Required because scripts run on HOST need the same auth as Docker services (which use
# compose --env-file dual-load via stack.sh::_compose per BUG-279 fix).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}"
ENV_FILE="${AI_MEMORY_ENV_FILE:-$INSTALL_DIR/docker/.env}"
SECRETS_FILE="${AI_MEMORY_SECRETS_FILE:-${ENV_FILE%/*}/.env.secrets}"
PY_BIN="$INSTALL_DIR/.venv/bin/python"

export QDRANT_HOST="${QDRANT_HOST:-localhost}"
export QDRANT_PORT="${QDRANT_PORT:-26350}"
export QDRANT_GRPC_PORT="${QDRANT_GRPC_PORT:-26351}"
export EMBEDDING_HOST="${EMBEDDING_HOST:-127.0.0.1}"
export QDRANT_USE_HTTPS="${QDRANT_USE_HTTPS:-false}"

load_env_var() {
    local name="$1"
    local value
    # Secrets-first lookup: mirrors _env_split_helpers.sh::_read_env_key (BUG-292 fix)
    if [ -f "$SECRETS_FILE" ]; then
        value=$(grep "^${name}=" "$SECRETS_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
        if [ -n "$value" ]; then
            export "$name=$value"
            return 0
        fi
    fi
    # Fallback to .env (non-secret config and blank PP-1/PP-2 placeholders post-BUG-277)
    value=$(grep "^${name}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
    if [ -n "$value" ]; then
        export "$name=$value"
    fi
}

# Load environment variables from docker/.env.secrets (secrets-first) and docker/.env (fallback)
if [ -f "$ENV_FILE" ] || [ -f "$SECRETS_FILE" ]; then
    load_env_var "QDRANT_API_KEY"
    load_env_var "AI_MEMORY_PROJECT_ID"
    load_env_var "GITHUB_REPO"
    load_env_var "GITHUB_BRANCH"
    load_env_var "GITHUB_TOKEN"
    load_env_var "GITHUB_SYNC_ENABLED"
else
    echo "Warning: $ENV_FILE and $SECRETS_FILE not found, running without API key"
fi

if [ ! -x "$PY_BIN" ]; then
    echo "Error: ai-memory venv python not found: $PY_BIN"
    echo "Run $INSTALL_DIR/scripts/install.sh or set AI_MEMORY_INSTALL_DIR correctly."
    exit 1
fi

# Check if script argument provided
if [ -z "$1" ]; then
    echo "Usage: $0 <script.py> [args...]"
    echo ""
    echo "Available scripts:"
    for script_path in "$SCRIPT_DIR"/*.py; do
        [ -e "$script_path" ] || continue
        basename "$script_path"
    done
    exit 1
fi

SCRIPT="$1"
shift

# If script doesn't have full path, look in scripts/memory/
if [ ! -f "$SCRIPT" ]; then
    SCRIPT="$SCRIPT_DIR/$SCRIPT"
fi

if [ ! -f "$SCRIPT" ]; then
    echo "Error: Script not found: $SCRIPT"
    exit 1
fi

# Run the script
exec "$PY_BIN" "$SCRIPT" "$@"
