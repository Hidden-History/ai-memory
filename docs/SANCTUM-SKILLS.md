# Sanctum Skills — Operator Guide

Per-agent sanctum directories hold an agent's persistent identity, memory, and behavioral files across sessions. Three skills govern the full lifecycle: **`aim-agent-sanctum-init`** scaffolds the directory on first activation, **`aim-content-drift`** detects when scaffolded files drift from evolving reference templates, and **`aim-lore-hygiene`** keeps the always-injected memory files under their size cap.

---

## Table of Contents

- [Sanctum Directory Layout](#sanctum-directory-layout)
- [aim-agent-sanctum-init](#aim-agent-sanctum-init)
- [aim-lore-hygiene](#aim-lore-hygiene)
- [Skill Lifecycle — How the Three Relate](#skill-lifecycle--how-the-three-relate)

---

## Sanctum Directory Layout

Each agent's sanctum lives at:

```
_ai-memory/sanctum/<agent_id>/
```

On initialization, the scaffold creates the root directory plus three subdirectories:

```
_ai-memory/sanctum/<agent_id>/
├── CREED.md           # Agent identity: role, non-negotiable constraints, core principles
├── PERSONA.md         # Communication style, tone, and behavioral personality
├── INDEX.md           # Navigation index: what each sanctum file contains
├── BOND.md            # Operator relationship: working agreements and mutual expectations
├── LORE.md            # Accumulated project knowledge (always-injected; ~200-line cap)
├── MEMORY.md          # Cross-session memory: key decisions and learned patterns (always-injected; ~200-line cap)
├── CAPABILITIES.md    # Skill and tool inventory
├── PULSE.md           # Session rhythm: how and when to check in with the operator
├── capabilities/      # Extended capability detail (overflow from CAPABILITIES.md)
├── sessions/          # Per-session summary archives
└── references/        # Stable reference files copied in during scaffold (e.g. caps.md, decision-rule.md)
```

The eight root files (CREED, PERSONA, INDEX, BOND, LORE, MEMORY, CAPABILITIES, PULSE) are the required sanctum files. All eight must be present for an agent to be considered fully initialized.

---

## aim-agent-sanctum-init

**Purpose:** Deterministic First Breath scaffolding — creates the sanctum folder structure and writes template-substituted files for any missing files.

### When it runs

`aim-agent-sanctum-init` runs automatically during **Parzival activation step 5** whenever any of the eight required sanctum files are absent. It also runs when `aim-agent-dispatch` spawns a memory-bearing domain agent that needs cross-session state.

It can be invoked manually to re-scaffold:

```bash
python3 scripts/init-sanctum.py <project-root> <skill-path>
```

where `<skill-path>` resolves to `_ai-memory/pov/skills/aim-agent-sanctum-init/`.

### File-level idempotency

The script iterates through every entry in `TEMPLATE_FILES` and checks each file individually:

- **File is missing** → create it from the template with substitution variables filled in.
- **File exists** → preserve it exactly; no overwrite, no merge, no modification.

This means re-running the script after partial initialization (e.g. after a failed First Breath) is always safe. It also means a tier upgrade — when new templates are added — automatically creates the new files without touching any existing ones.

### What the script scaffolds

The script reads configuration from two sources:

| Config file | Variables supplied |
|---|---|
| `_ai-memory/core/config.yaml` | `{user_name}`, `{communication_language}`, `{birth_date}` |
| `_ai-memory/pov/config.yaml` | `{project_root}`, `{sanctum_path}` |

Templates live in the skill bundle under `assets/*-template.md`. Each template is substituted and written as `<NAME>.md` in the sanctum root. The script then copies any static reference files from the skill's `references/` directory into the sanctum's `references/` subdirectory.

After the script exits 0, all eight required files are confirmed present.

### Current scope

`aim-agent-sanctum-init` is currently **Parzival-only** (single-agent scaffold). Multi-agent support (`--agent_id`, per-agent template selection, agent-type-driven seed content) is planned for a future release (v2.8.3+) when domain agents land.

---

## aim-lore-hygiene

**Purpose:** Compact always-injected sanctum files (LORE.md, MEMORY.md) under the BP-159 ~200-line cap. This is **file-content compaction only** — it has no interaction with Qdrant. Qdrant point purging by age is handled by `aim-purge`, a separate domain (PLAN-028 P0-3).

### When to run

| Trigger | Threshold |
|---|---|
| File size check | A sanctum file crosses ~80% of its cap — 160 of 200 lines |
| Scheduled hygiene pass | Session-stop hook or cron |
| Operator request | Operator asks to prune or compact lore, or flags a stale or wrong entry |

### Two-phase operation

The script never mutates by default. Always run the dry-run first:

**Phase 1 — Dry-run audit (default, read-only):**

```bash
python3 scripts/lore_hygiene.py <sanctum-path>
```

Reports per file: line count, percentage of cap, and the proposed prune / archive / dedup actions with a projected post-compaction line count. This is the verifiable intermediate output — review it before applying.

**Phase 2 — Apply (only after reviewing the plan):**

```bash
python3 scripts/lore_hygiene.py <sanctum-path> --apply
```

Each mutated file receives a timestamped `.bak` sidecar before any write. Archived entries move to `references/lore-archive/<FILE>.archive.md` with a one-line pointer left in the hot file. Pass `--qdrant --group-id <project>` to also push archived entries to the Qdrant cold tier (best-effort, opt-in).

A second `--apply` on an already-clean file is a no-op.

### What gets compacted vs archived vs kept

The script is **marker-driven** — it never guesses an entry is low-utility. Entries must be explicitly tagged:

| Action | Markers |
|---|---|
| **Prune** (delete) | `[superseded]`, `[contradicted]`, `[wrong]`, `[obsolete]`, `[prune]`, `[expired:YYYY-MM-DD]` (past date), or full-entry strikethrough (`~~…~~` spanning all content) |
| **Archive** (cold tier + one-line pointer) | `[stale]`, `[archive]` |
| **Dedup** (collapse to first) | Exact-duplicate entries within the same `## section` |
| **Keep** | Everything else |

**Markers must be in the leading position** — immediately after the bullet or number prefix (`- [superseded] …`) or in the first cell of a table row (`| [superseded] row | … |`). A marker only mentioned in prose or at the end of a line is ignored and the entry is kept. This single, unambiguous convention prevents accidental pruning of explanatory text that references marker names.

Tag entries during a Pulse, or when the operator says "that's not right anymore", so the next hygiene pass acts on them safely.

### Structure-aware: what the script never touches

The script passes these constructs through byte-for-byte without classifying, deduplicating, splitting, or rewriting them:

| Construct | Rule |
|---|---|
| **Code fences** | The entire block (opening delimiter through closing delimiter, including the info string) is one opaque unit. A marker token inside a fence is example text, never an entry. |
| **Table structure** | The header row and `\|---\|` separator are structural — never classified, so the separator is never orphaned. Only content rows below them are classified. For archived table content rows, the row is dropped in place (the table stays well-formed) with no inline pointer injected into the table body. |
| **Thematic breaks** | `---`, `***`, `___` and similar delimiters — structural, never deduped. |
| **Ambiguous constructs** | Blockquotes, indented code, raw HTML, and anything not confidently structural-or-content — kept opaque. The posture is keep-when-uncertain: because the skill mutates the operator's own memory, when it cannot confidently classify a block it preserves it intact. |

### Line cap and `--cap` override

LORE.md and MEMORY.md each carry a cap of ~200 lines. When scanning a sanctum directory the script uses each file's own cap. Passing `--cap N` overrides every file in the directory with a single value — useful when auditing a project-root `CLAUDE.md` at a different cap (e.g. `--cap 300`). `--cap` must be a positive integer.

---

## Skill Lifecycle — How the Three Relate

The three skills cover distinct phases of the sanctum lifecycle without overlap:

```
First Breath
    │
    ▼
aim-agent-sanctum-init
    Scaffolds the 8 required files from reference templates.
    File-level idempotency: missing → create, existing → preserve.
    │
    │  (templates evolve over time)
    ▼
aim-content-drift
    Detects when an operator's already-scaffolded files have drifted
    from updated reference templates. Surfaces recommended add/remove
    with rationale — never a silent overwrite, never auto-apply.
    Operator reviews recommendations and applies manually.
    │
    │  (LORE.md / MEMORY.md grow through normal session use)
    ▼
aim-lore-hygiene
    Compacts LORE.md and MEMORY.md under the ~200-line cap.
    Marker-driven: prunes superseded entries, archives stale ones,
    deduplicates exact copies within sections.
    FILE-CONTENT only — has no interaction with Qdrant.
    (Qdrant point purging by age = aim-purge, a separate domain.)
```

In practice:

1. **First Breath** → `aim-agent-sanctum-init` runs automatically when any of the 8 files are missing and scaffolds everything from templates in one deterministic pass.
2. **Templates evolve** → `aim-content-drift` runs on session-start or on demand to compare the operator's files against the latest reference templates and surface divergences. The operator decides which recommendations to apply.
3. **Files grow** → `aim-lore-hygiene` runs when a file approaches 160 lines (80% of cap), compacting it back under the limit so always-injected context stays focused.

The skills do not call each other — each is invoked independently by Parzival or by the operator. `aim-purge` is an entirely separate skill in a different domain (Qdrant vector store maintenance) and shares no overlap with any of the three above.
