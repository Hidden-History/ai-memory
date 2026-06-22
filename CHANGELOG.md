# Changelog

All notable changes to AI Memory Module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Evaluator audit-log write no longer masquerades as an evaluation error (TD-712)** — inside the evaluator-scheduler the bind-mounted `.audit/logs` directory is host-owned (default `1000:1000`) but the image baked a uid `1001` user, so each per-observation audit append failed with `Permission denied`. The failure occurred *after* the score was attached but inside the broad per-item handler, so it logged as `Error evaluating observation …`, masking a successful score as a scoring failure. `_append_audit_log` now catches and logs its own write failures (a benign audit-write error can no longer surface as an evaluation error), and the evaluator-scheduler service runs as the host user (`UID:GID`) so it can write the host-owned mount — matching the github-sync pattern.
- **`process_retry_queue.py` supports a scoped drain (TD-713)** — the queue processor now accepts `--group-id <group>` to drain only one project's entries. On a shared multi-project stack a per-project retry no longer flushes other projects' backlogged entries. The default (no `--group-id`) remains a global drain across all groups, preserving behavior for automated/cron callers.
- **`aim-purge` default scope resolves through the shared resolver (TD-714)** — `purge_collections.py` previously fell back to the raw cwd basename when `AI_MEMORY_GROUP_ID` was unset (e.g. `ai-memory-testV2`), which mismatched the canonical lowercased id used everywhere else and pointed a default purge at the wrong scope. It now resolves the group via the shared `resolve_project_id` helper (legacy `AI_MEMORY_GROUP_ID` honored as an explicit override) and fails loud rather than purging a guessed scope.
- **Async store no longer logs a spurious `Incorrect label names` error after a successful store (TD-715)** — `post_work_store_async.py` pushed `aimemory_captures_total` and `aimemory_dedup_events_total` with an incomplete label set (`collection`, and `action`, were missing), so the post-store Prometheus push raised `Incorrect label names`, which was caught and logged as a `validation_failed` ERROR even though the store succeeded. The push now supplies the full declared label set on every path, so a successful store no longer emits the misleading error.

## [2.8.0] - 2026-06-21

### Upgrade Instructions

**This release changes embedding dependencies and baked worker code, so a plain install + restart is not enough — the affected images must be rebuilt.**

```bash
# 1. Update source + install (refreshes ~/.ai-memory and any target project)
cd <your ai-memory clone> && git pull
./scripts/install.sh <project-path>

# 2. Rebuild the images that bake Python deps / code. Note evaluator-scheduler
#    and trace-flush-worker are defined in docker-compose.langfuse.yml:
cd ~/.ai-memory/docker && docker compose \
  --env-file .env --env-file .env.secrets \
  -f docker-compose.yml -f docker-compose.langfuse.yml \
  build embedding evaluator-scheduler classifier-worker trace-flush-worker github-sync

# 3. Restart to deploy the rebuilt images
~/.ai-memory/scripts/stack.sh restart
```

`install.sh` uses `up -d --no-recreate` and `stack.sh restart` does not rebuild images — so without step 2 the new `openai` dependency and the updated worker/embedding code are **not** deployed (the evaluator would fail with `No module named 'openai'`).

**Embedding memory default raised `4G` → `6G`.** The embedding service is shared across all projects on an install and must be sized for combined load; `4G` OOM-loops a multi-project install. The default is written to `docker/.env` on install. To tune it, edit `docker/.env` (`EMBEDDING_MEMORY_LIMIT=…`) and `stack.sh restart` — no rebuild needed for the memory cap. See [`docs/EMBEDDING-SIZING.md`](docs/EMBEDDING-SIZING.md).

### Added

- **`aim-tracking-rotate` fix action** (`--fix <file>` / `--fix-all` / `--fix-memory-md` / `--include-memory-md`) — non-interactive cap remediation that brings an over-cap oversight tree to a `--check` PASS without losing any record. The algorithm is conformance-first (adds D2 front-matter from the template when absent), then cap-fixes by class (entry rotation for append-only logs and rotatable registers; archive-whole-verbatim for table-row registers (`blockers-log.md`, `risk-register.md`), non-rotatable registers (`task-tracker.md`), and multi-table live-indexes (`SESSION_WORK_INDEX.md`, `session-index/INDEX.md`); template front-matter refresh for heartbeats), then proves conservation (`lost == 0`) before returning. Every mutation path creates a timestamped backup first and writes atomically; no interactive confirmation is required.
- **`auto-memory-index` file class** — fifth governed class for the Claude Code auto-memory `MEMORY.md`. Cap is 200 lines / 25 KB **whichever comes first** (load-window advisory). `--check` emits WARN (non-blocking) on cap or log-shape violations. `--fix-memory-md` triggers on **over-cap or log-shape** (log-shape: any entry > 2 non-blank lines or > 200 chars); a compliant MEMORY.md triggers no changes. When triggered, relocates over-long entries to hot sibling topic files (`feedback_*.md`, `project_*.md`, etc.) in the same `memory/` directory, leaving a one-line `- [Title](sibling.md) — hook` pointer; conservation is proved across the full union of `MEMORY.md` and all siblings. A `MEMORY.md` skeleton template (`templates/memory/MEMORY.md.template`) and detailed fix prose (`assets/memory_md_fix.md`, lazy-loaded) are shipped alongside.
- **Conservation helper module** (`_ai-memory/pov/lib/governance/conservation.py`) — standalone, unit-testable module providing entry-ID manifest generation (`build_id_manifest`) and `assert_no_id_loss` for oversight classes, plus content-set generation (`build_content_set`) and `assert_no_content_loss` for the auto-memory-index class.
- **Embedding-service resilience — bounded-queue backpressure + memory-aware self-throttle (BUG-324)** — under combined multi-repo load the shared embedding service now degrades (slows down) instead of dropping embeds or OOM-killing. A service-global async semaphore bounds concurrent inference; excess requests **wait** in a bounded queue (true backpressure) instead of being shed, and only a full queue or an exceeded admission timeout returns a last-resort `503 + Retry-After`. A background controller reads cgroup-v2 memory signals (`memory.current` / `memory.high` / `memory.events` / PSI `memory.pressure`) and collapses effective concurrency toward 1 under memory pressure (AIMD), recovering when healthy — preventing the OOM-kill/restart loop. New Prometheus signals: `embedding_inflight`, `embedding_queue_depth`, `embedding_admission_wait_seconds`, `embedding_backpressure_total{action}`, `embedding_oom_events_total`, `embedding_effective_concurrency_limit`, `embedding_memory_current_bytes`, `embedding_memory_headroom_bytes`, `embedding_memory_pressure_full_avg10`. Tunable via new conservative env knobs (`EMBEDDING_MAX_WAITERS`, `EMBEDDING_RETRY_AFTER`, `EMBEDDING_PRESSURE_INTERVAL`, `EMBEDDING_PSI_THRESHOLD`, `EMBEDDING_MEMORY_HIGH_RATIO`, `EMBEDDING_MEMORY_OK_RATIO`, `EMBEDDING_INFERENCE_THREADS`, `EMBEDDING_CLIENT_SUBBATCH`).
- **Capped POV startup loaders (`aim-parzival-loader`)** — two phase loaders (activation and session-start) load capped heads, a recency-weighted LORE slice, and lazy pointers instead of full files, cutting Parzival startup resident context ~60% (~72K → ~28.5K tokens); the Qdrant bootstrap is scoped to its own layers.
- **Sanctum governance** — a shared `_ai-memory/pov/lib/governance` package (conservation 0-lost proof + per-class `Contract`) imported by both `aim-tracking-rotate` and `aim-lore-hygiene`; per-class sanctum Contracts (LORE/MEMORY compact, PERSONA section-cap, CREED/BOND check-only) and a session-close `--check` gate spanning oversight and sanctum classes (LORE/MEMORY size reporting-only, not a closeout blocker). Every lore-hygiene relocation now carries the conservation proof.
- **Absolute-relevance ambient-injection gate (BP-174)** — the per-turn tier-2 injection gate now consults an absolute raw-cosine signal (store-baseline floor + scale-free top-1/top-2 margin + freshness-age cap) alongside the banded `hybrid_rrf_decay` score. The banded score min-max normalizes the top-1 to ~0.95 per result-set, so the per-collection confidence gate could never skip and a single-domain store injected same-domain-but-off-topic or stale memory on nearly every turn. `MemorySearch.search` now attaches an opt-in `raw_score` (dense cosine) consumed only by this gate; the gate is strictly additive (can only add a relevance skip, never force an injection) and defers to the banded gate on routes with no dense neighbor (`best_raw == 0.0`, e.g. code-patterns). Calibrated against a read-only live sweep and enabled (`INJECTION_ABSOLUTE_GATE_ENABLED=true`, `INJECTION_ABSOLUTE_FLOOR=0.76`); additional knobs `INJECTION_MARGIN_MIN`, `INJECTION_FRESHNESS_MAX_AGE_DAYS`, `INJECTION_DRIFT_SUPPRESSOR_THRESHOLD`.

### Changed

- **`aim-tracking-rotate` task-tracker cap** raised from 40 lines / 3 KB to **60 lines / 4.5 KB** (fits a full 10-line front-matter block plus a meaningful task body without false-positive cap failures).
- **`aim-tracking-rotate` section-scaffold preservation** — both `--fix` and the session-close `--apply` now fence an unfenced `## Entry Format` example before rotating so the section scaffold (`## How to Use`, `## Entry Format`, `## Decisions`) survives and entries stay under `## Decisions`. `--fix` additionally adds any missing `## ` section headers from the template when the file lacks them.
- **Embedding service footprint + concurrency model** — the image now sets `MALLOC_ARENA_MAX=2`, `OMP_NUM_THREADS=2`, and bounds the onnxruntime intra-op pool (`EMBEDDING_INFERENCE_THREADS=2`) to shrink anon-RSS and the allocator-fragmentation overshoot past the container cap. Endpoints are now `async` with a bounded inference executor sized to the concurrency semaphore, so the semaphore is the single concurrency bound.
- **Embedding client retries on backpressure** — `EmbeddingClient.embed()` now retries on HTTP 503/429 honoring `Retry-After` (previously only on timeout), keeping the client in lockstep with the service's backpressure so a transient shed no longer drops a memory. Batch storage (`store_memories_batch`) sub-batches large groups client-side (`EMBEDDING_CLIENT_SUBBATCH`) so an oversized batch is split rather than rejected (413) and degraded to PENDING.
- **Embedding memory default raised `4G` → `6G` (BUG-324)** — the shared embedding service climbs well past its ~3GB model footprint under real multi-project load (glibc arena retention), so the prior `4G` default OOM-loops a multi-project install. New [`docs/EMBEDDING-SIZING.md`](docs/EMBEDDING-SIZING.md) gives per-system sizing by concurrent-project count. (Default is provisional pending the BUG-324 capacity soak.)

### Removed

- **`aim-bmad-dispatch` backward-compat redirect stub** (`.claude/skills/aim-bmad-dispatch/`) — the v2.4.0 shim (originally intended for a single release) is now removed. Use `/aim-agent-dispatch` instead; it handles both BMAD and generic agent dispatch via a unified routing path. Operators whose `settings.json` still references `aim-bmad-dispatch` must update the path to `aim-agent-dispatch`.
- **`docs/parzival/BMAD-DISPATCH-GUIDE.md`** — the standalone BMAD dispatch guide is removed. BMAD agent selection and activation are documented in `aim-agent-dispatch` and `docs/parzival/AGENT-DISPATCH-GUIDE.md` now that BMAD dispatch is unified into `aim-agent-dispatch`.

### Fixed

