#!/bin/sh
# Prometheus entrypoint script
# Substitutes environment variables in prometheus.yml and web.yml before starting
# This ensures secrets from .env are injected at runtime, not in the repo

set -e

# CR-7: Validate required environment variables
: "${QDRANT_API_KEY:?Error: QDRANT_API_KEY must be set}"
: "${PROMETHEUS_ADMIN_PASSWORD:?Error: PROMETHEUS_ADMIN_PASSWORD must be set}"

# Create runtime config directory
mkdir -p /etc/prometheus/runtime

# Substitute environment variables in config using sed (Busybox compatible)
# envsubst requires musl libc which doesn't exist in Prometheus image
sed -e "s|\${QDRANT_API_KEY}|${QDRANT_API_KEY}|g" \
    -e "s|\${PROMETHEUS_ADMIN_PASSWORD}|${PROMETHEUS_ADMIN_PASSWORD}|g" \
    /etc/prometheus/prometheus.yml.template \
    > /etc/prometheus/runtime/prometheus.yml

echo "Environment variables substituted in prometheus.yml"

# Generate bcrypt hash from PROMETHEUS_ADMIN_PASSWORD and substitute into web.yml
# Uses Python3 + bcrypt (installed in Dockerfile) for proper hash generation
# This ensures the hash always matches the current password, fixing stale-hash 401s
BCRYPT_HASH=$(python3 -c "
import bcrypt, os
password = os.environ['PROMETHEUS_ADMIN_PASSWORD'].encode('utf-8')
print(bcrypt.hashpw(password, bcrypt.gensalt(12)).decode('utf-8'))
")

# Use Python for substitution because bcrypt hashes contain $ characters
# which sed interprets as backreferences regardless of delimiter choice
export BCRYPT_HASH
python3 -c "
import os
template = open('/etc/prometheus/web.yml.template').read()
result = template.replace('\${BCRYPT_HASH}', os.environ['BCRYPT_HASH'])
open('/etc/prometheus/runtime/web.yml', 'w').write(result)
"

echo "web.yml generated with fresh bcrypt hash"

# Start Prometheus with the generated config
exec /bin/prometheus \
    --config.file=/etc/prometheus/runtime/prometheus.yml \
    --web.config.file=/etc/prometheus/runtime/web.yml \
    --storage.tsdb.path=/prometheus \
    --storage.tsdb.retention.time=30d \
    --web.console.libraries=/usr/share/prometheus/console_libraries \
    --web.console.templates=/usr/share/prometheus/consoles \
    "$@"
