# Prometheus with environment variable substitution support
# Allows secrets to be injected at runtime from .env file
FROM prom/prometheus:v2.55.1

# Install envsubst (from gettext package)
USER root
RUN apk add --no-cache gettext

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy config template
COPY prometheus.yml /etc/prometheus/prometheus.yml.template

# CR-1: Create runtime directory as root before switching to nobody
# The entrypoint needs to write the processed config here
RUN mkdir -p /etc/prometheus/runtime && chown nobody:nogroup /etc/prometheus/runtime

USER nobody

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
