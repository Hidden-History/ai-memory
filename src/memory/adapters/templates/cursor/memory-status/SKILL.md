---
name: memory-status
description: Check ai-memory system status and collection stats
allowed-tools: Bash
---

Check the status of the ai-memory system including Qdrant health and collection statistics.

## Instructions

1. Invoke the status script with **no shell**: pass a discrete argv array — `$AI_MEMORY_INSTALL_DIR/.venv/bin/python`, then `$AI_MEMORY_INSTALL_DIR/src/memory/cli/status.py`. Do not embed the path inside a single quoted shell string.
2. Present the status output clearly to the user.
