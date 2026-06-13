---
name: aim-sot
description: Track the source-of-truth for each part of the user's own project — registry schema, templates, and engine (consult / detect-propose / verify).
allowed-tools: Bash, Read
---

# aim-sot — Source-of-Truth Subsystem

Manages a user-committed `.sot/registry.yaml` that declares where the canonical truth lives for each boundary of the user's project. Every entry is a pointer + provenance record — no copied source content ever.

## Overview

The registry lives in **the user's own repository** at `.sot/registry.yaml`, committed alongside code and diff-reviewable by the team. The skill ships the schema, templates, and engine. No project-specific data is baked into the skill.

## Modes

Three engine modes are implemented in subsequent build steps (Wave-1, Items 2–4):

- **consult** — read-only query engine over the user's committed `.sot/registry.yaml`. Subcommands: `list` (all entries), `get <id>` (full entry), `where <id>` (sot_location), `who <id>` (owner), `drift <id>` (drift_check). Global flags: `--registry PATH` (override path), `--json` (machine-readable output). Invoked via `run-with-env.sh` (Pattern B, BP-013). A 5b-cache slot in `_load_entries()` is ready for the derived memory cache (Item 3). Script: `_ai-memory/skills/aim-sot/scripts/aim_sot_consult.py`.
- **detect-propose** — hybrid auto-discover → propose: scans for candidate components, computes actual state, compares to the registry, and emits a proposed patch on drift or new candidates. Never writes the registry directly.
- **verify** — 16-check gate (Schema · Referential · Completeness · Content). Mandatory before any apply; human approval (HITL) required. CI/pre-commit hook is opt-in only, never auto-installed.

## Consult — Invocation

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_consult.py" \
  <subcommand> [--json] [--registry PATH]
```

## Detect-Propose — Invocation

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" \
  run [--json] [--registry PATH] [--limit N] [--all]
```

```bash
# Rebuild the 5b derived memory cache explicitly:
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" \
  reindex [--registry PATH]
```

**Hard invariant**: `detect-propose` NEVER writes `.sot/registry.yaml` — proposals only.
The human applies edits manually; the registry is always committed and diff-reviewable.

### Flags (`run`)

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | 20 | Cap new-candidate proposals per run |
| `--all` | off | Disable cap — surface all new candidates |
| `--json` | off | Machine-readable JSON output |
| `--registry PATH` | (git root) | Override registry path |

### Output — drift proposals

Each drift proposal includes `drift_type` (one of `location / staleness_temporal /
staleness_hash / declaration_reality`), `root_cause`, `impact`, and
`recommended_action`.  A `declaration_reality` entry with `"k1_trigger": true`
requires mandatory human re-confirmation before the description is considered valid
(spec §5 K1).

**Dual-firing on content change (by design):** when a file's hash changes, the engine
emits *both* `staleness_hash` (re-verify the artifact) *and* `declaration_reality`
(K1 trigger: description/tags must be re-confirmed by a human). These are
complementary signals — consumers may act on `k1_trigger` independently of the
staleness signal. Do not treat the two as duplicates; they require different actions.

**Hash drift covers file `sot_location`s only:** content-hash drift (types 2b/3/K1)
requires a readable file. When `sot_location` points to a **directory**, hash checks
are no-ops by design (spec §5: "sha256(file)"); the directory boundary still
participates in location and temporal-staleness drift. A directory-tree digest
extension is being considered separately — it is not implemented in this version.

### Output — new candidate proposals

Structural fields (`boundary_type`, `sot_location`, `confidence`, `inferred_from`)
are auto-inferred.  **Semantic fields (`owner`, `description`, `provenance_note`)
are never auto-filled — human-authored always (BP-029).**

### 5a and 5b caches

- **5a** (`~/.ai-memory/drift-state/sot_drift_{project_id}.json`) — per-install drift
  state; never committed.
- **5b** (Qdrant `conventions` collection, `memory_type=sot_entry`) — derived memory
  cache; deterministically rebuildable from the committed registry via `reindex`.

## Verify — Invocation

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" \
  run [--json] [--registry PATH] [--proposal PATH] \
  [--check-urls] [--exec-drift-checks]
