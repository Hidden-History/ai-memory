---
name: search-memory
description: Search ai-memory for relevant stored memories
allowed-tools: shell
---

Search ai-memory for relevant stored memories matching the user's query.

## Instructions

1. Invoke the search script with **no shell**: pass a discrete argv array — `$AI_MEMORY_INSTALL_DIR/.venv/bin/python`, then `$AI_MEMORY_INSTALL_DIR/src/memory/search.py`, then `--query`, then the user query string as its **own** token, then `--project`, then the current directory basename as its **own** token. Do not embed the query inside a single quoted shell string.
2. Present the ranked results clearly to the user.
