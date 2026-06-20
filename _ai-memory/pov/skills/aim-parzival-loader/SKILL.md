---
name: aim-parzival-loader
description: Two-phase capped startup context loaders for Parzival (activation + session-start)
allowed-tools: Bash
---

## Load Policy

Two thin, deterministic loader scripts that emit Parzival's startup context as a
single consolidated, **capped** block per phase — replacing the scattered
per-file reads at activation and session-start. Caps follow the approved A2 cap
table (`oversight/tasks/task077-startup-governance/A2-CAP-TABLE-APPROVED.md`).
The full files always remain on disk at full size; the loaders emit capped
heads / recency slices / pointers, never destructive edits.

Caps are enforced by line / byte / entry counts only — **no tokenizer at
runtime**. Per-phase token budgets are asserted separately by
`tests/unit/test_parzival_loaders.py`.

## Phase 1 — Activation (`/pov:parzival`, Tier A)

Run once during activation (after the sanctum presence-check / self-heal):

```bash
python3 "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/pov/skills/aim-parzival-loader/activation_loader.py" "$(pwd)"
```

Emits, in the approved A2 order: `config.yaml` (full) → `project-status.md`
(head-capped to Contract 60 lines / 6 KB) → global constraints (full) → phase
constraints (full; phase from project-status) → `CREED.md` (full) →
`PERSONA.md` (`## Evolution Log` capped to the last 10 identity-shift rows) →
`BOND.md` First-Breath **marker-scan only** (not a load) → `WORKFLOW-MAP.md`
(full).

## Phase 2 — Session-start (`/pov:parzival-start`, Tier B + oversight)

```bash
# oversight summaries (step-01)
python3 ".../aim-parzival-loader/session_loader.py" "$(pwd)" --scope oversight
# sanctum Tier B, after the bootstrap Qdrant section (step-01b section 4)
python3 ".../aim-parzival-loader/session_loader.py" "$(pwd)" --scope sanctum
```

`--scope` honors the A2 interleave (oversight → bootstrap Qdrant → sanctum):
- `oversight` — `SESSION_WORK_INDEX` (full) + tracking active sections + bugs/TD
  `## Quick Stats` only.
- `sanctum` — `LORE.md` recency-weighted slice (structural sections + newest
  "Things Learned" lessons ≤ 25 KB + pointer) → `BOND.md` full (vital floor) →
  sanctum `MEMORY.md` full.
- `all` — oversight then sanctum (used by the budget / live-smoke tests).

This loader never reads a `SESSION_HANDOFF_*.md` file — the most recent handoff
comes from bootstrap L1; the file is read only on the existing CASE-A/CASE-B
fallback (step-01b).

## Implementation

- Scripts: `activation_loader.py`, `session_loader.py`, shared `loader_common.py`
- Two distinct `MEMORY.md` files — do **not** conflate: the sanctum
  `_ai-memory/sanctum/parzival/MEMORY.md` (Tier-B identity, loaded here) is NOT
  the Claude-Code auto-memory `~/.claude/projects/<slug>/memory/MEMORY.md`.
- Failure mode: missing files degrade gracefully (`(absent)` markers); startup
  never blocks on a missing sanctum/oversight file.
