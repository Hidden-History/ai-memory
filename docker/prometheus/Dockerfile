# Prometheus with environment variable substitution support
# Allows secrets to be injected at runtime from .env file

# Stage 1: Get envsubst binary from Alpine
FROM alpine:3.21 AS builder
RUN apk add --no-cache gettext

# Stage 2: Prometheus with envsubst
FROM prom/prometheus:v2.55.1

# Copy envsubst from builder (prom/prometheus is Busybox-based, no apk)
USER root
COPY --from=builder /usr/bin/envsubst /usr/bin/envsubst

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy config template
COPY prometheus.yml /etc/prometheus/prometheus.yml.template

# CR-1: Create runtime directory as root before switching to nobody
# The entrypoint needs to write the processed config here
# Use numeric IDs (65534:65534) - Busybox doesn't have nogroup
RUN mkdir -p /etc/prometheus/runtime && chown 65534:65534 /etc/prometheus/runtime

USER nobody

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
