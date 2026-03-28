---
name: save-memory
description: Manually save current session context to ai-memory
allowed-tools: Bash
---

Manually trigger a save of the current session context to ai-memory.

## Instructions

1. Invoke the manual save script with **no shell**: pass a discrete argv array — `$AI_MEMORY_INSTALL_DIR/.venv/bin/python`, then `$AI_MEMORY_INSTALL_DIR/adapters/claude/manual_save_memory.py`. Do not embed the path inside a single quoted shell string.
2. Confirm to the user that the save was triggered.
