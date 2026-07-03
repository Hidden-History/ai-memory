---
name: aim-sot
description: Tracks the source-of-truth for each part of the user's own project — registry schema, templates, and engine (consult / detect-propose / verify). Detects file and directory drift (content-digest and directory tree-digest), runs a machine-local shadow-git history for change detection, and correlates code changes to stale docs (doc-drift via DOCOWNERS). Use when checking SOT drift, choosing a drift_strategy, setting up the shadow git, or reviewing doc-staleness findings. Do NOT use for AI Memory search or save operations, or for checking AI Memory system health (use aim-search, aim-save, or aim-status).
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
3. **Verify** — run `verify` (see **Verify — Invocation**); **0 failures required**. On a fresh registry the verdict is **CONDITIONAL, not PASS** — cold-start K1 `skipped_no_baseline` and advisory (C1) warnings are expected and do not block apply (see **Verdicts**); literal `PASS` needs an established baseline.
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
  run [--json] [--registry PATH] [--limit N] [--all] [--write-proposal] [--force]
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
   is present, and prints discovered candidates. Add **`--write-proposal`** to also
   scaffold a ready-to-edit staging draft (see below).
2. **Author** — for each candidate you keep, apply the [**Authoring**](#authoring) loop
   (categorize by type → propose entries → write each description to the D1–D4 rubric →
   fix any FAIL before emit); assemble the results into a new `.sot/registry.yaml`
   starting from `templates/registry.yaml.template` (or from the `--write-proposal`
   draft).
3. **Verify** — run `aim-sot verify` to gate the registry through the 16-check taxonomy.
4. **Approve** — apply after a clean verdict + human approval (HITL).

Discovery is still **propose-only** with no registry: candidates go to stdout and the
committed registry is never created or written.

#### `--write-proposal` — scaffold a staging draft (TD-744)

`detect-propose run --write-proposal` writes a **non-committed** staging file
`.sot/registry.proposed.yaml` from the discovered candidates, so you edit a
schema-shaped draft instead of transcribing a stdout list by hand. It fires **only
on a registry-less project** (the entry point that already runs cold-start
discovery); when a committed `.sot/registry.yaml` exists the registry-present drift
path takes over and `--write-proposal` does nothing.

- **What it fills.** Structural fields are written as real values (`boundary_type`,
  `sot_location`, `status: proposed`, `added_by: "aim-sot bootstrap"`). Every
  human-owned semantic field is an explicit `TODO(human): …` placeholder
  (`kind`, `owner`, `description`, `last_verified`, `provenance_note`) — **never
  auto-filled (BP-029)**. Each entry's `confidence` + mandatory `inferred_from` ride
  as advisory comments above it (they are not registry-schema fields).
- **Promotion = approval.** The engine writes a *draft*, never the SoT. You fill the
  `TODO(human)` fields, prune candidates, then **rename** the draft to
  `.sot/registry.yaml`, commit it, and run `aim-sot verify`. That promotion + commit
  is the human approval (BP-030). Recommend git-ignoring `.sot/registry.proposed.yaml`.
- **Idempotency.** A second run **skips** an existing draft (to protect in-progress
  edits) and says so; pass **`--force`** to overwrite. The committed registry is never
  written under any path (BP-030 invariant).
- **Owner candidates (advisory).** When the project is a git repo, the draft carries
  an `owner_candidates` advisory comment block — the top-3 committers per
  `sot_location` from `git log`, as a hint for authoring `owner` by hand. It is
  **never** written into the `owner` field, and **degrades silently** (block omitted)
  on a non-git project.

#### Confidence tiers (TD-744 Q5)

Candidates carry an ordinal `confidence` triage label paired with `inferred_from`:

| Tier | Signal | Example `inferred_from` |
|------|--------|-------------------------|
| `high` | the project *declares* the unit | a manifest filename, `adr_directory` |
| `medium` | structural heuristic (a top-level folder) | `top_level_directory` |
| `low` | weak/ambiguous (nested source dir, no manifest) | `nested_source_directory` |

The label is **review-triage priority only** — it is never an auto-approve gate and
never licenses auto-filling semantics; even a `high` candidate needs human authoring.

### Flags (`run`)

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | 20 | Cap new-candidate proposals per run |
| `--all` | off | Disable cap — surface all new candidates |
| `--json` | off | Machine-readable JSON output |
| `--registry PATH` | (git root) | Override registry path |
| `--write-proposal` | off | Registry-less project only: scaffold a non-committed `.sot/registry.proposed.yaml` staging draft (structural fields filled, semantic fields `TODO(human)`). Never writes the committed registry. See [First run — bootstrap from zero](#first-run--bootstrap-from-zero). |
| `--force` | off | With `--write-proposal`, overwrite an existing draft (default: skip to protect in-progress edits). |
| `--shadow` | off | Run the `[CL]` detect pass — BP-039 digest → BP-040 shadow-git commit → BP-042 doc-drift → structured `findings`. The Stop hooks pass it; see [Drift strategies, shadow git & doc-drift](#drift-strategies-shadow-git--doc-drift). |
| `--drift-only` | off | Hot path only: check the registered entries for drift and skip the discovery walk entirely (BP-047). Mutually exclusive with `--discover`. **Does not skip the 5b reindex gate** — a registry-content change still triggers the derived-cache rebuild; only `--no-reindex` suppresses Qdrant writes. |
| `--discover` | off | Force a full discovery walk now, bypassing the periodic cadence gate (TTL / session-count) and resetting it (BP-047). Mutually exclusive with `--drift-only`. |
| `--no-reindex` | off | Skip the 5b derived-cache reindex so drift / discovery can be exercised with **zero** Qdrant writes (offline / sandbox). |

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

**Drift digest is dispatched by strategy:** a **file** `sot_location` uses
`content-digest` (sha256 of the file — unchanged behavior); a **directory**
`sot_location` uses `tree-digest` (BP-039 sorted-per-file-SHA-256 over the tree),
so directory boundaries now get content-hash drift too. Override per entry with the
schema-validated `drift_strategy` enum (never a shell command). A strategy switch or
digest-version bump **re-baselines** the entry rather than firing drift. See
[Drift strategies, shadow git & doc-drift](#drift-strategies-shadow-git--doc-drift).

### Output — new candidate proposals

Structural fields (`boundary_type`, `sot_location`, `confidence`, `inferred_from`)
are auto-inferred.  **Semantic fields (`owner`, `description`, `provenance_note`)
are never auto-filled — human-authored always (BP-029).**

### 5a and 5b caches

- **5a** (`~/.ai-memory/drift-state/sot_drift_{project_id}.json`) — per-install drift
  state; never committed.
- **5b** (Qdrant `conventions` collection, `type=sot_entry`) — derived memory
  cache; deterministically rebuildable from the committed registry via `reindex`.

#### Connect to the SOT / memory Qdrant from a scratch script

To inspect the 5b collection (e.g. verify `--no-reindex` wrote nothing), use the
project's client factory rather than constructing `QdrantClient` by hand — it
resolves host/port, the API key, HTTPS, and the gRPC-vs-HTTP transport from config,
avoiding the "illegal request line" / TLS `WRONG_VERSION_NUMBER` errors an ad-hoc
client hits:

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.ai-memory/src"))  # the installed runtime
from qdrant_client import models
from memory.qdrant_client import get_qdrant_client

client = get_qdrant_client(read_only=True)  # defaults to prefer_grpc=True
count = client.count(
    "conventions",
    # gRPC mode requires a typed Filter, not a raw dict.
    count_filter=models.Filter(
        must=[
            models.FieldCondition(
                key="type", match=models.MatchValue(value="sot_entry")
            )
        ]
    ),
).count
print("sot_entry records:", count)
```

## Drift strategies, shadow git & doc-drift

The `--shadow` flag on `detect-propose run` runs the `[CL]` detect pass: one BP-039
tree-digest of the project → on change, a machine-local **shadow-git** commit
(BP-040) → a `git diff` → **doc-drift** correlation (BP-042) → a structured
**findings** pipe. All of it is engine-side, shared by every CLI; the per-CLI Stop
hooks are thin callers that pass `--shadow`.

Key guarantees:

- **Non-invasive** — the shadow git is a bare repo under `~/.ai-memory/sot-git/<project_id>/` driven by an explicit two-pointer (`GIT_DIR`/`GIT_WORK_TREE`); it writes **nothing** into the user's tree (no `.git`, no `.gitignore`). Teardown is `rm -rf`.
- **git-required, project-need-not-be-git** — git is a required tool, but the portable directory tree-digest never needs the project itself to be a git repo.
- **Propose-only + machine-local** — only `.sot/registry.yaml` and `.sot/DOCOWNERS` are committed; the shadow git, setup sentinel, and drift-state are machine-local and never committed.
- **Findings emit, Parzival records** — the engine emits the structured `findings[]` pipe (drift / doc-staleness / `ERROR` / `FRICTION`); it never writes any oversight register.

Registry config (optional, top-level): `exclude:` (extra gitignore-style globs for
the tree-digest) and `docowners:` (path override, default `.sot/DOCOWNERS`). Per
entry: `drift_strategy:` (enum override).

→ Full reference — strategy table, shadow-git setup/cadence/teardown, `.sot/DOCOWNERS`
format, the setup sentinel, and the findings schema: [`references/drift-and-shadow-git.md`](references/drift-and-shadow-git.md).

## Verify — Invocation

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" \
  run [--json] [--registry PATH] [--proposal PATH] \
  [--check-urls] [--exec-drift-checks] [--strict]
```

### Flags (`run`)

| Flag | Default | Description |
|------|---------|-------------|
| `--registry PATH` | (git root walk) | Override registry path |
| `--proposal PATH` | (committed registry) | JSON/YAML file with `entries` key — gate a detect-propose output pre-apply |
| `--check-urls` | off | Activate R2 URL resolution (default: no-op; no network hit offline) |
| `--exec-drift-checks` | off | Activate K3 drift_check execution (default: parse + PATH-exists only) |
| `--json` | off | Machine-readable JSON output |
| `--strict` | off | Exit non-zero (1) when the verdict is `FAIL` — for CI / pre-commit gates. `PASS` and `CONDITIONAL` still exit 0. Default (without `--strict`): always exit 0, verdict on stdout. Prefer this over parsing the default exit status — `verify run \|\| exit 1` does **not** catch a `FAIL`. |

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

## Stop Hook — Default-on

The Claude `Stop` hook (`sot_drift_stop.py`) is **registered by default on install**
alongside the core ai-memory hooks. It calls the engine with `--shadow`, so the Stop
event runs the full `[CL]` detect pass (digest → shadow-git commit → doc-drift →
findings) and surfaces a one-line `[ai-memory] SOT` summary to stderr. To opt out, set
`AI_MEMORY_SOT_HOOKS=off` (case-insensitive; only `off` disables — `false`/`0`/`no`
leave hooks on). This works two ways:

- **Install-time** — set it before running `install.sh` and the drift hooks are never
  registered (settings merge is append/base-wins, so this does **not** remove hooks a
  prior install already registered).
- **Runtime** — export it in the environment that launches Claude Code (your shell
  profile, or the `env` block of `settings.local.json`). The drift hook scripts read
  `AI_MEMORY_SOT_HOOKS` on each run and no-op when it is `off`, so an already-registered
  drift hook can be disabled per-session **without** reinstalling or hand-editing the
  hook entries in `settings.json`. Use `settings.local.json` (or your shell profile), not
  the generated `settings.json` — `generate_settings.py` **regenerates** the latter's
  `env` block on every install, so a value hand-added there is wiped on the next install.

  This runtime kill-switch covers the **drift** hooks only (the Claude Stop hook and the
  Codex/Cursor/Gemini stop adapters). The **digest** session-start hooks are not
  runtime-gated — disable those at install time (see *Digest Session-Start Hook* below).

Note: `docker/.env` is sourced only by `install.sh`, so setting the variable there
affects install-time registration only — it is never loaded into a live Claude Code
session, so it does not toggle the hooks at runtime.

> **BP-032 reconciliation**: the original portability concern is bounded — the hooks
> self-guard on `.sot/registry.yaml` presence (no-op in non-SOT projects), and the
> settings merge is backup + atomic + non-clobbering. Default-on is safe for
> multi-project operators.

The engine also runs standalone (`detect-propose run` manually or via cron).

### Drift-scan budgets (large / slow-filesystem projects)

The `[CL]` pass runs two full-project walks — the BP-039 tree-digest and the
candidate discovery scan. On a very large project (or a slow filesystem) either
can exceed the Stop hook's ~20s subprocess cap; the engine therefore bounds both
by wall-time and count and emits a visible `budget-truncated` signal (never a
silent zero-findings timeout). When truncated, the digest baseline is left
unchanged for the next run. Tune via the environment (all optional; positive
values only — a blank/invalid value keeps the default):

| Env var | Default | Bounds |
|---------|---------|--------|
| `AI_MEMORY_SOT_DIGEST_MAX_SECONDS` | `10.0` | tree-digest wall-time |
| `AI_MEMORY_SOT_DIGEST_MAX_FILES` | `20000` | tree-digest file count |
| `AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS` | `6.0` | discovery-scan wall-time |
| `AI_MEMORY_SOT_DISCOVERY_MAX_DIRS` | `5000` | discovery-scan directory count |

If you see the `budget-truncated` warning, raise the relevant budget **or**
narrow the registry exclude set so fewer files are walked (operator-side exclude
authoring is the durable fix; the budget is the engine guard).

→ Full hook-config reference (Claude Stop, Codex Stop, Cursor stop, Gemini AfterAgent, and all SessionStart variants): [`references/hook-setup.md`](references/hook-setup.md).

---

## Trigger Hooks — Codex / Cursor / Gemini

The Codex `Stop`, Cursor `stop`, and Gemini `AfterAgent` adapters are **registered by
default on install** (same as the Claude Stop hook above). Set `AI_MEMORY_SOT_HOOKS=off`
before `install.sh` to skip registration for all SOT hooks. To register only specific
adapters, remove the unwanted entries from your hook config after install. Like the
Claude Stop hook, these drift adapters also honor `AI_MEMORY_SOT_HOOKS=off` at
**runtime** — see *Stop Hook — Default-on* above for the durable delivery surfaces.

→ Per-CLI hook-config snippets (Codex Stop, Cursor stop, Gemini AfterAgent): [`references/hook-setup.md`](references/hook-setup.md).

---

## Digest Session-Start Hook — Default-on

The aim-sot digest session-start hooks are **registered by default on install** alongside
the core ai-memory hooks. Each hook fires on session start, invokes
`aim_sot_consult.py digest --json`, and injects a compact SOT digest as ambient
session-start context. Ships propose-only (digest is read-only — never writes
the registry).

Runtime gate: a `.sot/registry.yaml` in the project root is required (same gate as the
drift hooks). No registry → hook exits with empty context (no-op in non-SOT projects).

Disable SOT hooks with `AI_MEMORY_SOT_HOOKS=off` (case-insensitive; only `off`
disables — `false`/`0`/`no` leave hooks on). **Install-time** (set before `install.sh`)
skips registering **all** SOT hooks — drift *and* these digest session-start hooks.
**Runtime** (see *Stop Hook — Default-on* above for the durable delivery surfaces)
disables the **drift** hooks only; these digest session-start hooks are **not**
runtime-gated, so to turn off an already-installed digest hook set the variable before a
reinstall (or remove its entry from your hook config).

→ Per-CLI hook-config snippets (Claude, Codex, Cursor, Gemini SessionStart): [`references/hook-setup.md`](references/hook-setup.md).

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
