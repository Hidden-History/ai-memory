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

# BP-162 Pattern A: create config dirs with traversable mode BEFORE COPY --chmod,
# to avoid BuildKit's --chmod parent-dir propagation defect (moby/buildkit#5943
# — OPEN, maintainer-acknowledged). Without this, /etc/prometheus/ would
# inherit 0644 from the COPY below (= drw-r--r--, missing execute bit) and
# break runtime os.makedirs('/etc/prometheus/runtime', exist_ok=True) stat
# checks when the prometheus_runtime named volume is mounted at that path.
# See oversight/knowledge/best-practices/BP-162-docker-buildkit-copy-chmod-parent-dir-pattern-2026.md
RUN mkdir -p /etc/prometheus /scripts \
 && chmod 755 /etc/prometheus /scripts

COPY --chmod=644 web.yml /etc/prometheus/web.yml.template
COPY --chmod=644 prometheus.yml /etc/prometheus/prometheus.yml.template
COPY --chmod=755 gen-prometheus-config.py /scripts/gen-prometheus-config.py

# BP-162 §7.1 Layer 1: build-time guardrail — fails image build if dir mode
# regresses (defends against future --chmod additions that re-introduce the
# parent-dir propagation defect).
RUN stat -c '%a' /etc/prometheus | grep -q '^755$' \
 || (echo "FAIL: /etc/prometheus is not 0755 (BP-162 regression)" && exit 1)
RUN stat -c '%a' /scripts | grep -q '^755$' \
 || (echo "FAIL: /scripts is not 0755 (BP-162 regression)" && exit 1)
