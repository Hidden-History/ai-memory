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

Three engine modes:

- **consult** — read-only query engine over the user's committed `.sot/registry.yaml`. Subcommands: `list` (all entries), `get <id>` (full entry), `where <id>` (sot_location), `who <id>` (owner), `drift <id>` (drift_check). Global flags: `--registry PATH` (override path), `--json` (machine-readable output). Invoked via `run-with-env.sh` (Pattern B, BP-013). Script: `_ai-memory/skills/aim-sot/scripts/aim_sot_consult.py`.
- **detect-propose** — hybrid auto-discover → propose: scans for candidate components, computes actual state, compares to the registry, and emits a proposed patch on drift or new candidates. Never writes the registry directly.
- **verify** — 16-check gate (Schema · Referential · Completeness · Content). Mandatory before any apply; human approval (HITL) required. CI/pre-commit hook is opt-in only, never auto-installed.

## Lifecycle

### Create (bootstrap a new project)

1. **Discover** — run `detect-propose run` (see **Detect-Propose — Invocation**); emits candidate proposals, never writes the registry.
2. **Author** — apply the [**Authoring**](#authoring) loop to each kept candidate; assemble into `.sot/registry.yaml` starting from `templates/registry.yaml.template`.
3. **Verify** — run `verify` (see **Verify — Invocation**); all 16 checks must pass.
4. **Apply** — human applies the registry after a clean verdict (HITL).

### Update (ongoing — drift and new candidates)

1. **Detect** — run `detect-propose run`; emits drift proposals and new-candidate proposals; never writes the registry.
2. **Author** — apply the [**Authoring**](#authoring) loop to any changed or new entries.
3. **Gate** — run `verify` via the **pre-apply proposal gate** (see **Usage — pre-apply proposal gate** under **Verify — Invocation**); mandatory before applying.
4. **Apply** — human applies; drift is never auto-applied.

### Cross-cutting invariants

- **Propose-only** — `detect-propose` never writes `.sot/registry.yaml`.
- **Verify gates apply** — the 16-check `verify` gate is mandatory before any apply.
- **Human applies** — every registry change requires explicit human action (HITL).
- **Never auto-rewrite** — no mode auto-applies drift or candidate proposals.

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

### First run — bootstrap from zero

When no `.sot/registry.yaml` exists yet, `detect-propose run` still runs the
discovery scan and emits **candidate proposals** for the project (it does not bail).
Bootstrapping a new project:

1. **Discover** — run `detect-propose run` (optionally `--all` to lift the cap). The
   scan roots at the project root, or the current working directory when no registry
   is present, and prints discovered candidates.
2. **Author** — for each candidate you keep, apply the [**Authoring**](#authoring) loop
   (categorize by type → propose entries → write each description to the D1–D4 rubric →
   fix any FAIL before emit); assemble the results into a new `.sot/registry.yaml`
   starting from `templates/registry.yaml.template`.
3. **Verify** — run `aim-sot verify` to gate the registry through the 16-check taxonomy.
4. **Approve** — apply after a clean verdict + human approval (HITL).

Discovery is still **propose-only** with no registry: candidates go to stdout and the
registry is never created or written.

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
  "verdict": "PASS",
  "checks_run": ["S1","S2","S3","S4","R1","R2","R3","R4","C1","C2","C3","C4","K1","K2","K3","K4"],
  "failures": [],
  "warnings": [],
  "ran_pass": ["S1","S2","S3","S4","R1","R2","R4","C1","C3","K1","K2","K3","K4"],
  "no_op":    ["R3","C2","C4"],
  "skipped":  [],
  "pass_count": 13,
  "fail_count": 0
}
```

**Outcome buckets** (M3 DD-D):
- `ran_pass` — checks that ran substantively and produced zero findings.
- `no_op` — structurally inert checks with the current schema (R3 / C2 / C4); no findings possible regardless of registry content.
- `skipped` — checks that could not run because a drift baseline was unavailable (K1 cold-start, baseline-loss, or project-id resolution failure); a `skipped_no_baseline` CONDITIONAL warning is emitted for each.
- `pass_count` = `len(ran_pass)` only — inert and skipped checks are **not** counted as passed, so a human reading `pass_count` knows exactly how many checks substantively verified content.

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
| Content Correctness | K1 content hash changed or no baseline (hash-change: mandatory human re-confirm; no-baseline: `skipped_no_baseline` CONDITIONAL — never silent PASS) | CONDITIONAL |
| | K2 last_verified date plausible (past, non-epoch) | FAIL |
| | K3 drift_check executable (`--exec-drift-checks` for actual run) | FAIL (parse) / CONDITIONAL (PATH) |
| | K4 sot_location collision | FAIL |

**Soft-check rulings (wb-approved):** R2 is a strict no-op offline — URL fields do not affect the verdict without `--check-urls`. K3 never executes by default — security-safe. K1 is a deterministic hash trigger only, never a semantic judge; when no baseline exists (cold-start, baseline-loss, or project-id resolution failure) K1 emits a `skipped_no_baseline` CONDITIONAL warning — it never silently passes as if content were verified. R4 normalizes `@handle` before comparing; mismatch is always CONDITIONAL, never FAIL.

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

## Trigger Opt-in — Codex / Cursor / Gemini

The Codex `Stop`, Cursor `stop`, and Gemini `AfterAgent` adapters ship
**unregistered** (BP-032). Add the relevant entry to your project's hook config to
enable automatic SOT-drift detection for each CLI.

### Codex — Stop hook

Adapter: `src/memory/adapters/codex/sot_drift.py`  
Config: `.codex/hooks.json` — add under `hooks.Stop`:

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

Fires propose-only at every Codex session stop. Never writes any committed file.

### Cursor — stop hook

Adapter: `src/memory/adapters/cursor/sot_drift.py`  
Config: `.cursor/hooks.json` — add under `hooks.stop`:

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

Fires propose-only at end-of-turn (Cursor `stop` event). Never writes any committed file.

### Gemini — AfterAgent hook

Adapter: `src/memory/adapters/gemini/sot_drift.py`  
Config: `.gemini/settings.json` — add under `hooks.AfterAgent`:

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

Fires propose-only at end-of-turn (Gemini `AfterAgent` event). Never writes any committed file.

---

## Digest Session-Start Hook — Opt-in

The aim-sot digest session-start hooks ship in their respective hook script directories
but are **not auto-registered** (BP-032 portability rule). Each hook fires on session
start, invokes `aim_sot_consult.py digest --json`, and injects a compact SOT digest as
ambient session-start context. Ships propose-only (digest is read-only — never writes
the registry).

Opt-in gate: a `.sot/registry.yaml` in the project root is required (same gate as the
drift hooks). No registry → hook exits with empty context.

### Claude — SessionStart hook

Script: `.claude/hooks/scripts/sot_digest_session_start.py`  
Config: `.claude/settings.json` — add under `hooks.SessionStart`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_digest_session_start.py\" || true",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

Once registered, fires on every Claude Code session start and injects the SOT digest as
`additionalContext`. Requires `.sot/registry.yaml` in the project root to activate.

### Codex — SessionStart hook

Script: `src/memory/adapters/codex/sot_digest_session_start.py`  
Config: `.codex/hooks.json` — add under `hooks.SessionStart`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_digest_session_start.py\" || true",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Fires at Codex session start and injects the SOT digest as `systemMessage`.

### Cursor — sessionStart hook

Script: `src/memory/adapters/cursor/sot_digest_session_start.py`  
Config: `.cursor/hooks.json` — add under `hooks.sessionStart`:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_digest_session_start.py\" || true",
        "timeout": 30
      }
    ]
  }
}
```

Fires at Cursor session start and injects the SOT digest as top-level `additional_context`.

### Gemini — SessionStart hook

Script: `src/memory/adapters/gemini/sot_digest_session_start.py`  
Config: `.gemini/settings.json` — add under `hooks.SessionStart`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_digest_session_start.py\" || true",
            "timeout": 60000
          }
        ]
      }
    ]
  }
}
```

Fires at Gemini session start and injects the SOT digest as `additionalContext`.

---

## Registry contract

- `.sot/registry.yaml` is fully human-owned and committed; the schema and templates live in `_ai-memory/skills/aim-sot/`.
- **No-copy invariant**: every field is a pointer or provenance annotation — no copied source content.
- **No machine-auto-bumped fields**: content hashes, drift status, and machine timestamps belong in the per-install drift cache (`~/.ai-memory/drift-state/sot_drift_{project_id}.json`), never in the committed registry.

See `schema/registry.schema.json` and `templates/` for the machine-readable schema and user-facing starter templates.

---

## Authoring

Use this loop to categorize the project, propose the right entries, and write gradeable descriptions. Full decision procedure and per-type checklists: `references/authoring-guide.md`. Contrastive calibration examples: `references/grading-exemplars.md` — read before grading.

**1. Categorize** — Check each type's signals in order against the repo (see `references/authoring-guide.md → Categorize`). Record MATCH / NO-MATCH with the file(s) that triggered the match. Do not skip a type. Resolution: 0 matches → ask the user, do not guess; 1 match → run that type's checklist; ≥2 matches → superset: run each matched type's checklist scoped to its sub-tree, plus the monorepo cross-cutting checklist for shared ownership/membership.

**2. Propose entries** — For each matched type, run its canonical-parts checklist (`references/authoring-guide.md → Per-type checklists`). Flag any expected part absent from the registry as a gap.

**3. Write each description** — Author prose that names: what this part *is* and its role; who owns it (in the description or via the `owner` field — D2 is satisfied by either); why *this* location is the source of truth; how you'd know it went stale.

**4. Grade each description** — Run D1–D4. PASS only if all four pass. Emit one line per dimension before the verdict (the cited token must be literally present — do not award a dimension because you *intended* to include it).

| # | Check (yes/no) | YES requires | NO if |
|---|----------------|--------------|-------|
| **D1** Identity  | Names the artifact AND its role? | concrete noun + function/role phrase, >1 word beyond the `id` | empty, restates `id`, or pure type word ("the service", "config") |
| **D2** Ownership | Resolvable owner present (description **or** `owner` field)? | @-handle, team name, or named role | "TBD", "the team", "us", or no owner anywhere on the row |
| **D3** Authority | States WHY this location is the SOT? | "contract-first", "generated from", "canonical/declared", "single source", or `provenance_note` populated with the basis | only locates ("it's in /src"); asserts authority with no basis |
| **D4** Drift     | Staleness signal present (description **or** `drift_check`/`last_verified`)? | a check command, "stale when…" clause, or verifiable condition | no way to tell if current; no `drift_check`, no staleness clause |

Aggregate: PASS = D1 ∧ D2 ∧ D3 ∧ D4. WEAK = D1 passes, exactly one of D2/D3/D4 fails. FAIL = D1 fails OR ≥2 of D2/D3/D4 fail.

Emit per dimension, then the verdict:

```
D1: yes/no — <noun + role phrase found, or why absent>
D2: yes/no — <owner token found, or "none on row">
D3: yes/no — <authority basis phrase found, or "locates only">
D4: yes/no — <drift signal found, or "none">
VERDICT: PASS | WEAK (name the failing dim) | FAIL (name the failing dims)
```

**5. Fix FAILs** — If FAIL: rewrite targeting the failed dimension(s) only; re-grade. Cap: 2 rewrite passes; if still FAIL after 2, surface to the user with the failing dimensions named. If WEAK: accept and flag the one missing dimension on the entry.

**6. Emit** — Before emitting, run the schema-bind check (`references/authoring-guide.md §4`): entries with `kind` or `boundary_type` outside the valid enums are SCHEMA-INVALID and block emit. Never emit the registry while any entry is FAIL or SCHEMA-INVALID. See `references/authoring-guide.md → Emit structure` for the constrained output format.
