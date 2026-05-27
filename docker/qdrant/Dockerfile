# TD-582 image extension: bake the entrypoint shim into the qdrant image so
# the image filesystem (overlay-fs layers) owns the file. Avoids the Docker
# Desktop WSL2 single-file bind-mount tmpfs cache corruption class that
# fires on host reboot (failure manifests as runc "not a directory" mount
# errors against /run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/...).
#
# Reference: TECH-DEBT-582; replaces the prior bind-mount-based delivery.
FROM qdrant/qdrant:v1.16.3

COPY --chmod=755 entrypoint.sh /usr/local/bin/td582-entrypoint.sh
