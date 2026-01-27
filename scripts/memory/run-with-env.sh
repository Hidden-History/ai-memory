#!/bin/bash
# Run memory scripts with proper environment variables
# Usage: ./scripts/memory/run-with-env.sh <script.py> [args...]
#
# This script loads QDRANT_API_KEY and other env vars from docker/.env
# Required because scripts run on HOST need the same auth as Docker services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/docker/.env"

# Load environment variables from docker/.env
if [ -f "$ENV_FILE" ]; then
    # Export only specific variables needed by scripts (avoid polluting env)
    export QDRANT_API_KEY=$(grep '^QDRANT_API_KEY=' "$ENV_FILE" | cut -d= -f2)
    export QDRANT_HOST="${QDRANT_HOST:-localhost}"
    export QDRANT_PORT="${QDRANT_PORT:-26350}"
    export QDRANT_USE_HTTPS="${QDRANT_USE_HTTPS:-false}"
else
    echo "Warning: $ENV_FILE not found, running without API key"
fi

# Check if script argument provided
if [ -z "$1" ]; then
    echo "Usage: $0 <script.py> [args...]"
    echo ""
    echo "Available scripts:"
    ls -1 "$SCRIPT_DIR"/*.py 2>/dev/null | xargs -n1 basename
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
exec python3 "$SCRIPT" "$@"
