#!/usr/bin/env bash
# generate-manifest.sh — Generate SHA256 manifest of _ai-memory/ tree.
# Output: _ai-memory/MANIFEST.sha256 (JSON, path-relative, sorted by path).
#
# Excludes: sanctum/, __pycache__/, *.pyc, .sync-stamp, workspace-only allowlist.
# Workspace-only allowlist is HARDCODED here AND mirrored in sync-workspace.sh rsync excludes.
# Keep these two lists synchronized when adding new workspace-only paths.

set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="$SOURCE_REPO/_ai-memory/MANIFEST.sha256"

python3 - <<'PYEOF' "$SOURCE_REPO" > "$OUTPUT"
import hashlib, json, sys
from pathlib import Path

source_repo = Path(sys.argv[1])
root = source_repo / "_ai-memory"

EXCLUDE_DIRS = {"sanctum", "__pycache__", ".git"}
EXCLUDE_SUFFIX = {".pyc"}
EXCLUDE_NAMES = {".sync-stamp", "MANIFEST.sha256"}
# Workspace-only allowlist (paths NOT in source, but legitimately in workspace —
# do NOT include in manifest so sync does not push them out).
# Keep mirrored with sync-workspace.sh rsync --exclude list.
WORKSPACE_ONLY_ALLOWLIST = {
    "pov/knowledge/parzival-master-plan.md",
}

manifest = {}
for f in sorted(root.rglob("*")):
    if not f.is_file():
        continue
    rel_parts = f.relative_to(root).parts
    if any(part in EXCLUDE_DIRS for part in rel_parts):
        continue
    if f.suffix in EXCLUDE_SUFFIX:
        continue
    if f.name in EXCLUDE_NAMES:
        continue
    rel = "/".join(rel_parts)
    if rel in WORKSPACE_ONLY_ALLOWLIST:
        continue
    manifest[rel] = hashlib.sha256(f.read_bytes()).hexdigest()

print(json.dumps(manifest, indent=2, sort_keys=True))
PYEOF

echo "[generate-manifest] wrote $(wc -l < "$OUTPUT") lines to $OUTPUT"
