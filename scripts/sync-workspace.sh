#!/usr/bin/env bash
# sync-workspace.sh — Resync workspace _ai-memory/ from source _ai-memory/.
# Idempotent: safe to run repeatedly. Source → workspace only (never deletes
# workspace files). Sanctum content preserved (cp --no-clobber for scaffold).
#
# Usage:
#   sync-workspace.sh [--check-only]
#     --check-only    Exit 0 if in-sync, 1 if drift detected, no writes.
#
# Env overrides:
#   WORKSPACE_DIR       Override workspace root (default: /mnt/e/projects/dev-ai-memory/_ai-memory)
#   SYNC_DRY_RUN=1      Print rsync actions without applying

set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$SOURCE_REPO/_ai-memory/MANIFEST.sha256"
WORKSPACE_DIR="${WORKSPACE_DIR:-/mnt/e/projects/dev-ai-memory/_ai-memory}"
STAMP="$WORKSPACE_DIR/.sync-stamp"

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then CHECK_ONLY=1; fi

if [[ ! -f "$MANIFEST" ]]; then
    echo "[sync-workspace] ERROR: manifest missing — run scripts/generate-manifest.sh first" >&2
    exit 2
fi
if [[ ! -d "$WORKSPACE_DIR" ]]; then
    echo "[sync-workspace] ERROR: workspace dir not found: $WORKSPACE_DIR" >&2
    exit 2
fi

# Drift check via manifest comparison
STALE_PATHS=$(python3 - <<'PYEOF' "$MANIFEST" "$WORKSPACE_DIR"
import hashlib, json, sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
workspace = Path(sys.argv[2])
stale = []
for rel, want in manifest.items():
    target = workspace / rel
    if not target.exists():
        stale.append(rel)
        continue
    got = hashlib.sha256(target.read_bytes()).hexdigest()
    if got != want:
        stale.append(rel)
for s in stale:
    print(s)
PYEOF
)

if [[ -z "$STALE_PATHS" ]]; then
    echo "[sync-workspace] workspace in sync"
    [[ "$CHECK_ONLY" -eq 1 ]] && exit 0
else
    if [[ "$CHECK_ONLY" -eq 1 ]]; then
        echo "[sync-workspace] DRIFT DETECTED ($(wc -l <<<"$STALE_PATHS") paths):" >&2
        echo "$STALE_PATHS" | head -20 >&2
        exit 1
    fi
    echo "[sync-workspace] drift detected — $(wc -l <<<"$STALE_PATHS") paths; resyncing..."
fi

# Resync source → workspace.
# --checksum required for WSL2 9P-mounted /mnt/e (mtime unreliable, BP-161 §6 risk 1).
# Excludes mirror generate-manifest.sh's WORKSPACE_ONLY_ALLOWLIST + EXCLUDE_DIRS.
RSYNC_ARGS=(
    -a --checksum
    --exclude='sanctum/'
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='.sync-stamp'
    --exclude='MANIFEST.sha256'
    --exclude='pov/knowledge/parzival-master-plan.md'
)
[[ "${SYNC_DRY_RUN:-0}" -eq 1 ]] && RSYNC_ARGS+=(--dry-run -v)

rsync "${RSYNC_ARGS[@]}" "$SOURCE_REPO/_ai-memory/" "$WORKSPACE_DIR/"

# Scaffold sanctum/ from source if missing (never overwrite existing files)
if [[ -d "$SOURCE_REPO/_ai-memory/sanctum" ]]; then
    mkdir -p "$WORKSPACE_DIR/sanctum"
    rsync -a --ignore-existing "$SOURCE_REPO/_ai-memory/sanctum/" "$WORKSPACE_DIR/sanctum/"
fi

# Write .sync-stamp with current source HEAD
SOURCE_HEAD="$(git -C "$SOURCE_REPO" rev-parse HEAD)"
echo "$SOURCE_HEAD" > "$STAMP"

echo "[sync-workspace] workspace synced to ${SOURCE_HEAD:0:8}"
