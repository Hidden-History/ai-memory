# TD-583 image extension: bake prometheus-init config templates and generation
# script into the image. Eliminates the Docker Desktop WSL2 single-file
# bind-mount tmpfs cache corruption class on host reboot (same root cause as
# TECH-DEBT-582 / docker/qdrant/Dockerfile — tmpfs-backed bind-mount cache
# becomes inconsistent across reboots, causing container start failures).
#
# The init container uses python:3.12-alpine to run gen-prometheus-config.py,
# which generates the runtime prometheus.yml and web.yml from these templates
# into the prometheus_runtime named volume. Image-bake makes delivery
# reboot-stable; no tmpfs cache; no host path to corrupt.
#
# Reference: TECH-DEBT-583; mirrors docker/qdrant/Dockerfile pattern.
FROM python:3.12-alpine

COPY --chmod=644 web.yml /etc/prometheus/web.yml.template
COPY --chmod=644 prometheus.yml /etc/prometheus/prometheus.yml.template
COPY --chmod=755 gen-prometheus-config.py /scripts/gen-prometheus-config.py
