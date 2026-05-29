# TD-583 image extension: bake the ClickHouse retention config into the image.
# Eliminates the Docker Desktop WSL2 single-file bind-mount tmpfs cache
# corruption class on host reboot (same root cause as TECH-DEBT-582 /
# docker/qdrant/Dockerfile — runc "not a directory" mount errors after reboot).
#
# Reference: TECH-DEBT-583; mirrors docker/qdrant/Dockerfile pattern.

FROM clickhouse/clickhouse-server:24

# BP-162 Pattern A (defensive — clickhouse base normally provides
# /etc/clickhouse-server/config.d/ at mode 0777, but explicit dir-mode
# assertion documents the requirement and protects against future base-image
# regression). See moby/buildkit#5943 and BP-162.
RUN mkdir -p /etc/clickhouse-server/config.d \
 && chmod 755 /etc/clickhouse-server/config.d

COPY --chmod=644 clickhouse-config.xml /etc/clickhouse-server/config.d/retention.xml

# BP-162 §7.1 Layer 1: build-time guardrail — fails image build if dir mode
# regresses below 755 (executable bit present).
RUN test "$(stat -c '%a' /etc/clickhouse-server/config.d)" -ge 755 \
 || (echo "FAIL: /etc/clickhouse-server/config.d below 0755 (BP-162 regression)" && exit 1)
