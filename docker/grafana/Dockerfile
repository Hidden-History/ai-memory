# TD-582 image extension: bake the Grafana entrypoint shim into the image.
# Same rationale as docker/qdrant/Dockerfile — eliminates the Docker Desktop
# WSL2 single-file bind-mount tmpfs cache corruption class on host reboot.
#
# The upstream grafana image runs as user 472. We temporarily switch to root
# to write into /usr/local/bin/ at build time, then restore the upstream
# USER directive so the container's runtime identity is unchanged. Matches
# Grafana's documented image-extension pattern.
#
# Reference: TECH-DEBT-582; mirrors docker/qdrant/Dockerfile.
FROM grafana/grafana:12.0.0

USER root
COPY --chmod=755 entrypoint.sh /usr/local/bin/td582-entrypoint.sh
USER 472
