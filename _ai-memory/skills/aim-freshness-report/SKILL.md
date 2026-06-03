---
name: aim-freshness-report
description: "Scan code-patterns collection for stale memories by comparing against GitHub code blob data"
trigger: "/aim-freshness-report"
allowed-tools: Bash
---

## Canonical Execution

Always run the real script through `run-with-env.sh` so the skill uses the
installed ai-memory virtualenv and the standard local service defaults.

```bash
# Scan all projects
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" freshness_report.py

# Scan specific project
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" freshness_report.py my-project
```
