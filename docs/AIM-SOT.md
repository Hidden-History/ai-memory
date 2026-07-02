# Source-of-Truth Subsystem (aim-sot)

The `aim-sot` skill tracks where the canonical truth lives for each part of **your own project** — which directory owns the authentication logic, which manifest is the API contract, which ADR governs the data model. It answers "where does X live, who owns it, and is it still accurate" for any agent working in your codebase.

The registry lives in **your own repository** as a committed `.sot/registry.yaml`. Each entry is a pointer-plus-provenance record; no source content is ever copied. The skill ships the schema, templates, and engine — no project-specific data is baked into the skill itself.

## How It Works

| Part | Artifact | Location |
|------|----------|----------|
| **Registry of record** | `.sot/registry.yaml` | Your repo (committed, diff-reviewable) |
| **Skill** | `aim-sot` (consult · detect-propose · verify) | `_ai-memory/skills/aim-sot/` |
| **Triggers (default-on)** | Claude session-start digest + `Stop` hook; Codex, Cursor, Gemini adapters | Auto-registered on install; opt out with `AI_MEMORY_SOT_HOOKS=off` — see [Automatic Drift Detection](#automatic-drift-detection) |
| **Per-install drift cache (5a)** | `~/.ai-memory/drift-state/sot_drift_{project_id}.json` | Runtime; never committed |
| **Derived memory cache (5b)** | `conventions` collection, `memory_type=sot_entry` | Qdrant; rebuildable |

## The Registry (`.sot/registry.yaml`)

The registry is fully human-authored and committed alongside your code. Each entry is a pointer-plus-provenance record for one boundary of your project.

### Boundary types

| `boundary_type` | When to use |
|-----------------|-------------|
| `path` | A directory scope (CODEOWNERS-style) |
| `component` | A named unit with a co-located manifest (e.g. `package.json`, `Cargo.toml`) |
| `concern` | A cross-cutting scope: an ADR, an API contract, a shared platform concern |

### Schema

**Core (6 required fields)**:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier for this entry |
| `kind` | enum | `service \| library \| application \| api \| data \| infrastructure \| decision \| documentation` |
| `boundary_type` | enum | `path \| component \| concern` |
| `sot_location` | string | Relative path, URL, or structured ref — never copied content |
| `owner` | string | Owner team or handle (e.g. `@platform-team`) |
| `description` | string | One-line summary of what this boundary is and does |

**Provenance (3 fields)**:

| Field | Type | Description |
|-------|------|-------------|
| `last_verified` | string | Date a *person* last re-confirmed this entry is accurate. Use a quoted date string, e.g. `"2024-01-15"`. **Never auto-bumped by the engine.** |
| `added_by` | string | Handle of who added this entry |
| `provenance_note` | string | Free-text note on how/why this entry was added |

**Lifecycle**:

| Field | Type | Values |
|-------|------|--------|
| `status` | enum | `proposed → active → superseded` |

**Optional pointer links**: `source_repo`, `docs_url`, `api_spec`, `ci_url`, `runbook_url`, `dashboard_url`, `adr_dir`, `links`.

**Operational**: `drift_check` (shell command used as a project-specific drift assertion); `schema_version` (file-level).

### Machine state is never in the registry

Content hashes, drift status, and machine-generated timestamps belong in the per-install drift cache (`~/.ai-memory/drift-state/`), not in the committed registry. The engine never writes auto-updating values into `.sot/registry.yaml` — doing so would churn your VCS history with machine noise.

The committed registry's `last_verified` field is the **human-confirmation date** — it changes only when a person re-confirms an entry is still accurate. The machine's drift state (how recently the file was checked, what hash was found) lives entirely in the 5a cache.

### Getting started

A starter template is available at `_ai-memory/skills/aim-sot/templates/registry.yaml.template`. Copy it to `.sot/registry.yaml` in your project, then run `detect-propose` to build an initial candidate set:

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" \
  run
```

## Skill Modes

### consult — Orient before acting

Read-only query over your committed registry. Results are served from the derived memory cache (5b) only when every cached row's stamped `registry_sha` matches the committed registry's SHA **and** the row count matches the committed entry count — otherwise the engine falls back to the committed file directly. This ensures consult never returns stale, partial, or cross-state entries. Useful for agents that need to locate a component's owner or canonical location before editing it.

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_consult.py" \
  <subcommand> [--json] [--registry PATH]
```

Subcommands: `list` (all entries) · `get <id>` (full entry) · `where <id>` (sot_location) · `who <id>` (owner) · `drift <id>` (drift_check).

### detect-propose — Surface drift and new candidates

Hybrid auto-discover → propose mode. The engine scans your project for candidate components (manifest files → `component`; top-level directories → `path`; ADR directories → `concern`), computes actual state (SHA-256 of each `sot_location` file), and compares to the registry.

On drift or new candidates, it emits a **proposed patch**. It never writes the registry directly — see [The Propose-Only Guarantee](#the-propose-only-guarantee).

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" \
  run [--json] [--registry PATH] [--limit N] [--all]
```

**Flags (`run`)**:

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | 20 | Cap new-candidate proposals per run |
| `--all` | off | Disable cap — surface all candidates |
| `--json` | off | Machine-readable JSON output |
| `--registry PATH` | (git root walk) | Override registry path |

**Drift types detected**:

| Drift type | What it means |
|------------|---------------|
| `location` | `sot_location` path no longer resolves |
| `staleness_temporal` | `last_verified` older than the entry's volatility threshold (30 / 90 / 180 days) |
| `staleness_hash` | SHA-256 of the file at `sot_location` changed since the last baseline |
| `declaration_reality` | File hash changed; description/tags may no longer match — triggers mandatory K1 re-confirmation |

Content-hash drift (`staleness_hash` / `declaration_reality`) applies to **file** `sot_location`s only. Directory boundaries participate in location and temporal drift; hash-based drift checks are no-ops for directory entries.

**Semantic fields are never auto-filled.** Auto-discovery infers structural fields (`boundary_type`, `sot_location`, `confidence`, `inferred_from`); the human fills in meaning (`owner`, `description`, `provenance_note`).

**Baseline behavior:** when drift is detected, the engine holds the baseline SHA — it does not advance `last_verified_sha` — so the proposal re-fires on subsequent runs until a human confirms the change (by updating `last_verified` in the registry). The baseline advances to clean only when the entry is genuinely clean, or when the registry's `last_verified` is newer than the cached baseline (human re-confirmation signal). On a **cold start** (no cache or first run on this machine), `drift_status` is `unverified` — not `clean`.

**Proposal output**: each proposal includes `drift_type`, `root_cause`, `impact`, and `recommended_action`. A `declaration_reality` entry with `"k1_trigger": true` requires human re-confirmation before the description is considered valid.

**Rebuilding the 5b memory cache** (after an approved apply):

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" \
  reindex [--registry PATH]
```

### verify — Gate before applying

16-check gate (Schema · Referential · Completeness · Content) that runs before any proposal is applied. It produces a PASS / CONDITIONAL / FAIL verdict; the human is the approval gate. The verify tool never auto-applies.

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" \
  run [--json] [--registry PATH] [--proposal PATH] \
  [--check-urls] [--exec-drift-checks]
```

**Gate a detect-propose output before applying it**:

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" \
  run --proposal /path/to/proposal.json --json
```

**Verdicts**:

| Verdict | Condition | Apply-eligible? |
|---------|-----------|-----------------|
| `PASS` | 0 failures, 0 warnings | Yes |
| `CONDITIONAL` | 0 failures, ≥1 warning | Human review required — no auto-apply |
| `FAIL` | ≥1 failure | Blocked — fix and re-run |

The verdict report distinguishes **ran-pass** (check executed and found no issue), **no-op** (check is inert for this registry configuration), and **skipped-no-baseline** (check could not run because no baseline exists). All three are reported separately; no-op and skipped checks are not counted as passed.

**Check categories**:

| Category | Checks | Notes |
|----------|--------|-------|
| Schema / Structural | S1–S4 | Required fields, ID uniqueness, YAML parse, controlled vocabulary |
| Referential Integrity | R1–R4 | `sot_location` resolves (R1); URL resolution (R2, `--check-urls` only); CODEOWNERS owner (R4, CONDITIONAL) |
| Completeness | C1–C4 | Unregistered candidates (C1, CONDITIONAL); missing path (C3) |
| Content Correctness | K1–K4 | Hash changed (K1, CONDITIONAL); date plausibility (K2); drift_check executable (K3); location collision (K4) |

Key content-correctness notes:
- **K1** fires when the file at `sot_location` has a new hash since the baseline and reports CONDITIONAL — the description may need updating. When no baseline exists (cold start or cache loss), K1 also reports CONDITIONAL rather than a silent pass.
- **K4** — no two entries (proposed or committed) may claim the same `sot_location`.
- **R2** and **K3** are disabled by default for offline safety; enable with `--check-urls` and `--exec-drift-checks`.

CI and pre-commit integration with the verify gate is opt-in only — the tool never auto-installs hooks or CI steps into your repository.

## The Propose-Only Guarantee

**The tool never writes `.sot/registry.yaml`.** Every registry change goes through:

1. **detect-propose** emits a proposed patch
2. **verify** gates it (PASS, or human-reviewed CONDITIONAL)
3. **The human applies the change** — manually, via a PR, or via a pre-commit hook they opt into

This is an unconditional structural guarantee: the engine, the Stop hook, and all CLI adapters are read-and-propose only. No configuration option causes them to write the registry. The propose-only path also means the trigger is structurally loop-free — a proposal cannot trigger another proposal in the same session.

All trigger paths are **fail-open**: any error is logged to stderr and the adapter exits 0, so a transient failure never blocks a Claude Code (or Codex/Cursor/Gemini) session.

## Automatic Drift Detection

The per-session-start SOT digest hook and the end-of-session drift hook are **registered automatically on install** for every configured IDE (Claude Code, Codex, Cursor, Gemini). To opt out, set `AI_MEMORY_SOT_HOOKS=off` (case-insensitive; only `off` disables — `false`/`0`/`no` leave hooks on) before running `install.sh`. Note: `AI_MEMORY_SOT_HOOKS=off` prevents registration on install but does not remove hooks already written by a prior install; to disable an existing install, remove the SOT hook entries from the relevant config file manually.

The engine also runs standalone with no hook required — use this as an alternative, or schedule it as a cron job:

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" \
  run
```

### Claude Code

The installer registers two SOT hooks in your project's `.claude/settings.json`:

**Session-start digest** (under `hooks.SessionStart`, matcher `resume|compact`): invokes `sot_digest_session_start.py` and injects a compact SOT registry digest as ambient context on session resume or compact.

**Stop drift hook** (under `hooks.Stop`): invokes `sot_drift_stop.py` at every session end and prints a one-line drift summary to stderr when drift or new candidates are detected. The installed entry:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_drift_stop.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_drift_stop.py\" || true",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

### Codex — Stop hook

The installer registers a session-start digest hook and a Stop drift hook in `.codex/hooks.json`. The Stop entry:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_drift.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_drift.py\" || true",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

### Cursor — stop hook

The installer registers a session-start digest hook and a stop drift hook in `.cursor/hooks.json`. The stop entry:

```json
{
  "version": 1,
  "hooks": {
    "stop": [
      {
        "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_drift.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_drift.py\" || true",
        "timeout": 30
      }
    ]
  }
}
```

### Gemini CLI — AfterAgent hook

The installer registers a session-start digest hook and an AfterAgent drift hook in `.gemini/settings.json`. The AfterAgent entry:

```json
{
  "hooks": {
    "AfterAgent": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_drift.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_drift.py\" || true",
            "timeout": 60000
          }
        ]
      }
    ]
  }
}
```

### Tuning the drift-scan budgets

The default-on Stop-hook detect pass runs under a subprocess time cap, so the engine
bounds each scan and **truncates gracefully** (a visible warning, never a silent
under-report) rather than overrunning. All budgets are optional environment
overrides; the defaults suit most projects. See also `docker/.env.example`.

| Variable | Default | Bounds |
|----------|---------|--------|
| `AI_MEMORY_SOT_DIGEST_MAX_SECONDS` | `18.0` | Per-boundary tree-digest wall-time budget (seconds). A boundary that exceeds it yields a partial, truncated digest — carried over, never baselined (see [`references/drift-and-shadow-git.md`](../_ai-memory/skills/aim-sot/references/drift-and-shadow-git.md)). |
| `AI_MEMORY_SOT_DIGEST_MAX_FILES` | `20000` | Per-boundary tree-digest file-count budget. |
| `AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS` | `6.0` | Auto-discovery walk wall-time budget (seconds). |
| `AI_MEMORY_SOT_DISCOVERY_MAX_DIRS` | `5000` | Auto-discovery walk max directories. |

Discovery is split hot/cold (BP-047): the drift loop runs every session; the discovery
walk runs only when its **R1 cadence** gate is due (or forced with `--discover`). The
cadence is tunable:

| Variable | Default | Meaning |
|----------|---------|---------|
| `AI_MEMORY_SOT_DISCOVERY_TTL_SECONDS` | `86400` | Re-run discovery after this age (24 h). |
| `AI_MEMORY_SOT_DISCOVERY_SESSION_INTERVAL` | `20` | ...or after this many sessions, whichever comes first. |
| `AI_MEMORY_SOT_DISCOVERY_NUDGE_SESSIONS` | `10` | Emit a non-blocking nudge after this many sessions with no discovery run. |

Raising the budgets helps a manual `aim-sot detect-propose run` finish on a very large
tree, but can push the default-on Stop hook past its subprocess cap. The per-file hash
cache warms across sessions, so a large boundary that truncated cold typically completes
on a later warm run without any tuning.

## Runtime Caches

### 5a — Per-install drift cache

**Location**: `~/.ai-memory/drift-state/sot_drift_{project_id}.json`

Holds per-machine drift state for each registry entry: `last_verified_at`, `last_verified_sha` (SHA-256 first 8 characters), and `drift_status` (`clean | drifted | missing | stale | unverified`). Written atomically with advisory locking. **Never committed** — machine-local only.

On a **cold start** (first run on a machine, or if the cache file is deleted), `drift_status` is `unverified` for every entry. The engine builds a genuine baseline only after computing and storing a hash. Treat `unverified` as "not yet checked on this machine," not "clean."

The cache is keyed by `project_id` (resolved from the `AI_MEMORY_PROJECT_ID` environment variable, or auto-detected from the project directory). If the cache is lost or the project moves to a new machine, the engine rebuilds it on the next run.

### 5b — Derived memory cache

**Location**: Qdrant `conventions` collection, `memory_type=sot_entry`, `group_id=project_id`

After each approved apply, the engine reindexes the committed registry into this cache so `aim-sot consult` (and any agent using `aim-search`) can retrieve SOT entries via semantic search.

**Indexed fields**: `id`, `description`, `sot_location`, `owner`, `added_by`, `provenance_note`, `status`.

**Owner fidelity**: `owner` and `added_by` handles are stored exactly as authored in the registry. The shared security scanner's HANDLE-pattern filter is exempted for SOT entries so that ownership handles (e.g. `@platform-team`) are preserved faithfully — only PII and secrets screening applies.

**Not indexed here**: machine drift state (`last_verified_at`, `last_verified_sha`, `drift_status`) — that lives in 5a.

The cache is **deterministically rebuildable** at any time. Deleting the Qdrant entries loses no information; the committed registry is the source of truth.

```bash
# Rebuild the 5b cache from the committed registry:
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" \
  reindex [--registry PATH]
```

## Troubleshooting

### No registry found

Create `.sot/registry.yaml` in your project root using the starter template at
`_ai-memory/skills/aim-sot/templates/registry.yaml.template`, then run `detect-propose run`
to build the initial drift baseline.

### All entries show `drift_status: unverified`

Expected on the first run on a new machine. Run `detect-propose run` once to compute and store a baseline; subsequent runs will report actual drift status.

### Hook fires but produces no output

All adapters fail-open: errors go to stderr and the process exits 0. Run `detect-propose run` manually to see the engine output directly, or check the Claude Code hook log for stderr.

### 5b cache is stale after applying a proposal

Run `detect-propose reindex` to rebuild the derived memory cache from the committed registry.

### `CONDITIONAL` verdict from K1 after a clean baseline

K1 fires whenever the file hash changes since the last baseline — it is a deterministic trigger, not a semantic judge. A CONDITIONAL verdict from K1 means a human needs to review whether the entry's `description` still accurately describes the changed artifact. Update `last_verified` in the registry after re-confirming the entry.
