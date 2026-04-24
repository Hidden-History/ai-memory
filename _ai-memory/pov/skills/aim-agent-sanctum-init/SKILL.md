---
name: aim-agent-sanctum-init
description: Initialize sanctum directory for an agent. Runs deterministic First Breath scaffolding — creates folder structure and writes template-substituted files.
allowed-tools: Bash, Read, Write, Glob
---

# aim-agent-sanctum-init — Agent Sanctum Initialization

Initialize the sanctum directory structure for an agent. Deterministic scaffolding only — no conversational awakening. For Parzival this runs automatically on first activation when `sanctum/parzival/CREED.md` is absent. For domain agents it runs when Parzival spawns a memory-bearing agent needing cross-session state.

## Steps

1. Determine target sanctum path: `{project-root}/_ai-memory/sanctum/{agent_id}/`

2. Check idempotency: if sanctum dir already exists and contains CREED.md, exit cleanly without touching anything. "This agent has already been born."

3. Invoke `scripts/init-sanctum.py {project-root} {skill-path}` where `{skill-path}` is this skill's directory (resolves to `_ai-memory/pov/skills/aim-agent-sanctum-init/`).

4. The script:
   - Reads config from `_ai-memory/core/config.yaml` and `_ai-memory/pov/config.yaml` — supplies `{user_name}`, `{communication_language}`, `{birth_date}`, `{project_root}`, `{sanctum_path}` substitutions
   - Creates sanctum dir + `capabilities/`, `sessions/`, `references/` subdirs
   - Copies templates from `assets/*-template.md` and substitutes variables → writes `{NAME}.md` in sanctum
   - Skips CREED.md if already present (allows pre-filled Parzival CREED to survive)
   - Copies any reference files from `references/` into sanctum
   - Auto-generates CAPABILITIES.md from reference frontmatter — SKIPS if already exists (allows pre-filled CAPABILITIES)

5. Verify: after script returns 0, confirm sanctum/parzival/CREED.md loads without error.

## Parameters

| Name | Required | Default | Description |
|---|---|---|---|
| `agent_id` | yes | — | Target agent's sanctum dir name (e.g., `parzival`) |
| `agent_type` | yes | — | `parzival` or `domain` |
| `tier` | no | 3 | `1` (minimal), `2` (+capabilities), `3` (full — Parzival default) (reserved for future tier-upgrade support; currently not read by script) |
| `domain` | conditional | — | Required when agent_type=domain — used for persona seeding |

## Idempotency

If `sanctum/{agent_id}/CREED.md` exists, the script exits cleanly (exit 0) without modifying any files.

## Integration Points

- Called automatically by: Parzival activation step 5 when `sanctum/parzival/CREED.md` is absent
- Called by: aim-agent-dispatch when spawning a memory-bearing domain agent
- Called manually: `/aim-agent-sanctum-init --agent_id parzival` to re-scaffold (will no-op if already initialized)

## Future Work (not in Phase 1)

- Qdrant persistence layer for sanctum content (Phase 3 P3-01 open Q3)
- SubagentStart/SubagentStop hooks to auto-sync sanctum to vector store
- Agent registry discovery from CREED.md frontmatter
- Tier upgrades — planned: when dir exists but tier is lower than requested, add missing files without modifying existing ones; currently the script exits on CREED.md-present regardless of tier.
- Atomic scaffolding — wrap creation in try/except with partial cleanup on failure; currently all-or-nothing is aspirational.
