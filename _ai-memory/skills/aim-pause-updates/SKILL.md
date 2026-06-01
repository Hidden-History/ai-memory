---
name: aim-pause-updates
description: "Toggle auto_update_enabled kill switch for automatic memory updates"
trigger: "/aim-pause-updates"
allowed-tools: Bash
---

Toggle the `AUTO_UPDATE_ENABLED` kill switch in the active `.env` file.
When paused: GitHub sync and freshness scans still run, but auto-corrections
and auto-re-captures are disabled.

## Usage

```bash
# Toggle current state
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/pause_updates.py"

# Enable updates
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/pause_updates.py" on

# Disable updates
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/pause_updates.py" off
```
