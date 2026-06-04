---
name: parzival-save-handoff
description: "Save Parzival session handoff document to Qdrant for cross-session memory"
allowed-tools: Bash
---

Save a Parzival session handoff to Qdrant for cross-session retrieval.

## Canonical Execution

Always run the real script through `run-with-env.sh` so the skill uses the
installed ai-memory virtualenv and the standard local service defaults.

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" parzival_save_handoff.py --file oversight/session-logs/SESSION_HANDOFF_2026-02-16_PM54.md
```

Alternative input form:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" parzival_save_handoff.py "PM #54: Phase 1d scoping complete..."
```

When working from an `ai-memory` repo checkout, `./scripts/memory/run-with-env.sh ...`
is an equivalent contributor shortcut.

## Implementation

- Script: `scripts/memory/parzival_save_handoff.py`
- Memory type: `agent_handoff`
- Agent ID: `parzival`
- Failure mode: warn and continue because the handoff file is the primary record
