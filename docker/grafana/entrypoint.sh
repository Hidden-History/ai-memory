#!/bin/sh
# TD-582 entrypoint shim: translate canonical secret names from .env.secrets
# (GRAFANA_ADMIN_PASSWORD, GRAFANA_SECRET_KEY) into Grafana's native config
# namespace (GF_SECURITY_ADMIN_PASSWORD, GF_SECURITY_SECRET_KEY).
#
# Why: Grafana reads GF_SECURITY_* config keys via its built-in env-override
# convention. The split-secrets architecture (BUG-277, PM #274) stores secrets
# under canonical short names. env_file: delivers the canonical names into
# container env; this shim re-exports them under Grafana's expected names
# before exec'ing the upstream entrypoint. Removes the compose-side ${VAR}
# interpolation dependency on .env.secrets and makes bare `docker compose up
# -d` work for grafana the same way it does for qdrant (mirror of the qdrant
# shim approach, TECH-DEBT-582).
#
# Use exec "$@" to run the command passed from docker-compose `command:`.
# Docker Compose clears the image ENTRYPOINT when `entrypoint:` is overridden
# and the image's CMD is null upstream, so docker-compose.yml explicitly sets
# `command: ["/run.sh"]` (the grafana upstream entrypoint at /run.sh). The
# image has Entrypoint=["/run.sh"] + Cmd=null (docker image inspect
# grafana/grafana:12.0.0); compose:command restores that as the exec target.
#
# Reference: TECH-DEBT-582; mirrors docker/qdrant/entrypoint.sh.
set -eu

if [ -n "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
    export GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_ADMIN_PASSWORD"
fi
if [ -n "${GRAFANA_SECRET_KEY:-}" ]; then
    export GF_SECURITY_SECRET_KEY="$GRAFANA_SECRET_KEY"
fi

exec "$@"
