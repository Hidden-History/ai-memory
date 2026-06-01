---
name: aim-purge
description: "Purge old memories from Qdrant collections with safety guards"
trigger: "/aim-purge"
allowed-tools: Bash
---

Purge old memories from Qdrant collections with safety guards.

Default (no `--confirm`): dry-run preview — shows what would be purged, no deletions.
`--confirm`: executes the purge. **Irreversible** — audit log written to `.audit/logs/purge-log.jsonl`.

## Canonical Execution

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" purge_collections.py \
    --older-than <duration> \
    [--collection <name>] \
    [--confirm]
```

## Parameters

- `--older-than` (required): duration string — `30d`, `2w`, `3m`, `1y`
- `--collection`: limit purge to one collection (default: all four)
- `--confirm`: execute the purge (absence = dry-run safety gate)

## Script

`scripts/memory/purge_collections.py`