- **Evaluator-scheduler missing `openai` dependency** — the LLM-as-judge evaluator's default `ollama` provider (and the `openrouter`, `openai`, and `custom` provider paths) build their client through the `openai` SDK, but the package was not declared in `requirements.txt` or `pyproject.toml`. The evaluator-scheduler image installs only `requirements.txt`, so every evaluation failed at runtime with `No module named 'openai'` and the scheduler reported `scored: 0` despite sampling traces. `openai` is now declared in `requirements.txt` and the `observability` extra, and a smoke test asserts the configured default provider's client builds via the real import path while pinning the `requirements.txt` (image-bake) source-of-truth.
- **Jira connector at-exit Langfuse drain no longer wedges process teardown** — the `atexit`-registered shutdown hook in the Jira sync connector now bounds its `flush()`/`shutdown()` with an external watchdog (the V4 SDK's `flush()`/`shutdown()` take no timeout and block on the worker queue join when a backend is reachable but slow to drain), and skips the drain and its registration entirely when Langfuse is disabled at the app level. Scoped to the Jira connector's at-exit hook only: local unit suites that import the Jira sync connector no longer appear to hang after the final test on account of that hook (the sibling at-exit sites in other modules are addressed separately).
- **Trace-flush worker no longer silently drops traces on a hung backend** — `process_buffer_files()` previously unlinked a buffer file whenever `flush()` returned, but under the Langfuse V4 (OpenTelemetry) SDK the OTLP exporter swallows read-timeouts and non-2xx responses as an export failure without raising, so `flush()` returned normally even when the span never reached the server, and `force_flush()`'s boolean result is not propagated as a delivery signal. The unlink is now gated on both `flush()` not raising and the absence of an OTLP export-failure log during the flush window; a silently-failed export retains the buffer file for replay on the next pass (at-least-once), rather than deleting an undelivered trace. The detection is hardened against two failure modes: (1) it temporarily raises the `opentelemetry` logger — and any explicitly-silenced `opentelemetry.*` descendant logger (e.g. `setLevel(CRITICAL)` on the OTLP span exporter) — to `ERROR` for the duration of the flush window, restoring each afterward, so the gate cannot fail open when an operator has silenced either the parent or a specific emitter logger, which would otherwise suppress the export-failure record entirely; and (2) the failure marker is scoped to `"Failed to export span"` (was `"Failed to export"`) so a metric/log exporter's own failure line cannot be mistaken for a span-delivery failure and over-retain the buffer.
- **Evaluation-dataset golden fixtures (`create_datasets.py`)** — refreshed the Langfuse seed fixtures and the file's governance header from stale V3-only guidance to the current V4 (OTel-based) SDK. The dataset previously seeded V3-era answers (a decision fixture, an insight fixture, a retrieval expectation, and a spec-excerpt chunking fixture) that could score outdated responses as correct; their content and `key_terms_required` now reflect V4, and the spec-excerpt fixture's token estimate is re-derived from its rewritten text. The coupled `test_create_datasets.py` assertions are updated to match.
- **Unbounded Langfuse at-exit drain could wedge process teardown** — the GitHub code-blob sync, GitHub sync engine, evaluator scheduler, and classification-queue processor all flushed and shut down the Langfuse client on exit via a plain `flush()`/`shutdown()`. In langfuse 4.x these calls take no timeout and block on the SDK worker's internal queue drain, which never returns when a reachable-but-slow backend keeps the queue non-empty, so a normally-exiting process could hang indefinitely. Each drain now runs in a daemon thread bounded by an external watchdog join, and is skipped entirely (along with its `atexit` registration) when Langfuse is disabled at the app level. The two post-sync-cycle inline flushes in the GitHub connectors are bounded the same way.
- **Agent memory types now route to the discussions collection on the async/retry store paths (BUG-322)** — the four agent memory types (`agent_handoff`, `agent_insight`, `agent_memory`, `agent_task`) were omitted from the type-to-collection selection in both `process_retry_queue.py` (`get_collection_for_type`) and `post_work_store_async.py` (`store_memory_async`), so they fell through to the code-patterns collection instead of discussions. This diverged from the authoritative `MemoryStorage.store_agent_memory` path and could store an agent record into the wrong collection (and miss the discussions original during dedup). Both selection sites now map all four types to the discussions collection, matching the store path.
- **Embedding-service OOM-kill/restart loop under memory pressure (BUG-324)** — combined multi-repo load no longer drives the shared service past its cgroup cap; the memory-aware AIMD controller throttles *before* the kernel OOM-kills, turning the kill/restart loop into "slow down and survive".
- **Dropped memory on embedding backpressure (TD-678)** — a server backpressure 503/429 is now retried by the client instead of raising and losing the memory; the zero-vector rejection (TD-354) remains intact end to end.
- **`metrics_import_failed` startup warning (TD-694)** — the embedding service no longer imports the unused client-side `memory.metrics` module (which triggered the heavy `memory` package init absent from the slim image), eliminating the spurious startup WARNING.
- **NAME/HANDLE redaction no longer corrupts technical content (precision-first)** — the storage-time security scanner destructively masked SpaCy `PERSON` spans and `@handles` at write time, but SpaCy mis-tags technical proper nouns ("Docker"), filenames ("CLAUDE.md"), and diff-hunk headers as `PERSON`, so legitimate content was permanently replaced with `[NAME_REDACTED]`/`[HANDLE_REDACTED]` and later surfaced as garbled text. A precision gate for these low-precision classes now allow-lists known technical/product/tool names, exempts structural and technical tokens and lines (file extensions, ALLCAPS doc names, code identifiers, paths, git diff/index headers), and requires adjacent personal-data context (honorifics, sign-offs, contact cues) before masking a NAME candidate; HANDLE keeps its default masking with only structural-line handles exempted. False-positive candidates are still recorded as findings, but their replacement is cleared so stored content is preserved. High-precision classes (EMAIL/IP/CC/SSN) and all secret blocking remain strict. The change is forward-only and does not alter already-stored data.
- **Grafana no longer logs a startup `level=error` for a missing `provisioning/plugins` directory** — an empty `plugins/.gitkeep` is now shipped so the provisioning path exists (TD-538).

## [2.7.0] - 2026-06-16

### Upgrade Instructions

- **After updating, run two steps:**
  1. `./scripts/install.sh <project-dir>` — syncs the new `src/memory/` modules, the `aim-tracking-rotate` skill, the updated session-close workflow, and the cap-contract seed templates into your installation. No data is touched; existing oversight files are not overwritten.
  2. `~/.ai-memory/scripts/stack.sh restart` — recreates the running services so they pick up the updated code. (The installer brings services up with `--no-recreate`, so a running container keeps its previous code until a restart.)
- **No database migration is required.** The new injection-freshness read filter is backward-compatible — points written before this release (which lack the `is_current` field) continue to be returned; only points explicitly marked superseded are excluded.
- **Your existing oversight files are never overwritten** (no-clobber). They keep their current shape; the cap-contract front-matter applies to files scaffolded into a fresh project, and existing files can be brought into line manually or via `aim-tracking-freshness` / `aim-tracking-rotate`.

### Added

- **Oversight-file cap enforcement (`aim-tracking-rotate`)** — governed oversight files now carry a machine-readable cap contract in their front-matter (`class`, `read_path`, `owns`, `cap_lines`, `cap_kb`, `rotation_trigger`, `archive_target`, `index_file`, `reconciliation`). A new `aim-tracking-rotate` skill provides:
  - **`--check`** — a session-close gate that fails (and blocks closeout) when any governed file exceeds its line or byte cap, printing the offending file and a remedy. Enforced for every governed file.
  - **`--apply`** — archives the oldest entries of the append-only decision log into a dated shard with a maintained manifest index, atomically and with per-entry count conservation (never splits, loses, or duplicates an entry). If an entry being archived shares its id with an already-archived entry of identical content, the move is a safe replay and is skipped (so an interrupted run can be re-applied); if the ids match but the content differs, `--apply` refuses — exiting non-zero and leaving both the live file and the shard untouched — rather than silently overwriting or dropping a body. Table-format registers (blockers/risk) and multi-table indexes are check-only for now; they are rotated by hand until format-aware support lands.
- **Per-class oversight seed templates** carrying the cap contract, plus a new `project-status.md` heartbeat seed scaffolded and populated in place during project init.

### Changed

- **Session-close workflow** now enforces caps before completing, writes the `project-status.md` routing heartbeat in place (one datum, one home), and archives the session handoff. Decision-log entries are prepended newest-first so archival always sheds the oldest.
- **Tracking-freshness (`aim-tracking-freshness`)** — bug/tech-debt INDEX status cells are now length-bounded (previously rendered verbatim and unbounded); closed records beyond the ten most recent are sharded to a `CLOSED.md` file with an index pointer; generated INDEX files carry the cap contract; an over-cap WARNING is emitted on regenerate. Open/closed classification is unchanged.
- **Memory save (handoff/insight)** — saved content is now bounded to a single embedding vector with a pointer to the full file on disk, instead of fanning a large handoff into many injectable chunks. The full file is preserved on disk unchanged. This structurally resolves the recurring bootstrap `[FALLBACK-NEEDED]` condition (a compliant handoff fits the bootstrap budget).
- **Injection freshness** — superseded `discussions` memories are now excluded at read time via an `is_current` soft-delete filter (exclude-only-superseded; legacy points are retained). Saving a new handoff/insight auto-supersedes the prior one for the same agent within the same project scope; the opt-in `--supersedes` flag is project-scoped and refuses cross-project ids. Bootstrap Layer-3 insights are retrieved by recency (deterministic) rather than by semantic similarity, and the `agent_insight` decay half-life is shortened from 180 to 90 days.

## [2.6.0] - 2026-06-16

### Upgrade Instructions

- **Existing installs**: re-run `./scripts/install.sh <project-dir>` to pick up the `aim-sot` skill surface + agent-guidance files (both deploy on every install).
- **Embedding image (TD-626)**: run `~/.ai-memory/scripts/stack.sh restart` to recreate services and pull the prebuilt GHCR embedding image (`ghcr.io/hidden-history/ai-memory-embedding`). `scripts/install.sh` brings services up with `--no-recreate`, so a running `embedding` container keeps its previous locally-built image until a restart. Fresh installs pull the image automatically.
- **aim-sot hooks**: the SOT digest/drift hooks auto-register on install for all supported CLIs (default-on); set `AI_MEMORY_SOT_HOOKS=off` in `docker/.env` before install to opt out.
- **Maintainer (one-time)**: set the `ai-memory-embedding` GHCR package to **Public** (repo → Packages → Package settings → Change visibility) so anonymous `scripts/install.sh` pulls succeed without authentication; until then those pulls fall back to a local source build.

### Added

- **`aim-sot` Source-of-Truth subsystem** — new `aim-sot` skill that tracks where the
  canonical truth lives for each boundary of the user's own project. A committed
  `.sot/registry.yaml` (in the user's own repo) is the registry of record; the skill
  ships the schema, templates, and a three-mode engine:
  - **consult** — read-only query over the registry (served from the derived memory
    cache, falling back to the committed file); answers "where does X live / who owns it"
    for any component.
  - **detect-propose** — hybrid auto-discover → propose: scans for candidate components,
    computes actual state (SHA-256 of each `sot_location` file), and emits a **proposed
    patch** on drift or new candidates. **Never writes the registry** — the propose-only
    guarantee is unconditional; every registry change goes through the human-review +
    verify gate. The baseline SHA is held (not advanced) when drift is detected, so the
    proposal re-fires until a human confirms the change. Cold-start `drift_status` is
    `unverified`, not `clean`.
  - **verify** — 16-check gate (Schema · Referential · Completeness · Content) returning
    PASS / CONDITIONAL / FAIL. K1 (content-hash check) reports CONDITIONAL — not a
    silent pass — when no baseline exists. Verdicts distinguish checks that ran and
    produced a result from no-op/inert checks and skipped-no-baseline checks.

  Two runtime caches support the feature: a per-install drift cache
  (`~/.ai-memory/drift-state/sot_drift_{project_id}.json`, machine-local, never
  committed) and a derived memory cache (Qdrant `conventions` collection,
  `memory_type=sot_entry`, rebuildable from the committed registry at any time via
  `detect-propose reindex`). The session-start digest hook and drift Stop hook are
  **auto-registered on install for all supported CLIs** (Claude Code, Codex, Cursor,
  Gemini) — default on; set `AI_MEMORY_SOT_HOOKS=off` in `docker/.env` to skip
  registration. The engine also runs standalone (`detect-propose run`) as the default
  no-hook path. All trigger paths are fail-open (exit 0 on any error).

  **Data safety**: SOT `owner` and `added_by` fields carry GitHub handles that must
  survive the shared PII scanner intact. For `sot_entry` writes only, the scanner's
  `HANDLE` (GitHub @-handle) redaction is exempted so ownership attribution is
  preserved faithfully in the derived cache; all other masking — secrets, email
  addresses, IP addresses, SSNs — is unchanged for SOT entries and for every other
  memory type.

- **Per-source budget ledger in `select_results_greedy`** — `meta["per_source"]` now
  carries a per-collection breakdown of `requested_tokens`, `loaded_tokens`, and
  `dropped` counts by reason (`budget_exceeded`, `score_gap`, `freshness_block`,
  `dedup`, `already_injected`, `empty_content`). Budget-exceeded drops include a
  `tokens` tally so operators can verify reconciliation:
  `loaded_tokens + dropped["budget_exceeded"]["tokens"] == requested_tokens` per
  collection. The ledger is written to each `injection-log.jsonl` event under
  `per_source`. Observe-only: selection output is unchanged. (`injection.py`,
  `context_injection_tier2.py`)

- **Sanctum content-drift detection (`aim-content-drift`)** — a new skill that
  compares an operator's scaffolded sanctum files (BOND, CAPABILITIES, CREED, INDEX,
  LORE, MEMORY, PERSONA, PULSE) against the reference templates and surfaces
  recommended additions/removals with rationale when the templates evolve. Detection
  is read-only and never overwrites operator content: a section the operator has
  written or customized is never recommended for removal. Intentional divergences can
  be acknowledged in a per-project, diff-reviewable file so they stop resurfacing
  until the reference changes again. Reference fingerprints ship alongside the
  templates.
- **Agent-guidance file across all supported CLIs** — the installer now ships an
  AI-Memory guidance file into each project for every supported CLI, auto-loaded at
  session start, in that CLI's own always-on convention. It explains how to work with
  the memory system (the per-CLI memory commands, automatic recall, project scoping)
  and the general engineering conduct AI-Memory expects. Each CLI's own command names
  are used (Gemini and Cursor: `search-memory` / `memory-status` / `save-memory`;
  Codex: `search-memory` / `memory-status`):
  - **Claude Code** — AI-Memory-owned `.claude/rules/ai-memory.md`.
  - **Gemini CLI** — AI-Memory-owned `AI-MEMORY.md` at the project root, registered in
    `context.fileName` in `.gemini/settings.json` by appending (never dropping
    `GEMINI.md` or any user-set entries; the user's `GEMINI.md` is never written).
  - **Cursor** — AI-Memory-owned `.cursor/rules/ai-memory.mdc` with
    `alwaysApply: true`; never touches other `.mdc`, `.cursorrules`, or `AGENTS.md`.
  - **Codex** — a managed marker-block (`<!-- BEGIN AI-MEMORY -->` …
    `<!-- END AI-MEMORY -->`) in the project-root `AGENTS.md`, inserted if absent and
    replaced in place on update. A backup is made and the write is atomic; everything
    outside the markers is preserved byte-for-byte.

  Every CLI's delivery is own-file or managed-block, idempotent on re-install, and
  zero-clobber of user-authored files. Deployed on both fresh installs and in-place
  updates.

- **`aim-lore-hygiene` skill** — per-operator hygiene for always-injected sanctum
  files (`LORE.md`, `MEMORY.md`). Enforces the ~200-line cap, flags files crossing
  the ~80%-of-cap compaction trigger, and applies the prune-vs-archive decision
  rule: marker-tagged entries are deleted (superseded/contradicted/expired-TTL/
  full-entry strikethrough), archived to a local cold-tier file with a one-line
  hot-file pointer (stale-but-meaningful), or deduped. Markers are anchored in the
  **leading position only** (after the bullet/number prefix, or in the first table
  cell), so prose that merely mentions or ends in a marker token is kept, never
  pruned; partial strikethrough with live un-struck text is kept. The parser is
  **structure-aware**: only genuine content entries (bullets, paragraphs, table
  content rows) are ever classified or deduped. Code fences (the whole block, info
  string and all), thematic breaks (`---`/`***`/`___`), table header+separator
  rows, and ambiguous constructs (blockquotes, indented code, raw HTML) are opaque
  passthrough — copied byte-for-byte, never classified, deduped, or split — so a
  marker token inside a fence or a tagged table header can never corrupt the file
  (**keep-when-uncertain** is the safety posture: anything not confidently
  structural-or-content is kept intact). A marker-tagged table content row is dropped
  in place (archived rows still reach the cold tier) so the table stays well-formed
  and no marker/pipe leaks into the hot file. Read-only
  **dry-run by default**; `--apply` writes a timestamped backup first and never
  auto-truncates recall-value content (over-cap files with no mechanical actions are
  flagged for a manual/LLM summarization pass). Built as a thin `SKILL.md` over an
  external, unit-tested `scripts/lore_hygiene.py` invoked by path (W-07
  skills-with-scripts standard). This is FILE-content hygiene, distinct from
  `aim-purge` (Qdrant-point purging).

- **`docs/parzival/` POV docs refreshed (TD-544)** — three pre-existing doc-drift
  items corrected:
  - `data/` path under `_ai-memory/pov/` fixed to `knowledge/` in both
    `README-POV.md` and `INSTALL-GUIDE-POV.md` (factual error in user-facing docs).
  - `README-POV.md` project-structure tree refreshed to current layout: stale
    `(v2.1)` label dropped; `scripts/`, `module-help.csv`, and
    `STEP-FILE-TEMPLATE.md` added; skills list updated to reflect current skill set
    (`aim-agent-sanctum-init`, `aim-lore-hygiene`, `aim-tracking-freshness` added;
    `aim-bmad-dispatch` removed); templates list and `workflows/` directory updated
    to match current on-disk contents.
  - `INSTALL-GUIDE-POV.md` gains an `add-project` / shared-stack section documenting
    the `INSTALL_MODE=add-project` flow: when it triggers, what the installer skips
    vs. runs, prerequisites, per-project configuration, and verification steps.

### Changed

- **Agent-guidance files now refresh on every install** — existing installations
  pick up updated guidance automatically by re-running
  `./scripts/install.sh <project-dir>`. No special flag is needed; the guidance
  file for each configured CLI is deployed on every install, not only on the
  initial setup.

- **Sanctum templates** — aligned the eight scaffolded sanctum files (`CREED`,
  `PERSONA`, `BOND`, `LORE`, `MEMORY`, `CAPABILITIES`, `INDEX`, `PULSE`) to a
  per-file memory-type content model: each file states its memory type, and content
  that duplicated a canonical source held elsewhere is replaced with a pointer.
  `CAPABILITIES` points to the live `parzival.md` `<menu>` instead of a
  hand-maintained workflow table; the `CREED` anti-pattern catalog and the one-time
  `LORE` bootstrapping guide move to new `references/` files (copied into every
  sanctum) so they no longer load every session; `MEMORY` and `PULSE` point to the
  `aim-lore-hygiene` skill for the curation procedure. Content moves only — the
  eight-file structure is unchanged.

- **TD-626** — The embedding service image is now prebuilt and published to GHCR
  (`ghcr.io/hidden-history/ai-memory-embedding`) by a new
  `publish-embedding-image` workflow, and `docker compose` / `scripts/install.sh`
  pull it instead of baking the Jina v2 + bm25 models from HuggingFace on every
  run. The bake downloads the models from HuggingFace, which rate-limits (HTTP
  429) shared CI-runner egress IPs and intermittently failed both the install and
  E2E jobs. The compose `embedding` service keeps its `build:` block as a
  source-build fallback (`pull_policy: missing`), so a registry/cache miss still
  bakes locally. As defense-in-depth for that fallback bake, an optional
  `HF_TOKEN` BuildKit secret raises the HuggingFace rate limit, and
  `huggingface_hub` is exact-pinned to `1.18.0` so 429 responses are honored with
  precise backoff. The published image is multi-arch (`linux/amd64,linux/arm64`) so
  Apple-Silicon operators get a native image. CI builds the embedding image from
  source (rather than pulling) when a change touches embedding-relevant paths, so
  the E2E job always tests the code under review rather than a stale prebuilt image.

  **Operator note:** after the first publish, a maintainer must set the
  `ai-memory-embedding` GHCR package to **Public** (repo → Packages → Package
  settings → Change visibility) so anonymous `scripts/install.sh` pulls succeed
  without authentication; until then those pulls fall back to a local source build.
  A bare `docker compose up` expects the published image and relies on Compose's
  build fallback to bake locally if it is absent; the scripted paths
  (`scripts/install.sh`, CI) make that pull→build fallback explicit.

  **Upgrade note (existing installs):** `scripts/install.sh` brings services up
  with `--no-recreate`, so it will not recreate an already-running `embedding`
  container — an existing install keeps its previous locally-built image. After
  updating, run `~/.ai-memory/scripts/stack.sh restart` to recreate services and
  pull the prebuilt GHCR image. (Fresh installs pull it automatically.)

### Fixed

- **`aim-sot consult` no longer returns stale registry entries** — consult read the
  derived memory cache (5b) first and returned it whenever non-empty, with no binding
  to the committed `.sot/registry.yaml`, so after any registry edit (or when another
  project's rows shared the `group_id`) it shadowed the file with stale or cross-state
  data. Consult now uses the cache only when every row's stamped `registry_sha` matches
  the committed file's SHA **and** the row count matches the committed entry count; a
  SHA mismatch or count shortfall falls back to the committed file. Consult remains
  strictly read-only. Also: `verify --proposal` now flags a proposal that lacks an
  `entries` key instead of silently verifying it as empty; `detect-propose run` prunes
  drift-cache records for components no longer in the registry (parity with reindex);
  and the SKILL.md 5b-cache field name is corrected to `type=sot_entry` to match the
  engine. (`aim_sot_consult.py`, `aim_sot_verify.py`, `aim_sot_detect_propose.py`, `SKILL.md`)

- **BUG-302: tier-2 fallback marker now shows `remaining=` alongside `tokens=` and `budget=`**
  — the marker previously printed `tokens=<N> budget=<total>`, which read as a false
  contradiction when `tokens < budget` but `tokens > budget − tokens_used`. Adding
  `remaining=budget−tokens_used` makes the correct reject self-evident.
  (`context_injection_tier2.py` marker block)

- **`aim-sot` is now discoverable as a skill in installed projects** — the skill's
  engine lives under `_ai-memory/skills/aim-sot/`, which the installer copied as
  canonical files but never surfaced to `.claude/skills/`, so Claude Code could not
  index it even though its session/drift hooks were registered. `deploy_ai_memory_skills`
  now generates a thin discovery shim in `.claude/skills/` for `aim-*` skills that live
  under `_ai-memory/skills/` without a full copy. It runs on every install (matching
  aim-sot's always-on SOT hooks), never clobbers a skill that already has a full copy,
  and is idempotent on re-install; the `aim-*` prefix deliberately excludes the
  oversight-internal `parzival-save-*` skills. The `AI_MEMORY_SOT_HOOKS` opt-out is now
  documented as a commented line in `docker/.env.example`.
  (`scripts/install.sh`, `docker/.env.example`)

- **aim-sot verify** — `verify run --registry <path>` no longer crashes on a
  non-conforming (flat) registry path. A registry outside `<root>/.sot/` makes the
  project root resolve to `None`, which previously reached the path checks
  (R1/R4/C3/discovery/K1) unguarded and raised `TypeError`. Declared locations now
  resolve relative to the registry's own directory so the gate emits a structured
  verdict, and auto-discovery is skipped for a flat root (matching `detect-propose`)
  so no spurious "discovered component(s) not registered" findings are reported.

- **aim-sot 5b reindex** — `detect-propose reindex` now persists `sot_entry` rows.
  The core payload allow-list rejected the reindex's `source_hook`, so every derived-
  memory write silently failed and the cache stayed empty. The allow-list now accepts
  it. When writes are rejected by validation the command reports the rejection
  accurately and exits non-zero, instead of misreporting a connectivity problem; a
  genuinely unreachable store still exits zero and leaves the existing cache intact.

- **aim-sot cold start** — `detect-propose run` now runs the discovery scan and emits
  candidate proposals when no `.sot/registry.yaml` exists yet, instead of bailing with
  a circular message. Discovery from zero stays propose-only — the registry is never
  created or written — and the empty-state output points to the bootstrap steps
  (discover → copy → verify → approve).

- **aim-sot consult flag ordering** — `consult` now accepts `--json` and `--registry`
  after the subcommand (e.g. `consult list --json`, `consult get <id> --registry PATH`),
  matching `detect-propose`/`verify` and the documented invocation. Previously these
  flags were only accepted before the subcommand, so the documented form failed with
  `unrecognized arguments`.

- **BUG-318** — `aim-github-search` now defaults to the `github` Qdrant collection where
  GitHub content lives. The as-documented invocation (no `--collection` flag) returns
  results instead of zero; `--collection` remains supported for cross-collection queries.

- **TD-612** — Removed a source of intermittent CI failures in which a leaked
  `flush-watchdog` daemon thread (started by `trace_flush_worker` tests) could reach its
  stall deadline and call `os._exit`, hard-killing an already-passing `pytest` run with
  no failing test, assertion, or traceback. A session-wide test guard now neutralizes the
  watchdog's process-exit in-process — so an orphaned daemon bound to any re-imported
  module generation can no longer terminate the runner — and still asserts that no
  `flush-watchdog` thread leaks past a test, turning a leak into a loud, attributable
  failure rather than a silent kill. The watchdog's production stall-restart behavior is
  unchanged (test-only fix).

## [2.5.0] - 2026-06-03

### Added

- **RISK-021 / TASK-071 Phase 4(d).0** — New standalone script
  `scripts/memory/store_best_practice.py` externalizes the "Phase 4: Store to
  Database" Python block that was previously inlined in
  `_ai-memory/skills/aim-best-practices-researcher/RESEARCH-METHODOLOGY.md` and
  `SKILL.md`. The script accepts `--content`, `--session-id`, `--group-id`
  (optional), `--source-hook`, `--domain`, `--tags`, `--source`, and
  `--source-date`. Invoke via
  `scripts/memory/run-with-env.sh store_best_practice.py …` (BP-013 Pattern B).
  Companion unit tests in `tests/unit/test_store_best_practice_script.py`
  (importlib + sys.modules patching, mocked resolver at call boundary per DEC-109).

- **TASK-071 Items 13–14 (#167)** — Standalone scripts externalize the inline
  Qdrant query blocks from the GitHub and Jira search skills into
  `_ai-memory/skills/aim-github-search/scripts/query.py` and
  `_ai-memory/skills/aim-jira-search/scripts/query.py`, and the
  GitHubSyncEngine invoker from `aim-github-sync` into
  `scripts/memory/github_sync_runner.py`. All scripts are behavior-preserving
  and invoked via `scripts/memory/run-with-env.sh` (BP-013 Pattern B).

- **TASK-071 Groups 1–2 (#169)** — Standalone scripts externalize the inline
  programs from four core maintenance skills into
  `scripts/memory/purge_collections.py` (aim-purge),
  `scripts/memory/freshness_report.py` (aim-freshness-report),
  `scripts/memory/pause_updates.py` (aim-pause-updates), and
  `scripts/memory/refresh.py` (aim-refresh). Four reusable Bash helpers
  (`check_api_key.sh`, `cwd_sentinel.sh`, `inbox_inject.sh`,
  `validate_model.sh`) added under
  `_ai-memory/skills/aim-model-dispatch/scripts/lib/` replace duplicated
  inline blocks across `aim-model-dispatch` step files. All behavior-preserving;
  invoked via `scripts/memory/run-with-env.sh`.

### Changed

- **RISK-021 — Deliberate behaviour change (DEC-108 C-1 / DEC-106
  correctness-restoration carve-out)**: `aim-best-practices-researcher` Phase 4
  previously resolved project scope via `os.environ.get("AI_MEMORY_PROJECT_ID")`
  with a `RuntimeError` on unset (env-only). The new `store_best_practice.py`
  script routes scope through `resolve_project_id(cwd=os.getcwd(),
  explicit=args.group_id)`, which supports four tiers — explicit `--group-id`
  flag → `AI_MEMORY_PROJECT_ID` env → `.ai-memory-project` marker file → git
  remote → fail-loud `ValueError`. This aligns the BP write path with every
  other memory script already updated by PR #160 (BUG-314). Across 7 Session-61
  runs the old env-only path fragmented into 4 distinct scope values; the new
  path is deterministic. This change is disclosed per DEC-105 / DEC-108 C-1 and
  must appear in the PR description.
- **Langfuse SDK upgraded to `>=4.7.0,<4.8.0`** (was `>=4.0.6,<4.1.0`; resolves
  to 4.7.1). `uv.lock` regenerated. V3→V4 governance comment headers refreshed
  across trace-emitting modules.
- **Langfuse agent trace organization (BP-169 G1–G4).** Agent identity is mapped
  to `user_id` and agent role to a trace tag/metadata (`_resolve_user_id` /
  `_resolve_role_tag`); `LANGFUSE_TRACING_ENVIRONMENT` is now supported and
  validated to partition traces within a project by deployment stage/install.

### Fixed

- **BUG-315 — Trace-flush worker wedge (stuck-backlog data stall).** The
  trace-flush worker could wedge indefinitely when the Langfuse backend passed
  its health check but hung mid-flush, silently halting all trace delivery (a
  ~26K-trace backlog accumulated). `src/memory/trace_flush_worker.py` is
  hardened: an HTTP `/api/public/health` preflight skips the *drain* (not the
  loop) when the backend is unreachable; a stall watchdog hard-exits a
  genuinely-wedged worker so Docker (`restart: unless-stopped`) restarts it into
  a draining state; the heartbeat is taken at the top of each loop (liveness =
  loop cycling, not a blocking flush); the buffer drains oldest-first via
  `os.scandir`+sort; files are unlinked only after a successful `flush()`
  (loss-safe); poison buffer entries are skipped per-entry; and graceful
  shutdown drains within a bounded deadline. (BUG-315)

### Upgrade Instructions

- **After updating, run `~/.ai-memory/scripts/stack.sh restart`.** The
  `trace-flush-worker` is image-baked (its Langfuse SDK and worker code are
  built into the container image via `docker/Dockerfile.worker`), so pulling the
  new files and re-running `install.sh` alone does **not** upgrade the running
  worker — without the restart it keeps running the old SDK and old code.
  `stack.sh restart` rebuilds the image-bake services and waits for health.

## [2.4.5] - 2026-05-29

### Fixed

- **BP-162 / TD-583 regression** — `docker/prometheus/Dockerfile`: parent directory
  `/etc/prometheus/` inherited mode 0644 from `COPY --chmod=644` (BuildKit defect
  moby/buildkit#5943), breaking `os.makedirs()` stat checks at prometheus-init
  startup with the named volume mounted at `/etc/prometheus/runtime`. Pattern A
  fix applied: explicit `RUN mkdir -p && chmod 755` BEFORE `COPY --chmod=644`,
  plus build-time `stat` guardrails and a runtime integration test that
  exercises the actual init flow with the production volume layout. Same
  pattern applied defensively to `docker/langfuse/Dockerfile`. See
  `oversight/knowledge/best-practices/BP-162-docker-buildkit-copy-chmod-parent-dir-pattern-2026.md`.
- **TD-583** — Image-bake the remaining 4 WSL2 single-file bind-mount fragility sites into their service images. `docker/prometheus/Dockerfile` extends `python:3.12-alpine` and bakes the 3 prometheus-init config templates (`web.yml`, `prometheus.yml`, `gen-prometheus-config.py`) into the image; `docker/langfuse/Dockerfile` extends `clickhouse/clickhouse-server:24` and bakes `clickhouse-config.xml` into `/etc/clickhouse-server/config.d/retention.xml`. Both compose files updated to use `build:` + local `image:` tag; single-file bind-mounts removed. Closes the SG-1 fragility class structurally for all 6 affected services (qdrant + grafana from TD-582, prometheus-init + langfuse-clickhouse from TD-583). (TECH-DEBT-583)
- **TD-584** — Change `streamlit` service `restart: on-failure:3` to `restart: unless-stopped` in `docker/docker-compose.yml`. The `on-failure` policy does not restart containers that exit cleanly (exit 0); Docker daemon restart left streamlit alone needing manual `docker compose up -d streamlit` while all other services auto-recovered. Aligns with codebase convention; inline comment updated to reflect corrected explicit value. (TECH-DEBT-584)
- **TD-585** — Harden `scripts/install.sh` verification gates: (1) qdrant port-check in `verify_services_running` (add-project mode) replaced with `docker inspect` healthcheck-status poll with 45 s timeout — tolerates qdrant startup latency without false-fail immediate probe; (2) `pip install -e` failure in both `install_python_dependencies` (full mode) and `update_shared_scripts` (add-project mode) promoted from WARNING to STOP-GATE — exits 1 with explicit error and retry instructions; (3) early `.env` existence assert added post-`persist_user_choices_to_env` to catch the F-4 edge case where `.env.secrets` exists but `.env` was not created. (TECH-DEBT-585)
- **TD-587** — Add explicit `compose build --no-cache` for image-bake services to `stack.sh` `cmd_start`, matching the `install.sh` pattern. Core services (qdrant, grafana, prometheus-init) rebuilt unconditionally via `IMAGE_BAKE_SERVICES`; `langfuse-clickhouse` rebuilt separately via `IMAGE_BAKE_SERVICES_LANGFUSE` when `LANGFUSE_ENABLED=true`. Future additions go into whichever array matches their profile. Closes the silent-staleness blindspot where a source edit to a baked file was not picked up on `stack.sh restart`. (TECH-DEBT-587)

### Changed

- **TD-586** — Hygiene batch: drop `fix-r3` process token from `install.sh` `--ignore-buildable` comment; update `test_compose_bare_up_topology.py` module docstring to reference both qdrant + grafana entrypoint shims and TD-583 image-bake additions; clarify `stack.sh` `cmd_stop` comment to note that default-scope services (qdrant, embedding, classifier-worker) are always stopped without a profile flag. (TECH-DEBT-586)

### Upgrade Instructions

**From v2.4.4 → v2.4.5:**

1. `git pull --ff-only && git checkout v2.4.5`
2. `./scripts/install.sh <your project>`
3. `~/.ai-memory/scripts/stack.sh restart` — **REQUIRED**: rebuilds the image-bake services
   (`prometheus-init`, `langfuse-clickhouse`) from the fixed Dockerfiles. Without this,
   `prometheus-init` keeps running the old image and the monitoring fix is not applied.
4. Verify: `prometheus-init` exits 0; `prometheus` + `grafana` report healthy.

## [2.4.4] - 2026-05-27

### Added

- `aim-tracking-freshness --verify-code-state` flag — cross-checks every open BUG/TD record against the source git history to detect phantom-open candidates whose fix commits are already reachable from `main`. Confidence is scored HIGH / MEDIUM / LOW per the skill auditor's algorithm: HIGH when a main-reachable fix commit overlaps a file path cited in the record body and the record mtime predates the fix timestamp; MEDIUM when a main-reachable commit exists without file-path overlap; LOW when only inline evidence (PR ref / SHA in the body) exists without a main-reachable commit, or when a matching `Revert "…<RECORD-ID>…"` commit on `main` downgrades a fix. Source repo resolved via `--source-repo`, `AI_MEMORY_SOURCE_REPO` env var, or `../ai-memory` relative to the oversight root. Reports a `PHANTOM-OPEN CANDIDATES` section on stdout plus a `oversight/reports/PHANTOM-OPEN-CANDIDATES.md` sidecar (created and overwritten each run). Advisory only — does not affect the `--check` exit-code contract. Graceful skip with a `NOTE` to stderr when the source repo or `git` binary is unavailable. Supports `--last-n-sessions N` and `--bug-id RECORD-ID` for scoped sweeps. (TECH-DEBT-547)
- `aim-tracking-freshness` decision-log body coverage check — folded into `--check` (and `--write`) default. Parses `oversight/tracking/decision-log.md`, splits at the first `---` separator into a header block and body, expands range notation (`DEC-PM(\d+)-D(\d+)\.\.D(\d+)`) into individual DEC IDs, and diffs against `### DEC-PMnnn-Dn` body headings. Emits `DRIFT-DEC-MISSING` (✗) when a header reference has no body entry — the PM #299 closeout failure mode — and contributes to `--check` exit 1. Emits `DRIFT-DEC-ORPHAN` (ℹ) when a body heading lacks a header reference; informational only, does not affect exit code. Graceful skip with a `NOTE` to stderr when `tracking/decision-log.md` is absent. (TECH-DEBT-554)
- `aim-tracking-freshness` POV skill (`_ai-memory/pov/skills/aim-tracking-freshness/`) — scans `oversight/bugs/BUG-*.md` and `oversight/tech-debt/TECH-DEBT-*.md`, classifies each record as open or closed from its authoritative `**Status**` header, and regenerates both `INDEX.md` files on demand. Replaces the manual rebuild process introduced in PM #296. `--check` mode is strictly read-only and prints a staleness report (divergences, companions excluded, orphan INDEX rows, missing records); `--write` regenerates both INDEX files and then prints the same report. Handles three Status header formats (colon-outside-bold (`**Status**:`), colon-inside-bold (`**Status:**`), and table-row (`| **Status** | … |`)), two closed-class keyword sets (bugs vs tech-debt), and the `LIKELY FIXED` open-class edge case. Companion files sharing a numeric ID are excluded from INDEX generation and listed explicitly in the report. Oversight root is configurable via `--oversight-root` or `AI_MEMORY_OVERSIGHT_ROOT` env var. (PLAN-028 P0-4c)
- `_ai-memory/pov/templates/tech-debt-report.template.md` — new template for technical-debt records, matching the existing bug-report template style. Previously the tech-debt tracker had no template; the skill now has an explicit source-of-truth for the `TECH-DEBT-NNN` filename convention and status-token contract. (PLAN-028 P0-4c)
- `_ai-memory/pov/templates/bug-report.template.md` filename-convention clause — documents the slug-optional `BUG-NNN.md` / `BUG-NNN-<slug>.md` convention accepted by `aim-tracking-freshness`. (PLAN-028 P0-4c)
- Session-start (`[ST]`) and quick-status (`[SU]`) workflows now read the compact `bugs/INDEX.md` and `tech-debt/INDEX.md` Quick Stats table for bug and TD totals, instead of scanning individual record files. Keeps per-session startup context cost bounded as the trackers grow; a missing INDEX degrades gracefully without surfacing raw record file content. (PLAN-028 P0-4c)
- `github_sync_usable` derived config flag — set by `validate_github_config()`, True only when `github_sync_enabled` is true *and* the GitHub token and repo are both present and valid. GitHub sync entrypoints now gate on this flag so a misconfigured-but-enabled sync skips cleanly instead of raising at `MemoryConfig()` construction time. (PLAN-028 P1, TECH-DEBT-166 RC-B)

### Changed

- **PLAN-028 P1B / W-09 — System-wide required-explicit project scope.** Every public store and every public search entry point now requires a non-empty `group_id` parameter and fails loudly (`ValueError`) when missing or empty; the cross-project "graceful degradation: search without filter" fallback in `MemorySearch.search` and `search_both_collections` was removed entirely. `detect_project()` itself now raises `ValueError` on resolution failure rather than silently returning the `"unknown-project"` sentinel, and the directory-basename fallback that produced silently-guessed project IDs for non-git working directories was removed (the `AI_MEMORY_PROJECT_ID` env var and git-remote slug remain the only resolution paths; edge-case sentinels for `/`, `~`, and `/tmp/build-*` are kept for now, tracked separately). Public APIs updated: `store_memory`, `store_memories_batch`, `store_github_code_blob_chunks_batch`, `store_agent_memory` (storage), `MemorySearch.search`, `MemorySearch.search_both_collections`, `MemorySearch.get_recent`, `MemorySearch.cascading_search`, `search_memories` (search). Every Claude Code capture / retrieval hook (15 active hooks), every cross-tool adapter (7 files in `src/memory/adapters/`), every active `scripts/memory/` capture+save tool, and the two enforced admin tools (`ingest_markdown.py`, `seed_best_practices.py`) now resolve `AI_MEMORY_PROJECT_ID` env-first then fall through to `detect_project()` with a fail-loud final branch. Capture hooks log `project_resolution_failed` and exit 0 (§1.2 Principle 4 — hooks never block Claude); retrieval hooks log and exit 0 silently (no UI disruption); user-invoked CLIs print a friendly error message and exit 2 (β-style treatment) rather than dumping a raw traceback. (PLAN-028 P1B / W-09; DEC-PM302-D1 / DEC-PM302-D2 / DEC-PM302-D4)
- The `conventions` collection (best practices) is now project-scoped: every store and every retrieve carries an explicit project `group_id`. The former cross-project "shared" tier was removed — `conventions` behaves like all other collections. (PLAN-028 P1 / W-01; FR16 amended)
- `store_best_practice()` and `retrieve_best_practices()` now require an explicit non-empty `group_id`; they fail loudly with a `ValueError` rather than guessing from the working directory, eliminating cross-project contamination of `conventions`. (PLAN-028 P1, DEC-PM298-D4)
- Conventions retrieval in the `new_file_trigger`, `best_practices_retrieval`, and Tier-2 context-injection hooks now passes the detected project as `group_id` instead of `None`, ending cross-project leakage of best-practice results. (PLAN-028 P1)
- GitHub sync entrypoints (`GitHubSyncEngine.__init__` and `_build_github_enrichment()`) now check `github_sync_usable` instead of `github_sync_enabled`. (PLAN-028 P1, TECH-DEBT-166 RC-B)
- `aim-best-practices-researcher` skill — Phase 1 database lookup now resolves the project from `AI_MEMORY_PROJECT_ID` and passes it as `group_id` when searching the project-scoped `conventions` collection; the `RESEARCH-METHODOLOGY.md` Phase 1 `sys.path` bootstrap now points at `~/.ai-memory/src` instead of the broken `Path.cwd() / "src"`. (PLAN-028 P1, TECH-DEBT-166 RC-A)
- `RouteTarget.shared` is now always `False` — all Tier-2 routed collections, including `conventions`, are project-scoped. The field is retained only because the `context_injection_tier2.py` hook still reads it. (PLAN-028 P1 / W-01)

### Fixed

- `docker/docker-compose.yml` removes the `monitoring` profile gate from `classifier-worker`; `scripts/install.sh` `start_services()` now builds and starts `classifier-worker` explicitly after `setup_collections` completes, on every install path including the default no-profile install. `qdrant` is its only hard `depends_on` dependency. Previously, any install that did not activate the `monitoring` profile silently skipped classification, leaving every captured memory permanently unclassified. On a non-monitoring install, `classifier-worker` receives `PUSHGATEWAY_ENABLED=false` (via the `PUSHGATEWAY_ENABLED=${MONITORING_ENABLED:-false}` line in the compose service definition) and skips the metric push entirely — no connection attempt is made. When monitoring is enabled but the pushgateway container is transiently unreachable, connection errors are caught, logged at WARNING, and never block the queue-drain loop. (TD-573)
- `scripts/install.sh` now writes `COMPOSE_PROFILES` and `MONITORING_ENABLED` to `docker/.env` at install time via `persist_user_choices_to_env`, reflecting the monitoring and GitHub sync selections made during installation. Before this fix, Docker Compose profile activation depended entirely on passing `--profile` flags at the CLI; any invocation that bypassed `install.sh` or `stack.sh` — plain `docker compose up`, a host reboot, or an IDE Docker action — silently dropped all profile-gated services. Additionally, `MONITORING_ENABLED` in `docker/.env` retained the static template default rather than the user's actual choice, causing `stack.sh` and direct `docker compose` invocations to disagree on whether monitoring was active. Both values are derived from the same `INSTALL_MONITORING` / `GITHUB_SYNC_ENABLED` selection variables that drive `start_services`'s profile flags, and are written idempotently so reinstalls and selection changes are reconciled correctly. (BUG-311, TD-574)
- test: fix `test_duplicate_in_pending_queue_detected` env-var fixture under W-09 — adds `AI_MEMORY_PROJECT_ID` env setup so `_get_group_id()` returns early without invoking `detect_project()`, restoring the dedup fast-path assertion. (PLAN-028 P1B)
- test: fix missing `group_id` in remaining integration tests — adds explicit `group_id=` kwarg to all `store_memory`, `store_agent_memory`, `store_memories_batch`, and `search` call sites across `test_e2e_cross_phase.py`, `test_embedding_routing.py`, `test_seeding.py`, and `test_search.py`; adds `group_id` positional arg to `create_point_from_template` calls in `TestCreatePointFromTemplate`; adds `--group-id` CLI arg to `TestMainCLI` test argv so `seed_best_practices.main()` can pass the W-09 required-project-scope gate. (PLAN-028 P1B)
- The `Env Drift Gate` CI workflow now installs the full project dependencies (`-r requirements.txt`) before running the Pydantic completeness check, so `MemoryConfig` imports cleanly and `httpx` and other transitive dependencies are available. (BUG-312)
- `tests/integration/test_docker_stack.py` `docker_stack` fixture now provisions `docker/.env` from `docker/.env.example` when the file is absent, and removes it on teardown only if the fixture created it. The `classifier-worker` service (now always part of the default Compose scope after the TD-573 profile removal) marks `docker/.env` required, so a bare `docker compose up -d` in a clean CI checkout failed with a missing env-file error before this change. (BUG-311 follow-up)
- `scripts/install.sh` now extracts `COMPOSE_PROFILES` + `MONITORING_ENABLED` derivation into a new dedicated function `derive_and_persist_compose_profiles()` called from BOTH `INSTALL_MODE=full` AND `INSTALL_MODE=add-project` branches. The function derives values from shell-scope `INSTALL_MONITORING` / `GITHUB_SYNC_ENABLED` when set (the `full` install path), otherwise falls through to reading prior persisted state from `docker/.env` / `docker/.env.secrets` via `_read_env_key` (secrets-first; BUG-309 precedent). Idempotent and safe to re-run; preserves a clean skip on a first-time `add-project` install with no prior monitoring choice. Previously the derivation lived inside `persist_user_choices_to_env`, which is only called on the `full` install path; the `add-project` (update-in-place) path — the dominant operator scenario for any operator re-running the installer to add a project to an existing install — silently skipped the derivation entirely, leaving `COMPOSE_PROFILES=` blank in `docker/.env` and causing bare `docker compose up -d` invocations to silently drop all profile-gated services (monitoring stack, GitHub sync). The new function follows the 2024-2026 cross-paradigm consensus from Helm, Ansible, Puppet, Terraform, Kubernetes operators, Docker Compose, and Homebrew documented in BP-160 §7: installer-owned (Tier-1) derived state must be re-evaluated on every install run, both modes, via a dedicated subroutine called from both branches. Production-path integration test exercises the full `main()` flow on both `INSTALL_MODE` values plus a run-twice idempotency assertion; complementary structural-grep test asserts both call sites remain present in `install.sh`. Test-helper mirror of the new function matches production line-for-line. (BUG-311, TD-574)
- **Docker Compose bare-up resolves all secret-class values without `--env-file` flags** (TD-582). Refactored `prometheus-init`, `prometheus`, `grafana`, and `qdrant` services to consume secrets via the existing split `.env` + `.env.secrets` files using the compose `env_file:` directive. Operators running `docker compose up -d` directly — without `scripts/stack.sh` — no longer need to pass `--env-file .env --env-file .env.secrets`; the wrapper continues to work unchanged. The `qdrant` and `grafana` services each extend their upstream images via a small `Dockerfile` (`docker/qdrant/Dockerfile`, `docker/grafana/Dockerfile`) that bakes a shim translating canonical secret env names (`QDRANT_API_KEY` / `QDRANT_READ_ONLY_API_KEY` → `QDRANT__SERVICE__*`; `GRAFANA_ADMIN_PASSWORD` / `GRAFANA_SECRET_KEY` → `GF_SECURITY_*`) into each tool's native config namespace before exec'ing the upstream entrypoint. The image-bake delivery replaces an earlier host bind-mount approach and closes a host-reboot regression on Docker Desktop / WSL2 where the single-file bind-mount source could be cached under the docker-desktop-bind-mounts tmpfs and fail to remount, manifesting as `qdrant` exiting 127 with a runc "not a directory" mount error against `/usr/local/bin/td582-entrypoint.sh` (`grafana` is symmetrically affected once `monitoring` profile is active). If you were previously seeing `prometheus-init` exit 1, `qdrant` returning 401 on `/collections` despite a healthy `/readyz`, or `qdrant`/`grafana` exit-127 on container restart following a host reboot, this resolves both. Resolves the latent gap predicted by BUG-279 (PM #274) and confirmed during bare-up verification. (TD-582)

### Upgrade Instructions

**From v2.4.3 → v2.4.4:**

Installer-hygiene release for Docker Compose profile persistence. No data
migration. Your memories, credentials, and Parzival sanctum are untouched.

1. Pull the latest:
   ```bash
   cd /path/to/ai-memory
   git fetch origin && git checkout main && git pull
   ```

2. Re-run the installer against your project directory (volume-preserving —
   does **not** require `stack.sh nuke`):
   ```bash
   ./scripts/install.sh /path/to/your-project
   ```
   The installer persists your monitoring and GitHub-sync choices to
   `docker/.env` (`COMPOSE_PROFILES` + `MONITORING_ENABLED`) and rebuilds
   `classifier-worker`, which is now a default-scope service.

3. Verify the new keys persisted:
   ```bash
   grep -E "^(COMPOSE_PROFILES|MONITORING_ENABLED)=" ~/.ai-memory/docker/.env
   ```
   Both lines should be present with values matching your install choices.

After this release, a bare `cd ~/.ai-memory/docker && docker compose up -d`
(no `--profile` flag) brings up `classifier-worker` automatically — previously
it was skipped on any installation that did not activate the `monitoring`
profile, silently leaving every captured memory unclassified.

### Operator Remediation

Operators whose existing `~/.ai-memory/docker/.env` carries `COMPOSE_PROFILES=`
blank (visible via the grep in step 3) and have monitoring or GitHub sync
running should re-run step 2. The add-project install path now derives
`COMPOSE_PROFILES` from the persisted `MONITORING_ENABLED` and
`GITHUB_SYNC_ENABLED` values, so the re-run produces the correct
`COMPOSE_PROFILES=monitoring,github` (or `=monitoring` / `=github`, matching
your actual install) and the silent profile-skip on bare `docker compose up -d`
invocations is eliminated.

Operators upgrading from a release earlier than v2.4.3 should also follow the
v2.4.3 Operator Remediation section above (Jira project flags + secret-key
purge).

### TD-582 — Image-bake delivery (qdrant + grafana shims)

The `qdrant` and `grafana` services now use locally-built images
(`ai-memory-qdrant:v1.16.3` + `ai-memory-grafana:12.0.0`) extending their
upstream images with a small `Dockerfile` that bakes the TD-582 entrypoint
shim into the image filesystem. The installer rebuilds these two images
automatically on update — **no operator action required**.

This replaces an earlier short-lived host bind-mount delivery and closes a
host-reboot regression on Docker Desktop / WSL2 where single-file bind-mount
source paths cached under `docker-desktop-bind-mounts/` could go stale across
reboots, manifesting as `qdrant` exiting 127 with a runc "not a directory"
mount error against `/usr/local/bin/td582-entrypoint.sh`.

If you previously experienced any of these symptoms, they are resolved by
v2.4.4:

- `prometheus-init` exiting 1 on bare `docker compose up -d` (no `--env-file`)
- `qdrant` returning 401 on `/collections` despite a healthy `/readyz`
- `qdrant` or `grafana` Exited 127 after a host reboot or Docker daemon restart

Pre-existing wrappers (`scripts/stack.sh`, etc.) continue to work without
changes. No data migration. Your memories, credentials, Parzival sanctum,
and DocIntel data are untouched.

## [2.4.3] - 2026-05-20

Installer-hygiene release. Three coupled gaps from the v2.4.0 BUG-277 split-env-file architecture and one pre-existing security-scanner provisioning gap.

### Fixed

- `scripts/install.sh` interactive credential-detection routines now read from `docker/.env.secrets` in addition to `docker/.env`. Pre-fix, the `discover_jira_projects()` and `configure_project_sources()` functions grepped `docker/.env` only, missing secret-class values that legitimately live in `docker/.env.secrets` post-BUG-277. The detection layer saw empty values and emitted misleading `Jira credentials not configured -- run fresh install` and `No GITHUB_TOKEN found` warnings, then durably wrote `jira.enabled: false` into `~/.ai-memory/config/projects.d/<project>.yaml` — silently disabling Jira sync for every project registered since v2.4.0. The fix substitutes the existing `_read_env_key` helper (secrets-first fallthrough, matches `MemoryConfig` tuple env_file and docker-compose `--env-file` precedence) at both detection sites for `JIRA_INSTANCE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `GITHUB_TOKEN`, and `GITHUB_SYNC_ENABLED`. (BUG-309)
- `scripts/install.sh` upgrade path now removes secret-class key *lines* from `docker/.env` entirely once their canonical values have been migrated into `docker/.env.secrets`. Pre-fix, `migrate_secrets_to_split_file` invoked `_blank_key_in_env` for defense-in-depth (BUG-286), which blanked the value but kept the line — leaking the configured-key inventory to any reader of `docker/.env` (chmod 644 / 640). The new `purge_migrated_secret_keys_from_env` helper iterates `ALL_SECRET_KEYS` and removes any line whose canonical value lives in `docker/.env.secrets`, preserving non-secret keys, comments, and ordering. Idempotent. Companion `verify_env_split.py` invariant I9 (strict-only) fails if any secret-class key name is present in `docker/.env`. (TD-551 line-removal)
- `scripts/install.sh` now tightens per-file permissions on `docker/` after each bulk-copy site via the new `apply_docker_dir_permissions` helper. Pre-fix, `cp -r "$docker_source/"* "$INSTALL_DIR/docker/"` preserved the source-clone modes (commonly chmod 755 on WSL DrvFs sources), so `docker/.env`, `docker/.env.example`, and `Dockerfile.*` artifacts ended up world-readable + executable on every install. The canonical mode matrix is now enforced: `.env.secrets=600`, `.env=640`, `.env.example=644`, `.env.secrets.example=644`, `Dockerfile*=644`. WSL-safe: chmod failures degrade to `log_warning` matching the existing `verify_env_split.py` I2 WSL-degrade contract. (TD-551 per-file chmod)
- `en_core_web_sm` spaCy NER model is now pinned as a pip dependency in `pyproject.toml` (wheel URL pointing at the model 3.8.0 release, paired with the existing `spacy>=3.8.0,<4.0.0` constraint). Pre-fix, `install.sh` invoked `python -m spacy download en_core_web_sm` after `pip install -e .`, but the download failed silently on in-place upgrade paths where the venv was reused — leaving `SecurityScanner` Layer 3 NER permanently degraded to L1+L2 with the load failure WARNING firing only on first scan and easily missed. The wheel pin makes model installation deterministic and idempotent across all install paths (fresh + in-place upgrade). The existing `python -m spacy download` invocation remains as a safety net. Companion: `SecurityScanner.__init__` now eagerly probes spaCy model availability when `enable_ner=True` and emits an explicit INFO log recording active layer state (`security_scanner_initialized layers=L1+L2+L3`, `layers=L1+L2 reason=spacy_model_missing`, or `layers=L1+L2 reason=ner_disabled_by_config`) so operators can confirm L3 coverage from the startup log alone. (TD-552)

### Operator Remediation

Operators who installed during the BUG-309 defect window may have projects registered with `jira.enabled: false` despite valid credentials in `docker/.env.secrets`. To re-enable Jira sync for an affected project, edit `~/.ai-memory/config/projects.d/<project>.yaml` and flip `jira.enabled` to `true` (and confirm `projects:` carries the expected key list). Reinstalls on v2.4.3+ will detect credentials correctly and write `jira.enabled: true` automatically.

Operators on a multi-user host who completed an in-place upgrade from v2.3.x or v2.4.0/v2.4.1/v2.4.2 may also want to verify `docker/.env` no longer carries secret-class key names: `python ~/.ai-memory/scripts/verify_env_split.py --install-dir ~/.ai-memory --strict` will report any residual entries via the new I9 invariant. A clean reinstall on v2.4.3 enforces the new contract automatically.

Source-clone hygiene (the user clone at `/path/to/ai-memory/docker/.env`) is operator-side: review and remove any plaintext secret-class entries that landed there before v2.4.0. The fresh-install dotfile-cp path on v2.4.3+ does not re-introduce them.

## [2.4.2] - 2026-05-17

### Added

- Version-marker consistency check (`scripts/check_version_consistency.py`) that asserts the three repository version markers always agree: `version.txt`, `pyproject.toml` `[project] version`, and `src/memory/__version__.py` `__version__`. It runs on every pull request and push via the `Test Suite` workflow, and on a release build additionally asserts the markers equal the release tag and the latest non-`[Unreleased]` `CHANGELOG.md` heading. Covered by `tests/test_check_version_consistency.py` (agree, disagree, and tag-mode cases). (BUG-307)

### Fixed

- `src/memory/__version__.py` `__version__` was stale at `2.3.2` while `version.txt` and `pyproject.toml` declared `2.4.1`, so v2.4.0/v2.4.1 installs self-reported the wrong version and the `Release Management` workflow's version-consistency step failed on every tag-cut. Corrected `__version__` to `2.4.1` and added version-history lines for 2.4.0 and 2.4.1. (BUG-307)
- `src/memory/metrics.py` no longer carries an independent hardcoded version string for its Prometheus version `Info` metric. The `importlib.metadata` fallback now reads `src/memory/__version__.py` instead of a literal, so the metric value cannot drift from the single source of truth. (BUG-307)
- The `Release Management` workflow's release-validation summary now names the specific validation step that failed — and surfaces the version-mismatch detail — instead of emitting a generic "Release validation failed" message. (BUG-307)

### v2.4.2 — POV Token Budget Restructure

Reduces Parzival activation surface and full-session token cost by deduplicating identity content between `parzival.md`, sanctum templates (CREED + PERSONA), and constraint summaries; collapses inline boilerplate in step files to single-source references; extracts low-frequency reference material from eager-loaded workflow files into lazy-loaded reference docs. Source-repo PR scope only; per-operator user-data hygiene (project-status.md, oversight/tracking files, sanctum CREED/PERSONA/BOND/LORE per-instance) is operator-side and not in this release.

#### Acceptance criteria (module-only profile, Anthropic SDK `count_tokens` authoritative)

| AC | Target | Measured | Verdict |
|----|--------|----------|---------|
| AC-01 | Activation surface ≤9,000 SDK tokens | 10,546 | Approached, not met (over by 1,546). Deferred to v2.4.4 dedicated cleanup PR. |
| AC-02 | Activation + `[ST]` ≤25,000 SDK tokens | 18,294 | PASS — margin +6,706 |
| AC-03 | Full session (`[ST]` + `[DA]` + `[CL]`) ≤35,000 SDK tokens | 34,104 | PASS — margin +896 |

Cumulative reduction: full-session 37,160 → 34,104 SDK tokens (−8.2%); activation 12,642 → 10,546 SDK tokens (−16.6%).

#### Highlights

- **EDIT-A** (`_ai-memory/pov/agents/parzival.md`): dedupes 11 rules → 7 operational rules; collapses `<persona>` and `<constraints critical="true">` blocks to single-line pointers into CREED.md sections; replaces verbose confidence-levels behavior body with PERSONA.md reference. Activation surface delta: −1,011 SDK tokens.
- **EDIT-B** (`_ai-memory/pov/constraints/global/constraints.md`): removes Self-Check Schedule and Violation Severity Reference sections that re-stated information already present in the 21-row Constraint Summary table and in each individual `GC-NN-*.md` body file. Replaces with one 3-line pointer block. Activation surface delta: −1,085 SDK tokens.
- **EDIT-C** (`_ai-memory/pov/workflows/WORKFLOW-MAP.md`): 5-section eager/lazy split. Routing logic, init entry points, cycle workflow table, user-invoked command table, and Verification Hierarchy stay eager-loaded; phase summaries, phase transition rules, project-status.md schema, workflow header standard, and end-of-session protocol move to new `_ai-memory/pov/references/workflow-map-details.md` lazy reference (EDIT-D).
- **EDIT-E** (`STEP-PREAMBLE.md`): adds Standard Step Frame as single-source location for universal step preamble + sequence admonition wording.
- **EDIT-F** (21 step files): removes the inline preamble pointer line + collapses the verbose `## Sequence of Instructions (Do not deviate, skip, or optimize)` header to `## Sequence`. Applied to `steps-c/` step files across 8 subdirectories: `cycles/agent-dispatch/` (9 steps), `session/close/` (4 steps), `session/start/` (3 steps — step-01b/02/03), and `step-01` of `cycles/legitimacy-check/`, `session/blocker/`, `session/decision/`, `session/handoff/`, and `session/verify/`. Of the 21, the 12 that sit on the AC-03-measured surface account for the bulk surface delta of −720 SDK tokens (12 files × −60 SDK/file); the remaining 9 off-surface files received the same mechanical edit for consistency.
- **EDIT-G** (`CREED-template.md` + `PERSONA-template.md`): slims duplicate identity content per dedupe map (CREED 699→613 words, PERSONA 510→430 words).
- **EDIT-H** (aim-parzival-bootstrap `SKILL.md`): adds Load Policy section clarifying skill content loads only on invocation, not at agent activation.
- **EDIT-I** (`oversight/docs/`): moves `_ai-memory/pov/knowledge/parzival-master-plan.md` to new `oversight/docs/parzival-master-plan-history.md`. Historical planning artifact retained in source repo but removed from runtime install scope. Three external references repointed.
- **EDIT-J** (`_ai-memory/pov/references/auto-memory-best-practices.md`): new lazy-loaded reference doc for per-Claude-user `MEMORY.md` hygiene guidance.
- **EDIT-K** (workflow-map-details.md schema hardening): ≤80-word caps and DO / DO-NOT examples on the project-status.md schema fields.

#### Methodology lessons (documented for future token-budget work)

This release surfaces two empirical rules for projecting token cost of markdown content edits:

1. **Content-type density variance**: token cost per word varies materially by content type. Measured densities (Anthropic SDK, `claude-opus-4-7`): XML prose 1.722 tok/word; markdown tables 2.385 tok/word (+38%); inline-code-heavy markdown 3.545 tok/word (+106%); step-file boilerplate 4.369 tok/word (+154%). Word-count proxies (`words × 1.3`) are insufficient for content with elevated token-boundary density. Direct `count_tokens` measurement is the reliable path.

2. **Chunking-boundary discount**: content-only measurement of a deletion block (extracted to an isolated blob and measured) systematically overstates the resulting file-surface delta by approximately 32%. Validated empirically across EDIT-B (31.3% loss content-only → surface) and EDIT-F sample (32.5% loss). Sample-then-bulk methodology using surface-measured per-file delta as the extrapolation baseline avoided this entirely: EDIT-F bulk projection landed at 0.0% divergence against the −720 SDK projection (12 files × empirically-measured −60 SDK/file).

#### Tooling

- New: `scripts/measure_tokens.py` — measurement script for activation / `[ST]` / `[DA]` / `[CL]` token surfaces using Anthropic SDK `count_tokens` as authoritative tokenizer; tiktoken `cl100k_base` cross-reference; module-only profile excludes per-operator user data for AC-binding measurements. Output to JSON + Markdown.

#### Out of scope (deferred)

- Per-operator user-data hygiene (project-status.md slim, oversight/tracking active-only, sanctum per-instance content) — operator-side, post-install per release notes.
- Approximately 30 additional step files in non-AC-measured surfaces (`session/{blocker,decision,verify,handoff}/steps-c/` and `cycles/legitimacy-check/steps-c/` outside `step-01`, all `cycles/{review-cycle,approval-gate,research-protocol}/steps-c/`) — deferred to v2.4.4 dedicated cleanup PR. Sample-then-bulk methodology now proven and re-applies cleanly.
- AC-01 full close (activation surface ≤9,000 SDK) — deferred to v2.4.4 dedicated cleanup PR.
- `measure_tokens.py` `--output` path-truncation bug on multi-dot paths — deferred to v2.4.3.

#### Compatibility note

Sanctum template changes (`CREED-template.md`, `PERSONA-template.md` slim per EDIT-G) only affect new sanctums created at First Breath after install. Existing operator sanctums (already-filled `CREED.md` / `PERSONA.md` / `BOND.md` / `LORE.md` per-instance files) are not modified by this release; they remain as the operator filled them. Operators who want the slim template prose can manually re-init their sanctum, but this is not required for v2.4.2 functionality.

### Upgrade Instructions

**From v2.4.1 → v2.4.2:**

POV-content restructure release — Parzival identity and workflow files were
deduplicated and reorganized to reduce token cost. No breaking changes, no data
migration. Your memories, credentials, and Parzival sanctum are untouched.

1. Pull the latest:
   ```bash
   cd /path/to/ai-memory
   git fetch origin && git checkout main && git pull
   ```
2. Re-run the installer:
   ```bash
   ./scripts/install.sh /path/to/your-project
   ```

Re-running the installer refreshes all POV files in place: new files are added,
and obsolete or superseded files from earlier versions are removed
automatically. Your data and sanctum identity are preserved. This is the same
single step for every user — a fresh install, an operator updating an existing
project, or an add-project user. No manual steps.

## [2.4.1] - 2026-05-16

### Added

- `backup_qdrant.py` gains `--collection`, `--retry`, and `--version` flags, and honors `BACKUP_SNAPSHOT_CREATE_TIMEOUT` / `BACKUP_SNAPSHOT_DOWNLOAD_TIMEOUT` environment overrides; the snapshot-create timeout default is raised to 300s (TD-517).
- `restore_qdrant.py` gains `--dry-run`, `--collection`, `--target-name`, and `--skip-checksum-verify` flags (TD-517).
- Integration test covering the production-shape backup/restore round-trip and the failed-restore rollback path (`tests/integration/test_backup_restore_round_trip.py`).
- Regression coverage for Parzival bootstrap consumer pipeline handling L1 ceiling rejection without `AttributeError` (BUG-301). Root cause was a pre-v2.4.0 SKILL.md consumer that did not unpack the `retrieve_bootstrap_context` 2-tuple, passing the raw tuple to `select_results_greedy` and triggering `.get()` on a list element. Fix shipped in v2.4.0; regression coverage added in v2.4.1 (`tests/test_l1_handoff_realistic_size.py` case e, production-size 40-chunk fixture). Negative sub-test proves the pre-fix pattern raises `AttributeError: 'list' object has no attribute 'get'`.
- POV bootstrap observability documentation. `docs/prometheus-queries.md` now
  documents the `aimemory_retrieval_budget_reject_total` counter — its labels,
  cardinality, example PromQL queries, and alerting guidance.
  `docs/CONFIGURATION.md` documents the `HANDOFF_CEILING_TOKENS` environment
  variable, including default, valid range, and ceiling-breach behavior.
  `docs/PARZIVAL-SESSION-GUIDE.md` describes the `[FALLBACK-NEEDED:]` marker
  contract for the session-start handoff fallback. (TD-526)

### Fixed

- E2E test `test_collection_type_system_e2e` used the generic two-word query `"database queries"` which scored below the default `similarity_threshold=0.7` on the Jina v2 code model (cosine similarity 0.5857), producing zero results in CI where defaults apply. Replaced with `"async await database queries"` (cosine similarity 0.9497) to pass the default threshold while preserving the test's intent of verifying type-filtered retrieval of implementation memories. No production code change; test query text only.
- Langfuse post-init membership fix-up now succeeds on fresh install (BUG-298). `psql -c` (single-command mode) does not expand `:'var'` quoted-variable substitutions; the `-v`/`:'var'` pattern passed the literal colon-string to postgres, producing a syntax error that was silently swallowed by `2>/dev/null`. Replaced with shell-expanded SQL in `_fixup_init_user` (both the `UPDATE users` and `INSERT INTO project_memberships` blocks). Added input validation for `init_email` and `init_project_id`. Removed `2>/dev/null` and upgraded error severity to `log_error` so failures surface in the install log. Effect: `users.admin=true`, `users.email_verified` set, and `project_memberships` row created on every fresh install — Langfuse UI lands on the init project instead of the onboarding page.
- Installer `import_user_env` warning text updated to accurately describe stub behavior (TD-523). The previous warning stated "The root `.env` is no longer used" alongside guidance to manually add API keys — a contradiction that misled operators. Updated to informational messages: root `.env` present is acknowledged and credentials-not-auto-imported is stated clearly.
- Same-version backup/restore round-trip is now correct for hybrid-schema collections (TD-517). On a fresh-install restore the previous code created the target collection with a hardcoded single-vector 768/Cosine config; Qdrant then rejected the snapshot upload with an HTTP 400 schema mismatch, leaving the backup unrestorable. Backup manifests now capture a full schema fingerprint (vectors, sparse vectors, multivector config, HNSW config, quantization config, payload indexes) and restore recreates the target collection byte-equivalently before uploading the snapshot.
- Snapshot recover now requests snapshot priority, so a restore makes the backup data canonical instead of merely filling gaps and leaving stale local points in place (TD-517).
- Restore now verifies the recovered point count against the manifest, and fails fast — rather than reporting a misleading success — when a collection comes back partially populated (TD-517).
- Restore over an existing collection now snapshots that collection's current state first; if the restore fails partway through, every pre-existing collection is recovered to exactly its prior state and freshly created collections are removed (TD-517).
- Restore now hard-fails with actionable guidance when the backup's schema fingerprint does not match the live target (cross-version restore) or when a legacy backup carries no fingerprint, instead of silently producing a broken collection (TD-517).
- Backups now write `CHECKSUMS.sha256` over the manifest and every snapshot file, and restore verifies it before uploading anything (TD-517).
- Backup and restore now handle the BUG-277 split env layout, capturing and restoring `docker/.env` and `docker/.env.secrets` (with `644`/`600` permissions) alongside the legacy root `.env` (TD-517).
- `_memory/` user file modification timestamps are now preserved across
  reinstalls. The installer's backup and restore copy steps now pass `cp -p`,
  so `stat` and `find -newer` audit checks remain meaningful after an upgrade.
  Per-instance sanctum identity files (LORE.md, BOND.md, sessions) also retain
  their original timestamps on the restore path. Note: CREED.md is rewritten by
  the frontmatter merge step on the normal update path; only the failure-fallback
  `cp` retains its original mtime. File content was already preserved across
  reinstalls; only the timestamps were being reset. (BUG-299)
- The pushgateway `grouping_key` for pushgateway-emitting metric functions now
  includes `collection` to prevent per-collection series from clobbering each
  other. Three paths were affected: retrieval-budget rejection
  (`push_retrieval_reject_metric_async`), context injection
  (`push_context_injection_metrics_async`), and capture
  (`push_capture_metrics_async`). Previously, pushes sharing the same
  tier+reason or hook_type but differing only in collection overwrote each
  other in the pushgateway scope. The `grouping_key` instance for each function
  now encodes collection as an additional dimension —
  `reject_{tier}_{reason}_{collection}`,
  `ctx_injection_{hook_type}_{collection}`, and
  `capture_{hook_type}_{collection}` respectively — making the documented ~40
  sparse series (4 reasons × 2 tiers × 5 collections) achievable in practice.
  (BUG-300, BUG-304)

### Upgrade Instructions

**From v2.4.0 → v2.4.1:**

Maintenance release — bug fixes and backup/restore tooling hardening. No breaking changes, no data migration.

1. Pull the latest:
   ```bash
   cd /path/to/ai-memory
   git fetch origin && git checkout main && git pull
   ```
2. Re-run the installer:
   ```bash
   ./scripts/install.sh /path/to/your-project
   ```

The installer preserves your data, credentials, and Parzival sanctum. New config keys are migrated into `docker/.env` automatically. No manual steps.

## [2.4.0] - 2026-05-13 — BUG-297 Silent-Drop Fix + Sanctum Identity + Env-Secrets Split + Classifier Resilience

v2.4.0 closes the **BUG-297 silent-drop class** as its marquee item: L1 handoff
results were dropped at the retrieval budget with no log, no metric, and no
signal to the caller — fixed via a 3-component bundle (structured WARN +
Prometheus counter for budget rejects, a typed `fallback_signaled` sentinel
threaded through `select_results_greedy` and surfaced as a
`[FALLBACK-NEEDED:]` marker, and a per-tier `handoff_ceiling_tokens=8000`
ceiling sized for whole-handoff aggregation against the Jina v2 single-vector
ceiling). Verified end-to-end via PM #289 Session A/B functional gate on a
live 6,760-token handoff retrieval.

Supporting work shipped in the same release:
- **Parzival sanctum identity layer** (PLAN-027): source ships an EMPTY
  sanctum; `aim-agent-sanctum-init` scaffolds 8 universal templates at First
  Breath. File-level idempotency hard rule — re-runs never overwrite an
  existing sanctum file. New conversational First Breath workflow fills BOND
  with owner specifics + LORE with project specifics. Bootstrap path
  (BUG-283), partial-fill contradiction (BUG-284), and Qdrant status-line
  accuracy (BUG-285) closed alongside.
- **`.env` + `.env.secrets` split with Compose `env_file:` directive**
  (BP-152 / BUG-277 / BUG-279): 25 secret-class keys moved to a `chmod 600`
  file with last-file-wins precedence; `${PROJECT_ENV_FILE}` enables
  per-project env layering. Closes TD-477 and retires the
  `unset QDRANT_API_KEY` ritual.
- **Installer hardening pass**: BUG-273 (UID/GID readonly), BUG-274 (user
  input persistence), BUG-275 (consumer-side dual-file read), BUG-281
  (Docker mount root-owned host dirs), BUG-282 (`.env` dotfile glob skip),
  BUG-286 (SSoT secrets-split enforcement), BUG-287 (Qdrant read-only API
  key compose wiring), BUG-292/293 (`run-with-env.sh` + `health_check.sh`
  secrets-first read), BUG-291 (activation step 5 detect-and-repair).
- **Classifier provider resilience** (BUG-290/294/295/296): retired
  OpenRouter default replaced; Ollama cold-start handled via `/api/ps` +
  `keep_alive: -1`; retired Anthropic default replaced; dual-listed
  Langfuse blanks removed.
- **GitHub code-blob sync graceful degradation** (BUG-288, BP-155):
  abandon-set persistence + reconciliation pre-sort + `/health`-503
  readiness gate (BUG-289) so `service_healthy` correctly gates startup.
- **Decision-type emit at session closeout** (TD-519) and **L1 handoff
  retrieval aggregation** (TD-518) — both close gaps where canonical
  storage existed (decision-log.md) or chunked storage existed
  (`agent_handoff`) but Qdrant retrieval was silently empty or
  single-chunk.
- **`INSTALL_PARZIVAL=true` install-time opt-in** for non-interactive runs
  (PR #124).

### Added
- **`EMBEDDING_READ_TIMEOUT_CODE` env var** (BUG-288): new per-request read
  timeout override for code-model embedding calls (default 30s). The client-level
  `EMBEDDING_READ_TIMEOUT` (default 15s) is designed for fast en-model requests;
  code-model requests under CPU load regularly approach 20-30s, causing
  per-file timeout false positives. The code-model override is applied inline in
  `EmbeddingClient._embed_once()` when `model="code"` without affecting en-model
  or sparse/late calls. Documented in `docker/.env.example`.
- **Prometheus metrics for sync abandonment** (BUG-288):
  `github_code_sync_abandoned_files_total` (Counter) tracks files abandoned per
  sync cycle due to total-timeout or circuit-breaker;
  `github_code_sync_completion_ratio` (Gauge, 0.0-1.0) reports the ratio of
  eligible files successfully synced. Both pushed to Pushgateway with the
  existing `grouping_key={"instance": repo_slug}` scope. Enables alerting on
  recurring partial-sync cycles.
- **`GitHubSyncEngine.load_code_blob_state()` / `save_code_blob_state()`**
  (BUG-288): two new methods on `GitHubSyncEngine` that read and write the
  `code_blobs` sub-key of `github_sync_state_*.json` via the existing
  POSIX-atomic `_load_state()` / `_save_state()` mechanism. Forward-compatible:
  state files that pre-date BUG-288 simply lack the key and return `{}`.
- **`CodeSyncResult.abandoned_paths`** (BUG-288): new list field on
  `CodeSyncResult` accumulating paths of all files cut off by total-timeout or
  circuit-breaker in a given sync cycle. Populated from two sources: tasks
  cancelled mid-flight by `_cancel_pending()` and entries that were never
  dispatched before the index was clamped to `total_eligible`.
- **Parzival sanctum identity layer**: Introduces per-instance Parzival identity storage under `_ai-memory/sanctum/parzival/`. Source ships an EMPTY sanctum directory; `aim-agent-sanctum-init` scaffolds all 8 standard files from universal templates at First Breath: Tier A `CREED.md` + `PERSONA.md` (philosophical anchor + identity, loaded at activation); Tier B `LORE.md` + `BOND.md` + `MEMORY.md` (project knowledge + owner relationship + working memory, loaded at session-start); Tier C `CAPABILITIES.md` + `INDEX.md` + `PULSE.md` (workflows + sanctum map + autonomous heartbeat scaffold, loaded on-demand via Read tool when referenced). New conversational First Breath workflow (`pov/workflows/first-breath/`) fills BOND with owner specifics + LORE with project specifics on first activation. File-level idempotency hard rule: re-running scaffolding NEVER overwrites an existing sanctum file — owner customizations survive every reinstall. Filesystem-only — no Qdrant storage for sanctum files. AI Memory is a multi-user system; universal templates ensure every install starts from the same authored Parzival baseline and grows its own identity through use.
- **Tier B sanctum wiring into `aim-parzival-bootstrap`**: New `sanctum_tier_b.py` sibling module (Option P pattern) reads `LORE.md` + `BOND.md` and prepends their content under `## Sanctum — LORE` / `## Sanctum — BOND` headers before the existing L1-L4 cross-session Qdrant retrieval output. Graceful degradation: missing/empty files skip silently (valid pre-First-Breath state). 6 pytest unit tests covering both-present, only-LORE, only-BOND, neither, empty-file, and OSError paths.
- **Pre-spawn model-catalog validation gate**: `aim-model-dispatch` step-02 now validates the requested model ID against the per-provider model catalog (`models-claude.md`, etc.) before attempting to spawn. Prevents reviewer dispatches from silently downgrading when a requested model is missing from the per-provider catalog.
- **Three-marker CWD sentinel**: Agent-lifecycle and dispatch workflows now verify three distinctive directory markers (`_ai-memory/` + `_bmad/` + `oversight/`) instead of a single marker before spawning agents. Detects accidental shell-`cd` drift into sibling repos (e.g., `ai-memory/` source repo vs. `dev-ai-memory/` workspace).
- **`INSTALL_PARZIVAL=true` install-time opt-in** (PR #124, contributed by Phil): Enables the full Parzival V2 setup path during `NON_INTERACTIVE=true` installer runs (CI / add-project automation). Default non-interactive behavior is unchanged — still skips Parzival unless opted in.
- **Compose `env_file:` directive + sensitive-secret split** (BP-152, ENV-MANAGEMENT-V2.md): `docker/docker-compose.yml` refactored to use a YAML anchor `x-python-service-defaults: &python-service-defaults` with `env_file:` directive applied to 4 Python services (`monitoring-api`, `streamlit`, `classifier-worker`, `github-sync`). Replaces per-key `${KEY:-default}` hand-mapping with a single source of truth: `.env` (required) + `.env.secrets` (optional sensitive split, chmod 600) + `${PROJECT_ENV_FILE:-/dev/null}` (optional per-project layer). `environment:` blocks retained only for service-specific overrides (container hostnames, ports, image-tag interpolation). Closes TD-477 (15 of 17 user-tunable env keys silently fell back to code defaults inside containers because `environment:` blocks did not propagate them) and the BUG-184 shadow class — the `unset QDRANT_API_KEY` ritual is no longer required for compose operations.
- **`docker/.env.secrets.example` template**: New file documenting 25 sensitive keys (API keys, passwords, tokens) split out from `.env.example` for `chmod 600` enforcement. The real `.env.secrets` is gitignored. Installer copies the template and applies `chmod 600` on deploy.
- **`${PROJECT_ENV_FILE}` multi-project env layering**: When the installer is given a project name, `scripts/install.sh` writes `PROJECT_ENV_FILE=<absolute-path>` into `docker/.env` so Compose can resolve a per-project override file at `~/.ai-memory/projects.d/<name>/.env`. When no project name is given, the variable resolves to `/dev/null` (safe no-op).
- **`scripts/check_env_completeness.py` Pydantic drift gate**: New script that introspects `MemoryConfig.model_fields` + `AliasChoices` and asserts every field is documented in `docker/.env.example` (active or commented). Exits non-zero on drift with a clear remediation message. Self-contained for CLI invocation (`PYTHONPATH=src python3 scripts/check_env_completeness.py`). Currently 100 fields documented, 0 drift.
- **`.github/workflows/env-drift.yml` CI gate**: Triggers on PRs that touch `config.py`, `docker/.env.example`, `docker/.env.secrets.example`, `docker-compose.yml`, or `check_env_completeness.py`. Runs `dotenv-linter check` on each env file separately + `python3 scripts/check_env_completeness.py`.
- **`tests/test_env_management.py` (5 tests)**: defaults-only `MemoryConfig()` instantiation; `env_file` reading; `secrets_dir` honored when `env_file` does not contain the key; drift-gate orphan detection via direct-import; v2.3.2 backward-compat without `.env.secrets` present.
- **`secrets_dir='/run/secrets'` Pydantic Settings forward-compat**: `MemoryConfig.model_config` adds Docker Swarm / Kubernetes Secrets compatibility. No behavior change today; positions the project for future secrets-mount workflows. `extra='ignore'` was already present.
- **Per-instance sanctum backup/restore in `deploy_parzival_v2()`**: Installer Option 1 updates now mirror the existing `_memory/` PID-suffixed backup/restore pattern for `sanctum/`. Per-instance content (LORE.md, BOND.md, accumulated Tier-C in `sessions/`/`capabilities/`/`references/`) is preserved across updates. CREED.md frontmatter merge preserves 4 specifically-mutating fields (`sessions_completed`, `last_session`, `updated`, `tier_promoted_on`) per DQ-3 (a); static identity fields come from the new template body. Closes the HIGH-severity sanctum data-loss path discovered in PM #261 pre-install audit.
- **`scripts/_merge_sanctum_creed_frontmatter.py`**: New stdlib-`re`-based YAML frontmatter merger invoked by `deploy_parzival_v2()`. Atomic write via `tempfile` + `os.replace` (mirrors the `merge_settings.py` pattern). Module docstring documents single-line scalar limitation + `ruamel.yaml` upgrade path if the preserve set later expands to multi-line block scalars. Helper script path is overridable at install time via `${CREED_MERGE_SCRIPT}` for failure-mode regression testing.
- **`tests/test_install_sanctum_preservation.py` (31 tests)**: Covers the Python helper directly + bash-subprocess integration tests for `deploy_parzival_v2()`. Includes `test_creed_merge_failure_falls_back_to_backup` regression test that exercises the failure path: when the merge helper exits non-zero, install logs an error and `cp`-restores the backup CREED.md verbatim, preserving per-instance frontmatter rather than letting the fresh template body wipe user state.

### Changed
- **`EmbeddingClient._embed_once()` per-request code-model timeout** (BUG-288):
  when `model="code"`, `_embed_once()` now passes an explicit
  `httpx.Timeout(read=EMBEDDING_READ_TIMEOUT_CODE)` on the individual `.post()`
  call, overriding the client-level `EMBEDDING_READ_TIMEOUT` for that request
  only. En-model and sparse/late calls are unaffected. Tunable via new
  `EMBEDDING_READ_TIMEOUT_CODE` env var (default 30s; configurable in
  `docker/.env`).
- **`sync_code_blobs()` signature** (BUG-288): new optional `code_blob_state`
  parameter (default `None`) carries the prior cycle's abandon-set dict.
  Callers that do not pass the parameter receive identical behaviour to the
  prior release (no prior abandoned files → no reconciliation pre-sort).
- **Total-timeout log level in `sync_code_blobs()`** (BUG-288): two
  `logger.warning` calls that fire when the 1800s total timeout is reached
  upgraded to `logger.error`. Silent WARNING was the reason large-repo
  abandonment went unnoticed in production (WARNING filtered in standard
  configs).
- **`GITHUB_SYNC_TOTAL_TIMEOUT` comment in `docker/.env.example`**: updated
  to note that files exceeding the timeout are recorded and prioritized on
  the next cycle (reconciliation), replacing the misleading "max 7d" guidance.
- **Parzival POV subsystem rebaselined**: Full rebaseline replacing the pre-existing source-repo `_ai-memory/pov/` tree with a canonical evolution developed across multiple iterations of dispatch-discipline embeds, 4-layer architecture refinement for orchestration skills, `§2a`/`§2b` instruction-form split for dispatch briefs, BMAD Intent picker support, and accumulated remediation landings. Net ~−7.2k lines (346 files changed; +7,303 / −14,524).
- **Orchestration skill consolidation**: `aim-model-dispatch/` absorbs the prior `model-dispatch-framework/` scaffolding (references, scripts, workflows, wrappers, evals) — the post-installer-merge runtime layout now matches the shipping-source layout. Reduces indirection during agent dispatch debugging.
- **`step-02-create-team.md` renamed to `step-02-spawn-agent.md`** (R6 template rename): The workflow step that spawns an agent pane is no longer called "create-team" — naming now reflects the actual action. Templates referencing the old filename have been rewritten.
- **POV step-file template consolidation** (R6): 63 `steps-e/` and `steps-v/` stub files rewritten to reference two shared templates (`STEP-FILE-TEMPLATE.md` and a variant) instead of carrying boilerplate inline. Replaces ~4,284 lines of duplicated boilerplate with ~780 lines of stubs + 2 shared templates — net −3,500 lines in this one consolidation alone.
- **Dependency floor: `langfuse>=4.0.6,<4.1.0`** (PR #120): Tightened the langfuse Python SDK lower bound from `4.0.0` to `4.0.6`. Picks up upstream patches v4.0.1-v4.0.6 including asyncio.CancelledError handling in `@observe` (v4.0.2), scores session ID parsing fix (v4.0.2), and experiments propagation context maintenance (v4.0.2). No API-surface changes affecting our V3 SDK usage (`get_client`, `observe`, `propagate_attributes`, `Langfuse`, `span_filter`).
- **`docker/*/requirements.txt` pin alignment to `pyproject.toml` floors**
  (TD-385 class audit): `docker/github-sync/requirements.txt` langfuse pin
  raised to `>=4.0.6,<4.1.0` (was `>=4.0.0,<4.1.0`) so the github-sync
  container picks up the same v4.0.6 fixes as the host install; anthropic
  pins in `docker/github-sync/requirements.txt` and
  `docker/streamlit/requirements.txt` raised from `==0.87.0` to
  `>=0.89.0,<1.0.0` to match pyproject; `docker/streamlit/requirements.txt`
  streamlit bumped from `==1.54.0` to `==1.56.0`. Docker build smoke tests
  pass; prometheus-client was already consistent at `==0.24.1` across all
  three docker `requirements.txt` files (TD-385 audit no-op for that pin).
- **GitHub Actions group bump** (PR #113): Bumped 2 actions in `.github/workflows/community.yml`, `dependabot-auto-merge.yml`, `release.yml`. CI-only impact; no runtime change.

### Fixed
- **L1 handoff silent-drop on budget rejection** (BUG-297): The TD-518
  handoff aggregation works correctly (5,386 tokens from 40 chunks of
  Session 47), but the aggregated body was silently dropped at
  `select_results_greedy` when it exceeded `bootstrap_token_budget=2500`.
  No log, no metric, no signal to caller — the `[ST]` Cross-Session
  Memory block showed an empty `### Last Handoff` despite Qdrant having
  complete data. Closed via a 3-component MVF bundle ([[BP-158-rag-budget-reject-silent-drop-fallback-sentinel-observability-2026]]
  P1/P2/§5):
  - **C-1 observability**: `select_results_greedy` now emits a structured
    `retrieval_budget_reject` log line and a Prometheus
    `aimemory_retrieval_budget_reject_total{reason,tier,collection}`
    counter at every skip-and-continue site (`budget_exceeded`,
    `score_gap`, `dedup`). Cardinality: 4 × 2 × 5 = 40 series, well
    under BP-158 §3 budget.
  - **C-2 typed-sentinel return**: `select_results_greedy` accepts a
    keyword-only `return_meta` flag (default `False` preserves the
    2-tuple shape; 15 call sites unaffected). When `True`, returns
    `(selected, tokens_used, meta)` where `meta.fallback_signaled` is
    `True` iff any budget-rejected result is `type=="agent_handoff"`.
    `retrieve_bootstrap_context` returns `(results, meta)` so the
    Layer 1 ceiling rejection signal composes with the greedy-fill
    signal. The bootstrap skill emits a `[FALLBACK-NEEDED: ...]`
    marker as the first content line of the Cross-Session Memory
    block when `fallback_signaled` is `True`.
  - **C-3 per-tier ceiling**: New `handoff_ceiling_tokens` MemoryConfig
    Field (default 8000, ge=2500, le=10000) sized for whole-handoff
    aggregation against the Jina v2 single-vector ceiling. Applied as
    a pre-filter inside `retrieve_bootstrap_context` after
    `_aggregate_chunked_result`: oversized handoffs are excluded from
    `results` and signaled via `meta.fallback_signaled`.
    `bootstrap_token_budget` semantics for snippet content (decisions,
    insights) remain untouched at `le=5000`.
  - Workflow `step-01b-parzival-bootstrap` CASE B extended to recognize
    the marker as a filesystem-fallback trigger, so cross-session
    continuity never silently degrades.
  - Realistic-size integration test (`tests/test_l1_handoff_realistic_size.py`)
    gates a Session 47-class fixture (40 chunks, ~5,400 aggregated
    tokens) against all three components per
    [[feedback_realistic_size_production_artifact_tests]].
- **Tier-2 handoff-class rejection observability** (F-010): The Tier-2
  per-turn injection hook (`context_injection_tier2.py`) now passes
  `tier=2, return_meta=True` to `select_results_greedy` so the
  rejection counter is attributed to the `2_injection` label. When a
  handoff-class result is budget-rejected at Tier 2, a single
  `# [tier-2 fallback: ...]` comment marker is prepended to the
  injected output as a debugging surface. Tier 2 has no filesystem
  fallback path; behavior is otherwise unchanged.
- **Triggers keyword-collision noise** (F-008): Downgraded the
  `keyword_pattern_collisions_detected` emission from WARN to DEBUG
  level — the substring overlaps in `best_practices_keywords` are
  intentional pattern-design (see BP-040), not real conflicts. The
  collision validator already runs once at module-load time per
  TECH-DEBT-113; this fix only adjusts emission severity to prevent
  per-hook-invocation noise polluting stderr.
- **Prometheus collection allowlist missing `github`** (F-009): The
  `github` collection (PLAN-010, separated from `discussions`) was
  not in `VALID_COLLECTIONS` in `metrics_push.py`, so retrieval
  metrics with `collection="github"` were coerced to `unknown`. All
  5 production collections are now allowlisted (`code-patterns`,
  `conventions`, `discussions`, `github`, `jira-data`).
- **`/run/secrets` UserWarning suppression** (F-012): pydantic-settings
  probes `/run/secrets` at every `MemoryConfig()` instantiation for
  Docker-secrets discovery. The probe is intentional, but the
  UserWarning emitted per-hook-process polluted stderr on host
  environments. A scoped `warnings.filterwarnings` is installed at
  `src/memory/config.py` module-load — in place before any importer
  instantiates the settings model — to suppress the specific
  message without masking other warnings.
- **SKILL.md frontmatter audit** (F-013): Three skills already
  declared `allowed-tools` correctly per Claude Code Skills spec
  2026. Four were missing it. Audit added the actual tool set per
  skill body: `aim-agent-lifecycle` (Bash — tmux send-keys /
  capture-pane / kill-pane), `aim-parzival-team-builder` (Read —
  Step 1 reads work-to-be-parallelized; non-standard `context:
  fork` runtime extension preserved), `aim-agent-dispatch` and
  `aim-model-dispatch` (Read — reference workflow files consulted
  when routing). No skill body content modified.
- **L1 handoff retrieval aggregation** (TD-518 / F-001): Bootstrap Layer 1
  now reassembles multi-chunk `agent_handoff` results via type-agnostic
  scroll-and-concat. Previous behavior returned only the single
  highest-scoring chunk — testV2 Session 45 measured this delivering a
  102-byte trailer (~0.5%) of a 20,039-byte handoff body across 37 chunks,
  silently breaking cross-session continuity. Trigger condition is purely
  metadata-based (`chunking_metadata.total_chunks > 1`); whole-emit
  handoffs (`total_chunks=1`) bypass aggregation, no perf regression.
  Fallback returns the original chunk + `bootstrap_aggregation_*` WARN
  on any scroll/match-key failure (never crashes bootstrap). Aggregated
  results expose `chunking_metadata.aggregated_from_chunks=True` for
  diagnostic visibility. Composes with future emit types that ever chunk.
  See `oversight/tech-debt/TECH-DEBT-518-handoff-retrieval-aggregation.md`.
- **Decision-type emit at session closeout** (TD-519 / F-002): Closes the
  long-standing gap where session decisions were canonical-stored in
  `oversight/tracking/decision-log.md` but never emitted to Qdrant.
  Bootstrap L2 retrieval (`memory_type=["decision"]`) was permanently
  empty as a result. New `/parzival-save-decision` skill fires once per
  DEC entry from session-close `step-04-save-and-confirm.md`; per-DEC
  failure is non-fatal (`decision-log.md` is the primary record, script
  returns 0). Storage shape is whole, 1 vector, no chunking, no
  thresholds, no truncation per Chunking-Strategy-V2 §3.3 + §7
  (guaranteed by `content_type_map` not mapping `MemoryType.DECISION`,
  so the chunker is skipped entirely). Re-emit is idempotent via
  SHA-256 `content_hash` dedup. Adds `"decision"` to the
  `store_agent_memory` allowlist (D-2-A) — purely additive. See
  `oversight/tech-debt/TECH-DEBT-519-decision-emit-additive.md`.
- **Closeout hard-fails on missing handoff template** (TD-520 / F-C6):
  Session-close `step-02-update-tracking.md` and `step-03-create-handoff.md`
  now both check for `_ai-memory/pov/templates/session-handoff.template.md`
  at entry. If missing, halt with an operator-actionable error
  ("Handoff template missing — cannot enforce TD-500 empirical
  commits-ahead capture. Restore template before continuing: ..."). Was
  a silent skip risk for the TD-500 empirical commits-ahead mandate
  because TD-500 enforcement is template-bound. Belt-and-suspenders
  pre-condition at both step entry points covers any future workflow
  refactor. See `oversight/tech-debt/TECH-DEBT-520-td500-enforcement-hardening.md`.
- **Q-5**: Documented expected 0-result Qdrant baseline on fresh install in
  `oversight/specs/POST-INSTALL-VERIFICATION-2026-04-25.md` (testV2 +
  workspace dual-copy per DEC-PM286-D9) to prevent operator false-alarm
  reads.
- **Documentation: terminology cleanup for "Tier B Qdrant persistence"**
  (Q-7): Replaced stale "Tier B Qdrant persistence" wording in active
  workspace docs with the shipped "Tier B filesystem persistence" /
  "Tier B sanctum reload" terminology per DEC-253-14. Tier B is
  filesystem-only in v2.4.0; the future Qdrant-overlay enhancement is
  logged as TD-470 (PLAN-025 backlog — no standalone TECH-DEBT file yet,
  registered in the plan progress doc). Historical/archived docs
  preserved (accurate at their writing date). Documentation-only change;
  no functional impact.
- **TD-518 follow-up — collection-aware aggregation + drift signal**: L1
  handoff aggregation in `src/memory/injection.py::_aggregate_chunked_result`
  is now collection-aware via `result.get("collection") or COLLECTION_DISCUSSIONS`
  — composes with future emit types routed to non-discussions collections
  (default-to-discussions preserves backward-compat for callers whose result
  dict lacks the `collection` key). The aggregated result also preserves the
  original advertised count separately as
  `chunking_metadata.total_chunks_advertised` while
  `chunking_metadata.total_chunks` reflects siblings actually concatenated,
  making partial-drift detectable from result metadata, not just the
  `bootstrap_aggregation_partial` WARN log. Two new tests cover the
  collection-aware contract and the default-to-discussions backward-compat
  path. Workspace TD-518 spec §"Fix Design" item 5 + AC #4 updated to reflect
  the dual-field shape.
- **TD-519 follow-up — `decision_summary` prefix-strip**: the
  `decision_summary` payload field captured by the `/parzival-save-decision`
  skill now strips the leading `DEC-XXX-D#:` prefix when present, since the
  `dec_id` payload field already carries the ID. The summary stores the
  meaningful suffix only (e.g., `"Add 'decision' to allowlist"` rather than
  `"DEC-PM286-D2: Add 'decision' to allowlist"`). Applied symmetrically in
  both `scripts/memory/parzival_save_decision.py` and the inline
  `.claude/skills/parzival-save-decision/SKILL.md` copy.
- **TD-519 follow-up — closeout step-04 multi-line DEC body safety**: the
  closeout `step-04-save-and-confirm.md` `Emit Decisions to Qdrant` sub-step
  now uses a single-quoted heredoc pattern
  (`DEC_BODY=$(cat <<'PARZIVAL_DEC_END' ... PARZIVAL_DEC_END)`) instead of single-line
  `--content "<text>"` shell quoting. Multi-line DEC bodies with embedded
  `"`, `$`, or newlines were previously vulnerable to silent truncation past
  the first embedded `"`, corrupting the SHA-256 `content_hash` and
  defeating the per-DEC dedup contract with no error signal.
- **TD-518/TD-519 test visibility**: dropped `@pytest.mark.integration` from
  9 in-memory tests in `tests/test_l1_handoff_aggregation.py` and
  `tests/test_session_close_decision_emit.py` — they use only
  `QdrantClient(":memory:")` (zero Docker), but the marker was auto-skipping
  them under default `pytest tests/` invocation while the integration test
  job in CI only targets `tests/integration/` directly. The 9 tests now run
  at the unit-tier gate without any CI workflow change.
- **`src/memory/injection.py` import grouping**: moved `qdrant_client.models`
  import from inside the first-party `from memory.*` block to the
  third-party section alongside `numpy`. PEP 8 / isort alignment; no
  runtime impact.
- **Langfuse setup `_fixup_init_user` postgres role/db concatenation
  (TD-512 fix)**: `scripts/langfuse_setup.sh _fixup_init_user` was
  concatenating `"$prefix"langfuse` to construct postgres `-U` (role) and
  `-d` (database) arguments for `docker exec ... psql`. With `prefix="ai-memory"`
  (compose project name), the result was `ai-memorylangfuse` — but the
  actual postgres role/db inside the container is `langfuse` (per
  `docker/docker-compose.langfuse.yml` `POSTGRES_USER` and `POSTGRES_DB`
  declarations). Result: 2 FATAL events at fresh-install startup
  (`role "ai-memorylangfuse" does not exist`). No functional impact (Will
  verified login works PM #283; FATAL did not recur on restart). Fix:
  drop `$prefix` from `-U` and `-d` arguments; postgres role/db are literal
  `langfuse` inside the container, while `$prefix` remains correct for
  container/volume naming. See
  `oversight/tech-debt/TECH-DEBT-512-langfuse-setup-prefix-concat.md`.
- **`run-with-env.sh::load_env_var` reads secrets from `.env` only** (BUG-292 HIGH):
  `load_env_var` now applies a secrets-first / env-fallback dual-source pattern,
  mirroring `_env_split_helpers.sh::_read_env_key`. PP-2 key `QDRANT_API_KEY` and
  PP-1 key `GITHUB_TOKEN` were blank after the BUG-277 split (real values moved to
  `docker/.env.secrets`), causing Qdrant 401 errors in every maintenance script
  invoked via `run-with-env.sh` (`process_retry_queue.py`, `post_work_store_async.py`,
  `collection_stats.py`). `SECRETS_FILE` is now derived from `ENV_FILE` and read first;
  `ENV_FILE` serves as fallback for non-secret config and pre-BUG-277 installs.
  Script header updated to acknowledge the dual-file architecture.
- **`health_check.sh` QDRANT_API_KEY read site reads from `.env` only** (BUG-293 MED):
  Added `SECRETS_FILE` variable and a two-step secrets-first / env-fallback read for
  `QDRANT_API_KEY`. Post-BUG-277 installs had a blank key → Qdrant `/collections`
  endpoint returned 401 → operator lost collection-count diagnostics. Non-auth probe
  endpoints (`/readyz`, `/healthz`) were unaffected (auth-whitelisted).
- **Three install.sh subshells source only `.env` before invoking Python** (W1-F1 MED,
  defense-in-depth pattern alignment): `setup_github_indexes`, `run_initial_github_sync`,
  and `drain_pending_queue` now each source `docker/.env.secrets` in addition to
  `docker/.env`, matching the `setup_collections` BUG-275 reference pattern. All three
  subshells are restructured to the parenthesized multi-line format of `setup_collections`
  for full architectural consistency. Current runtime was safe (`MemoryStorage`/`MemoryConfig`
  dual-file pydantic-settings read compensates for blank shell-exported vars via
  `env_ignore_empty=True`; W1-F2 trace confirmed `process_retry_queue.py` uses only
  `MemoryStorage`, not direct `os.getenv()` for PP-1/PP-2 keys). The fix ensures
  future direct env reads in these subshells will also receive correct PP-1/PP-2 values.
  "Re-run manually" log hint in `run_initial_github_sync` updated to move `.env.secrets`
  source within the `set -a` / `set +a` scope (robust for installs where `.env` lacks
  the key as a placeholder). Note: `drain_pending_queue` aligned to `setup_collections`
  architecture — `.venv/bin/activate` source + system `python3` fallback removed;
  `.venv/bin/python` invoked directly (`.venv` is guaranteed present by install order;
  consistent with `setup_collections` reference pattern).
- **HIGH: sanctum data-loss on installer Option 1 updates**: Before this fix, `deploy_parzival_v2()` ran `rm -rf "$dst"` then `cp -r` from the source-repo template, wiping LORE/BOND/CREED-frontmatter/Tier-C accumulation on every update — only `_memory/` had explicit preservation. Discovered in PM #261 pre-install audit (testV2 Parzival). Fix mirrors the `_memory/` PID-suffix backup/restore pattern + adds CREED.md frontmatter merge for the 4 mutating fields. Closes F-H1.
- **CREED frontmatter merge silent-failure path** (cycle-1 review F-M2): Previous implementation chained `python3 ... CREED.md || true` followed by an unconditional `log_debug "Merged"` — a merge failure would silently destroy per-instance frontmatter while logging success. Replaced with explicit if/else: on success, log debug confirmation; on failure, log error + `cp` backup CREED.md verbatim to preserve user identity. Install continues in both paths. Subsequent installer runs retry the merge.
- **streamlit `restart: on-failure:3` regression** (cycle-1 review F-M1): When the new `<<: *python-service-defaults` anchor was applied to the streamlit service, the anchor's `restart: unless-stopped` silently overrode streamlit's original `restart: on-failure:3`. Restored via explicit service-level override: `restart: on-failure:3` placed at the streamlit service, taking YAML-merge precedence over the anchor.
- **Installer (BUG-273 fix)**: filter `UID` and `GID` from the bash `source` of `docker/.env` at the four sites in `setup_github_indexes()`, `run_initial_github_sync()`, `drain_pending_queue()`, and the manual re-run instruction string. Pre-fix, `docker/.env.example` since v2.3.0 contains `UID=1000` and `GID=1000`; bash treats these as readonly built-ins, so `set -a && source docker/.env` short-circuited the `&&` chain before reaching the Python helpers, causing GitHub index creation and initial sync to silently fail with install exit code 1. Fix: `source <(grep -v -E '^(UID|GID)=' docker/.env)`. Latent in v2.3.0–v2.3.2. See `oversight/bugs/BUG-273-install-source-env-uid-readonly.md`.
- **Installer (BUG-274 fix)**: persist user-provided GitHub / Jira / Langfuse answers
  to `docker/.env` and `docker/.env.secrets` via the existing `set_env_value` helper.
  Pre-fix, fresh installs lost user choices because the install script collected
  answers into shell variables but never wrote them back to the runtime env files;
  later subshells that sourced from `.env` re-imported template defaults, breaking
  GitHub sync (and any other feature whose enablement was answered "yes"). Sibling
  to BUG-273 — both manifest at the same install.sh region. See
  `oversight/bugs/BUG-274-install-user-input-not-persisted-to-env.md`.
- **Installer (BUG-275 fix)**: extend pydantic-settings consumer-side loading to read
  both `docker/.env` and `docker/.env.secrets`. Pre-fix, `MemoryConfig.model_config`
  declared a single-string `env_file=docker/.env`, so secrets persisted by the
  BUG-274 fix to `docker/.env.secrets` (chmod 600) were invisible to every Python
  entry into `memory.*`. Fresh installs with `GITHUB_SYNC_ENABLED=true` exited 1 at
  the `setup_collections` step with a `ValidationError`. Sibling of BUG-273 (UID/GID
  readonly source) and BUG-274 (user-input persistence) — same install region,
  consumer-side root cause. Fix research-validated by BP-153 (pydantic-settings
  2.7.1 source code + live test). Pattern A: 1-line tuple `env_file=(_docker_env,
  _docker_secrets)` in `MemoryConfig`. Pattern B: install.sh subshell sources both
  files at the `setup_collections()` call site (defense-in-depth). Pattern C: extend
  manual dotenv loaders in `migrate_v221_hybrid_vectors.py` and the user-invoked CLI
  scripts (`backup_qdrant.py`, `restore_qdrant.py`, `list_projects.py`) to load
  both files via shared helper `scripts/_env_loader.py`. Achieved precedence:
  shell > `.env.secrets` > `.env` > Field defaults. See
  `oversight/bugs/BUG-275-memoryconfig-single-env-file-secrets-blind.md` and
  `oversight/knowledge/best-practices/BP-153-pydantic-settings-split-env-consumers-2026.md`.
- **Installer (BUG-277 fix)**: migrate all 25 secret-class keys from `docker/.env`
  (chmod 644) to `docker/.env.secrets` (chmod 600) — completing the ENV-MANAGEMENT-V2
  split-file architecture (PM #261-262). Prior to this fix, only GITHUB_TOKEN and
  JIRA_API_TOKEN were correctly written to `.env.secrets` (BUG-274); 17 auto-generated
  keys (Qdrant, Grafana, Prometheus, Langfuse infra/project/bootstrap) and 6
  user-supplied optional keys remained at chmod 644. Fix architecture: 17 PP-2 write
  sites moved in install.sh and langfuse_setup.sh; Option γ atomic migration
  (write-to-tempfile → chmod 600 → atomic mv → verify → blank source) for v2.3.x
  in-place upgrades; langfuse_setup.sh env_get()/env_has() extended to read from
  .env.secrets. Rollback (v2.3.x reinstall): auto-generated credentials regenerate;
  user-supplied tokens (GITHUB_TOKEN, JIRA_API_TOKEN) re-prompt. Research-validated
  by BP-154 (POSIX rename() + Docker Compose v5.0.2 live test + compose-spec/compose-go
  source, PM #270). See oversight/bugs/BUG-277-secrets-class-keys-written-to-env-not-secrets.md
  and oversight/knowledge/best-practices/BP-154-env-secrets-migration-2026.md.
- **Installer + stack scripts (BUG-279 fix)**: pass `docker/.env.secrets` as a
  second `--env-file` flag to every `docker compose` invocation in
  `scripts/install.sh`, `scripts/stack.sh`, `scripts/langfuse_setup.sh`,
  `scripts/enable-hybrid-search.sh`, and `scripts/rollback.sh`. Without this,
  Compose's auto-loaded `.env` interpolation reads the BLANK PP-2 keys
  post-BUG-277 R3 migration, producing `QDRANT__SERVICE__API_KEY=""` in the
  Qdrant container (locked-out: 401 on all auth-required endpoints) and
  `LANGFUSE_PUBLIC_KEY=""` / `DATABASE_URL` interpolation failures across the
  Langfuse stack — affects all 29 secret-class `${VAR}` interpolation sites
  in `docker-compose.yml` + `docker-compose.langfuse.yml`. Empirically
  verified: `docker compose --env-file .env --env-file .env.secrets config`
  resolves all secret interpolations to real values. Compose v2.21+
  multi-env-file last-file-wins precedence per BP-154 §Q2. See
  `oversight/bugs/BUG-279-compose-env-secrets-not-loaded-by-wrappers.md`.
- **Installer (BUG-281 fix)**: pre-create `${INSTALL_DIR}/config/projects.d`
  and `${INSTALL_DIR}/github-state/logs` in `create_directories()` so the
  github-sync container's volume mounts find existing parzival-owned host
  paths instead of triggering Docker daemon auto-create (which runs as root
  and would leave host paths root-owned, locking out subsequent
  `register_project_sync()` writes from install.sh). Sibling consumer-side
  resolution to BUG-279. See
  `oversight/bugs/BUG-281-docker-mount-creates-root-owned-host-dir.md`.
- **Installer (BUG-282 fix)**: explicitly copy `docker/.env` (dotfile) from
  source to install dir during fresh install. Bulk `cp -r .../docker/*` in
  `copy_files()` uses shell glob `*` which excludes dotfiles, so `.env` was
  silently skipped — leaving the install dir without a `.env` until the
  merge ELSE branch fell back to copying `.env.example` over `.env`,
  silently overwriting user customizations (uncommented opt-in keys like
  `GITHUB_CODE_BLOB_INCLUDE`, `DECAY_*`, `FRESHNESS_PENALTY_*`, `INJECTION_*`
  thresholds reverted to commented template defaults). Sibling of BUG-040
  (which only handled `.env.example` dotfile copying); fix mirrors the
  same explicit-cp pattern, gated by `! -f "$INSTALL_DIR/docker/.env"` so
  it only fires for fresh installs and does not interfere with the
  TD-198 backup/restore + merge logic for Option 1 reinstalls. Discovered
  during PM #274 P4-08 verification when a customized
  `GITHUB_CODE_BLOB_INCLUDE=*.yaml,*.toml,Makefile,Dockerfile` was lost
  across reinstall.
- **Sanctum architecture redesign (BUG-283 + BUG-284 + BUG-285)**: testV2 lead-dev verification surfaced a contradiction in the prior PM #255 partial-fill sanctum delivery model: source shipped pre-filled `CREED.md` while `init-sanctum.py` `TEMPLATE_FILES` excluded `CREED-template.md`, and directory-level idempotency at `init-sanctum.py:215-218` exited clean if `CREED.md` existed — net result, fresh installs got CREED + 3 empty subdirs only, with Tier B (LORE/BOND) never created. Plus the templates contained literal `{}` placeholders (e.g., `{agent-title}`, `{vibe-prompt}`, `{bond-domain-sections}`) that survived as raw text in scaffolded output because `substitute_vars` only fills 6 specific keys. PLAN-027 redesign: empty-ship sanctum + `TEMPLATE_FILES` extended to 8 (adds CREED, CAPABILITIES, PULSE) + file-level idempotency in 3 write sites (`copy_references`, `copy_scripts`, TEMPLATE_FILES loop) + `CREED-template.md` becomes the authored Parzival philosophy (relocated from prior shipped `CREED.md`) + 5 other templates rewritten as universal scaffolds with substitution-key-only placeholders (no leak-prone `{X}` literals) + new conversational First Breath workflow (3 steps: meet owner → learn project → confirm and begin). Bootstrap fixes (BUG-283): `_bootstrap_skill_dir` path corrected to include `_ai-memory/` segment; `sanctum_tier_b` import wrapped for graceful degrade. Status-line accuracy (BUG-285): per-layer Qdrant status capture via `logging.Handler` subclass distinguishes "available", "degraded (N of 4 layers unreachable)", "unreachable (all retrieval calls failed)" instead of hardcoded "available" that masked Connection refused errors. Activation step 5 detect-and-repair: invokes `/aim-agent-sanctum-init` if any of 8 required sanctum files missing; invokes First Breath workflow if BOND has scaffold markers. 4 regression tests (T1-T4) verify no `{}` placeholder leakage / idempotency / partial-sanctum recovery / customization preservation. See `oversight/bugs/BUG-283-bootstrap-path-and-sanctum-tier-b-import.md`, `oversight/bugs/BUG-284-sanctum-init-contradicts-shipped-creed.md`, `oversight/bugs/BUG-285-bootstrap-status-line-masks-qdrant-unreachable.md`.
- **Installer (BUG-286 fix)**: enforce env-secrets split for ALL 25 secret-class
  keys including PP-1 (`GITHUB_TOKEN`, `JIRA_API_TOKEN`). Pre-fix, the recovery
  menu and `configure_environment` Add Jira/GitHub blocks wrote PP-1 tokens to
  `docker/.env` (chmod 644) instead of `docker/.env.secrets` (chmod 600) — an
  active leak in the recovery path, plus latent risk in the configure path.
  `migrate_secrets_to_split_file` excluded PP-1 from migration scope, and
  TD-198 backup-and-restore preserved the leaked `.env` across reinstalls so
  `verify_env_split.py I4` failed on every reinstall of a customized clone.
  Fix introduces `ALL_SECRET_KEYS` as the single source of truth in
  `scripts/_env_split_helpers.sh` (25 keys = PP-1 + PP-2 + PP-3), routes
  recovery-menu writes to `.env.secrets`, replaces `configure_environment`
  token echoes with blank placeholders, extends migration + detection probes
  to include PP-1, adds defensive blank-in-`.env` via
  `persist_user_choices_to_env`, and adds T13/T14/T15 regression tests
  covering the reinstall #5 scenario, all-25-key enforcement, and
  idempotency. Cycle-2 dual-review fix-r2 makes the SSoT truly consumed
  (single iteration over `ALL_SECRET_KEYS` instead of parallel pp1/pp2/pp3
  arrays) and dedupes the detection grep alternation. See
  `oversight/bugs/BUG-286-installer-pp1-secrets-leak.md`.
- **Compose (BUG-287 fix)**: wire `QDRANT__SERVICE__READ_ONLY_API_KEY` into the
  Qdrant container `environment:` block, completing the TD-333 read-only auth
  surface. The producer side (`install.sh` R2.7 key generation + `.env.secrets`
  write site via `configure_environment`) and consumer side
  (`MemoryConfig.qdrant_read_only_api_key` field + `get_qdrant_client(read_only=True)`
  key-swap branch) were fully implemented; the server-side compose wiring was the
  only missing piece. Without this line, Qdrant rejects the read-only key with
  HTTP 401 — the generated 32-byte secret-class key was wasted. Adds regression
  tests: `test_compose_qdrant_wiring.py` (NEW unit-layer test, runs in unit CI tier —
  no Docker required); `tests/integration/test_qdrant_read_only_wiring.py` (integration
  tier — live container probes with PUT-403 write-rejection assertion). See
  `oversight/bugs/BUG-287-qdrant-read-only-api-key-not-wired-in-compose.md`.
- **Compose (BUG-287 fix-r2)**: cycle-2 dual-review hardening (Sonnet CHANGES-REQUESTED
  + Opus APPROVE-WITH-NITS). All 12 findings addressed: split test placement so
  YAML-parse test (`test_compose_wires_read_only_api_key`) runs in unit CI tier via
  `test_compose_qdrant_wiring.py` with `_find_repo_root()` helper and prefix-match
  assertions (Sonnet F-1 + Opus M1 + Opus L4 + Opus L7); CI env injection for
  `QDRANT_READ_ONLY_API_KEY` + `QDRANT__SERVICE__READ_ONLY_API_KEY` in
  `integration-tests` job (Sonnet F-2); write-rejection probe (PUT → 403) added
  per bug-doc verification step 4 with try/finally best-effort cleanup (Sonnet F-3 +
  Opus M2); Python consumer probe via `get_qdrant_client(read_only=True)` added as
  `test_qdrant_read_only_key_python_consumer` (Opus M3); CHANGELOG claim updated to
  reflect unit-tier test relocation (Sonnet F-4); URL fallback aligned to
  `localhost:26350` (Opus L6); exception catch broadened to `httpx.RequestError`
  (Sonnet F-7); compose BUG-184 caveat enumerates both `QDRANT_API_KEY` and
  `QDRANT_READ_ONLY_API_KEY` (Opus L5); CHANGELOG BUG-287 entry repositioned after
  BUG-283/284/285 to restore ascending order (Sonnet F-6); fix-r2 commit subjects
  ≤72 chars (Sonnet F-5). **Known limitation (TD-494)**: integration-tests CI job
  still skips `test_qdrant_read_only_key_accepted_by_container` and the new Python
  consumer probe due to a pre-existing `tests/conftest.py:integration_test_env`
  autouse fixture that unconditionally pins `QDRANT_URL=http://localhost:26350`,
  overriding the workflow step env; CI Qdrant binds host port 6333, so
  `_qdrant_reachable()` returns False and the live probes still skip in CI.
  Pre-existing wider issue affecting all `tests/integration/*` modules; surfaced
  by Opus cycle-2 review NEW-1; tracked for v2.4.1+ via TD-494. Production
  behavior of the read-only API key wiring is fully validated empirically
  (PM #276 reinstall #6 in-container env shows both keys; live verification
  passed before push of `82e4fcb`). See `oversight/reports/bug287-review-sonnet.md`,
  `oversight/reports/bug287-review-opus.md`,
  `oversight/reports/bug287-review-r2-sonnet.md`,
  `oversight/reports/bug287-review-r2-opus.md`.

- **GitHub code-blob sync (BUG-288 fix)**: resolve silent data-loss when the
  1800s total timeout cuts off >50% of files on large repositories. Five-part
  fix: (1) `CodeSyncResult.abandoned_paths` field records every file that was
  cut off by total-timeout or circuit-breaker; (2) `sync_code_blobs()` accepts
  a new `code_blob_state` dict carrying the prior cycle's abandon-set — on the
  next run, previously abandoned files are sorted to the front of the eligible
  queue (`reconciliation pre-sort`, BP-155 §3) so they are least likely to be
  cut off again; (3) `GitHubSyncEngine.load_code_blob_state()` /
  `save_code_blob_state()` persist the abandon-set as a `code_blobs` sub-key
  in the existing POSIX-atomic `github_sync_state_*.json` state file —
  forward-compatible (old state files lacking the key return `{}`);
  (4) `github_sync_service.py` Phase 2 block threads state through the call
  (load before sync, save after); (5) `CodeBlobSync._wait_for_embedding_ready()`
  pre-sync probe polls `/health` before the file-tree fetch; if the embedding
  service is not ready within 60s, sync proceeds anyway (probe is advisory).
  Total-timeout log sites upgraded from `WARNING` to `ERROR`. New Prometheus
  metrics: `github_code_sync_abandoned_files_total` (Counter) +
  `github_code_sync_completion_ratio` (Gauge). See
  `oversight/bugs/BUG-288-github-code-sync-silent-data-loss.md` and
  `oversight/knowledge/best-practices/BP-155-graceful-sync-degradation-and-reconciliation-2026.md`.
- **Embedding service `/health` endpoint (BUG-289 fix)**: `/health` now returns
  HTTP 503 (with full JSON body) when `model_loaded=False`, enabling Docker
  Compose `depends_on: condition: service_healthy` (`curl -f`) to correctly
  gate `github-sync` startup on actual model readiness rather than mere process
  liveness. Previously `/health` always returned HTTP 200 regardless of whether
  the Jina v2 en/code models had finished loading, causing `github-sync` to
  start before code-model embeddings were functional. See
  `oversight/bugs/BUG-289-embedding-health-endpoint-no-status-gating.md`.
- **Classifier `all_providers_failed` cascade (BUG-290 fix)**: Three simultaneous
  provider failures caused the classifier to fail on every call, leaving all new
  memories unclassified. Three root causes addressed: (1) OpenRouter default model
  `google/gemma-2-9b-it:free` retired — replaced with
  `meta-llama/llama-3.2-3b-instruct:free` in `config.py` and `docker/.env.example`
  (stable-namespace model per BP-156 §1.4 policy); (2) Ollama cold-start timeout —
  `keep_alive: -1` added as a top-level key in `OllamaProvider.classify()` POST body
  to prevent model eviction between classify calls; `MEMORY_CLASSIFIER_TIMEOUT` default
  raised from 10 s to 120 s; `docker/.env.example` updated with
  `MEMORY_CLASSIFIER_TIMEOUT=120` and an `OLLAMA_KEEP_ALIVE=-1` host-side guidance
  comment block (server variable, cannot be set from the compose env block; block
  covers Linux systemd, compose-managed Ollama, and Windows/macOS); `docker/docker-compose.yml`
  propagates the new timeout default to the `classifier-worker` env block; (3)
  `OllamaProvider.is_available()` probe used `/api/tags` (disk-downloaded model list)
  instead of `/api/ps` (VRAM-loaded model list) — replaced with a two-tier hybrid
  probe: `/api/ps` returns `True` immediately when the model is VRAM-loaded, logs
  `ollama_model_cold` WARNING (structured fields: `model`, `action`) when cold but
  reachable, and falls back to `/api/tags` for older Ollama daemons lacking `/api/ps`.
  Cold probe returns `True` so the circuit breaker still routes to Ollama — cold-start
  is recoverable; daemon-down is not. See
  `oversight/bugs/BUG-290-classifier-all-providers-failed-cascade.md` and
  `oversight/knowledge/best-practices/BP-156-classifier-provider-resilience-2026.md`.
- **Ollama default model user-namespace risk (BUG-294 fix)**: `OLLAMA_MODEL` default
  changed from `sam860/LFM2:2.6b` (user-namespace model — upstream removal risk) to
  `llama3.2:3b` (official Ollama project namespace). `docker/.env.example` `OLLAMA_MODEL`
  updated to match; inline comment added warning against user-namespace models (BP-156
  §1.4). See `oversight/bugs/BUG-294-ollama-model-third-party-upstream-removal-risk.md`.
- **Anthropic retired model default (BUG-295 HIGH fix)**: `ANTHROPIC_MODEL` default
  changed from `claude-3-5-haiku-20241022` (retired Feb 19, 2026) to
  `claude-haiku-4-5-20251001` (versioned ID; Anthropic lifecycle commitment through
  Oct 15, 2026 minimum). `config.py` and `docker/.env.example` both updated; re-validation
  comment added for Q1 2027. See `oversight/bugs/BUG-295-anthropic-model-stale-default.md`.
- **Langfuse keys dual-listed in `.env.example` (BUG-296 LOW fix)**: Removed 5 blank
  Langfuse placeholder entries (`LANGFUSE_DB_PASSWORD`, `LANGFUSE_CLICKHOUSE_PASSWORD`,
  `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY`) from the
  Section 2 "Auto-generated" block of `docker/.env.example`. These keys were already
  (correctly) documented in `docker/.env.secrets.example`; the dual-listing created a
  risk of the `.env` blank overriding the `.env.secrets` real value under certain env-file
  ordering. Replaced with a single cross-reference comment directing operators to
  `.env.secrets.example`. See
  `oversight/bugs/BUG-296-langfuse-blank-secrets-dual-listed.md`.
- **Parzival activation step 5 detect-and-repair refinement (BUG-291
  closure)**: PLAN-027 §53 F4 was largely implemented by Phase D commits
  `bb8a6b5` (sanctum bootstrap path/status fixes) + `b88fef4` (cycle-2
  refinements). This commit closes the 2 remaining gaps in
  `_ai-memory/pov/agents/parzival.md` step 5: (1) adds explicit
  failure-mode handling bullet for `init-sanctum.py` non-zero exit
  (log error + warn-and-continue per W-04 self-heal pattern; activation
  does not block on scaffolding failure), (2) tightens the First Breath
  scaffold-marker check from a broad pattern to the literal
  `_Filled during First Breath:` match per `BOND-template.md` actual
  scaffold marker text. Adds 3 new regression tests (T5-T7) verifying
  step 5 decision logic. T1-T4 (init-sanctum.py file-level idempotency)
  were landed by Phase D in
  `_ai-memory/pov/skills/aim-agent-sanctum-init/tests/test_init_sanctum_idempotency.py`.
  Closes BUG-291. See `oversight/bugs/BUG-291-init-sanctum-not-auto-invoked.md`
  and `oversight/plans/PLAN-027-sanctum-redesign.md` §53 + Phase D F4.

### Removed
- **`aim-bmad-dispatch/` skill**: The BMAD-specific dispatch skill is removed — `aim-agent-dispatch/` now handles both BMAD and generic agents via a unified routing path. All references to `/aim-bmad-dispatch` in prior orchestration pipeline documentation are superseded by `/aim-agent-dispatch`.
- **`step-01c-parzival-constraints.md`** (Phase 3 startup pipeline optimization): The Parzival session-start workflow no longer runs a dedicated constraints-loading step — constraints are now loaded during activation (step 4) and re-injected during `aim-parzival-bootstrap` (step 1b) when needed. Net token reduction on session start.

### Documentation
- **`claude-opus-4-7` added to model catalog**: `_ai-memory/pov/skills/aim-model-dispatch/references/models-claude.md` now lists Opus 4.7 as the newest Opus model (ordered newest-first), plus a row in the Model Selection Guide table and appended to the OpenRouter model list as `anthropic/claude-opus-4-7`. Aligns the catalog with the current Opus default for reviewer dispatches.
- **INSTALL.md non-interactive Parzival section** (PR #124 follow-up): Documented the new `INSTALL_PARZIVAL=true` env var alongside the existing `NON_INTERACTIVE=true` guidance.
- **Authoritative env-management knowledge**: New `oversight/knowledge/best-practices/BP-152-docker-compose-env-management-pydantic-multi-container-2026.md` (367 lines, 15 cited 2024-2026 sources) + `oversight/specs/ENV-MANAGEMENT-V2.md` (Parzival-direct synthesis from BP-152, 8 sections covering Compose pattern, Pydantic Settings layering, sensitive split, drift gate, multi-project layering). Drives the env-mgmt refactor in this release.

### Upgrade Instructions

**From v2.3.2 → v2.4.0:**

This release includes:

1. A **Parzival POV subsystem rebaseline**. Existing Parzival users must re-run installer Option 1 to pick up the new `_ai-memory/pov/` tree, the `aim-agent-sanctum-init` scaffolding skill, and the sanctum directory structure. Sanctum files (`sanctum/parzival/LORE.md`, `BOND.md`, etc.) are created at First Breath by the scaffolding — no pre-existing Parzival identity is disturbed.
2. Removal of `aim-bmad-dispatch/` skill. The DEPRECATED redirect stub at `.claude/skills/aim-bmad-dispatch/SKILL.md` ships for one release as a backward-compat shim — it routes invocations of `/aim-bmad-dispatch` to `/aim-agent-dispatch`. Existing `settings.json` references continue to work via the stub. Direct callers should update the skill path to `/aim-agent-dispatch` before the stub is removed in a later release. The installer does not modify `settings.json`.
3. A **langfuse SDK floor bump** that **requires a Python container rebuild** for the change to take effect at runtime. Pure config/docs changes need only the standard installer Option 1 update.
4. A **Compose env-management refactor** (BP-152 / ENV-MANAGEMENT-V2). The 4 Python services (`monitoring-api`, `streamlit`, `classifier-worker`, `github-sync`) now read env from `.env` + optional `.env.secrets` via `env_file:` directive instead of per-key `environment:` mapping. Existing `docker/.env` continues to work — sensitive keys can stay in `.env` (everything still loads) or be moved to `.env.secrets` for `chmod 600` enforcement (see post-install steps below). The `unset QDRANT_API_KEY` ritual previously required before compose operations is no longer needed.
5. A **HIGH-severity sanctum data-loss fix** in `deploy_parzival_v2()`. Existing per-instance Parzival identity (LORE.md content, BOND.md content, Tier-C accumulation in `sessions/`/`capabilities/`/`references/`, CREED frontmatter mutations like `sessions_completed`) is now preserved across installer Option 1 updates. No user action required — preservation is automatic.
6. A **sanctum architecture redesign** (BUG-283 + BUG-284 + BUG-285). The prior partial-fill model (source ships pre-filled CREED.md, init-sanctum.py exits clean if CREED.md exists, Tier B never created) is replaced with empty-ship + file-level idempotency. `init-sanctum.py` now scaffolds all 8 standard sanctum files (CREED, PERSONA, INDEX, BOND, LORE, MEMORY, CAPABILITIES, PULSE) from universal templates at First Breath, with per-file idempotency guards in 3 write paths so existing files are never overwritten. New conversational First Breath workflow (`pov/workflows/first-breath/`) fills BOND with owner specifics + LORE with project specifics on first activation. Bootstrap path bug (BUG-283) and Qdrant status-line accuracy bug (BUG-285) also closed. No user action required for fresh installs — `aim-agent-sanctum-init` runs automatically on first activation.
7. **BUG-289 breaking change** (embedding `/health` status code): the embedding
   service `/health` endpoint now returns HTTP 503 instead of HTTP 200 when
   models are not yet loaded. **External monitors** that alert on HTTP non-200
   from `/health` will now correctly fire during the model-load window (up to
   ~5 minutes on first startup). **`curl -f` healthchecks** (as used by Docker
   Compose `depends_on: condition: service_healthy`) will now correctly fail
   during loading. No action required for standard Docker Compose deployments
   — the compose healthcheck is the intended consumer and the 503-on-load
   behavior is exactly what BUG-289 was designed to enable.

**Partial-sanctum recovery (BUG-283/284/285)**: If you previously installed pre-PLAN-027 v2.4.0-candidate code and your `~/.ai-memory/_ai-memory/sanctum/parzival/` contains only `CREED.md` + 3 empty subdirs (no PERSONA/INDEX/BOND/LORE/MEMORY/CAPABILITIES/PULSE), the new file-level idempotency will detect-and-repair on next `/pov:parzival` activation: parzival.md activation step 5 checks for the 8 required sanctum files; missing files trigger `aim-agent-sanctum-init` which scaffolds only what's missing. Existing CREED.md is preserved verbatim (file-level idempotency means the script never overwrites an existing sanctum file). After scaffolding, BOND.md will have unfilled scaffold markers — activation invokes the new First Breath workflow to fill BOND with owner specifics + seed LORE with project specifics. No manual intervention required.

1. **Pull the latest from main:**
   ```bash
   cd /path/to/ai-memory
   git fetch origin && git checkout main && git pull
   ```

2. **Run the installer Option 1 (update existing installation):**
   ```bash
   ./scripts/install.sh /path/to/your/project
   # Choose Option 1 when prompted
   ```

3. **Rebuild Python containers to pick up `langfuse>=4.0.6`:**
   ```bash
   cd ~/.ai-memory/docker
   unset QDRANT_API_KEY    # avoid shell-env override of .env
   docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile '*' \
     build --no-cache classifier-worker trace-flush-worker evaluator-scheduler monitoring-api streamlit
   docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile '*' up -d
   ```

4. **Verify the langfuse version pickup:**
   ```bash
   docker exec ai-memory-classifier-worker pip show langfuse | grep Version
   # Expect: Version: 4.0.6 (or higher within <4.1.0)
   ```

5. **Verify all 17 ai-memory containers report healthy:**
   ```bash
   docker ps --format '{{.Names}}\t{{.Status}}' | grep ai-memory | grep -v '(healthy)'
   # Expect: zero output (all healthy)
   ```

**Optional: Move sensitive keys to `.env.secrets`** (recommended; existing `.env` continues to work):

```bash
cd ~/.ai-memory/docker

# Copy the template (do this once)
cp .env.secrets.example .env.secrets
chmod 600 .env.secrets

# Move sensitive values from .env to .env.secrets
# Edit .env.secrets — paste actual API keys, passwords, tokens
# Edit .env — delete the lines for keys now in .env.secrets

# Restart containers to pick up the split
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile '*' up -d
```

The 4 Python services read both files automatically via `env_file:` directive; values from `.env.secrets` take precedence on overlap. If `.env.secrets` is absent, behavior matches v2.3.2 (everything from `.env`).

**Optional: Per-project env layering via `${PROJECT_ENV_FILE}`**:

```bash
# Create per-project override (only applies when PROJECT_ENV_FILE is set in docker/.env)
mkdir -p ~/.ai-memory/projects.d/my-project
cat > ~/.ai-memory/projects.d/my-project/.env <<EOF
FRESHNESS_PENALTY_HALFLIFE_SECONDS=86400
DECAY_MIN_SCORE=0.45
EOF

# install.sh writes PROJECT_ENV_FILE=<path> to docker/.env when given a project name.
# To enable manually: add PROJECT_ENV_FILE=/home/$USER/.ai-memory/projects.d/my-project/.env to docker/.env
```

**Verify env propagation to containers** (post-restart):

```bash
docker exec ai-memory-classifier-worker env | grep DECAY_MIN_SCORE
# Expect: shows the value from .env (or per-project override if PROJECT_ENV_FILE set).
# Before this release, this would have been empty for 15 of 17 user-tunable keys (TD-477).
```

**Optional new flag for non-interactive installs:**

```bash
NON_INTERACTIVE=true INSTALL_PARZIVAL=true \
  AI_MEMORY_ADD_PROJECT_MODE=true \
  GITHUB_REPO=my-org/my-project \
  ./scripts/install.sh /path/to/project my-org/my-project
```

`INSTALL_PARZIVAL=true` enables the full Parzival V2 setup path during CI / scripted installs. See `INSTALL.md` for full details.

**Skipped for this upgrade**: GitHub Actions bump (#113) is CI-only and applies on the next workflow trigger automatically.

**Special case: stuck install with root-owned `~/.ai-memory/config/`** (rare,
only affects users who hit the BUG-281 trigger before pulling the fix):

If a prior install attempt left root-owned subdirectories in `~/.ai-memory/`
(e.g., `~/.ai-memory/config/projects.d/` owned by `root` from Docker
auto-create), plain `rm -rf ~/.ai-memory` fails at the root-owned subdir.
Recovery requires sudo, one-time:

```bash
sudo rm -rf ~/.ai-memory
cd /path/to/your/clone
git pull origin main           # ensure BUG-281 fix is in place
./scripts/install.sh /path/to/project
```

Future installs (with the BUG-281 fix in place) will not produce root-owned
host paths because `create_directories()` pre-creates `config/projects.d/`
and `github-state/logs/` with parzival ownership before any container starts.

**Customized `docker/.env` preservation across reinstall** (BUG-282 fix):

Fresh installs now correctly copy your customized `docker/.env` from the
source repo into the install dir. Before this fix, the bulk `cp -r` glob
silently skipped `.env` (a dotfile), causing the merge fallback to
overwrite with `.env.example` template defaults — losing uncommented
values for opt-in keys like `GITHUB_CODE_BLOB_INCLUDE`, `DECAY_*`,
`FRESHNESS_PENALTY_*`, and `INJECTION_*` thresholds. No user action
required for v2.4.0+ — your customizations now survive across both fresh
installs and Option 1 reinstalls.

**Classifier provider defaults updated (BUG-290/294/295 fix)**:

If you previously customized `OPENROUTER_MODEL`, `OLLAMA_MODEL`, or `ANTHROPIC_MODEL`
in `docker/.env`, your values are preserved — the new defaults apply only to fresh
installs or Option 1 reinstalls that do not already have those keys set.

> **ACTION REQUIRED for operators with a customized `ANTHROPIC_MODEL`**: If your
> `docker/.env` explicitly sets `ANTHROPIC_MODEL=claude-3-5-haiku-20241022` or
> `ANTHROPIC_MODEL=claude-3-haiku-20240307` (both retired by Anthropic), the
> "values are preserved" rule above **leaves you broken** — the Anthropic classifier
> provider will fail on every call with a model-not-found error. You must manually
> update your `docker/.env`:
>
> ```
> ANTHROPIC_MODEL=claude-haiku-4-5-20251001
> ```
>
> No container rebuild required — a `docker compose up -d` restart picks up the
> new value. Operators who never customized this key (used the old code default)
> receive the correct new value automatically via installer Option 1.

> **ACTION REQUIRED for operators with a customized `OPENROUTER_MODEL`**: If your
> `docker/.env` explicitly sets `OPENROUTER_MODEL=google/gemma-2-9b-it:free` (retired
> by OpenRouter; absent from the live `/api/v1/models` catalog as of PM #281
> verification), the OpenRouter classifier provider will fail on every call with
> a model-not-found error, dropping you to Ollama-only. You must manually update
> your `docker/.env`:
>
> ```
> OPENROUTER_MODEL=meta-llama/llama-3.2-3b-instruct:free
> ```
>
> No container rebuild required — a `docker compose up -d` restart picks up the
> new value. Operators who never customized this key receive the correct new
> value automatically via installer Option 1.

**Advisory: customized `OLLAMA_MODEL` and `MEMORY_CLASSIFIER_TIMEOUT`**:

If your `docker/.env` sets `OLLAMA_MODEL=sam860/LFM2:2.6b` (the prior code default
— a user-namespace model with upstream removal risk per BP-156 §1.4), the model
still works today but is not ecosystem-stable. Recommended: switch to the new
official-namespace default `OLLAMA_MODEL=llama3.2:3b` at your convenience.

If your `docker/.env` sets `MEMORY_CLASSIFIER_TIMEOUT=10` (the prior code default),
the classifier will time out on Ollama cold-starts under CPU load. Recommended:
raise to `MEMORY_CLASSIFIER_TIMEOUT=120` to match the new default. Combine with
`OLLAMA_KEEP_ALIVE=-1` on the Ollama host (see §4.1 of `docker/.env.example`) to
prevent eviction-induced cold-starts entirely.

If you are using the defaults unchanged, the new values take effect after pulling
the latest and running the installer Option 1. No container rebuild required — only
`docker/.env` and `docker/docker-compose.yml` changed.

Recommended: set `OLLAMA_KEEP_ALIVE=-1` on your Ollama host daemon (see the
`OLLAMA_KEEP_ALIVE` comment block in `docker/.env.example` §4.1 for per-platform
instructions) to prevent cold-start latency on the classifier's Ollama primary.

## [2.3.2] - 2026-04-13

Security patches, group_id normalization, Phase B live-verify fixes, and canonical shell wrapper.

### Added
- **`group_id` normalization** (PR #111): `group_id` values normalized at config load time; malformed or legacy IDs are sanitized before Qdrant tenant routing.
- **Group ID audit and migration tools** (PR #111): New `scripts/audit_group_ids.py` and `scripts/migrate_group_ids.py` for inspecting and correcting `group_id` values in existing Qdrant collections.
- **`run-with-env.sh` canonical wrapper** (PR #110, cherry-picked as `4b1bb15`): Shell script that sources `.env` and executes hook scripts under the correct virtualenv. Replaces ad-hoc env sourcing in individual skill scripts.
- **Script-backed skills** (PR #110, cherry-picked as `4b1bb15`): `aim-status`, `aim-save-handoff`, and `aim-save-insight` skills now delegate to shell scripts via `run-with-env.sh` for consistent environment handling.

### Fixed
- **`run-with-env.sh` `.env` quote stripping** (PR #111, commit `ba4b916`): `.env` values surrounded by quotes (e.g., `"true"`) triggered pydantic `ValidationError` on boolean fields. Wrapper now strips surrounding single and double quotes from all sourced values.
- **`install_dir` catastrophic regression in github-sync container** (PR #111, commit `a8ba885`): `install_dir` was computed as `"/.ai-memory"` inside the container, resolving to filesystem root. Fixed via validator guard, `AI_MEMORY_INSTALL_DIR=/app` in Docker Compose, and github-state volume remounted to `/app/github-state`.
- **`config.py` `AliasChoices` binding for `install_dir`** (PR #111, commit `2e07e4c`): `install_dir` field now correctly bound to `AI_MEMORY_INSTALL_DIR` canonical env var via pydantic `AliasChoices`.
- **`trace_buffer` volume missing from github-sync service** (PR #111, commit `3be8743`): github-sync container attempted writes to trace buffer path on a read-only filesystem layer. Volume mount added to `docker-compose.yml`.

### Security
- **pygments ReDoS** (GHSA-5239-wwwm-4pmq, LOW): `pygments` 2.19.2→2.20.0 (PR #99)
- **anthropic SDK patch — streamlit** (GHSA-w828-4qhx-vxx3, GHSA-q5f5-3gjm-7mfm): `anthropic` 0.86→0.87 in `docker/streamlit/requirements.txt` (PR #105)
- **anthropic SDK patch — github-sync** (GHSA-w828-4qhx-vxx3, GHSA-q5f5-3gjm-7mfm): `anthropic` 0.86→0.87 in `docker/github-sync/requirements.txt` (PR #107)
- **Dependency batch patch** (PR #112): `anthropic` 0.86→0.89 (GHSA-w828-4qhx-vxx3, GHSA-q5f5-3gjm-7mfm), `pytest` →9.0.3 (CVE-2025-71176), `uvicorn`/`ruff`/`mypy` minor/patch updates (9 packages total). All 14 open vulnerability alerts closed; `black` HIGH alert auto-resolved via `uv.lock` regeneration.

### Upgrade Instructions

**From v2.3.1 → v2.3.2:**

This release includes changes to the `github-sync` Docker container (baked code + compose configuration) and **requires a container rebuild**, not just an installer Option 1 pass.

1. **Pull the latest release:**
   ```bash
   cd /path/to/ai-memory
   git fetch origin && git checkout main && git pull
   ```

2. **Run the installer** (Option 1 for existing installations):
   ```bash
   ./scripts/install.sh /path/to/your/project
   # Select: Option 1 — Add project to existing installation
   ```

3. **Unset `QDRANT_API_KEY` before compose operations** (CRITICAL — pydantic-settings precedence):
   ```bash
   unset QDRANT_API_KEY
   ```

4. **Rebuild the `github-sync` container** (REQUIRED — baked code + compose env changes from PR #111):
   ```bash
   cd ~/.ai-memory/docker
   unset QDRANT_API_KEY   # re-affirm; shell state resets
   docker compose build --no-cache github-sync
   docker compose up -d github-sync
   ```

5. **Verify stack health:**
   ```bash
   # All 17 services healthy
   docker compose ps | grep -c "healthy"
   # Expect output: 17

   # github-sync logs clean — no container filesystem or config errors
   docker compose logs github-sync --tail=30
   # Expect: no [Errno 30] read-only filesystem errors
   # Expect: no pydantic.ValidationError
   # Expect: no install_dir="/.ai-memory" in startup logs
   ```

6. **(Optional) Run the `group_id` audit + migration tool** if your install has mixed-case repo slugs from an earlier version:
   ```bash
   cd /path/to/ai-memory
   python scripts/memory/audit_group_ids.py          # inspect plan (dry run)
   python scripts/memory/migrate_group_ids.py --apply  # execute migration
   ```
   The tool normalizes legacy mixed-case `group_id` values to canonical lowercase in Qdrant. Safe to skip on fresh installs.

**Important notes:**
- Always `unset QDRANT_API_KEY` before running `docker compose` commands. Shell env vars override `.env` file values, causing auth mismatches.
- The `github-sync` container's code is baked into the Docker image — installer Option 1 alone is not sufficient. The `docker compose build --no-cache github-sync` step is mandatory for this release.
- If the audit tool reports no legacy records, the migration step is a no-op.

## [2.3.1] - 2026-04-09

Endpoint alignment and documentation accuracy patch.

### Fixed
- Generated hook configs now target correct local service ports: `QDRANT_GRPC_PORT=26351` added, `EMBEDDING_HOST` changed from `localhost` to `127.0.0.1` for IPv4 reliability (PR #108)
- Qdrant recency retrieval uses typed `OrderBy`/`Direction` API instead of rejected dict form — fixes `unknown enum label "desc"` failure in `search.py` and `stats.py` (PR #108)
- Claude adapter config in installer aligned with Cursor and Codex adapters (PR #108)
- Test assertion format corrected to match Python dict syntax in installer (PR #108)
- Test environment isolation added to `test_generate_hook_config_service_defaults` (PR #108)

### Changed
- `EMBEDDING_HOST` default updated to `127.0.0.1` across all documentation: README, INSTALL.md, CONFIGURATION.md, skill files, and E2E verification script (PR #108)

## [2.3.0] - 2026-04-07

Stabilization, observability, and data integrity release. Includes Langfuse v3-to-v4 SDK migration, security hardening, installer robustness improvements, Docker infrastructure fixes, CI regression gate, and comprehensive documentation accuracy fixes.

### Security
- **Credential removed from committed settings** (V1-NEW-001): `QDRANT_API_KEY` removed from committed `settings.json`. Added `.gitignore` patterns.
- **Grafana default password removed** (TD-370): Removed `:-admin` default from `docker-compose.yml`. Installer already generates a secure password.
- **`qdrant_api_key` converted to `SecretStr`** (V5-NEW-2): Config field converted to `SecretStr | None`. All 9 consumers updated to call `.get_secret_value()`.
- **Cache key fingerprint** (TD-371): Cache key uses SHA-256[:8] fingerprint instead of raw API key.
- **SecretStr validation error protection**: `hide_input_in_errors=True` added to `MemoryConfig` model_config. Prevents `SecretStr` values from leaking in plaintext in pydantic `ValidationError` messages.
- **AI-ecosystem secret patterns** (TD-367): Security scanner Layer 1 regex patterns for OpenAI (`sk-`, `sk-proj-`, `sk-svcacct-`), Anthropic (`sk-ant-`), and HuggingFace (`hf_`) API keys with boundary tests.
- **Session content now scanned in relaxed mode** (TD-368): Layer 2 (detect-secrets) runs on session content even in relaxed mode. Previously, relaxed mode skipped Layer 2 for both GitHub and session content. Now only GitHub content (trusted source) skips detect-secrets.

### Fixed
- **Broken Tier 2 injection on fresh installs** (BUG-250, CRITICAL): Installer template registered archived `unified_keyword_trigger.py` instead of `context_injection_tier2.py`. Added deny-list to `_remove_dead_hooks()`.
- **Orphaned Langfuse traces** (BUG-251, CRITICAL): `CLAUDE_SESSION_ID` not propagated to library module calls. Added `os.environ.setdefault()` in `code_sync.py`, `sync.py`, `agent_sdk_wrapper.py`.
- **Missing Langfuse stop hook** (BUG-249, CRITICAL): `langfuse_stop_hook.py` registered in dev `settings.json` Stop hooks with guard pattern and 10s timeout.
- **MinIO bucket not auto-created** (BUG-263, CRITICAL): Langfuse traces silently lost — `Failed to upload JSON to S3: NoSuchBucket`. Added `langfuse-minio-init` one-shot service using `minio/mc` to create the `langfuse` bucket before web/worker start.
- **MinIO init permission denied** (BUG-264): `minio/mc` failed with `mkdir /root/.mc: permission denied` under `cap_drop: ALL` security hardening. Fixed with `MC_CONFIG_DIR=/tmp`.
- **Trace data loss via `update_trace()`** (TD-373, HIGH): `update_trace()` removed in Langfuse v4 SDK — fallback silently dropped `session_id`/`user_id`. Replaced with `propagate_attributes()` in trace flush worker and stop hook.
- **Evaluator 501 on self-hosted** (TD-374, HIGH): `api.observations.get_many()` returns 501 on self-hosted Langfuse ("v2 APIs only available on Langfuse Cloud"). Replaced with `api.legacy.observations_v1.get_many()`.
- **Hook pipeline traces silently dropped** (TD-372, HIGH): v4 SDK smart span filter only exports spans from `langfuse-sdk`, `gen_ai.*`, and known LLM framework scopes. Custom OTel scope `ai-memory.flush-worker` was silently filtered — all hook pipeline traces were lost. Fixed with composed `should_export_span` filter that keeps v4 defaults + adds `ai-memory.*` scope.
- **Venv path mismatch** (BUG-253, HIGH): `install.sh` referenced `venv/bin/python3` in 2 locations while the rest of the file used `.venv/bin/python`. Both paths corrected.
- **Env var consumption outside config** (BUG-254, HIGH): `AI_MEMORY_LOG_LEVEL` and `AI_MEMORY_QUEUE_DIR` consumed via raw `os.getenv()`, bypassing pydantic-settings validation. Consolidated into `MemoryConfig` with `AliasChoices` for backward compat — both prefixed (`AI_MEMORY_*`) and non-prefixed (`LOG_LEVEL`, `QUEUE_DIR`) names work. `BMAD_LOG_LEVEL` deprecated alias preserved.
- **Stale SessionStart matcher** (BUG-256): Dev `settings.json` had `startup|resume|compact|clear` — corrected to `resume|compact`. `_normalize_session_start_matcher()` now strips both `startup` and `clear`.
- **Streamlit missing tiktoken + prometheus-client** (BUG-257): Import chain `memory.storage` → `chunking` → `tiktoken` and `memory.metrics_push` → `prometheus_client` crashed Streamlit container. Added both to `docker/streamlit/requirements.txt`.
- **CI E2E collection init** (BUG-259): Added `github` to the `collections` array in test workflow to match `COLLECTION_NAMES` from `config.py`. Prevents silent test skips.
- **Regression tests gate** (BUG-260): Removed `continue-on-error: true` from regression test steps. Regression failures now BLOCK merges. Secret-gated conditional skip for fork PRs.
- **Stale installation paths in docs** (BUG-261): 40 references to `~/.claude-memory/` updated to `~/.ai-memory/` in `docs/RECOVERY.md`.
- **Wrong env var in docs** (BUG-262): `MEMORY_LOG_LEVEL` corrected to `AI_MEMORY_LOG_LEVEL` in README.md and INSTALL.md.
- **Langfuse compose project name** (BUG-265): `docker-compose.langfuse.yml` missing `name: ai-memory` — Langfuse containers appeared as separate "docker" project. Added `name: ai-memory` to unify all containers.
- **Hook stdin hang** (CI fix): `post_tool_capture.py` moved stdin read before network/metrics setup. Empty input exits immediately.
- **Orphaned profiled services on reinstall** (TD-331): `handle_reinstall()` now reads `MONITORING_ENABLED` and `GITHUB_SYNC_ENABLED` from existing `docker/.env` and passes `--profile` flags to `docker compose down`.
- **Qdrant auth check before collection setup** (TD-339): Authenticated health check (`GET /collections` with `api-key` header) added after liveness loop, before `setup_qdrant_collections()`. Retries 3 times with 2s backoff.
- **Qdrant healthcheck TCP to HTTP** (TD-341): Docker Compose healthcheck converted from TCP port probe to HTTP readiness check (`GET /readyz`). Unhealthy detection window reduced from ~100s to ~45s.
- **Evaluator 25-hour start_period** (TD-345): `start_period: 90000s` (25 hours) corrected to `120s` in `docker-compose.langfuse.yml`.
- **Unused classifier_queue volume removed** (TD-346): Named volume declared but never mounted by any service. Removed from `docker-compose.yml`.
- **Placeholder tests replaced with real assertions** (TD-362): `test_confidence_within_3_turns` uses ast.parse verification; `test_metrics_update_with_real_collection` uses Prometheus delta pattern; `test_manual_testing_checklist` deleted and moved to docs.
- **Langfuse retry tests broken** (TD-372 regression): Updated mocks to target `Langfuse` constructor and `langfuse.span_filter` module after v4 migration.
- **CI test timeout hardening** (TD-407, TD-412, TD-413): Fixed intermittent CI failures across 18 subprocess-based tests caused by cold-boot import chain latency. Raised subprocess timeouts from 5s to 10-30s.
- **Stale paths in scripts and tests** (TD-434, TD-435): 9 `~/.claude-memory` references updated to `~/.ai-memory` across scripts and tests.
- **MAX_RETRIEVALS default wrong in docs** (TD-437, TD-438): Corrected from `5` to `10` in `docs/HOOKS.md` and `aim-settings/SKILL.md`.
- **Nonexistent env var in docs** (TD-439): `MEMORY_MAX_RETRIEVALS` corrected to `MAX_RETRIEVALS` in `TROUBLESHOOTING.md`.
- **Mixed units in docs** (TD-440): `~1.3 GB` standardized to `~1.3 GiB` in `docs/LANGFUSE-INTEGRATION.md`.
- **RAM contradiction in docs** (TD-369): INSTALL.md RAM requirements made consistent.
- **detect-secrets false positives on natural language** (BP-151): Security scanner Layer 2 used `default_settings()` which flagged English words as Base64. Replaced with `transient_settings()` using pattern-only detectors for user session content.
- **health_check.sh container detection** (Docker Compose v5): Container status checks grepped for `"running"` but Compose v5 shows `"Up ... (healthy)"`. Changed to grep for `"Up"`.
- **Excessive Qdrant scroll traffic on large repos** ([#102](https://github.com/Hidden-History/ai-memory/issues/102)): `_update_last_synced()` performed O(n) scroll+set_payload per unchanged file every sync cycle. Replaced with `_batch_update_last_synced()` using `MatchAny` filter — single scroll + chunked set_payload (500 IDs/batch). Reduces sync-cycle Qdrant load from O(tracked_files) to O(1) for metadata updates.

### Added
- **Storage tracing** (TD-317): `emit_trace_event` calls added to all 5 storage entry points (`store_memory`, `store_memories_batch`, `store_github_code_blob_chunks_batch`, `store_agent_memory`, `store_best_practice`) with start/end timing, tags, and project_id.
- **Retriever observation type** (TD-323): Search spans now emit `as_type="retriever"` for proper Langfuse dashboard categorization.
- **@observe prohibition documented** (TD-325): Architecture note added to `injection.py`, `search.py`, `embeddings.py` headers documenting why `@observe` must not be used in hook-called modules.
- **Zero-vector validation** (TD-354): Embedding responses validated for degenerate all-zero vectors. Raises `EmbeddingError` in single-embed path; defense-in-depth check in batch path.
- **Session summary agent_id** (BUG-258): `agent_id` field added to `pre_compact_save.py` for Parzival tenant isolation of session summaries.
- **Read-only Qdrant API key** (TD-333): `qdrant_read_only_api_key: SecretStr | None` field in `MemoryConfig`. `get_qdrant_client(read_only=True)` prefers the read-only key, falls back to the read-write key. Supports Qdrant's native read-only key feature (v1.7+).
- **CI schema parity guard**: New `tests/test_ci_schema_parity.py` asserts set-equality between CI fixture collections and code-defined `COLLECTION_NAMES`. Catches future drift between code and CI.

### Changed
- **Langfuse SDK v3 to v4** (LANGFUSE-4X): Upgraded from `langfuse>=3.0,<4.0.0` to `langfuse>=4.0.0,<4.1.0`. Metadata values converted to strings for v4 compliance. `propagate_attributes()` replaces `update_trace()`. LANGFUSE-INTEGRATION-SPEC.md updated to v1.3.
- **Tag standardization** (TD-326, TD-376): `emit_trace_event` tags changed from `"trigger"` to `"code_change"` in 15 call sites across storage and hook scripts.
- **V3 to V4 SDK comment headers** (TD-377): Updated 9 source files from `# LANGFUSE: V3 ONLY` to `# LANGFUSE: V4 SDK`.
- **`AI_MEMORY_INSTALL_DIR` force-updated on merge** (TD-334): `merge_settings.py` now force-updates from hooks directory path, preventing stale install paths.
- **DRY hook utilities** (TD-338): Extracted shared functions to `scripts/hook_utils.py`. All 3 consumers (`generate_settings.py`, `merge_settings.py`, `recover_hook_guards.py`) import from it.
- **Robust matcher normalization** (BUG-078 hardening): Upgraded from exact-string match to frozenset-based approach. Scope-restricted to AI Memory hooks only.
- **Queue dir tilde + env var expansion** (TD-340): Validator now applies both `expanduser()` and `expandvars()`.
- **.env.example audit** (TD-340): All env vars verified against actual consumers. `QDRANT_READ_ONLY_API_KEY` documented.
- **Standardize Python base image** (TD-343): All 6 Dockerfiles now use `python:3.12-slim`.
- **Remove dead Dockerfile HEALTHCHECK instructions** (TD-349): Removed from 3 Dockerfiles — Docker Compose healthchecks are authoritative.
- **Document UID/GID env vars** (TD-344): Added to `.env.example` Section 6 (Container Identity).
- **Coverage config**: Extended `pyproject.toml` coverage source to include hook scripts and memory scripts. Excluded archived scripts from measurement.

### Upgrade Instructions

**From v2.2.8 to v2.3.0:**

1. **Pull the latest release:**
   ```bash
   cd /path/to/ai-memory
   git fetch origin && git checkout main && git pull
   ```

2. **Run the installer** (Option 1 for existing installations):
   ```bash
   ./scripts/install.sh /path/to/your/project
   # Select: Option 1 — Add project to existing installation
   ```

3. **Rebuild containers** (code is baked into Docker images, not volume-mounted):
   ```bash
   cd ~/.ai-memory/docker
   unset QDRANT_API_KEY
   docker compose build --no-cache github-sync streamlit embedding monitoring-api classifier-worker
   docker compose -f docker-compose.langfuse.yml build --no-cache trace-flush-worker evaluator-scheduler
   ```

4. **Restart the full stack:**
   ```bash
   cd ~/.ai-memory/docker
   unset QDRANT_API_KEY
   bash ../scripts/stack.sh restart
   ```
   Wait ~60 seconds for all services to reach healthy state.

   If upgrading from v2.2.x with the old Langfuse project name bug (BUG-265), first clean up the orphaned stack:
   ```bash
   docker compose -p docker -f docker-compose.langfuse.yml --profile langfuse down
   ```

5. **Verify:**
   ```bash
   # Health check (all services)
   bash ~/.ai-memory/scripts/memory/health_check.sh

   # Verify all 17 containers healthy (all should show "Up ... (healthy)")
   cd ~/.ai-memory/docker && docker compose ps -a

   # Verify 5 collections intact
   source ~/.ai-memory/docker/.env
   curl -sf -H "api-key: $QDRANT_API_KEY" http://localhost:26350/collections | python3 -m json.tool
   ```

**Important notes:**
- Always `unset QDRANT_API_KEY` before running `docker compose` commands. Shell env vars override `.env` file values, causing auth mismatches.
- The `github-sync` container has Python code baked into its Docker image. A rebuild is required after every code update.
- Run `docker compose` from `~/.ai-memory/docker/`, never from the source repo clone.

**Upgrade notes:**
- The `langfuse-minio-init` service is a one-shot container that creates the S3 bucket and exits. It runs before `langfuse-web` and `langfuse-worker` via `depends_on: service_completed_successfully`.
- `propagate_attributes()` replaces `update_trace()` (removed in Langfuse v4). If you have custom hooks that called `update_trace()`, migrate to `propagate_attributes(trace_name=..., session_id=..., user_id=..., metadata=..., tags=...)`.
- The evaluator now uses `api.legacy.observations_v1.get_many()` — this is the correct namespace for self-hosted Langfuse instances.
- The `trace-flush-worker` container must be rebuilt for hook pipeline traces to appear in Langfuse. Without this, the v4 smart span filter silently drops all `ai-memory.*` scoped spans.
- `hook_utils.py` is a new shared module — the installer copies it automatically.
- If you previously hand-edited `.claude/settings.json` matchers with `startup` or `clear`, they will be automatically cleaned on next `merge_settings.py` run.
- The authenticated Qdrant health check runs during fresh installs and reinstalls. If your Qdrant instance does not use an API key, the check is skipped with a warning.
- `AI_MEMORY_LOG_LEVEL`, `LOG_LEVEL`, and `BMAD_LOG_LEVEL` all set the log level. Priority: `AI_MEMORY_LOG_LEVEL` > `LOG_LEVEL` > `BMAD_LOG_LEVEL` (deprecated).
- `QDRANT_READ_ONLY_API_KEY` is optional. If not set, all Qdrant operations use the regular `QDRANT_API_KEY`.
- **Langfuse project unification** (BUG-265): After upgrade, you must stop the Langfuse stack using the old project name (`docker compose -p docker -f docker-compose.langfuse.yml down`) before restarting. Otherwise, orphaned containers from the old "docker" project will remain alongside the new "ai-memory" project containers.

---


## [2.2.8] - 2026-03-30 — Multi-IDE Adapter Support

Adds native lifecycle hook support for Gemini CLI, Cursor IDE, and Codex CLI alongside existing Claude Code integration. All four IDEs share the same memory pipeline through a canonical event schema — memories created in one IDE are available in all others.

### Added
- **Multi-IDE adapter layer** (FEATURE-001): Canonical event schema (`src/memory/adapters/schema.py`) normalizes hook events from Claude Code, Gemini CLI, Cursor IDE, and Codex CLI into a unified format. Each IDE has dedicated adapter scripts that translate native events and fork to the existing storage pipeline. Claude Code hooks remain unchanged — the adapter layer is purely additive.
- **Gemini CLI support**: 5 adapter scripts (session_start, after_tool_capture, error_detection, error_pattern_capture, pre_compress) + 3 TOML command templates (search-memory, memory-status, save-memory) for `.gemini/commands/`.
- **Cursor IDE support**: 5 adapter scripts (session_start, post_tool_capture, error_detection, error_pattern_capture, pre_compact) + 3 SKILL.md templates for `.cursor/skills/`.
- **Codex CLI support**: 5 adapter scripts (session_start, error_detection, error_pattern_capture, context_injection, stop) + 2 SKILL.md templates for `.agents/skills/` and `.codex/skills/`.
- **Installer IDE auto-detection**: `detect_gemini_cli()`, `detect_cursor_ide()`, `detect_codex_cli()` detect installed IDEs and generate native config files during installation. Supports `--ide` flag for explicit selection and `--force` for overwriting existing configs. Idempotent by default.
- **169 adapter tests**: Schema validation (62), Gemini normalizer (13), Cursor normalizer (25), Codex normalizer (20), cross-IDE integration (13), installer config generation (3+).

### Architecture
- **Strangler Fig pattern** (BP-119): Existing Claude Code hook scripts in `.claude/hooks/scripts/` are completely unchanged. New IDE adapters normalize their events via `schema.py` then call the same pipeline scripts (`store_async.py`, `error_store_async.py`, etc.). Zero breaking changes to existing installations.
- **Canonical event schema**: Stable envelope fields (`session_id`, `cwd`, `hook_event_name`, `ide_source`, `tool_name`, `tool_response`) with per-IDE normalizers that map native hook names and tool names to canonical values. MCP tool names normalized across all IDEs.

### How to Test (from feature branch)
1. Pull the feature branch: `git checkout fix/pr87-multi-ide-adapter-architecture`
2. Run the installer: `./scripts/install.sh <project-dir>` — IDE detection runs automatically
3. For Gemini CLI: check `.gemini/settings.json` was created with hook entries
4. For Cursor: check `.cursor/hooks.json` was created with hook entries
5. For Codex: check `.codex/hooks.json` was created with hook entries
6. Open a session in your IDE — session_start should inject memories
7. Report issues at https://github.com/Hidden-History/ai-memory/issues

## [2.2.7] - 2026-03-28 — Per-Project Tokens, Data Quality & Observability

Adds two-tier credential model for GitHub PATs, LLM-as-Judge eval visibility with threshold alerting, three deduplication quality gates, gRPC Qdrant client with HTTP fallback, HNSW inline storage, OTel startup retry, and PyPI/docs CI workflows.

### Fixed
- **Add-project flow silent auth failure** (BUG-245): Fine-grained PATs (`github_pat_*`) scoped to specific repos caused HTTP 404 when adding new projects, with no recovery path. Now shows token-type-aware error message and interactive 4-option recovery menu (per-project token, replace shared token, skip sync, continue anyway).
- **Backup script missing `github` collection** (BUG-246): `backup_qdrant.py` only backed up 4 of 5 collections — the `github` collection (13K+ points, largest collection) was missing. A `stack.sh nuke` without manual backup would lose all GitHub sync data. Added `github` to the COLLECTIONS list.
- **Classifier queue path not expanded** (BUG-247): `AI_MEMORY_QUEUE_DIR=~/.ai-memory/queue` in `.env` was read literally by Python (tilde not expanded), causing hooks to write to a `~` directory under CWD instead of `$HOME/.ai-memory/queue`. The classifier container read from the correct path but found an empty queue — classification was silently broken. Added `os.path.expanduser()` to queue path resolution. Installer now auto-cleans the stale literal `~` directory and migrates any stranded queue items.
- **Stale oversight templates removed**: Removed outdated V1 oversight template files (`PARZIVAL_AGENT_IMPROVEMENTS.md`, `PROJECT_IMPROVEMENTS.md`, `README.md`) from `templates/oversight/` that were superseded by the V2 POV system.
- **`test_touch_health_file_logs_failure` caplog miss**: The test was asserting log output from a logger with `propagate=False`, so `caplog` never captured it. Fixed by attaching the handler directly to the module logger, matching the pattern used across the test suite.

### Added
- **Per-project GitHub token support**: Optional `github.token` field in `projects.d/*.yaml` overrides the shared `GITHUB_TOKEN` for individual projects. Existing configs without the field continue to use the shared token (full backward compatibility).
- **Token-aware error handling**: Installer detects token type (fine-grained vs classic) and shows targeted guidance on auth failures. Warns against editing existing fine-grained PATs (known GitHub bug).
- **Interactive recovery menu**: 4 recovery options on auth failure — enter per-project token, replace shared token, skip GitHub sync, or continue anyway.
- **Non-interactive `GITHUB_PROJECT_TOKEN` env var**: CI/automation support for per-project tokens without interactive prompts.
- **Startup token validation**: github-sync container validates each project's token on startup, logs warnings for failures, and skips sync for projects with invalid tokens instead of crashing.
- **Sync engine per-project token resolution**: `GitHubSyncEngine` and code blob sync resolve per-project token before falling back to global `GITHUB_TOKEN`.
- **`list_projects.py` token visibility**: JSON output includes `has_per_project_token` boolean per project; table output adds a `TOKEN` column showing `project` or `shared` for each entry.
- **Eval threshold alerting** (TD-284): Prometheus metrics for LLM-as-Judge scores (`ai_memory_eval_score`, `ai_memory_eval_threshold_breach_total`). The evaluator runner pushes per-dimension scores and fires a breach counter when any score falls below its configured threshold. Alert rules in `ai-memory-alerts.yaml`.
- **Grafana evaluation dashboard** (TD-285): 6-panel dashboard (`evaluation-dashboard.json`) covering average eval score by dimension, threshold breach rate, score distribution heatmap, low-score traces table, eval latency, and a time-series view for trend analysis.
- **Agent response quality gate** (TD-048): `agent_response_store_async.py` rejects responses shorter than 50 characters and filters out pure acknowledgment patterns (e.g. "Sure!", "Got it.", "OK") before embedding. Prevents noise injection from low-signal responses.
- **User message semantic deduplication** (TD-049): `user_prompt_store_async.py` checks cosine similarity of the incoming message against the last 10 stored user messages (threshold 0.92) before storing. Near-duplicate re-submissions (e.g. repeated `/compact` triggers) are silently skipped.
- **Cross-collection deduplication** (TD-060): `deduplication.py` now checks the incoming content hash across all 5 Qdrant collections before storage, not just the target collection. Prevents identical content appearing in multiple collections. Configurable via `CROSS_DEDUP_ENABLED` (default: `true`); fail-open — a Qdrant error skips the cross-check and proceeds to store.
- **OTel DNS retry at startup** (TD-206): `langfuse_config.py` wraps the initial OTel connection attempt with tenacity exponential backoff (3 retries, 1s base, 10s max). Eliminates `NXDOMAIN` startup failures in Docker environments where the Langfuse container DNS name resolves slightly after the hook containers start.
- **PyPI trusted publishing** (TD-096): `.github/workflows/publish.yml` publishes the `ai-memory` package to PyPI on tagged releases using OIDC trusted publishing (no API key required). `.github/workflows/docs.yml` deploys Sphinx-generated docs to GitHub Pages on each push to `main`.

### Performance
- **HNSW inline_storage enabled** (TD-106): `setup-collections.py` now creates all collections with `hnsw_config.on_disk=False` and `quantization_config.always_ram=True`, keeping quantized vectors in RAM. Benchmarks show ~10x QPS improvement for quantized vector search. Existing collections are not migrated automatically — rebuild to benefit.
- **gRPC client with HTTP fallback** (TD-107): `qdrant_client.py` prefers gRPC (`prefer_grpc=True`, port `QDRANT_GRPC_PORT`, default `6334`) for all Qdrant operations. A probe on init detects gRPC unavailability and transparently falls back to HTTP, so deployments without gRPC exposed continue to work without config changes.

### Parzival Oversight
- **Mandatory team orchestration pipeline** (TD-316, GC-21): New global constraint requiring every agent dispatch to follow the full orchestration pipeline: TeamCreate → aim-parzival-team-builder → aim-bmad-dispatch/aim-agent-dispatch → aim-model-dispatch → Agent tool spawn (with `mode: "acceptEdits"` from project root) → aim-agent-lifecycle. Enforces fresh agent per task, one story per SM dispatch, `/bmad-bmm-code-review` for all review agents, `/bmad-agent-bmm-tech-writer` for all documentation tasks, and `/bmad-help` when unsure of available agents/workflows. Applied across 10 Parzival workflow and skill files.

### Documentation
- **INSTALL.md auth failure description corrected** (M-4): Recovery flow description now says "non-200 HTTP response (e.g., 401, 403, 404)" instead of the inaccurate "HTTP 404" — any non-200 triggers recovery, not just 404.
- **INSTALL.md `GITHUB_PROJECT_TOKEN` scope clarified** (L-4): Added note that `GITHUB_PROJECT_TOKEN` only applies in add-project mode (Option 1); initial setup uses `GITHUB_TOKEN`.
- **CONFIGURATION.md updated**: Added `QDRANT_GRPC_PORT` and `CROSS_DEDUP_ENABLED` reference entries.

### Update Instructions
After pulling v2.2.7:
1. Run `./scripts/install.sh <your-project-dir>` and choose Option 1 (Add project to existing installation) for each registered project — this updates all Python source files, deploys Parzival V2 with GC-21, and auto-cleans the stale BUG-247 tilde directory.
2. Rebuild the github-sync container (code baked into image, not volume-mounted):
   ```
   unset QDRANT_API_KEY
   cd ~/.ai-memory/docker
   docker compose build --no-cache github-sync
   docker compose up -d github-sync
   ```
3. Restart the classifier-worker to pick up the queue path fix: `cd ~/.ai-memory/docker && docker compose restart classifier-worker`

## [2.2.6] - 2026-03-26 — Multi-Project Installer Fix

Fixed the installer's add-project mode which silently registered new projects with the wrong GitHub repository (stale value from `.env`) and no Jira support.

### Fixed
- **Installer add-project registers wrong GitHub repo** (#85): The `add-project` flow (Option 1 on existing installation) skipped `configure_options()`, causing new projects to inherit the stale `GITHUB_REPO` from `.env` instead of prompting for project-specific values. New `configure_project_sources()` function auto-detects the GitHub repo from the project's `.git/config`, prompts for confirmation, and optionally configures Jira project keys.
- **github-sync not restarted after add-project**: New project registrations now automatically restart the github-sync container so the new project is picked up immediately.
- **Custom SSH hostnames break git URL detection**: `configure_project_sources()` required literal `github.com` in the hostname, failing on custom SSH config aliases like `github.com-hidden-history` (multi-account setups). Replaced with universal `[:/]` pattern that works with any git host.
- **Existing project config silently skipped on re-add**: `register_project_sync()` returned early when a `projects.d/` config already existed, giving no feedback. Now shows existing config values as defaults and allows updates.
- **Jira add-project prompts for raw text keys**: Free-text key entry was error-prone (e.g., user typing "n" captured as a project key). Replaced with Jira API project discovery — numbered selection, same UX as fresh install. Falls back to manual entry if API unreachable.
- **Stale `parzival-team.md` not cleaned from existing projects**: The deleted command (replaced by `aim-parzival-team-builder` skill in v2.2.4) was left behind in existing project installations. Installer now removes it during add-project runs.

### Added
- **7 Parzival dispatch skill shims**: `aim-agent-dispatch`, `aim-agent-lifecycle`, `aim-bmad-dispatch`, `aim-model-dispatch`, `aim-parzival-bootstrap`, `aim-parzival-constraints`, `aim-parzival-team-builder` — thin routing shims in `.claude/skills/` now ship with the installer. These were generated dynamically in v2.2.4 but never committed to the source repo, causing them to be missing from add-project installations.
- **Stale reference cleanup**: Removed deleted `/pov:parzival-team` command references from SESSION-GUIDE, INSTALL-GUIDE-POV, and aim-help.csv.
- **`docs/DISPATCH-SKILLS.md`**: New user guide for the Parzival dispatch skill suite — multi-provider LLM routing, team design, and agent lifecycle management.

### Upgrade Instructions

Three releases were published on 2026-03-26. Your upgrade steps depend on which version you're coming from:

#### From v2.2.3 or earlier → v2.2.6 (full upgrade)

You need container rebuilds (v2.2.4 code changes) + new features (v2.2.5) + this fix:

```bash
# Step 1: Pull latest code
cd /path/to/your/ai-memory-clone
git pull origin main

# Step 2: Run installer Option 1 on your project
./scripts/install.sh /path/to/your-project
# Select Option 1 (Add project to existing installation)

# Step 3: Rebuild ALL baked-code containers (required for v2.2.4 + v2.2.5 changes)
cd ~/.ai-memory/docker
unset QDRANT_API_KEY  # Prevent shell env overriding .env file

docker compose build --no-cache github-sync classifier-worker monitoring-api
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml \
  build --no-cache trace-flush-worker

# Step 4: Recreate baked containers + restart volume-mounted
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up -d \
  github-sync classifier-worker monitoring-api trace-flush-worker
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml restart \
  streamlit evaluator-scheduler

# Step 5: Verify
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml ps
```

See [v2.2.4](#224---2026-03-26) and [v2.2.5](#225---2026-03-26--batch-github-sync--include-overrides) entries below for details on new features and environment variables added in those releases.

#### From v2.2.4 → v2.2.6

You need v2.2.5 container rebuilds + this fix:

```bash
cd /path/to/your/ai-memory-clone
git pull origin main
./scripts/install.sh /path/to/your-project  # Option 1

cd ~/.ai-memory/docker
unset QDRANT_API_KEY
docker compose build --no-cache github-sync classifier-worker monitoring-api
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml \
  build --no-cache trace-flush-worker
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up -d \
  github-sync classifier-worker monitoring-api trace-flush-worker
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml restart \
  streamlit evaluator-scheduler
```

See [v2.2.5](#225---2026-03-26--batch-github-sync--include-overrides) for new optional environment variables.

#### From v2.2.5 → v2.2.6 (minimal upgrade)

This is a pure installer script fix — **no container rebuild needed**:

```bash
cd /path/to/your/ai-memory-clone
git pull origin main
./scripts/install.sh /path/to/your-project  # Option 1
```

The installer now prompts for project-specific GitHub repo and Jira config during add-project. github-sync restarts automatically.

#### Adding a new project to an existing installation (any version)

After upgrading to v2.2.6, adding additional projects now properly prompts for each project's GitHub repository:

```bash
cd /path/to/your/ai-memory-clone
./scripts/install.sh /path/to/new-project  # Option 1 auto-detected

# Installer will:
# 1. Auto-detect GitHub repo from project's .git/config
# 2. Prompt for confirmation (or manual entry)
# 3. Optionally configure Jira project keys
# 4. Register project in ~/.ai-memory/config/projects.d/
# 5. Restart github-sync to pick up new project
```

#### Verifying multi-project setup

```bash
# Check registered projects
ls ~/.ai-memory/config/projects.d/
cat ~/.ai-memory/config/projects.d/*.yaml

# Check github-sync is syncing all projects
cd ~/.ai-memory/docker
unset QDRANT_API_KEY
docker compose logs --tail=50 github-sync | grep "Syncing project"
```

## [2.2.5] - 2026-03-26 — Batch GitHub Sync + Include Overrides

Batched code blob sync with bounded concurrency and path-level include/exclude overrides for GitHub code blob indexing. Cherry-picked from contributor fork ([thecontstruct/ai-memory](https://github.com/thecontstruct/ai-memory)) with 36 code review findings resolved.

### Added
- **Batched code blob sync** (#76): Bounded file concurrency and batched embed+store for GitHub code blob ingestion. Configurable `file_concurrency` and `chunk_batch_size`. Supersede correctness (prior blob hash only), partial-batch rollback with `PointIdsList`, circuit-breaker consistency.
- **Path-level include overrides** (#77): `GITHUB_CODE_BLOB_INCLUDE` env var — comma-separated glob patterns to force-include files that would normally be filtered. Binary protection always wins. `GITHUB_CODE_BLOB_INCLUDE_MAX_SIZE` sets a hard ceiling (default: 5x `GITHUB_CODE_BLOB_MAX_SIZE`, max: 10MB).
- **`store_code_blobs_batch()`**: New batch storage method in `MemoryStorage` with sub-batch upserts, embedding count validation, and deterministic point IDs.
- **Shared `detect_language()`**: Language detection moved from `code_sync.py` to `extraction.py` for reuse. Case-insensitive Dockerfile detection. `.dockerfile` extension supported.
- **766 lines of new tests**: 2 new test files (`test_code_sync_batching.py`, `test_github_code_blob_batch_storage.py`) + 4 modified test files.

### Changed
- **Circuit breaker thread safety**: `RLock` protects all `ProviderState` mutations (safe with `asyncio.to_thread` concurrency).
- **Event loop safety**: `_get_stored_blob_map`, `_update_last_synced`, and `_supersede_old_blobs` wrapped in `asyncio.to_thread` (were blocking the event loop).
- **Supersede guard**: Batch path requires both full chunk completeness AND real embeddings before superseding old blobs (prevents replacing good data with zero-vector fallbacks).
- **`store_memories_batch()`**: Now uses sub-batch upserts (64-point cap) to avoid Qdrant gRPC 64MB limit. Shallow-copies input dicts to prevent caller mutation. Guards against `None` embeddings.
- **Pattern validation**: Bare `*` and `*.` patterns rejected (were matching everything via `endswith("")`). Structured logging with `setting_name` context.

### Activation Instructions

These features are **opt-in**. To activate include overrides:

#### Step 1: Add environment variables

Add to your `~/.ai-memory/docker/.env`:

```bash
# Force-include specific file patterns (bypasses standard filter skips, NOT binary protection)
# Supported: *.ext (extension match) or bare-token (path segment match, e.g. Makefile)
# NOT supported: path patterns with / (e.g. src/*.py), bare * or *. (too broad)
GITHUB_CODE_BLOB_INCLUDE=*.yaml,*.toml,Makefile,Dockerfile

# Hard ceiling for explicitly included files (default: 512000 = 5x base, max: 10MB)
# GITHUB_CODE_BLOB_INCLUDE_MAX_SIZE=512000
```

#### Step 2: Run Option 1 installer

```bash
cd /path/to/your/ai-memory-clone
git pull origin main
./scripts/install.sh /path/to/your-project
# Select Option 1 (Add project to existing installation)
```

#### Step 3: Rebuild and restart all containers

The batch sync changes are baked into the github-sync Docker image. All 4 baked-code containers should be rebuilt to pick up code changes, and volume-mounted containers restarted:

```bash
cd ~/.ai-memory/docker
unset QDRANT_API_KEY  # Prevent shell env overriding .env file

# Rebuild baked-code containers
docker compose build --no-cache github-sync classifier-worker monitoring-api
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml \
  build --no-cache trace-flush-worker

# Recreate baked containers (picks up new env vars from .env)
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up -d \
  github-sync classifier-worker monitoring-api trace-flush-worker

# Restart volume-mounted containers
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml restart \
  streamlit evaluator-scheduler
```

> **Important**: `docker compose restart` does NOT reload `.env` values. You must use `up -d` (recreate) for new environment variables to take effect.

#### Step 4: Verify

```bash
# Check all containers healthy
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml ps

# Verify include vars reached the container
docker inspect ai-memory-github-sync --format '{{range .Config.Env}}{{println .}}{{end}}' | grep INCLUDE

# Check logs for successful sync with included patterns
docker compose logs --tail=30 github-sync
```

Look for: no `invalid_include_pattern_ignored` warnings, successful sync messages with included file types.

### Fixed
- **36 code review findings resolved**: Rollback correctness (dead code, PointIdsList wrapper), supersede guards (completeness + embedding check), pattern validation (bare wildcard rejection), thread safety (circuit breaker RLock), event loop blocking (asyncio.to_thread wrapping), config ceiling (10MB cap), embedding guards (None fallback), and language map regressions.
- **Language map regressions**: Restored `"bash"` value (was changed to `"shell"`), added `.dockerfile` extension, case-insensitive Dockerfile detection.

---

## [2.2.4] - 2026-03-26

Parzival V2.1 shim architecture, 7 dispatch skills, and PLAN-018 Zero Debt Sprint: floating-point precision, reclassification protection, log level env var rename, Langfuse optional deps, SQL injection hardening, and full semantic tag coverage across all 108 hook trace calls.

### Added
- **Parzival V2.1 — shim architecture**: Dispatch skills, GC-19/GC-20 constraints, and POV step-file workflow architecture
- **7 Parzival skill shims**: `team-builder`, `agent-dispatch`, `bmad-dispatch`, `agent-lifecycle`, `model-dispatch`, `bootstrap`, `constraints` — thin routing shims (≤576 bytes each)
- **PLAN-019 Phase 6 — POV restructure swap**: `pov.restructured/` promoted to `pov/`, completing BMAD-compliant directory restructure (TD-306)
- **`knowledge/` directory**: POV reference data migrated from `data/` to `knowledge/` with 10 files including new `pov-index.csv` and status workflow docs
- **Step-file tri-modal architecture**: All 21 workflows now have `steps-c/` (create), `steps-e/` (edit), `steps-v/` (validate) directories with `checklist.md`, `instructions.md`, `workflow.yaml` per workflow

### Changed
- **Skill files converted to thin routing shims**: All Parzival skill files refactored to ≤576 bytes each for maintainability
- **Session start hook simplified**: Removed ambient injection per injection architecture v2.2 (sessions start clean)
- **pyproject.toml**: `black 26.3.0` formatting applied
- `.env.example` reorganized into 5 clear sections with all features enabled by default
- All PLAN/SPEC/BUG references removed from `.env.example` comments
- **36 audit findings resolved** (PM #211/212): 4 CRITICAL, 7 HIGH, 14 MEDIUM+LOW findings across skills, workflows, constraints, and knowledge docs
- **Constraint count**: 17 → 20 global constraints (GC-16 mandatory bug tracking, GC-17 complex bug unified spec, GC-18 oversight document sharding)

### Upgrade Instructions

> **Important**: The installer (Option 1) automatically merges new keys from `docker/.env.example` into your `docker/.env`, but it does **not** update existing key values. Review your `.env` after install to verify new keys have correct values for your setup.

#### Step 1: Pull latest code

```bash
cd /path/to/your/ai-memory-clone
git pull origin main
```

#### Step 2: Review new environment variables

Check `docker/.env.example` (updated by pull) for any new keys added in this release. The installer will append new keys to your `.env` with their default values, but you should review them after install. Existing key values in your `.env` are never overwritten.

**New in v2.2.4** — add these to your `~/.ai-memory/docker/.env` if missing:

```bash
# Section 3 — Feature Toggles (after SECURITY_SCANNING_ENABLED):
MONITORING_ENABLED=true

# Section 4.7 — GitHub Sync (uncomment if still commented):
GITHUB_SYNC_TOTAL_TIMEOUT=1800
GITHUB_SYNC_INSTALL_TIMEOUT=600
GITHUB_SYNC_PER_FILE_TIMEOUT=60
GITHUB_SYNC_CIRCUIT_BREAKER_THRESHOLD=5
GITHUB_SYNC_CIRCUIT_BREAKER_RESET=60

# Section 5 — Internal (after EMBEDDING_PORT):
QDRANT_TIMEOUT=30
QDRANT_USE_HTTPS=false

# Section 5 — Internal (before GRAFANA_ADMIN_USER):
AI_MEMORY_QUEUE_DIR=~/.ai-memory/queue
```

**If upgrading from pre-v2.2.4** — also rename these (old names still work with deprecation warning):
- `BMAD_LOG_LEVEL` → `AI_MEMORY_LOG_LEVEL`
- `BMAD_LOG_FORMAT` → `AI_MEMORY_LOG_FORMAT`

#### Step 3: Run Option 1 installer

```bash
./scripts/install.sh /path/to/your-project
# Select Option 1 (Add project to existing installation)
```

This syncs all code, scripts, monitoring, Docker files, skills, evaluators, and Parzival V2 package to your installation. Your `docker/.env` credentials are preserved.

#### Step 4: Rebuild containers with baked-in code

Four containers have code copied into their Docker images at build time and must be rebuilt after any code update:

```bash
cd ~/.ai-memory/docker
unset QDRANT_API_KEY  # Prevent shell env overriding .env file

# Rebuild baked-code containers (main compose)
docker compose build --no-cache github-sync classifier-worker monitoring-api

# Rebuild baked-code containers (Langfuse compose)
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml \
  build --no-cache trace-flush-worker
```

#### Step 5: Recreate rebuilt containers and restart volume-mounted containers

```bash
# Recreate containers with new images
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up -d \
  github-sync classifier-worker monitoring-api trace-flush-worker

# Restart volume-mounted containers to reload Python modules
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml restart \
  streamlit evaluator-scheduler
```

#### Step 6: Verify all containers are healthy

```bash
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml ps
# All containers should show "(healthy)"
```

#### Step 7: Langfuse (optional)

If you use Langfuse observability, install the extras group:
```bash
pip install ai-memory[observability]
```

#### Container reference

| Container | Code Delivery | After Update |
|-----------|--------------|--------------|
| github-sync | Baked (COPY in Dockerfile) | Rebuild + recreate |
| classifier-worker | Baked (COPY in Dockerfile) | Rebuild + recreate |
| monitoring-api | Baked (COPY in Dockerfile) | Rebuild + recreate |
| trace-flush-worker | Baked (COPY in Dockerfile) | Rebuild + recreate |
| streamlit | Volume-mounted (`../src:/app/src:ro`) | Restart only |
| evaluator-scheduler | Volume-mounted (`../src:/app/src:ro`) | Restart only |
| qdrant, embedding, prometheus, grafana, pushgateway, langfuse-* | Third-party images | No action needed |

#### Important notes

- **Always** run `unset QDRANT_API_KEY` before any `docker compose` operation — shell env vars override the `.env` file (pydantic-settings precedence)
- **Always** run `docker compose` from `~/.ai-memory/docker/`, never from the source repo (source `.env` has template values, installed `.env` has real credentials)
- Option 1 now syncs all directories including Docker files, monitoring, evaluators, and docs (BUG-244 fix)

### Fixed
- **Installer Option 1 skips pip install**: `update_shared_scripts()` synced new `pyproject.toml`/`requirements.txt` but never re-ran `pip install` in the venv — new dependencies (e.g. croniter) were missing until manual pip. Now runs `pip install -e .[dev]` in venv during Option 1 updates.
- **`__version__.py` out of sync**: Was stuck at `2.2.1` while `pyproject.toml` said `2.2.4`. Updated to `2.2.4` with version history entry.
- **github-sync freshness log write failure**: Container has `read_only: true` but `/app/.audit/logs/` had no writable volume mount — freshness scanner log writes failed silently. Added bind mount for logs directory.
- **BUG-244**: Installer Option 1 (`update_shared_scripts`) only synced 4 of 13 directories — extracted shared `sync_installed_files()` function used by both fresh install and Option 1. Also added Docker file sync with `.env` backup/restore to Option 1 path. Fixed pre-existing `log_warn` → `log_warning` typos.
- **BUG-236**: `docker/github-sync/requirements.txt` missing `tiktoken` — container crash loop after rebuild due to `memory.__init__` → `storage` → `chunking` → `truncation` → `tiktoken` import chain
- **TD-308**: Single `docker/.env` source of truth — restructured .env architecture
  - New 5-section `.env.example` layout (API Keys, Auto-Generated, Feature Toggles, Configuration, Internal)
  - `import_user_env()` deprecated (no longer imports from root `.env`)
  - Fixed `upgrade.sh` reading `.env` from wrong path (`$INSTALL_DIR/.env` → `$INSTALL_DIR/docker/.env`)
  - Fixed `rollback.sh` restoring `.env` to wrong location (now restores to `docker/`)
  - Fixed `classifier/config.py` searching `~/.ai-memory/.env` (now `~/.ai-memory/docker/.env`)
  - Fixed `config.py` pydantic `env_file` to use absolute path via `AI_MEMORY_INSTALL_DIR`
  - All compose-referenced vars now uncommented in `.env.example` (11 were previously commented or missing)
- **BUG-218**: RRF score floating-point precision (`0.9500000000000001` exceeds range)
- **BUG-219**: `store_async.py` missing explicit `source_type="user_session"` on `scanner.scan()` call
- **BUG-222**: Verified `step-03-create-handoff.md` exists in Parzival close workflow (QA report referenced wrong filename)
- **BUG-225**: `SKIP_RECLASSIFICATION_TYPES` expanded to protect `agent_response`, `decision`, `agent_handoff`
- **BUG-227**: Installer Option 1 now updates `docker/.env.example`
- **BUG-228–235**: Copy-paste tags, hook_type labels, Langfuse port fixes, caplog reliability, log format tests
- **TD-262**: Log level/format env vars renamed to `AI_MEMORY_*` (`BMAD_*` deprecated with warnings)
- **TD-189**: Langfuse moved to optional dependencies
- **TD-275/289**: Semantic tags on all 108 `emit_trace_event` calls in hook scripts
- **TD-290**: `@observe(as_type="generation")` on classifier LLM calls
- **TD-291–292**: Freshness naming consistency, quality gate push metrics
- **injection.py case-sensitivity**: Fixed `CONSTRAINTS.md` → `constraints.md` path references (lines 882, 901) for Linux filesystem compatibility
- **Issue #73**: `github_sync_total_timeout` ceiling raised from 2 hours to 7 days — supports large-repo initial syncs without source patching
- **Issue #74**: `scripts/list_projects.py` rewritten to work without importing `memory` package — runs with system Python, no venv required
- **Issue #75**: `health-check.py` skips monitoring checks when `MONITORING_ENABLED=false` — shows "skipped" instead of noisy "connection refused" warnings
- **Installer stale cleanup**: Added `pov/data/` directory removal for users upgrading from pre-v2.2.4 installations
- **BUG-237**: 9 test-ordering isolation flakes documented (pre-existing BUG-209/BUG-234 pattern — tests pass individually)
- **BUG-238**: Langfuse RAM check crashes on macOS — `/proc/meminfo` replaced with OS-aware check (`sysctl -n hw.memsize` on macOS, `/proc/meminfo` on Linux) (GitHub #71)
- **BUG-239**: `set -e` + `result=$(...)` silent installer abort — full audit of `install.sh`, all non-subshell-safe command substitutions corrected (GitHub #71)
- **BUG-240**: `JIRA_PROJECTS` non-interactive `JSONDecodeError` — comma-separated value now normalized to JSON array in non-interactive install path (GitHub #71)
- **BUG-241**: Stale `docker/.env` on `add-project` — non-interactive `add-project` now runs `configure_environment` for project-specific vars (GitHub #71)
- **BUG-242**: `GITHUB_REPO` format not validated — `owner/repo` format check added before GitHub API calls (GitHub #71)
- **BUG-243**: `register_project_sync`/`projects.d` skipped in non-interactive path — wired into non-interactive flow; `INSTALL.md` updated with non-interactive multi-project instructions (GitHub #71)

### Security
- **TD-220**: SQL injection fix in `langfuse_setup.sh` (parameterized psql queries)

---

## [2.2.3] - 2026-03-15

Complete Langfuse observability pipeline: observation-level evaluation for all 6 evaluators, automated scheduling, exponential backoff retry, and security hardening.

### Added
- **Observation-level evaluation**: Runner scores individual Langfuse observations (spans) for EV-01 to EV-04, not just whole traces. Enables per-retrieval, per-injection, per-capture quality scoring
- **Evaluator-scheduler container**: Automated daily evaluations via `evaluator-scheduler` Docker service with `croniter`-based scheduling, health checks, graceful shutdown, and live config reload
- **Exponential backoff retry**: Provider retries on HTTP 500/502/503/429 and network errors (ConnectionError, TimeoutError) with configurable `max_retries` (default: 3) and jitter
- **12 evaluator files on disk**: 6 YAML configs + 6 prompt templates materialized from PLAN-012 spec. Filters aligned to actual `emit_trace_event()` event_types via codebase audit
- **Score config idempotency**: `create_score_configs.py` pre-checks existing configs via `.get()` API; `--cleanup-duplicates` archives extras via `update(isArchived=True)`
- **Ollama cloud auto-detection**: Provider automatically uses `https://ollama.com/v1` when `OLLAMA_API_KEY` env var is set (no manual `base_url` config needed)
- **Installer copies evaluator files**: Both fresh install and Option 1 update paths copy `evaluator_config.yaml`, `evaluators/`, `requirements.txt`, and `pyproject.toml`
- **Installer imports .env on Option 1**: `import_user_env()` now runs during add-project updates, not just fresh installs — ensures credentials like `OLLAMA_API_KEY` reach the installed `.env`

### Changed
- **Default evaluator model**: `gemma3:4b` (Ollama cloud compatible) replaces `llama3.2:8b` (not available on cloud)
- **Observation filtering**: Path B — evaluators filter observations by `name` (event_type) instead of tags. Langfuse V3 does not support observation-level tags; trace-level tags remain for trace filtering
- **Pagination**: Both `trace.list()` and `observations.get_many()` use page-based pagination per V3 SDK (`page=`, `total_pages`)

### Fixed
- **Log injection sanitization**: All `str(e)` in `monitoring/main.py` log statements wrapped with `sanitize_log_input()` inline at call sites (CodeQL `py/log-injection` compliance)
- **CATEGORICAL score handling**: EV-04 passes string values (`"correct"`, `"partially_correct"`, `"incorrect"`) with validation against allowed categories before submission
- **Score ID collision**: `_make_score_id()` includes `observation_id` in hash seed — prevents silent overwrites when multiple observations share a trace
- **Installer `SOURCE_DIR` unbound**: `import_user_env()` falls back to `SCRIPT_DIR/..` in Option 1 path

### Security
- **7 CodeQL HIGH findings resolved**: `monitoring/main.py` log injection vectors sanitized at every call site with AST-verified test coverage

### Upgrade Instructions

1. **Pull and run installer**:
   ```bash
   cd /path/to/your/ai-memory-clone
   git pull origin main
   ./scripts/install.sh /path/to/your-project
   # Select Option 1 (Add project to existing installation)
   ```

2. **Build and start the evaluator-scheduler container**:
   ```bash
   cd ~/.ai-memory/docker
   unset QDRANT_API_KEY
   docker compose -f docker-compose.yml -f docker-compose.langfuse.yml build evaluator-scheduler
   docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile langfuse up -d evaluator-scheduler
   ```

3. **Create score configs** (one-time, idempotent):
   ```bash
   cd /path/to/your/ai-memory-clone
   source .venv/bin/activate
   cd ~/.ai-memory
   set -a && source docker/.env && set +a && unset QDRANT_API_KEY
   python scripts/create_score_configs.py
   ```

4. **Configure evaluator provider** (optional — defaults to Ollama):
   - **Ollama cloud**: Set `OLLAMA_API_KEY` in your `.env` (auto-detects cloud endpoint)
   - **Local Ollama**: No config needed (default `http://localhost:11434/v1`)
   - **Other providers**: Edit `evaluator_config.yaml` `provider:` field
   - Model: Edit `evaluator_config.yaml` `model_name:` (default: `gemma3:4b`)

5. **Run evaluations manually** (optional — scheduler runs daily at 05:00 UTC):
   ```bash
   python scripts/run_evaluations.py --config evaluator_config.yaml
   ```

---

## [2.2.2] - 2026-03-13

AI Memory System Optimization: Unified behavior specification, per-collection confidence gating, freshness injection blocking, error-to-fix linkage, remembrance protection, and best practices auto-activation.

### Added
- **Per-collection confidence thresholds**: Tier 2 injection uses collection-specific thresholds (conventions: 0.65, code-patterns: 0.55, discussions: 0.60) instead of a single global threshold
- **4-tier gating model**: HARD SKIP / SOFT SKIP / SOFT GATE / FULL — graduated injection based on confidence with hard floor at 0.45
- **Freshness injection blocking**: STALE and EXPIRED code patterns blocked from injection with score penalty 0.0. Prometheus counter tracks blocked injections
- **Error-to-fix linkage**: Errors and fixes linked via deterministic `error_group_id` (SHA-256). Two-phase retrieval finds similar errors then follows links to paired fixes. Resolution confidence scoring (0.3-0.9)
- **Best practices auto-activation**: Retrieves relevant best practices when error detected in same file or 3+ edits to same file. Confidence gate at 0.6
- **Remembrance protection**: Frequently-retrieved memories (access_count >= 3) exempt from temporal decay. Batch `set_payload` for efficient tracking
- **Agent-scoped compact restore**: Named agents get their own cross-session memories filtered by `agent_id`. Parzival: 3 summaries + 5 decisions; other named agents: 2 + 3
- **Chunked embedding for session summaries**: Session summaries use Jina mean-pooling endpoint for better retrieval precision (BP-028)
- **Freshness metrics**: 4 Prometheus metrics (status gauge, scan counter, blocked injections counter, scan duration histogram)
- **Unified Behavior Specification**: `AI-Memory-Behavior-Spec-V1.md` — single source of truth for all memory system behavior

### Changed
- **`max_retrievals` default**: Increased from 5 to 10 for broader recall
- **Code chunk size**: Increased from 512 to 1024 tokens for better function body capture
- **Minimum chunk filtering**: Chunks below 50 tokens filtered out (removes trivial one-liners)
- **Prose overlap**: Corrected to 15% per spec (was inadvertently 20%)
- **Cross-turn dedup**: `access_count` increments deduplicated within a turn to prevent inflation

### Fixed
- **Hook exit codes**: All hooks now exit 0 on failure per §1.2 Principle 4
- **Metric name prefix**: `aim_freshness_blocked_injections_total` corrected to `ai_memory_freshness_blocked_injections_total`
- **Missing `access_count` field**: Added to agent_response, user_prompt, and manual_save store payloads (§2.2)
- **Dead code removal**: ~175 lines of unused functions removed from session_start.py
- **Error pattern false positives**: Replaced substring matching with pattern matching for actual error indicators
- **Tier 2 type filtering**: Discussions excludes user_message/error_pattern; code-patterns excludes error_pattern
- **Terminology**: "late chunking" renamed to "chunked embedding" (TD-274 for true late chunking)
- **Freshness field names**: Standardized to `checked_at`, `freshness_status` (lowercase), tags `["freshness"]`
- **Langfuse V3 compliance**: Full audit confirmed zero V2 violations across 31 files

### Deprecated
- `Context-Injection-V2.md` — superseded by AI-Memory-Behavior-Spec-V1.md §4
- `Core-Architecture-Principle-V2.md` §7.2/§15 — superseded by Behavior-Spec-V1 §4/§7
- `Temporal-Awareness-V1.md` §3 — contradicts zero-truncation principle, superseded by Behavior-Spec-V1 §4.2.5
- `Chunking-Strategy-V2.md` §2.1/§2.6 — clarified in Behavior-Spec-V1 §7.4
- `GitHub-Integration-V1.md` — collection targeting superseded by Behavior-Spec-V1 §2.1

### Upgrade Instructions

1. **Update code and reinstall** (from your ai-memory clone):
   ```bash
   cd /path/to/your/ai-memory-clone
   git pull origin main
   ./scripts/install.sh /path/to/your-project
   # Select Option 1 (Add project to existing installation)
   ```

   No migration required. All changes are Python-level (hooks, library, scripts). No Docker rebuild needed.

## [2.2.1] - 2026-03-10

Triple Fusion Hybrid Search (PLAN-013): Dense vectors augmented with BM25 sparse vectors and optional ColBERT late interaction reranking via Qdrant's native RRF fusion. 4-path search composition with automatic fallback. RRF score normalization to [0.5, 0.95] range for compatibility with existing confidence thresholds.

### Added
- **BM25 sparse vectors**: All 5 collections gain BM25/IDF sparse embeddings via fastembed `Qdrant/bm25` model, stored alongside dense vectors
- **ColBERT late interaction reranking** (opt-in): `COLBERT_RERANKING_ENABLED=true` adds ColBERT multi-vector reranking via embedding service `/rerank` endpoint
- **4-path search composition**: PATH 1 (hybrid+decay), PATH 2 (hybrid-only), PATH 3 (decay-only), PATH 4 (plain dense) — automatic fallback through paths
- **Sparse embedding in hooks**: `store_async.py` generates BM25 sparse vectors alongside dense embeddings for code-pattern storage
- **Migration script**: `scripts/migrate_v221_hybrid_vectors.py` — idempotent, resumable migration that adds BM25 sparse vectors to existing collections
- **Installer migration notice**: Success message includes hybrid search migration command for existing installations
- **BM25 model pre-download**: Embedding service Dockerfile downloads `Qdrant/bm25` model at build time (no cold-start delay)
- **`COLBERT_ENABLED` passthrough**: Docker Compose passes ColBERT toggle to embedding container
- **Langfuse trace tags** (PLAN-014): All 93 trace emit calls now include semantic tags (capture, retrieval, injection, bootstrap, search, embedding, etc.) for Langfuse dashboard filtering
- **Skill tracing** (PLAN-014): 9 Python-based skills instrumented with Langfuse trace events
- **Embedding GENERATION traces** (PLAN-014): Dense, sparse, and ColBERT embedding API calls emit Langfuse GENERATION observations with model and usage metadata
- **Turnkey hybrid search enablement**: `scripts/enable-hybrid-search.sh` and `stack.sh enable-hybrid` for one-command hybrid search setup (pre-flight checks, container rebuild, migration, verification)
- **`discussion` memory type**: New MemoryType for general discussion points (total types: 31)

### Changed
- **`hybrid_search_enabled` default**: Changed from `True` to `False` in config.py for backward compatibility — requires explicit opt-in + migration
- **Search result tagging**: All results now include `search_mode` field for downstream observability
- **pytest configuration**: Migrated from `pytest.ini` to `pyproject.toml`; removed redundant `sys.path.insert()` from test files

### Fixed
- **Prometheus stale bcrypt hash** (BUG-210, BLK-021): `web.yml` had a hardcoded bcrypt hash that became stale on password changes/reinstalls, causing health check 401 failures. Init container now generates `web.yml` at runtime from `PROMETHEUS_ADMIN_PASSWORD` with a fresh bcrypt hash. Uses stock `prom/prometheus:v2.55.1` image — no custom Dockerfile required.
- **Conditional exports** (TD-197): `AsyncSDKWrapper` names only exported when `anthropic` is installed, preventing `NameError` in embedding container
- **DEC-062 RRF score normalization**: RRF reciprocal-rank scores (~0.01-0.05) normalized to [0.5, 0.95] range using min-max scaling. Prevents confidence gating bypass, score gap filter malfunction, and adaptive budget distortion.
- **Missing `github` collection in decay**: `resolve_half_life()` now includes `github` collection with configurable `decay_half_life_github` (default: 14 days)
- **EmbeddingClient resource leak**: `pre_compact_save.py` now uses `with` context manager for EmbeddingClient
- **`COLBERT_ENABLED` env var**: Was missing from docker-compose embedding service environment
- **Installer Option 1 Docker sync**: Add-project mode now copies Docker files (Dockerfiles, main.py, requirements.txt) and merges new `.env.example` keys — previously only full reinstall (Option 2) updated Docker files

### Upgrade Instructions

1. **Update code and reinstall** (from your ai-memory clone):
   ```bash
   cd /path/to/your/ai-memory-clone
   git pull origin main
   ./scripts/install.sh /path/to/your-project
   # Select Option 1 (Add project to existing installation)
   # This updates hooks, scripts, skills, AND Docker files
   ```

2. **Recreate Prometheus** (required — fixes health check 401):
   ```bash
   cd ~/.ai-memory/docker
   unset QDRANT_API_KEY
   docker compose --profile monitoring up -d --force-recreate prometheus-init prometheus
   ```
   This starts the new init container which generates `web.yml` with a fresh bcrypt hash from `PROMETHEUS_ADMIN_PASSWORD`. No image rebuild required — uses stock Prometheus image.

3. **Enable hybrid search** (run from anywhere):
   ```bash
   unset QDRANT_API_KEY && ~/.ai-memory/scripts/enable-hybrid-search.sh
   ```
   Or equivalently:
   ```bash
   unset QDRANT_API_KEY && ~/.ai-memory/scripts/stack.sh enable-hybrid
   ```
   This handles everything automatically:
   - Pre-flight checks (Docker, Qdrant, embedding health)
   - Embedding container rebuild (adds BM25 sparse model)
   - Configuration update (`HYBRID_SEARCH_ENABLED=true`)
   - Data migration (adds sparse vectors to existing Qdrant points)
   - Verification (confirms hybrid search is operational)

4. **Optional — ColBERT reranking**:
   ```bash
   # Add to ~/.ai-memory/docker/.env BEFORE running enable-hybrid-search.sh:
   COLBERT_ENABLED=true
   COLBERT_RERANKING_ENABLED=true
   ```

5. **No Qdrant schema changes required**: Sparse vectors are added alongside existing dense vectors. Plain dense search continues to work without migration.

> **Note**: The installer Option 1 now syncs Docker files (Dockerfiles, main.py, requirements.txt, docker-compose.yml) alongside hooks, scripts, and skills. Previous versions required Option 2 (full reinstall) for Docker changes.

---

## [2.2.0] - 2026-03-08

Agent-activated architecture (PLAN-011 + PLAN-012): Cross-session memory moves from automatic ambient injection to agent-activated retrieval via skills. Sessions start clean — no Qdrant noise on startup or resume. Parzival V2 deployment with deployable `_ai-memory/` package, PCB step-file workflows, constraint re-injection, and layered bootstrap skill. Installer upgraded with V2 deployment pipeline, V1-to-V2 migration, and stale matcher cleanup.

### Added

#### Parzival V2 Deployment Architecture (PLAN-011)
- **Deployable `_ai-memory/` package**: Self-contained Parzival agent with POV workflows, constraints, config, and `_memory/` user data directory — deployed to both install dir and project dir
- **PCB step-file workflows**: Multi-step session start, closeout, and team orchestration workflows using file-based step sequencing
- **9 command shims**: `/pov:parzival`, `/pov:parzival-start`, `/pov:parzival-closeout`, `/pov:parzival-status`, `/pov:parzival-handoff`, `/pov:parzival-blocker`, `/pov:parzival-decision`, `/pov:parzival-team`, `/pov:parzival-verify`
- **Agent-activated bootstrap**: `/aim-parzival-bootstrap` skill with 4-layer retrieval (L1: last handoff, L2: recent decisions, L3: insights, L4: GitHub enrichment) — replaces ambient injection
- **Constraint re-injection**: `/aim-parzival-constraints` skill loads behavioral constraints (GC-01 through GC-13) on activation and post-compact
- **GC-13 constraint**: "ALWAYS Research Best Practices Before Dispatching for New Tech or After Failed Fix" — 5 mandatory triggers integrated into 4 workflow steps
- **`update-pov.sh`**: Script to update Parzival agent files from upstream source

#### Session Injection Fix (PLAN-012)
- **Resume handler (DEC-054)**: `session_start.py` now outputs NOTHING on resume — Claude Code restores sessions natively. No Qdrant connection made.
- **Non-Parzival compact (DEC-055)**: Outputs rich session summary ONLY (`get_recent(type=session, limit=1)`) — no decisions, patterns, or conventions injected
- **Parzival compact (DEC-056)**: Outputs session summaries(3) + decisions(5) + filesystem constraints — unchanged from previous behavior

#### Installer V2 Pipeline (PLAN-011a)
- **7 new installer functions**: `deploy_parzival_v2()`, `deploy_ai_memory_skills()`, `deploy_ai_memory_agents()`, `deploy_parzival_commands()`, `sync_parzival_config_yaml()`, `create_project_symlinks()`, `cleanup_parzival_v1()`
- **V1-to-V2 upgrade**: Automatic backup and removal of V1 Parzival directories (`agents/parzival/`, `commands/parzival/`)
- **V1 skill cleanup**: 13 old skill names (`memory-status`, `search-memory`, etc.) automatically removed on install, replaced by `aim-*` prefixed equivalents
- **`_memory/` preservation**: User-created memory files backed up and restored during `_ai-memory/` package updates (PID-suffixed for race safety)

### Changed

#### Session Start Behavior (Breaking)
- **`startup` trigger removed**: SessionStart hook no longer fires on new sessions. Sessions start clean with zero Qdrant queries.
- **Matcher narrowed**: `generate_settings.py` now generates `"resume|compact"` (was `"startup|resume|compact"`)
- **`merge_settings.py` matcher normalization**: New `_normalize_session_start_matcher()` strips vestigial `startup` from existing matchers during upgrade. Ensures all installations get the correct v2.2.0 behavior.
- **Non-Parzival compact simplified**: Replaced 20-session + decisions + patterns + conventions retrieval (~4000 tokens) with single rich session summary (~500 tokens)

#### Parzival Agent
- **Bootstrap moved to skill**: Cross-session memory loaded via `/aim-parzival-bootstrap` (agent-activated), not automatically injected
- **Constraints loaded via skill**: `/aim-parzival-constraints` replaces inline constraint loading
- **Handoff/insight Qdrant save**: `/parzival-save-handoff` and `/parzival-save-insight` skills for cross-session persistence

### Fixed
- **BUG-206**: Session start injecting ~4000 tokens of Qdrant noise on every resume/compact event
- **BUG-207**: `generate_settings.py` verified — produces correct `"resume|compact"` matcher (no code change needed)
- **FAIL-03**: `merge_settings.py` preserving stale `startup` matcher on upgrade from v2.1.0
- **FAIL-07**: 13 stale V1 skill directories not cleaned during install (duplicate skills in menu)

### Upgrade Instructions

#### Existing Installations

**Important**: v2.2.0 changes the session start behavior. After upgrading, sessions start clean — no automatic Qdrant injection on new sessions or resume. Cross-session memory is now accessed via skills (`/aim-parzival-bootstrap`, `/aim-search`).

1. Update code and reinstall:
   ```bash
   cd /path/to/your/ai-memory-clone
   git pull origin main
   ./scripts/install.sh /path/to/your-project
   # Select Option 1 when prompted (updates hooks and code only)
   ```

2. **Verify matcher was updated**: After install, check your project's `.claude/settings.json`:
   ```bash
   grep -A2 'session_start.py' /path/to/your-project/.claude/settings.json
   ```
   The `"matcher"` field should be `"resume|compact"` (NOT `"startup|resume|compact"`). The installer handles this automatically via `merge_settings.py`, but verify on first upgrade.

3. **V1 skill cleanup is automatic**: The installer removes 13 old V1-named skill directories. You should see 17 skills (not 30) in `/path/to/your-project/.claude/skills/` after upgrade.

4. **No migration scripts required**: v2.2.0 does not change Qdrant collections or data format.

5. **No container rebuilds required**: All changes are in hook scripts and installer code (volume-mounted, not baked into Docker images).

#### Parzival Users

If you use Parzival oversight agent:

1. Run the installer as above (deploys `_ai-memory/` package automatically)
2. On first session, activate with `/pov:parzival` (new command format)
3. Cross-session memory is now loaded via `/aim-parzival-bootstrap` (called automatically by the session start workflow)
4. Constraints are loaded via `/aim-parzival-constraints` (called at activation and after compact events)
5. Old V1 commands (`/parzival-start`, etc.) are replaced by `/pov:parzival-start` — the installer removes V1 directories automatically

#### New Installations

No special action needed — `install.sh` deploys the complete v2.2.0 architecture including Parzival V2 package, correct matchers, and all skills.

---

## [2.1.0] - 2026-03-03

Observability and code quality sprint: full Langfuse V3 SDK migration across all services, agent identity metadata for per-agent trace filtering, and graceful shutdown handling for Docker workers.

### Added
- **Agent identity metadata**: All Langfuse trace events now include `agent_name` and `agent_role` in metadata, enabling per-agent filtering in the Langfuse UI. Defaults to `main`/`user` for non-team sessions.
- **Graceful Langfuse shutdown**: `atexit` handlers added to classification worker (`process_classification_queue.py`), GitHub sync (`sync.py`), and code sync (`code_sync.py`) Docker services for reliable span flushing on container stop.
- **Session ID propagation**: All 4 `emit_trace_event()` calls in `search.py` now include `session_id` for end-to-end trace correlation in Langfuse.

### Changed
- **Langfuse V3 SDK migration**: All instrumentation migrated from V2 to V3 SDK across the entire codebase. Uses `get_client()`, `start_as_current_observation()`, `propagate_attributes()`. V2 patterns (`Langfuse()` constructor, `start_span()`, `langfuse_context`) are project-banned.
- **V3 compliance review**: 2 critical, 6 standard, and 9 warning-level issues resolved across 18 files (commit `77e9f97`).
- **`TRACE_CONTENT_MAX` standardization**: Replaced 4 hardcoded `[:10000]` literals in `search.py` with `TRACE_CONTENT_MAX` constant per LANGFUSE-INTEGRATION-SPEC §9.2.
- **ClickHouse memory limit**: Set explicit 16 GiB cap in `clickhouse-config.xml` (up from previous 4 GiB, down from ClickHouse unlimited default) to balance query performance with OOM prevention on constrained hosts.
- **Type name correction**: Renamed `error_fix` → `error_pattern` across 36 files for consistency with the error pattern detection rewrite in v2.0.9.
- **Installer permissions**: Added `chmod +x` for executable files in subdirectories during installation.

### Fixed
- **BUG-175**: Flaky rate limiter integration test — replaced real-time sleep with mocked `asyncio.sleep` for deterministic behavior.
- **TD-236/237/238/239**: Stale task tracker entries reconciled.
- **TD-240/241/243**: Quality sprint tech debt items resolved.
- **TD-245**: GitHub sync missing atexit Langfuse shutdown handler.
- **TD-246**: Code sync missing atexit Langfuse shutdown handler.

### Upgrade Instructions

v2.1.0 is a non-breaking, additive release. No migration scripts required.

1. Pull latest code: `git pull origin main`
2. Reinstall: `pip install -e .` (or re-run installer Option 1 for full installations)
3. If using ClickHouse: note the memory cap is now 16 GiB in `clickhouse-config.xml` (was 4 GiB)

**Optional environment variables** (new, with sensible defaults):
- `CLAUDE_AGENT_NAME` — Agent identity for Langfuse traces (default: `main`)
- `CLAUDE_AGENT_ROLE` — Agent role for Langfuse traces (default: `user`)
- `LANGFUSE_FLUSH_TIMEOUT_SECONDS` — Langfuse flush timeout (default: `15`)

## [2.0.9] - 2026-03-02

Injection quality sprint (PLAN-010): Dedicated `github` Qdrant collection for GitHub-synced data, fixing 79.6% noise in discussions. Structured error pattern detection eliminates false positives. Tier 2 context injection now filters by memory type. Content quality gate prevents low-value messages from being stored. Langfuse observability with 7 emit_trace_event() calls across search, injection, and session pipelines. Parzival layered priority bootstrap with deterministic + semantic retrieval layers.

### Added

#### Dedicated GitHub Collection (PLAN-010)
- New `github` Qdrant collection (768-dim, cosine, HNSW on-disk, int8 quantization) for all GitHub-synced data
- `COLLECTION_GITHUB` constant in `config.py` as single source of truth
- 7 GitHub-specific indexes: `source`, `github_id`, `file_path`, `sha`, `state`, `last_synced`, `update_batch_id`
- `decay_half_life_github` configuration field (default 14 days)
- Migration script `migrate_v209_github_collection.py` — idempotent, --dry-run support, audit logging

#### Langfuse Observability
- 7 `emit_trace_event()` calls across search, injection, and session_start pipelines
- Trace events for compact/resume retrieval paths
- Session ID linking for end-to-end trace correlation

#### Parzival Layered Priority Bootstrap
- L1 [DETERMINISTIC]: Last handoff via `get_recent()` timestamp-sorted scroll
- L2 [DETERMINISTIC]: Recent decisions (5) via `get_recent()`
- L3 [SEMANTIC]: Recent insights (3) via `search()`
- L4 [SEMANTIC]: GitHub enrichment (10) via `search()` on github collection
- Results returned in layer order, not score-sorted
- Score gap filter excludes deterministic results from semantic threshold calculation

#### Content Quality Gate
- Skip storing messages under 4 words or matching low-value patterns ("ok", "yes", "lgtm", "nothing to add")
- Applied to both `user_prompt_store_async.py` and `agent_response_store_async.py`

### Changed

#### GitHub Sync Target Collection
- `github_sync.py`, `code_sync.py`, `sync.py` now write to `github` collection instead of `discussions`
- `schema.py` imports `COLLECTION_GITHUB` from `config.py` (eliminates duplicate constant)
- Parzival L4 enrichment queries `github` collection instead of filtering discussions

#### Tier 2 Context Injection Type Filters
- `context_injection_tier2.py` now filters by `memory_type` IN (`decision`, `guideline`, `session`, `agent_insight`, `agent_handoff`, `agent_memory`)
- Excludes `user_message`, `agent_response`, `error_fix`, `github_code_blob` from injection
- Uses `COLLECTION_DISCUSSIONS` constant instead of hardcoded string

#### Error Pattern Detection Rewrite
- `error_pattern_capture.py` `detect_error_indicators()` completely rewritten
- Now detects directory listing output and skips file-path-only content
- Structured error patterns: `TypeError:`, `Traceback (most recent`, `npm ERR!`, `exit code [1-9]`, `FAILED`, `command not found`, `permission denied`, `no such file`
- Eliminates false positives from filenames containing "error" (e.g., `error-handling.md`)

#### Content-Type-Aware Embedding Model Routing
- `search.py` routes code content to `jina-embeddings-v2-base-code` model
- Prose content continues using `jina-embeddings-v2-base-en`

### Fixed
- BUG-197: Lazy import `contextlib.suppress` for optional anthropic dependency
- BUG-198/199: Langfuse trace event fixes (PM #135)
- BUG-200: Error pattern capture false positives — 100% of code-patterns were garbage (PLAN-010)
- BUG-201: Tier 2 injection missing type filter — injected "nothing to add" at 99% similarity (PLAN-010)
- BUG-204: Langfuse trace visibility — removed 15 hardcoded `[:300]` truncations across 5 hook scripts. `TRACE_CONTENT_MAX=10000` standardized everywhere. Full pipeline content now visible in Langfuse traces.
- BUG-205: Installer Option 1 (`update_shared_scripts()`) now copies all files recursively — previously used `*.py` glob that missed `scripts/memory/` (33 files) and `.sh` files (6 files). Added `chmod +x` parity with `copy_files()`.
- TD-237: Classifier LLM prompt now includes `error_pattern` type definition, preventing reclassification to wrong type
- CodeQL: Removed partial API key logging from migration script (CWE-117)
- Migration script now renames remaining `error_fix` → `error_pattern` in code-patterns after purging false positives
- E2E test screenshots directory fixture (TD-219)
- 11 E2E test failures: search model routing, Grafana selectors, panel error detection
- Ruff lint errors in injection.py and search.py
- Parzival bootstrap test assertions updated for layered priority retrieval

### Upgrade Instructions

#### Existing Installations (no nuke required)

1. Update code via Installer **Option 1** ("Add project to existing installation"):
   ```bash
   cd /mnt/e/projects/ai-memory   # your clone
   git pull                        # get v2.0.9
   ./scripts/install.sh /path/to/your-project
   # Select Option 1 when prompted
   ```
   Option 1 updates hooks and code only — preserves running containers, volumes, and data.

2. Rebuild containers that bake source code into Docker images:
   ```bash
   cd ~/.ai-memory/docker
   # Classifier worker (has updated prompts + TRACE_CONTENT_MAX)
   docker compose build --no-cache classifier-worker
   docker compose up -d classifier-worker
   ```
   **If you also use GitHub sync**:
   ```bash
   docker compose build --no-cache github-sync
   docker compose --profile github up -d github-sync
   ```
   Without rebuilding, these containers continue using old code (stale type names, truncated traces).
   **Important**: Always run `docker compose` from `~/.ai-memory/docker/` (not the source repo) to ensure the correct `.env` is used.

3. Run the migration script manually (installer does NOT run migrations):
   ```bash
   # IMPORTANT: Get API key from .env, not shell env.
   # If QDRANT_API_KEY is set in your shell, it overrides .env and may be stale.
   # Use: unset QDRANT_API_KEY
   export QDRANT_API_KEY="$(grep '^QDRANT_API_KEY=' ~/.ai-memory/docker/.env | cut -d= -f2 | tr -d '\"')"

   # Preview first
   python3 ~/.ai-memory/scripts/migrate_v209_github_collection.py --dry-run

   # Run migration
   python3 ~/.ai-memory/scripts/migrate_v209_github_collection.py
   ```

4. The migration:
   - Creates the `github` collection if it doesn't exist
   - Moves ~4,000 `github_code_blob` points from `discussions` → `github`
   - Purges false-positive `error_fix` entries from `code-patterns`
   - Renames remaining `error_fix` → `error_pattern` (correct type name per BUG-200)
   - Idempotent — safe to run multiple times
   - Use `--skip-backup` to skip the automatic pre-migration backup

#### New Installations

No action needed — `setup-collections.py` creates all 5 collections (including `github`) automatically during fresh install.

---

## [2.0.8] - 2026-02-25

Multi-project sync (PLAN-009): Prometheus-style `projects.d/` discovery, per-repo/per-Jira-instance state files, and parameterized sync engines. AI issue triage via multi-model Ollama consensus. Housekeeping: CI fixes, security credential hardening, Dependabot updates.

### Added

#### Multi-Project Sync (PLAN-009)
- `projects.d/` directory-based project discovery (Prometheus-style pattern) with per-project YAML config
- `ProjectSyncConfig` dataclass and `discover_projects()` function in config.py
- `register_project_sync()` in installer — writes per-project YAML to `~/.ai-memory/config/projects.d/`
- `projects.d/` volume mount in Docker Compose for github-sync container
- `list_projects.py` CLI tool for listing registered projects
- `docs/multi-project.md` setup guide for multi-project configuration
- Per-repo GitHub sync state files with collision-safe naming (`__` separator for `/`)
- Per-instance Jira sync state files for multi-Jira-instance support
- Branch parameter propagated through all GitHub sync engines (sync.py + code_sync.py)
- Legacy `GITHUB_REPO` env var fallback for backward compatibility
- `--project-id` flag on `jira_sync.py` for targeted per-project sync
- 52 new tests (20 discovery + 15 GitHub multi-project + 17 Jira alignment)

#### AI Issue Triage (GitHub Actions)
- `auto-triage-issue` job in `claude-assistant.yml` — multi-model Ollama consensus (3 analysis + 3 classification, 2/3 majority vote)
- Bot filter (endsWith '[bot]', dependabot, github-actions) prevents cost amplification
- Graceful degradation: `has_key=false` when OLLAMA_API_KEY missing (no crash, just no triage)

### Changed
- **Skills renamed to `aim-` prefix**: `/memory-status` → `/aim-status`, `/search-memory` → `/aim-search`, `/save-memory` → `/aim-save`, `/memory-settings` → `/aim-settings`, `/memory-purge` → `/aim-purge`, `/memory-refresh` → `/aim-refresh`, `/freshness-report` → `/aim-freshness-report`, `/pause-updates` → `/aim-pause-updates`, `/search-github` → `/aim-github-search`, `/github-sync` → `/aim-github-sync`, `/search-jira` → `/aim-jira-search`, `/jira-sync` → `/aim-jira-sync`
- `GitHubSyncEngine.__init__()` now takes `repo: str` parameter (was hardcoded from config)
- `CodeBlobSync.__init__()` now takes `repo: str` and `branch: str` parameters
- `JiraSyncEngine.__init__()` accepts optional `instance_url` and `jira_projects` overrides
- `github_sync_service.py` now iterates all registered projects from `discover_projects()`
- Installer `set_env_value()` rewritten for BSD sed compatibility (macOS/FreeBSD)

### Fixed
- **BUG-128** (HIGH): Grafana E2E selectors broken by AI Memory branding — updated selectors
- **BUG-129** (MEDIUM): Qdrant API key missing from CI test environment — added to workflow
- **BUG-130** (HIGH): Release workflow broken — fixed artifact path and permissions
- **BUG-193** (MEDIUM): Installer `import_user_env()` stripped quotes from `.env` values, breaking bash `source` — preserved quoted values in import and added quoting in `set_env_value()`
- **BUG-194** (MEDIUM): `create_agent_id_index()` failed when `docker/.env` didn't exist — added existence check before grep
- **BUG-195** (LOW): `settings.local.json` not in `.gitignore` — added to prevent accidental credential commits
- **BUG-196** (MEDIUM): Embedding service container missing `PYTHONPATH` — added to Docker environment for correct module resolution
- **SPEC-021** (gap): SessionStart trace coverage incomplete — added tracing spans for session_start hook execution

### Security
- QDRANT_API_KEY moved from `settings.json` (committed to git) to `settings.local.json` (gitignored) — Fixes GitHub issue #38
- Project ID detection from git remote (org/repo slug) instead of folder name — Fixes GitHub issue #39

### Dependencies
- `bcrypt` upper bound widened `<5.0.0` → `<6.0.0` (Dependabot #30 — passwords >72 bytes now raise ValueError instead of silent truncation)
- `pydantic-settings` 2.12→2.13, `anthropic` 0.77→0.80, `tenacity` 9.1.2→9.1.4, `ruff` 0.14→0.15, `pyyaml` 6.0.2→6.0.3, `fastapi` 0.128→0.129, `uvicorn` 0.40→0.41 (Dependabot #43)
- `tenacity` upper bound widened `<9.0.0` → `<10.0.0`
- GitHub Actions group updated (Dependabot #41)

---

## [2.0.7] - 2026-02-24

LLM Observability via Langfuse (optional): Full pipeline tracing, cost tracking, session grouping, and Grafana integration.

### Added

#### LLM Observability — Langfuse (Optional)

##### Phase 1: Infrastructure (SPEC-019)
- Docker Compose extension (`docker-compose.langfuse.yml`) with 7 services: Langfuse Web, Worker, PostgreSQL, ClickHouse, Redis, MinIO, Trace Flush Worker
- `langfuse_setup.sh` bootstrap script with admin user creation, MinIO bucket init, and verification
- Kill-switch control via `LANGFUSE_ENABLED=true|false` environment variable
- Health checks for all 7 Langfuse services

##### Phase 2: SDK Integration (SPEC-020)
- `trace_buffer.py` — File-based trace buffer (~5ms overhead per event)
- `trace_flush_worker.py` — Docker service that flushes buffered traces to Langfuse
- `langfuse_config.py` — Configuration with validation and Langfuse client factory
- `AnthropicInstrumentor` — Custom model registration for cost tracking (`ollama/*`, `openrouter/*`)
- Buffer overflow protection (100 MB default, oldest-first eviction, Prometheus alerting)

##### Phase 3: Pipeline Instrumentation (SPEC-021)
- 9-step trace spans across 10 hook scripts (`1_capture` → `2_log` → `3_detect` → `4_scan` → `5_chunk` → `6_embed` → `7_store` → `8_enqueue` → `9_classify` + `context_retrieval`)
- Each span includes: duration, token counts, collection, status, error details

##### Phase 4: Session Tracing (SPEC-022 §1-2)
- Session-based trace grouping using Claude Code session ID
- Stop hook (`pre_compact_save.py`) creates session-level trace with summary

##### Phase 5: Grafana Integration (SPEC-022 §3)
- "LLM Observability" collapsed row in main Grafana dashboard with 3 Langfuse link panels
- `$project_id` template variable for Langfuse dashboard filtering
- Classifier latency >5s alert rule with Langfuse deeplink for investigation

#### Stack Management
- `scripts/stack.sh` v1.1.0 — Unified Docker Compose manager for the full stack (core + Langfuse)
  - Commands: `start`, `stop`, `restart`, `status`, `nuke`, `help`
  - Correct startup order: core first (creates network) → Langfuse joins
  - Correct shutdown order: Langfuse first (leaves network) → core removes
  - Profile-aware: respects `LANGFUSE_ENABLED`, `MONITORING_ENABLED`, `GITHUB_SYNC_ENABLED`
  - Token masking, Docker Compose V2 best practices, non-interactive safety checks

#### Documentation
- `docs/LANGFUSE-INTEGRATION.md` — Comprehensive guide (440 lines): setup, architecture, pipeline spans, troubleshooting
- README.md updated with v2.0.7 badge, Langfuse feature section, and service ports

### Fixed

#### Langfuse Install Bugs (BUG-132 through BUG-139) — PM #97
- **BUG-132** (HIGH): Langfuse config validation blocks install on missing optional fields — Changed to warning
- **BUG-133** (HIGH): Missing Dockerfile reference for trace-flush-worker service
- **BUG-134** (HIGH): `cap_drop: ALL` + `no-new-privileges` breaks Postgres/ClickHouse/Redis containers
- **BUG-135** (MEDIUM): `CLICKHOUSE_CLUSTER_ENABLED` not set — ClickHouse queries fail on single-node deployment
- **BUG-136** (MEDIUM): Langfuse web/worker healthchecks use `localhost` which resolves to IPv6 — Changed to `127.0.0.1` + `HOSTNAME=0.0.0.0`
- **BUG-137** (HIGH): `LANGFUSE_ENABLED` env var missing from trace-flush-worker container
- **BUG-138** (HIGH): `AI_MEMORY_INSTALL_DIR` not set in trace-flush-worker — import paths fail
- **BUG-139** (MEDIUM): MinIO healthcheck uses `curl` but Chainguard distroless image has no `curl` — bash TCP probe

#### Langfuse Auth/Config Bugs (BUG-140 through BUG-142) — PM #98
- **BUG-140** (HIGH): Langfuse bootstrap not resilient to repeated installs — Added `verify_bootstrap()` + dynamic volume names + `email_verified=true` SQL fix
- **BUG-141** (MEDIUM): `.local` TLD rejected by Langfuse frontend — Changed to `admin@example.com`
- **BUG-142** (HIGH): Missing 3 of 6 Langfuse env vars in `.env` — hooks receive empty settings

#### Langfuse Runtime Bugs (BUG-143 through BUG-145) — PM #99
- **BUG-143** (HIGH): `trace_buffer/` directory owned by root — hooks can't write trace files. Fix: `mkdir -p` before docker compose up
- **BUG-144** (HIGH): `langfuse` package missing from `pyproject.toml` — pip install from source fails
- **BUG-145** (HIGH): Langfuse SDK v3 removed v2 methods (`client.trace()`) — Migrated to v3 API (`start_span()`, `update_trace()`)

#### Langfuse Pipeline Bugs (BUG-146 through BUG-147) — PM #99
- **BUG-146** (HIGH): Missing `9_classify` Langfuse span — Added 3 emission points to classification worker (success, failure, low-confidence)
- **BUG-147** (MEDIUM): Trace flush worker missing `PUSHGATEWAY_URL` env var — metrics push to wrong endpoint inside Docker

#### Stack Management (BUG-148) — PM #100
- **BUG-148** (MEDIUM): No unified stack management command — Two compose files, `docker compose down` on Langfuse produced no output, 7 containers left running. Fix: `scripts/stack.sh` with correct ordering

#### Deployment Bugs (BUG-149 through BUG-151) — PM #100-101
- **BUG-149** (HIGH): Trace flush worker runs as UID 1001 (Dockerfile `USER classifier`) but buffer files written by host hooks as UID 1000 — Permission denied on read. Fix: `user: "${UID:-1000}:${GID:-1000}"` in compose
- **BUG-150** (MEDIUM): Classifier-worker Docker container missing `LANGFUSE_ENABLED` env var — `emit_trace_event()` kill-switch check silently returns False. Fix: added env var
- **BUG-151** (MEDIUM): MinIO bucket creation command fails — `--entrypoint sh` needed for `minio/mc` image

#### Other Fixes
- **BUG-131** (MEDIUM): Installer stash conflicts — 9 conflict markers across 2 files, applied `-L` symlink guard for `deploy_parzival_commands`

### Changed
- Langfuse SDK dependency: `langfuse>=3.0` added to both `requirements.txt` and `pyproject.toml`
- Docker stack now managed via `stack.sh` (recommended) or direct `docker compose` (still supported)
- Classifier-worker now participates in Langfuse trace pipeline (receives `LANGFUSE_ENABLED` env var)

## [2.0.6] - 2026-02-17

LLM-Native Temporal Memory: Decay scoring, freshness detection, progressive injection,
GitHub enrichment, security scanning, and Parzival session agent integration.

### Added

#### Temporal Memory (Phase 1a)
- Exponential decay scoring via Qdrant Formula Query API (SPEC-001)
- Audit trail with tamper-detection (SPEC-002)
- GitHub sync engine with PR/issue/commit/CI ingestion (SPEC-003)
- Source authority classification (SPEC-004)
- Content deduplication and versioning (SPEC-005)
- Memory type routing for collection/type assignment (SPEC-006)
- Token budget management for context injection (SPEC-007)
- Docker infrastructure, install script, Grafana dashboard, CLI, and collection setup (SPEC-008)

#### Security & Injection (Phase 1b+1c)
- 3-layer security scanning pipeline: regex + detect-secrets + SpaCy NER (SPEC-009)
- Dual embedding routing for prose vs code content (SPEC-010)
- SOPS+age encryption for secrets management (SPEC-011)
- Progressive context injection with 3-tier bootstrap (SPEC-012)
- Freshness detection with git blame integration (SPEC-013)

#### Skills & Integration (Phase 1d)
- 5 new skills: /memory-purge, /search-github, /github-sync, /pause-updates, /memory-refresh (SPEC-014)
- 2 Parzival skills: /parzival-save-handoff, /parzival-save-insight for cross-session memory (SPEC-015)
- Post-sync freshness feedback loop for merged PRs (SPEC-014)
- Parzival session agent integration with Qdrant-backed memory (SPEC-015)
- Parzival session pipeline: enhanced bootstrap, GitHub enrichment, closeout dual-write (SPEC-016)
- 3 upgraded skills: /memory-status (4 new sections), /search-memory (decay scores), /save-memory (agent types) (SPEC-017)

#### Release Engineering (Phase 1d)
- v2.0.5 → v2.0.6 migration script with auto-backup (SPEC-018)
- Historical handoff ingestion (57+ sessions → Qdrant) (SPEC-018)
- 6 cross-phase E2E integration tests (SPEC-018)
- 3 new docs: GITHUB-INTEGRATION.md, TEMPORAL-FEATURES.md, PARZIVAL-SESSION-GUIDE.md (SPEC-018)

#### Parzival Integration (PLAN-007)
- 37 oversight templates now tracked in git (`templates/oversight/`) — fixed `.gitignore` root-anchor pattern
- CLAUDE-PARZIVAL-SECTION.md template moved to `templates/` root for user CLAUDE.md integration
- 8 POV reference docs added to `docs/parzival/` (deprecating standalone POV repo)
- Backup-on-overwrite for Parzival commands during re-install (`.bak.YYYYMMDDHHMMSS`)
- Agent files always deploy latest version on re-install (system-owned files)

### Fixed

#### Install #7 Bug Fixes (BUG-112 through BUG-115)
- **BUG-112** (HIGH): Code blob sync hangs indefinitely — Added total timeout, per-file timeout via `asyncio.wait_for()`, circuit breaker (reuses existing `CircuitBreaker` class), and progress logging every 10 files to `code_sync.py`. 5 new config fields for tuning thresholds.
- **BUG-113** (MEDIUM): Embedding service timeouts with no retry — Added retry with full-jitter exponential backoff (AWS formula) to `EmbeddingClient.embed()`. Configurable via `EMBEDDING_MAX_RETRIES`, `EMBEDDING_BACKOFF_BASE`, `EMBEDDING_BACKOFF_CAP` env vars. Only retries on timeout errors.
- **BUG-114** (LOW): `indexed_vectors_count=0` appeared broken — Documented as expected behavior when `full_scan_threshold=10000` and collection has < 10K vectors. Qdrant uses brute-force search, not HNSW, which is correct.
- **BUG-115** (LOW): `install.sh` initial sync has no timeout — Wrapped sync call with `timeout` command, tracks exit status (success/timeout/error), displays status in install success message.

- BUG-104: Collection setup errors hidden by `2>/dev/null` — now uses `log_error` with re-run command
- BUG-105: Embedding model download fails on first start — pre-download at build time with graceful fallback
- BUG-106: Broken symlinks left after hook archival — cleanup before verification + replaced archived trigger
- BUG-107: Parzival commands not deployed — `cp -r` for entire commands directory
- BUG-108: Agent deployment fails on same-file copy — skip if already installed by `create_project_symlinks()`
- DOC-001: Verification doc references wrong config field name (`auto_update` → `auto_update_enabled`)
- BUG-103: PyYAML missing from test dependencies (SPEC-017)
- TECH-DEBT-156: Dead code branch in security scanner (SPEC-017)
- TECH-DEBT-157: Session state path injection vulnerability (SPEC-017)
- TECH-DEBT-158: Missing @pytest.mark.integration markers (SPEC-017)
- TECH-DEBT-159: Missing PII pattern test coverage (SPEC-017)
- TECH-DEBT-160: Test filename mismatch (SPEC-017)
- TECH-DEBT-161: GitHub handle regex false positives (SPEC-017)
- TECH-DEBT-162: detect-secrets per-call import overhead (SPEC-017)
- TECH-DEBT-163: scan_batch() sequential loop (SPEC-017)
- TECH-DEBT-164: Missing store_memory() return docstring (SPEC-017)
- TECH-DEBT-165: scan_batch() missing force_ner parameter (SPEC-017)

#### Install #11 Bug Fix (BUG-116) — PM #78, commit `fe8aedb`
- **BUG-116** (HIGH): `schema.py` passed `is_tenant=True` as direct kwarg to `create_payload_index()` — qdrant-client >=1.14 requires `is_tenant` inside `KeywordIndexParams`, not as top-level kwarg. Caused `AssertionError: Unknown arguments: ['is_tenant']` on first index, all 10 GitHub indexes failed. Fixed by using `KeywordIndexParams(type="keyword", is_tenant=True)` matching existing pattern in `setup-collections.py`. Secondary fix: `install.sh:2417` changed from `|| result="FAILED"` to `local rc=$?` pattern preserving both exit code and error output.

#### Install #12 Bug Sprint (BUG-118-125 + TD-167/168/170) — PM #79, commit `11728ed`
- **BUG-118** (HIGH): SessionStart matcher hardcoded to `"resume|compact"` in `generate_settings.py` and actively downgraded by `merge_settings.py` — Parzival sessions require `"startup"` in matcher. Fixed: conditional matcher in `generate_settings.py`, bidirectional matcher management in `merge_settings.py`, new `update_parzival_settings.py` called from `install.sh:setup_parzival()`.
- **BUG-119** (MEDIUM): `write_health_file()` only called after first github-sync cycle (5+ min) — Docker healthcheck marked service unhealthy during startup. Fixed: startup `write_health_file()` before main loop, `start_period: 30s → 120s`, file freshness check (mtime < 3600s).
- **BUG-120** (HIGH): Parzival env vars (`PARZIVAL_ENABLED` + 5 others) missing from `settings.json` because `configure_project_hooks()` runs before `setup_parzival()`. Host-side hooks read env from `settings.json`, not `docker/.env`. Fixed: `scripts/update_parzival_settings.py` patches `settings.json` env block + SessionStart matcher after `docker/.env` is written.
- **BUG-121** (MEDIUM): `pre_compact_save.py` stored session summaries directly to Qdrant with no SecurityScanner call — all other hooks DO scan. OWASP LLM08 gap. Fixed: SecurityScanner integration with BLOCKED (returns False + logs + pushes failure metrics) and MASKED (uses masked content) handling.
- **BUG-122** (MEDIUM): Embedding readiness gate (`verify_embedding_readiness`) fired after Jira sync, causing 44% embedding failure rate on initial GitHub issues. Fixed: moved gate to before `seed_best_practices` (first storage operation).
- **BUG-124** (LOW): Grafana `start_period: 60s` insufficient for 2GB Docker systems. Fixed: increased to `120s`; installer now detects Docker memory <3GB and reduces wait to 30s with advisory message.
- **BUG-125** (MEDIUM): `process_retry_queue.py` is standalone manual script with no automatic trigger — 76 items queued during install startup never retried. Fixed: `drain_pending_queue()` function in `install.sh` runs after all sync phases complete.
- **TD-167**: Replaced `estimate_tokens()` (rough 4-chars-per-token) with `count_tokens()` (tiktoken-based) in `session_start.py` — 9 call sites updated.
- **TD-168**: BUG-020 lock cleanup copy-pasted 6x in `session_start.py` — refactored into `cleanup_dedup_lock()` helper.
- **TD-170**: CHANGELOG.md not deployed to install directory — added copy in `install.sh:copy_files()`.

#### CI Fix Sprint — PM #80
- SpaCy NER skip guard added to CI (no model loaded in CI environment)
- Ruff `noqa` annotations added for intentional patterns flagged by linter
- Black formatting applied to 7 hook scripts

#### Install #14 Bug Sprint (BUG-126) — PM #83, commit `cccc318`
- **BUG-126** (HIGH): `settings.local.json` overrides `settings.json` in Claude Code settings hierarchy — stale `QDRANT_API_KEY` persists after reinstall, causing all hook storage to fail silently. Fixed: `configure_project_hooks()` now syncs `QDRANT_API_KEY` to `settings.local.json` if it exists.
- Fixed unbound `$LOG_FILE` variable at 2 locations in `install.sh` (replaced with `$INSTALL_LOG`).
- Added `SECURITY_SCAN_SESSION_MODE=relaxed` to `docker/.env` during install.
- Fixed 2 stale test assertions in `test_generate_settings.py` + added Parzival path coverage.
- Fixed `test_parzival_config_defaults` env isolation (6 `delenv` guards).
- Added 5 v2.0.6 payload fields to `seed_best_practices.py` with type-aware `source_authority`.

#### BUG-127 Field Gap Fix — PM #84, commit `1c64227`
- **BUG-127** (HIGH): v2.0.6 payload fields (`decay_score`, `freshness_status`, `source_authority`, `is_current`, `version`, `stored_at`) only populated in migration script, seed data, and GitHub sync — not in 6 runtime storage paths. Semantic Decay formula fell back to `stored_at=2020-01-01`, giving hook-captured data artificially low temporal scores. Fixed across all 8 storage paths: `store_async.py`, `error_store_async.py`, `agent_response_store_async.py`, `user_prompt_store_async.py`, `MemoryPayload.to_dict()`, `seed_best_practices.py`, `sync.py`, `code_sync.py`. GitHub `authority_tier` (int) renamed to `source_authority` (float 0.4/0.6/1.0 via `SOURCE_AUTHORITY_MAP`).

#### Documentation Accuracy Sprint — PM #85, commit `e6b3358`
- 51 documentation accuracy fixes across 6 files: README, INSTALL, CONFIGURATION, GITHUB-INTEGRATION, TEMPORAL-FEATURES, PARZIVAL-SESSION-GUIDE. Source-code-verified by 2 parallel review agents (6 FAILs + 6 WARNs found; all FAILs + 5 WARNs resolved).

#### Install #16 Fixes — PM #87
- Fixed stale test assertion in decay integration latency threshold
- `docs/` directory now deployed to install directory
- TESTING-SOURCE-OF-TRUTH.md corrections for accuracy
- Installer UX cleanup (output formatting improvements)

### Changed

#### Documentation — PM #86, commit `823dbdc`
- **README**: Parzival section rewritten — new badge, 28-line section with accurate PM framing (not "session agent")
- **PARZIVAL-SESSION-GUIDE.md**: Full rewrite (254 → 365 lines, 11 sections) — accurate role description, startup protocol, cross-session memory patterns, Gate 10 live round-trip
- Decay half-lives: agent_handoff 30→180d, added agent_insight 180d, agent_task 14d (SPEC-018)
- CONFIGURATION.md updated with all v2.0.6 variables (SPEC-018)
- Installer: `shopt -s nullglob` for safe glob expansion in all deployment functions
- Installer: all arithmetic uses POSIX `$((expr))` pattern (replaced 12 bash-specific `((var++))` instances)
- Installer: `cp` commands in `copy_files()` have error handling with actionable messages
- Installer: `setup-collections.py` adds `--force` flag, try/except per collection, skip-if-exists default
- Installer: `generate_settings.py` uses `os.environ.get()` for service config, correct hook timeouts
- Installer: `merge_settings.py` deep merge preserves user scalar values (base-wins pattern)
- Installer: `configure_parzival_env()` respects `NON_INTERACTIVE` mode with proper sed escaping
- Installer: `create_agent_id_index()` checks docker/.env exists before grep
- Installer: broken symlink and stale file cleanup in `create_project_symlinks()`
- Installer: skills symlink uses `${skill_dir%/}` for trailing slash safety
- Installer: SOPS+age secrets option shows availability status (`NOT INSTALLED` / `Recommended`) before user selects
- INSTALL.md: Added SOPS+age prerequisite section with install instructions for macOS, Ubuntu/Debian, and WSL2

## [2.0.5] - 2026-02-10

Jira Cloud Integration: Sync and semantically search Jira issues and comments alongside your code memory.

### Added

#### Jira Cloud Integration
- **Jira API client** (`src/memory/connectors/jira/client.py`) — Async httpx client with Basic Auth, token-based pagination for issues, offset-based pagination for comments, configurable rate limiting
- **ADF converter** (`src/memory/connectors/jira/adf_converter.py`) — Converts Atlassian Document Format JSON to plain text for embedding. Handles paragraphs, headings, lists, code blocks, blockquotes, mentions, inline cards, and unknown node types gracefully
- **Document composer** (`src/memory/connectors/jira/composer.py`) — Transforms raw Jira API responses into structured, embeddable document text with metadata headers
- **Sync engine** (`src/memory/connectors/jira/sync.py`) — Full and incremental sync with JQL-based querying, SHA256 content deduplication, per-issue fail-open error handling, and persistent sync state
- **Semantic search** (`src/memory/connectors/jira/search.py`) — Vector similarity search against `jira-data` collection with filters for project, type, status, priority, author. Includes issue lookup mode (issue + all comments, chronologically sorted)
- **`/jira-sync` skill** — Incremental sync (default), full sync, per-project sync, and sync status check
- **`/search-jira` skill** — Semantic search with project, type, issue-type, status, priority, and author filters. Issue lookup mode via `--issue PROJ-123`
- **`jira-data` collection** — Conditional fourth collection (created only when Jira sync is enabled) for JIRA_ISSUE and JIRA_COMMENT memory types
- **2 new memory types**: `JIRA_ISSUE`, `JIRA_COMMENT` (total: 17 memory types)
- **Installer support** — `install.sh` prompts for optional Jira configuration, validates credentials via API, runs initial sync, configures cron jobs (6am/6pm daily incremental)
- **Health check integration** — `jira-data` collection included in `/memory-status` and `health-check.py`
- **182 unit tests** for all Jira components (client, ADF converter, composer, sync, search)

#### Documentation
- `docs/JIRA-INTEGRATION.md` — Comprehensive guide covering prerequisites, configuration, architecture, sync operations, search operations, automated scheduling, health checks, ADF converter reference, and troubleshooting
- README.md updated with Jira Cloud Integration section, 17 memory types, four-collection architecture
- INSTALL.md updated with optional Jira configuration step, environment variables, and post-install verification

#### CI & Observability
- Docker services (Qdrant, Embedding, Grafana) added to CI test job for E2E tests
- 9 memory system E2E tests enabled with service containers
- Activity logging added to `/search-memory` and `/memory-status` skill functions

#### Monitoring
- **Grafana Jira Data panel** — "Jira Data (Conditional)" row in Memory Operations V3 dashboard with 3 panels: `jira-data` collection size (Pushgateway), Qdrant Native cross-check (`collection_points`), and per-tenant breakdown (bar gauge by `project` label)
- 4 new BUG-075 regression tests (AST chunker byte-offset, header capture, multibyte UTF-8)
- 1 new BUG-076 test (jira-data valid collection)

### Fixed

#### Grafana Dashboard — Pushgateway `increase()` Fix (79 queries across 7 dashboards)

All Grafana dashboards used `increase(metric[1h])` which always returns 0 with Pushgateway push-once semantics. Each hook creates a fresh Python registry and pushes `count=1`, overwriting the previous value — counters never increment between Prometheus scrapes.

- **BUG-083**: `or vector()` fallback pattern caused duplicate series in Grafana — Removed unnecessary `or vector(0)` from 5 queries in `hook-activity-v3.json`
- **BUG-084**: Hook Activity dashboard all panels showing zero — Replaced `increase(..._count[1h])` with `changes(..._created[$__rate_interval])` across 33 queries (stat, timeseries, table panels). The `_created` timestamp changes on every push, making `changes()` an accurate execution counter
- **BUG-085**: NFR Performance dashboard stat panels showing wrong data, SLO gauges showing infinity — Removed `increase()` from `histogram_quantile()` (raw bucket values ARE the distribution with push-once), and from SLO ratio queries (`bucket/count` directly instead of `increase(bucket)/increase(count)` = 0/0 = NaN). 18 queries across stat, timeseries, and gauge panels
- **Systemic `increase()` fix** across 5 remaining dashboards:
  - `memory-overview.json` — 12 histogram_quantile changes (p50/p95/p99 for hook, embedding, search, classifier latencies)
  - `memory-performance.json` — 8 expression + 5 description changes (topk/max wrappers around histogram_quantile)
  - `classifier-health.json` — 4 histogram_quantile changes (classifier + batch duration latency)
  - `system-health-v3.json` — 6 histogram_quantile + 6 failure counter changes (`_total` → `changes(_created)`)
  - `memory-operations-v3.json` — 24 changes (14 `_total` → `changes(_created)`, 4 histogram_quantile, 4 `_count` → `changes(_created)`, 2 `_sum` raw values)
- **Heatmap panels preserved** — 2 heatmap panels retain `increase(_bucket)` (correct semantics for latency distribution visualization)

#### Other Fixes

- **`store_memories_batch()` chunking compliance** — All memory types now route through `IntelligentChunker` (was only USER_MESSAGE and AGENT_RESPONSE). Chunks are batch-embedded individually (previously chunks after index 0 received zero vectors, making them unsearchable). All stored points now include `chunking_metadata`
- **Workflow security** (`claude-assistant.yml`) — Added secret validation, HTTP error handling, JSON escaping, and secret redaction (7 hardening fixes)
- **Streamlit dashboard** — Added `jira-data` collection and JIRA memory types to both imported and fallback code paths
- **BUG-066**: `rm -rf ~/.ai-memory` broke Claude Code in ALL projects — Hook commands now guarded with existence check, installer protects against cascading failure
- **BUG-067**: `validate_external_services()` crashes installer — Exception handling for urllib calls before Docker services are ready
- **BUG-068**: Jira project keys UX — Added auto-discovery of Jira projects via API during install
- **BUG-069**: JIRA_PROJECTS .env format incompatible with Pydantic v2 — Changed from comma-separated to JSON array format
- **BUG-070**: Classifier worker crash on read-only filesystem — Graceful skip when mkdir fails on read-only Docker volume
- **BUG-071**: Jira sync 400 error — Corrected POST to GET for read-only API endpoint
- **BUG-072**: JQL date format silently breaks incremental sync — Fixed to ISO 8601 format
- **BUG-073**: `source_hook` validation rejects `jira_sync` — Added `jira_sync` to source_hook whitelist
- **BUG-075**: AST chunker truncates beginning of JS files — Fixed byte-offset drift (tree-sitter returns bytes, Python indexes chars) and comment header loss (`_find_import_nodes()` skipping comment nodes)
- **BUG-076**: Metrics label warning for `jira-data` collection — Added `jira-data` to `VALID_COLLECTIONS` set and created dynamic `_get_monitorable_collections()` helper
- **BUG-077**: Streamlit statistics page IndexError with 4 collections — `st.columns(3)` → `st.columns(len(COLLECTION_NAMES))`, updated Getting Started text
- **BUG-078**: SessionStart matcher too broad — Narrowed from `startup|resume|compact|clear` to `resume|compact` per Core-Architecture-V2 Section 7.2
- **BUG-079**: Source-built containers stale after install — Added `--build` flag to `docker compose up` commands in installer
- **BUG-080**: Pushgateway persistence permission denied — Mounted volume at `/pushgateway` (owned by nobody:nobody) instead of `/data` (root:root), set explicit `user: "65534:65534"`
- **BUG-081**: `merge_settings.py` does not upgrade SessionStart matcher on reinstall — Added BUG-078 matcher upgrade to `_upgrade_hook_commands()` so existing projects get the narrowed matcher on next install
- **BUG-082**: All Grafana hook dashboard panels show zero — Added `grouping_key={"instance": "<prefix>_<value>"}` to all 16 `pushadd_to_gateway()` calls in `metrics_push.py`. Without grouping keys, each hook push overwrote the previous hook's metrics in the shared Pushgateway group
- **22 code review fixes** across 9 files (silent env fallbacks, error messages, import guarding, migration path for JIRA_PROJECTS format)

### Added
- **`/save-memory` skill** — Manual memory save wrapping `scripts/manual_save_memory.py`, stores to `discussions` collection with `type=session`
- **`scripts/recover_hook_guards.py`** — Standalone CLI recovery tool for existing installs affected by BUG-066 (unguarded hooks) and BUG-078 (broad SessionStart matcher). Dry-run by default, `--apply` to fix, `--scan` for multi-project discovery. Atomic writes with `fsync`+`os.replace`, file permission preservation, bidirectional safety checks. Enhanced with `installed_projects.json` manifest support and multi-path search (manifest → sibling directories → common project paths)
- **`install.sh` project manifest** — Installer now records each installed project to `~/.ai-memory/installed_projects.json` via `record_installed_project()`, enabling reliable multi-project discovery by recovery and maintenance scripts
- **BP-007**: Pushgateway grouping key convention — documents that every `pushadd_to_gateway()` call must include a unique `grouping_key` to prevent silent metric overwrites

### Changed
- Memory type count: 15 → 17 (added JIRA_ISSUE, JIRA_COMMENT)
- Collection architecture: 3 core collections + 1 conditional (`jira-data`)
- `store_memory()` accepts additional metadata fields and passes unknown fields directly to Qdrant payload (enables Jira-specific fields like `jira_issue_key`, `jira_author`, `jira_project`)
- JIRA_ISSUE and JIRA_COMMENT mapped to `ContentType.PROSE` in both `store_memory()` and `store_memories_batch()` content type maps
- `/search-jira` skill enhanced with complete Qdrant payload schema, connection details, and direct curl-to-file-to-python query examples

### Known Issues
- **BUG-064**: `hattan/verify-linked-issue-action@v1.2.0` tag missing upstream (pre-existing, cosmetic CI failure)
- **BUG-065**: `actions/first-interaction@v3` input name breaking change (pre-existing, cosmetic CI failure)
- **Backup/Restore scripts** do not yet support the `jira-data` collection — Jira database backup and reinstall will be added in the next version

## [2.0.4] - 2026-02-06

v2.0.4 Cleanup Sprint: Resolve all open bugs and actionable tech debt (PLAN-003).

### Fixed

#### Phase 1: Infrastructure + Documentation
- **BUG-060**: Grafana dashboards using wrong metric prefix (`ai_memory_` → `aimemory_`)
  - Updated 10 dashboard JSON files with correct `aimemory_` prefix per BP-045
- **BUG-061**: Grafana dashboards using `rate[5m]` which shows nothing with infrequent pushes
  - Switched to `increase[1h]` for counter panels across all dashboards
- **BUG-063**: Hardcoded bcrypt hash in `docker/prometheus/web.yml`
  - Replaced with valid bcrypt hash, cleaned comments
- **TECH-DEBT-078**: Docker `.env.example` had real credentials as placeholder values
  - Replaced with safe placeholder values
- **TECH-DEBT-081**: Grafana dashboard panels showing "No data" (auto-resolved by BUG-060/061 fixes)
- **TECH-DEBT-093**: No authentication on Prometheus web interface
  - `web.yml` now references valid bcrypt hash for basic auth
- **TECH-DEBT-140**: Classifier metrics missing `project` label for multi-tenancy
  - Added `project` as first label to all 9 classifier Prometheus metrics
  - Updated all 4 helper functions to accept and pass `project` parameter
  - Added defensive `project_name = "unknown"` initialization
- **README accuracy**: 6 factual fixes applied
  - Broken `CLAUDE.md` reference → `CONTRIBUTING.md`
  - Duplicate Quick Start sections consolidated
  - Wrong method name (`send_message_streaming` → `send_message_buffered`)
  - Outdated model IDs (`claude-3-5-sonnet-20241022` → `claude-sonnet-4-5-20250929`)
  - Python version clarification (3.11+ required for AsyncSDKWrapper)
  - Hook architecture diagram updated (unified keyword trigger, pluralized hook types)

#### Phase 2: Metrics Pipeline + Hook Behavior + Quick Wins
- **BUG-020**: Duplicate SessionStart entries after compact
  - Implemented file-based deduplication lock (session_id + trigger key, 5s expiry)
  - Second execution exits gracefully with empty context
- **BUG-062**: NFR metrics not pushed to Pushgateway
  - All hooks now use `push_hook_metrics_async()` instead of local metrics
- **TECH-DEBT-072**: Collection size metrics not visible in Grafana
  - Monitoring API now pushes `aimemory_collection_size` to Pushgateway
  - Includes both total and per-project breakdown
- **TECH-DEBT-073**: Missing `hook_type` labels on duration metrics
  - All hooks now push duration with correct `hook_type` label via `track_hook_duration()`
  - SessionStart verified (already correct)
- **TECH-DEBT-074**: Incomplete trigger type labels
  - Verified all trigger scripts push correct `trigger_type` values
- **TECH-DEBT-075**: Missing `collection` label on capture metrics
  - Verified capture hooks pass correct collection parameter
- **TECH-DEBT-085**: Documentation still references "BMAD Memory" product name
  - Renamed product references to "AI Memory" in 6+ docs files
  - Preserved BMAD Method/workflow methodology references
  - Updated env var names, container names, and metric names in docs
- **TECH-DEBT-091**: Logging truncation violates architecture principle
  - Removed `content[:50]` truncation in 2 structured log fields
  - Removed `conversation_context[:200]` truncation in activity log
- **TECH-DEBT-141**: `VALID_HOOK_TYPES` missing 3 hook type values
  - Added `PreToolUse_FirstEdit`, `PostToolUse_Error`, `PostToolUse_ErrorDetection`
- **TECH-DEBT-142**: Hooks using local Prometheus metrics instead of Pushgateway push
  - Converted all hook scripts from local `hook_duration_seconds` to push-based metrics
  - Removed dead local metric imports/definitions from 10 hook scripts

#### Phase 3: Verification
- **Wrong `detect_project` import** in 4 hook scripts (pre-existing)
  - `post_tool_capture.py`, `error_pattern_capture.py`, `user_prompt_capture.py`, `agent_response_capture.py` imported from `memory.storage` instead of `memory.project`
  - Caused silent project detection failure (fell back to "unknown")
  - Fixed: all 4 files now import from `memory.project`
- **BUG-047**: Verified fixed - installer properly quotes all path variables, handles spaces

#### TECH-DEBT-151: Zero-Truncation Chunking Compliance (All 5 Phases)
- **Phase 1**: Removed `_enforce_content_limit()` from `storage.py` — was causing up to 97% data loss on guidelines
- **Phase 2**: Created `src/memory/chunking/truncation.py` with `smart_end` (sentence boundary finder) and `first_last` (head+tail extraction) utilities
- **Phase 3**: Hook store_async scripts now use ProseChunker topical chunking for oversized content:
  - `user_prompt_store_async.py`: >2000 tokens → multiple chunks (512 tokens, 15% overlap)
  - `agent_response_store_async.py`: >3000 tokens → multiple chunks (512 tokens, 15% overlap)
  - `error_store_async.py`: Removed `[:2000]` hard truncation fallback
- **Phase 4**: `IntelligentChunker.chunk()` now accepts `content_type: ContentType | None` parameter
  - Routes USER_MESSAGE (2000 token threshold), AGENT_RESPONSE (3000), GUIDELINE (always chunk)
- **Phase 5**: All stored Qdrant points now include `chunking_metadata` dict (chunk_type, chunk_index, total_chunks, original_size_tokens)
- **storage.py integration**: `store_memory()` maps MemoryType → ContentType and routes through IntelligentChunker for multi-chunk storage

#### Trigger Script NameError Fixes (12 fixes across 5 scripts)
- **first_edit_trigger.py**: `patterns` → `results`, `duration_seconds` moved before use
- **error_detection.py**: `solutions` → `results`, `duration_seconds` moved before use
- **best_practices_retrieval.py**: `matches` → `results`, `hook_name` fixed to `PreToolUse_BestPractices`, env prefix `BMAD_` → `AI_MEMORY_`
- **new_file_trigger.py**: `conventions` → `results`, added `duration_seconds` in except block
- **user_prompt_capture.py**: `MAX_CONTENT_LENGTH` increased from 10,000 to 100,000

### Added
- `src/memory/chunking/truncation.py` — Processing utilities for chunk boundary detection and error extraction
- `tests/unit/test_chunker_content_type.py` — 6 new unit tests for content_type routing
- `ContentType` enum (USER_MESSAGE, AGENT_RESPONSE, GUIDELINE) for content-aware chunking
- `chunking_metadata` on all stored Qdrant points for chunk provenance tracking

### Changed
- Dashboard hook_type labels standardized to PascalCase across all Grafana panels
- Classifier `record_classification()` and `record_fallback()` now require `project` parameter
- Monitoring API `update_metrics_periodically()` now pushes to Pushgateway alongside in-process gauges
- `IntelligentChunker` now accepts explicit `content_type` parameter for content-aware routing
- `MemoryStorage.store_memory()` routes all types through IntelligentChunker (maps MemoryType → ContentType)
- Grafana memory-overview dashboard hook dropdown updated with current hook script names

### Known Gaps
- **TECH-DEBT-077** (partial): `/save-memory` has activity logging; `/search-memory` and `/memory-status` skills are markdown-only with no hook scripts to add logging to. Deferred to future sprint.
- **TECH-DEBT-151** (partial): Session summary late chunking and chunk deduplication (0.92 cosine similarity check) deferred to v2.0.6

## [2.0.3] - 2026-02-05

### Changed
- Hook commands now use venv Python: `$AI_MEMORY_INSTALL_DIR/.venv/bin/python`
- `docker/.env.example` reorganized with quick setup guide and sync warnings
- Metrics renamed from `ai_memory_*` to `aimemory_*` (BP-045 compliance)
- All metrics now include `project` label for multi-tenancy
- NFR-P2 and NFR-P6 now have separate metrics (was shared)
- All hooks now push project label to metrics (TECH-DEBT-124)
- Hook labels standardized to CamelCase ("SessionStart", "PreToolUse_NewFile")

### Added
- Venv health check function in `health-check.py` (TECH-DEBT-136)
- Venv verification during installation with fail-fast behavior
- Troubleshooting documentation for dependency issues
- Best practices research: BP-046 Claude Code hooks Python environment
- NFR-P3 dedicated metric: `aimemory_session_injection_duration_seconds`
- NFR-P4 dedicated metric: `aimemory_dedup_check_duration_seconds`
- Grafana V3 dashboards: NFR Performance, Hook Activity, Memory Operations, System Health
- BP-045: Prometheus metrics naming conventions documentation
- `docs/MONITORING.md`: Comprehensive monitoring guide
- TECH-DEBT-100: Log sanitization with `sanitize_log_input()`
- TECH-DEBT-104: content_hash index for O(1) dedup lookup
- TECH-DEBT-111: Typed events (CaptureEvent, RetrievalEvent)
- TECH-DEBT-115: Context injection delimiters `<retrieved_context>`
- TECH-DEBT-116: Token budget increased to 4000
- Prometheus Dockerfile with entrypoint script for config templating

### Fixed
- **CRITICAL: Hook Python interpreter path** (TECH-DEBT-135)
  - Hooks were configured to use system `python3` instead of venv interpreter
  - This caused ALL hook dependencies to be unavailable (qdrant-client, prometheus_client, tree-sitter, httpx, etc.)
  - **Symptoms**: Silent failures, `ModuleNotFoundError` in logs, memory operations not working, "tree-sitter not installed" warnings
  - **Root Cause**: `generate_settings.py` used bare `python3` instead of `$AI_MEMORY_INSTALL_DIR/.venv/bin/python`
  - **Action Required for Existing Installations**: Re-run `./scripts/install.sh` to regenerate `.claude/settings.json` with correct Python path
- **Hook metrics missing collection label** (TECH-DEBT-131)
  - `memory_captures_total` metric expected 4 labels but hooks only passed 3
  - Caused `ValueError` after successful storage (data saved but error logged)
  - Fixed in 5 async storage scripts (19 total label additions)
- **Venv verification added to installer** (TECH-DEBT-136)
  - Installer now verifies venv creation and critical package imports
  - Fails fast with clear error message if dependencies unavailable
  - Added troubleshooting documentation
- **Classifier metrics prefix** (TECH-DEBT-128)
  - Migrated `classifier/metrics.py` from `ai_memory_classifier_*` to `aimemory_classifier_*` per BP-045
  - Updated legacy dashboards (classifier-health.json, memory-overview.json) to match
- **Docker environment configuration** (TECH-DEBT-127)
  - Created `docker/.env` with all required secrets
  - Enhanced `docker/.env.example` with generation commands and sync warnings
  - Fixed Grafana security secret key configuration
- **BUG-019**: Metrics were misleading (shared metrics for different NFRs)
- **BUG-021**: Some metrics not collecting (missing NFR-P4, wrong naming)
- **BUG-059**: restore_qdrant.py snapshot restore now works correctly
- **#13**: E2E test now uses `--project` argument or current working directory
- **CI Tests**: Fixed test_monitoring_performance.py label mismatches:
  - Added missing `collection` label to `memory_captures_total` test calls
  - Added missing `status`, `project` labels to `hook_duration_seconds` test calls
  - Reformatted with black 26.1.0 (was using 25.12.0 locally)
  - Changed upload from PUT to POST with multipart/form-data (Qdrant 1.16+ API)
  - Fixed recover endpoint to use `/snapshots/recover` with JSON body location
  - Added `create_collection_for_restore()` for fresh install support
  - Removed collection deletion before upload (was causing 404 errors)

## [2.0.2] - 2026-02-03

### Fixed
- **BUG-054**: Installer now runs `pip install` for Python dependencies
- **BUG-051**: SessionStart hook timeout parameter cast to int (was float)
- **BUG-058**: store_async.py handles missing session_id gracefully with .get() fallback

### Added
- `scripts/backup_qdrant.py` - Database backup with manifest verification
- `scripts/restore_qdrant.py` - Database restore with rollback on failure
- `scripts/upgrade.sh` - Upgrade script for existing installations
- `docs/BACKUP-RESTORE.md` - Complete backup/restore documentation
- `backups/` directory for storing backups outside install location

### Changed
- black version constraint updated to allow 26.x (`<26.0.0` → `<27.0.0`)
- 66 files reformatted with black 26.1.0

## [2.0.0] - 2026-01-29

### Added
- **V2.0 Memory System** with 3 specialized collections (code-patterns, conventions, discussions)
- **15 Memory Types** for precise categorization
- **5 Automatic Triggers** (error detection, new file, first edit, decision keywords, best practices)
- **Intent Detection** - Routes queries to the right collection automatically
- **Knowledge Discovery** features:
  - `best-practices-researcher` skill - Web research with local caching
  - `skill-creator` agent - Generates Claude Code skills from research
  - `search-memory` skill - Semantic search across collections
  - `memory-status` skill - System health and diagnostics
  - `memory-settings` skill - Configuration display
- **Quick Start section** in README.md with git clone instructions
- **"Install ONCE, Add Projects" warning** - Prevents common installation mistake
- **Comprehensive hook documentation**: Created `docs/HOOKS.md` documenting all 12+ hooks
- **Slash commands reference**: Created `docs/COMMANDS.md` with Skills & Agents section
- **Configuration guide**: Created `docs/CONFIGURATION.md`

### Changed
- **Major architecture update** - Three-collection system replaces single collection
- **README.md** - Added Quick Start, Knowledge Discovery section, clarified BMAD relationship
- **INSTALL.md** - Added warning about installing once, emphasized cd to existing directory
- **docs/COMMANDS.md** - Added Skills & Agents section (best-practices-researcher, skill-creator, search-memory, memory-status, memory-settings)
- **Repository URLs**: Updated from `[redacted]/ai-memory` to `Hidden-History/ai-memory`

### Fixed
- **PreCompact hook documentation**: Added missing documentation
- **Multi-project installation clarity**: Emphasized using same ai-memory directory

## [1.0.1] - 2026-01-14

### Fixed
- **Embedding model persistence**: Added Docker volume for HuggingFace cache. Model now persists across container restarts (98.7% faster subsequent starts)
- **Installer timeout**: Increased service wait timeout from 60s to 180s to accommodate cold start model downloads (~500MB)
- **Disk space check**: Fixed crash when installation directory doesn't exist yet
- **Qdrant health check**: Fixed incorrect health endpoint (was `/health`, now `/`)
- **Progress indicators**: Added elapsed time display during service startup

### Added
- `requirements.txt` for core Python dependencies
- Progress messages explaining model download during first start

### Changed
- Embedding service health check `start_period` increased to 120s
- Improved error messages with accurate timeouts and troubleshooting steps

## [1.0.0] - 2026-01-14

### Added
- Initial public release
- One-command installation (`./scripts/install.sh`)
- Automatic memory capture from Write/Edit operations (PostToolUse hook)
- Intelligent memory retrieval at session start (SessionStart hook)
- Session summarization at session end (Stop hook)
- Multi-project isolation with `group_id` filtering
- Docker stack: Qdrant + Jina Embeddings + Streamlit Dashboard
- Monitoring: Prometheus metrics + Grafana dashboards
- Deduplication (content hash + semantic similarity)
- Graceful degradation (Claude works without memory)
- Comprehensive documentation (README, INSTALL, TROUBLESHOOTING)
- Test suite: Unit, Integration, E2E, Performance

[Unreleased]: https://github.com/Hidden-History/ai-memory/compare/v2.8.0...HEAD
[2.8.0]: https://github.com/Hidden-History/ai-memory/compare/v2.7.0...v2.8.0
[2.4.2]: https://github.com/Hidden-History/ai-memory/compare/v2.4.1...v2.4.2
[2.4.1]: https://github.com/Hidden-History/ai-memory/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/Hidden-History/ai-memory/compare/v2.3.2...v2.4.0
[2.3.2]: https://github.com/Hidden-History/ai-memory/compare/v2.3.1...v2.3.2
[2.3.1]: https://github.com/Hidden-History/ai-memory/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/Hidden-History/ai-memory/compare/v2.2.1...v2.3.0
[2.2.1]: https://github.com/Hidden-History/ai-memory/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/Hidden-History/ai-memory/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/Hidden-History/ai-memory/compare/v2.0.9...v2.1.0
[2.0.9]: https://github.com/Hidden-History/ai-memory/compare/v2.0.8...v2.0.9
[2.0.8]: https://github.com/Hidden-History/ai-memory/compare/v2.0.7...v2.0.8
[2.0.7]: https://github.com/Hidden-History/ai-memory/compare/v2.0.6...v2.0.7
[2.0.6]: https://github.com/Hidden-History/ai-memory/compare/v2.0.5...v2.0.6
[2.0.5]: https://github.com/Hidden-History/ai-memory/compare/v2.0.4...v2.0.5
[2.0.4]: https://github.com/Hidden-History/ai-memory/compare/v2.0.3...v2.0.4
[2.0.3]: https://github.com/Hidden-History/ai-memory/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/Hidden-History/ai-memory/compare/v2.0.0...v2.0.2
[2.0.0]: https://github.com/Hidden-History/ai-memory/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/Hidden-History/ai-memory/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Hidden-History/ai-memory/releases/tag/v1.0.0
