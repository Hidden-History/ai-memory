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
    local caller_wins="${2:-}"
    local value
    # Caller-wins guard (I2): when the second arg is set, a value the caller
    # already exported takes precedence over the file value (${!name+x} is set
    # even for an intentional empty export). Scoped to the AI_MEMORY_SOT_* tuning
    # family only — NOT the secrets/GitHub keys below, whose whole purpose is to
    # inject Docker-managed values into host scripts (file-wins, BUG-292).
    if [ -n "$caller_wins" ] && [ -n "${!name+x}" ]; then
        return 0
    fi
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
#
# BUG-314 (scoped Part D): AI_MEMORY_PROJECT_ID is deliberately NOT loaded here.
# The install-global value in docker/.env is a *service* default (for the long-
# running Docker services, which consume it via compose env_file and have no cwd).
# Injecting it into *operator* scripts run from a different workspace is a confused-
# deputy bug: it overrode the workspace's own project, mis-filing memory under the
# install-global group_id. Operator scripts now resolve per-workspace via
# resolve_project_id (caller-set AI_MEMORY_PROJECT_ID -> cwd/git slug -> fail-loud).
# A caller-exported AI_MEMORY_PROJECT_ID (e.g. from a workspace .claude/settings.json)
# is preserved untouched. Only secrets/connectivity config is loaded below.
if [ -f "$ENV_FILE" ] || [ -f "$SECRETS_FILE" ]; then
    load_env_var "QDRANT_API_KEY"
    load_env_var "GITHUB_REPO"
    load_env_var "GITHUB_BRANCH"
    load_env_var "GITHUB_TOKEN"
    load_env_var "GITHUB_SYNC_ENABLED"
    # F-D1-1: forward the aim-sot engine's AI_MEMORY_SOT_* budget family. The
    # engine reads these via os.environ (aim_sot_detect_propose.py / _shadow.py)
    # with safe defaults, but operator/hook scripts run on the HOST, so unless
    # they are exported here the documented tuning surface in docker/.env is
    # inert. Forward the whole namespace by prefix (future-proof: new SOT knobs
    # auto-forward — no per-key list to drift out of sync). Each key still goes
    # through load_env_var, preserving secrets-first + empty-skip. The anchored
    # prefix never matches AI_MEMORY_PROJECT_ID (BUG-314 exclusion above stays
    # intact) nor commented '# AI_MEMORY_SOT_...' example lines.
    for sot_env_file in "$SECRETS_FILE" "$ENV_FILE"; do
        [ -f "$sot_env_file" ] || continue
        while IFS= read -r sot_key; do
            # caller_wins: a caller-exported AI_MEMORY_SOT_* (e.g. a per-invocation
            # budget override) is an intentional tuning signal and must not be
            # clobbered by the install-global docker/.env value (I2).
            load_env_var "$sot_key" caller_wins
        done < <(grep -oE '^AI_MEMORY_SOT_[A-Z_]+=' "$sot_env_file" | cut -d= -f1 | sort -u)
    done
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
