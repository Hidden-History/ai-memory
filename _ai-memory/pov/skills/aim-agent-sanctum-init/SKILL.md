---
name: aim-agent-sanctum-init
description: Initialize sanctum directory for an agent. Runs deterministic First Breath scaffolding — creates folder structure and writes template-substituted files.
allowed-tools: Bash, Read, Write, Glob
---

# aim-agent-sanctum-init — Agent Sanctum Initialization

Initialize the sanctum directory structure for an agent. Deterministic scaffolding only — no conversational awakening. For Parzival this runs automatically on first activation when any of the 8 required sanctum files are missing. For domain agents (future work) it runs when Parzival spawns a memory-bearing agent needing cross-session state.

## Steps

1. Determine target sanctum path: `{project-root}/_ai-memory/sanctum/{agent_id}/`

2. File-level idempotency: each sanctum file is created if missing, preserved if existing. The script never overwrites an existing file in the sanctum.

3. Invoke `scripts/init-sanctum.py {project-root} {skill-path}` where `{skill-path}` is this skill's directory (resolves to `_ai-memory/pov/skills/aim-agent-sanctum-init/`).

4. The script:
   - Reads config from `_ai-memory/core/config.yaml` and `_ai-memory/pov/config.yaml` — supplies `{user_name}`, `{communication_language}`, `{birth_date}`, `{project_root}`, `{sanctum_path}` substitutions
   - Creates sanctum dir + `capabilities/`, `sessions/`, `references/` subdirs
   - Copies templates from `assets/*-template.md` and substitutes variables → writes `{NAME}.md` in sanctum
   - Each TEMPLATE_FILES entry is checked individually. Existing files are preserved (file-level idempotency). Missing files are created from template with substitution variables filled.
   - Copies any reference files from `references/` into sanctum

5. Verify: after script returns 0, confirm all required sanctum files exist (for parzival: CREED.md, PERSONA.md, INDEX.md, BOND.md, LORE.md, MEMORY.md, CAPABILITIES.md, PULSE.md).

## Parameters

This skill is currently **parzival-only** (single-agent scaffold). The script accepts these positional arguments:

| Position | Description |
|---|---|
| `<project-root>` | Required. Path to the project where `_ai-memory/` lives. |
| `<skill-path>` | Required. Path to this skill bundle (where `assets/`, `scripts/` live). |

Multi-agent support (`agent_id` / `agent_type` / `tier` / `domain` parameters) is planned. See "Future Work" below.

## Idempotency

The script always runs through all TEMPLATE_FILES. Each file is checked individually — existing files are preserved, missing files are created.

## Integration Points

- Called automatically by: Parzival activation step 5 when any of the 8 required sanctum files are missing
- Called by: aim-agent-dispatch when spawning a memory-bearing domain agent
- Called manually: `python3 init-sanctum.py <project-root> <skill-path>` to re-scaffold (file-level idempotency: existing sanctum files preserved, missing files created)

## Future Work (not in Phase 1)

- Qdrant persistence layer for sanctum content (Phase 3 P3-01 open Q3)
- SubagentStart/SubagentStop hooks to auto-sync sanctum to vector store
- Agent registry discovery from CREED.md frontmatter
- Tier upgrades — file-level idempotency means tier upgrade is automatic: rerunning the script with new templates creates any missing files without modifying existing ones.
- Atomic scaffolding — wrap creation in try/except with partial cleanup on failure; currently all-or-nothing is aspirational.
- Multi-agent support: wire `--agent_id` CLI arg, per-agent template directory selection, agent_type-driven CREED/PERSONA seed selection (planned for v2.5.0+ when domain agents land)
