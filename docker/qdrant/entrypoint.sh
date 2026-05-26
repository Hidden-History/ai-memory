#!/bin/sh
# TD-582 entrypoint shim: translate canonical secret names from .env.secrets
# (QDRANT_API_KEY, QDRANT_READ_ONLY_API_KEY) into Qdrant's native config
# namespace (QDRANT__SERVICE__API_KEY, QDRANT__SERVICE__READ_ONLY_API_KEY).
#
# Why: Qdrant reads QDRANT__SERVICE__* config keys. The split-secrets architecture
# (BUG-277, PM #274) stores secrets under canonical short names. env_file: delivers
# the canonical names into container env; this shim re-exports them under Qdrant's
# expected names before exec'ing qdrant. Removes the compose-side ${VAR} interpolation
# dependency on .env.secrets and makes bare `docker compose up -d` work.
#
# Use exec "$@" to run the command passed from docker-compose `command:`.
# Docker Compose clears the image CMD when `entrypoint:` is overridden, so
# docker-compose.yml explicitly sets `command: ["./entrypoint.sh"]` (the
# qdrant signal-handling + OOM recovery wrapper at /qdrant/entrypoint.sh).
# The image has Entrypoint=null + CMD=["./entrypoint.sh"] (docker image
# inspect qdrant/qdrant:v1.16.3 PM #309); compose:command restores that.
#
# Reference: TECH-DEBT-582; PM #309 Will-locked Option 1.
set -eu

if [ -n "${QDRANT_API_KEY:-}" ]; then
    export QDRANT__SERVICE__API_KEY="$QDRANT_API_KEY"
fi
if [ -n "${QDRANT_READ_ONLY_API_KEY:-}" ]; then
    export QDRANT__SERVICE__READ_ONLY_API_KEY="$QDRANT_READ_ONLY_API_KEY"
fi

exec "$@"
