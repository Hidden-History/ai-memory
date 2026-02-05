#!/bin/sh
# Prometheus entrypoint script
# Substitutes environment variables in prometheus.yml before starting
# This ensures secrets from .env are injected at runtime, not in the repo

set -e

# Create runtime config directory
mkdir -p /etc/prometheus/runtime

# Substitute environment variables in config
envsubst '${QDRANT_API_KEY} ${PROMETHEUS_ADMIN_PASSWORD}' \
    < /etc/prometheus/prometheus.yml.template \
    > /etc/prometheus/runtime/prometheus.yml

echo "Environment variables substituted in prometheus.yml"

# Start Prometheus with the generated config
exec /bin/prometheus \
    --config.file=/etc/prometheus/runtime/prometheus.yml \
    --web.config.file=/etc/prometheus/web.yml \
    --storage.tsdb.path=/prometheus \
    --storage.tsdb.retention.time=30d \
    --web.console.libraries=/usr/share/prometheus/console_libraries \
    --web.console.templates=/usr/share/prometheus/consoles \
    "$@"
