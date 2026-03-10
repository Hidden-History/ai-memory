# Prometheus with environment variable substitution support
# Allows secrets to be injected at runtime from .env file
# Uses sed instead of envsubst (Busybox compatible, no external deps)
FROM prom/prometheus:v2.55.1

USER root

# Install Python3 + bcrypt for runtime bcrypt hash generation (web.yml auth)
# Alpine base — use apk. Pinned bcrypt for reproducibility.
RUN apk add --no-cache python3 py3-pip && \
    pip3 install --no-cache-dir --break-system-packages bcrypt==4.2.1

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy config templates
COPY prometheus.yml /etc/prometheus/prometheus.yml.template
COPY web.yml /etc/prometheus/web.yml.template

# CR-1: Create runtime directory as root before switching to nobody
# The entrypoint needs to write the processed config here
# Use numeric IDs (65534:65534) - Busybox doesn't have nogroup
RUN mkdir -p /etc/prometheus/runtime && chown 65534:65534 /etc/prometheus/runtime

USER nobody

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
