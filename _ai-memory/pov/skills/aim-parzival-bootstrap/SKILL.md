---
name: aim-parzival-bootstrap
description: Load Parzival cross-session memory from Qdrant
allowed-tools: Bash
---

## Load Policy

This skill is invoked **only on demand** from `[ST]` Session Start workflow step-01b. It does NOT auto-load at activation.

`parzival.md` activation step 4 verifies the **presence** of the core skills (aim-parzival-bootstrap, aim-parzival-constraints, aim-parzival-loader) in `{skills_path}` without reading their content. Per `parzival.md <rules> r6` ("Load files ONLY when executing user-chosen workflow"), skill content is read only when the menu command that uses the skill is invoked.

# Parzival Bootstrap — Cross-Session Memory

Load cross-session context from previous Parzival sessions stored in Qdrant. This replaces the automatic startup injection with an on-demand skill invocation.

## Output layers (Qdrant only)

The script retrieves three layers from Qdrant and emits each as a markdown section:

- **L1 `### Last Handoff`** — most recent agent handoff (deterministic, agent_id=parzival)
- **L2 `### Recent Decisions`** — recent decisions and agent memories (deterministic)
- **L3 `### Insights`** — recent agent insights (deterministic, agent_id=parzival)

Sanctum Tier B files (LORE.md, BOND.md) are **not** loaded here — they load in step-01b
section 4 (Tier B), after the Qdrant gate completes.

## Steps

1. Run the bootstrap script with the installed ai-memory virtualenv to retrieve cross-session context:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/pov/skills/aim-parzival-bootstrap/bootstrap.py"
```

2. Include the script output in your current context as cross-session memory from previous Parzival sessions.

3. If the script reports Qdrant unavailable or an error, note this and continue with file-based context only (MEMORY.md, oversight/ files).

## Implementation

- Script: `_ai-memory/pov/skills/aim-parzival-bootstrap/bootstrap.py`
- Project scope: resolved through the shared `resolve_project_id` (env-first → cwd/git → fail-loud), the same helper the write paths use, so read and write never disagree (BUG-314)
- Failure mode: print a friendly notice and continue with file-based context (the bootstrap is best-effort; files are the primary record)
