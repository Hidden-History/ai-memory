# TD-583 image extension: bake the ClickHouse retention config into the image.
# Eliminates the Docker Desktop WSL2 single-file bind-mount tmpfs cache
# corruption class on host reboot (same root cause as TECH-DEBT-582 /
# docker/qdrant/Dockerfile — runc "not a directory" mount errors after reboot).
#
# Reference: TECH-DEBT-583; mirrors docker/qdrant/Dockerfile pattern.
FROM clickhouse/clickhouse-server:24

COPY --chmod=644 clickhouse-config.xml /etc/clickhouse-server/config.d/retention.xml
