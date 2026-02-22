#!/usr/bin/env bash
set -euo pipefail

# start.sh - Secrets-Aware Service Startup Wrapper
# SPEC-011: SOPS+age Secrets Encryption
# Purpose: Decrypt secrets and start Docker Compose services based on configured backend

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$SCRIPT_DIR/docker"

# Read secrets backend from config (default: env-file for backward compat)
SECRETS_BACKEND="${AI_MEMORY_SECRETS_BACKEND:-env-file}"

case "$SECRETS_BACKEND" in
    sops-age)
        SECRETS_FILE="$DOCKER_DIR/secrets.enc.yaml"
        if [ ! -f "$SECRETS_FILE" ]; then
            echo "ERROR: No encrypted secrets at $SECRETS_FILE"
            echo "Run: ./scripts/setup-secrets.sh"
            exit 1
        fi
        if ! command -v sops &>/dev/null; then
            echo "ERROR: sops not installed. Install: brew install sops  OR  apt install sops"
            exit 1
        fi
        echo "Decrypting secrets and starting services..."
        cd "$DOCKER_DIR"
        # Build command string with all arguments properly quoted
        COMPOSE_CMD="docker compose up -d"
        for arg in "$@"; do
            COMPOSE_CMD="$COMPOSE_CMD $(printf '%q' "$arg")"
        done
        sops exec-env "$SECRETS_FILE" "$COMPOSE_CMD"
        ;;
    keyring)
        echo "Reading secrets from system keyring..."
        # Export all 8 secrets (empty values are okay for optional secrets)
        export QDRANT_API_KEY=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'qdrant_api_key') or '')" 2>/dev/null || echo "")
        export GITHUB_TOKEN=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'github_token') or '')" 2>/dev/null || echo "")
        export JIRA_API_TOKEN=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'jira_api_token') or '')" 2>/dev/null || echo "")
        export GRAFANA_ADMIN_PASSWORD=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'grafana_admin_password') or '')" 2>/dev/null || echo "")
        export PROMETHEUS_ADMIN_PASSWORD=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'prometheus_admin_password') or '')" 2>/dev/null || echo "")
        export OPENROUTER_API_KEY=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'openrouter_api_key') or '')" 2>/dev/null || echo "")
        export ANTHROPIC_API_KEY=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'anthropic_api_key') or '')" 2>/dev/null || echo "")
        export OPENAI_API_KEY=$(python3 -c "import keyring; print(keyring.get_password('ai-memory', 'openai_api_key') or '')" 2>/dev/null || echo "")
        cd "$DOCKER_DIR"
        docker compose up -d "$@"
        ;;
    env-file)
        echo "WARNING: Using plaintext .env file. Consider upgrading to SOPS+age encryption."
        echo "  Run: ./scripts/setup-secrets.sh"
        cd "$DOCKER_DIR"
        docker compose up -d "$@"
        ;;
    *)
        echo "ERROR: Unknown secrets backend: $SECRETS_BACKEND"
        echo "Valid options: sops-age, keyring, env-file"
        exit 1
        ;;
esac

echo "Services started."