```

### Flags (`run`)

| Flag | Default | Description |
|------|---------|-------------|
| `--registry PATH` | (git root walk) | Override registry path |
| `--proposal PATH` | (committed registry) | JSON/YAML file with `entries` key — gate a detect-propose output pre-apply |
| `--check-urls` | off | Activate R2 URL resolution (default: no-op; no network hit offline) |
| `--exec-drift-checks` | off | Activate K3 drift_check execution (default: parse + PATH-exists only) |
| `--json` | off | Machine-readable JSON output |

### Verdicts (BP-024 §3.3)

| Verdict | Condition | Apply-eligible? |
|---------|-----------|-----------------|
| `PASS` | 0 failures, 0 warnings | Yes |
| `CONDITIONAL` | 0 failures, ≥1 warning | Human review required; no auto-apply |
| `FAIL` | ≥1 failure | Blocked; fix and re-run |

### JSON output schema (BP-024 §2)

```json
{
  "verdict": "PASS | CONDITIONAL | FAIL",
  "checks_run": ["S1","S2","S3","S4","R1","R2","R3","R4","C1","C2","C3","C4","K1","K2","K3","K4"],
  "failures": [{"check": "R1", "entry_id": "my-svc", "detail": "..."}],
  "warnings": [{"check": "R4", "entry_id": "my-svc", "detail": "..."}],
  "pass_count": 14,
  "fail_count": 0
}
```

### 16-check taxonomy (BP-024)

| Category | Check | Verdict on issue |
|----------|-------|-----------------|
| Schema / Structural | S1 required fields + type | FAIL |
| | S2 ID uniqueness | FAIL |
| | S3 YAML parse | FAIL |
| | S4 controlled vocabulary (enum) | FAIL |
| Referential Integrity | R1 sot_location resolves (superseded exempt) | FAIL |
| | R2 URL resolves (`--check-urls` only; never network by default) | CONDITIONAL |
| | R3 cross-ref (no-op — no ID cross-ref fields in current schema) | — |
| | R4 owner in CODEOWNERS (normalized, no hard-FAIL) | CONDITIONAL |
| Completeness | C1 unregistered candidates (run detect-propose to register) | CONDITIONAL |
| | C2 orphan entries (no-op — propose-only format adds, never removes) | — |
| | C3 missing path + not superseded | FAIL |
| | C4 count assertion (N/A — no declared-count field in current schema) | — |
| Content Correctness | K1 content hash changed (mandatory on hash change — deterministic trigger) | CONDITIONAL |
| | K2 last_verified date plausible (past, non-epoch) | FAIL |
| | K3 drift_check executable (`--exec-drift-checks` for actual run) | FAIL (parse) / CONDITIONAL (PATH) |
| | K4 sot_location collision | FAIL |

**Soft-check rulings (wb-approved):** R2 is a strict no-op offline — URL fields do not affect the verdict without `--check-urls`. K3 never executes by default — security-safe. K1 is a deterministic hash trigger only, never a semantic judge. R4 normalizes `@handle` before comparing; mismatch is always CONDITIONAL, never FAIL.

### Usage — standalone audit

```bash
# Audit the committed registry in the current project:
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" \
  run --json
```

### Usage — pre-apply proposal gate

```bash
# Gate a detect-propose output before applying it to the registry:
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" \
  run --proposal /path/to/proposal.json --json
```

## Stop Hook — Opt-in

The Claude `Stop` hook (`sot_drift_stop.py`) ships in `.claude/hooks/scripts/` but is
**not auto-registered** in `settings.json` on install (BP-032 portability rule — the
tool never writes into the user's VCS/hook config without explicit opt-in). The engine
also runs standalone as the no-hook default (`detect-propose run` manually or via cron).

### Manual enablement

Add the following entry to your project's `.claude/settings.json` (under `hooks.Stop`):

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

Once registered, the hook fires automatically at every Claude Code session end. It invokes
`detect-propose` in propose-only mode and prints a one-line summary to stderr when drift
or new candidates are detected. It never writes any committed file.

---

## Registry contract

- `.sot/registry.yaml` is fully human-owned and committed; the schema and templates live in `_ai-memory/skills/aim-sot/`.
- **No-copy invariant**: every field is a pointer or provenance annotation — no copied source content.
- **No machine-auto-bumped fields**: content hashes, drift status, and machine timestamps belong in the per-install drift cache (`~/.ai-memory/drift-state/sot_drift_{project_id}.json`), never in the committed registry.

See `schema/registry.schema.json` and `templates/` for the machine-readable schema and user-facing starter templates.
