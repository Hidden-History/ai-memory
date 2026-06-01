---
name: aim-refresh
description: "Manually re-evaluate freshness for code-patterns memories"
trigger: "/aim-refresh"
allowed-tools: Bash
---

Manually re-evaluates freshness for code-patterns memories. Reuses the
freshness scan pipeline from SPEC-013 with optional scope filters.

## Canonical Execution

Always run the real script through `run-with-env.sh` so the skill uses the
installed ai-memory virtualenv and the standard local service defaults.

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
    "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/refresh.py"
```

## Examples

```bash
# Scan all code-patterns memories
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
    "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/refresh.py"

# Limit to a specific project group_id
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
    "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/refresh.py" my-project

# Topic filter (v2.1 — currently runs full scan with project filter)
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
    "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/refresh.py" --topic "authentication"
```

## Implementation

- Script: `scripts/memory/refresh.py`
- Interpreter: `run-with-env.sh` (imports `memory.*`, requires venv)
- Args: `[project]` (optional positional group_id filter), `--topic` (v2.1, no-op today)
- Output: tier table (Fresh / Aging / Stale / Expired / Unknown) + actionable count
