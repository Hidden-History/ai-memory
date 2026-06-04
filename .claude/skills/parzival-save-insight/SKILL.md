---
name: parzival-save-insight
description: "Save a Parzival insight or learning to Qdrant for cross-session memory"
allowed-tools: Bash
---

Save a Parzival insight or learning to Qdrant for cross-session retrieval.

## Canonical Execution

Always run the real script through `run-with-env.sh` so the skill uses the
installed ai-memory virtualenv and the standard local service defaults.

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" parzival_save_insight.py "PyYAML not in test deps caused CI failures"
```

Run one insight command per invocation.

When working from an `ai-memory` repo checkout, `./scripts/memory/run-with-env.sh ...`
is an equivalent contributor shortcut.

## Implementation

- Script: `scripts/memory/parzival_save_insight.py`
- Memory type: `agent_insight`
- Agent ID: `parzival`
- Failure mode: non-zero exit on save failure
