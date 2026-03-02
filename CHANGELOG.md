# Changelog

All notable changes to AI Memory Module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- E2E test screenshots directory fixture (TD-219)
- 11 E2E test failures: search model routing, Grafana selectors, panel error detection
- Ruff lint errors in injection.py and search.py
- Parzival bootstrap test assertions updated for layered priority retrieval

### Migration
- Run `scripts/migrate_v209_github_collection.py` on existing installations
- Moves ~4,000 `github_code_blob` points from `discussions` → `github` collection
- Purges false-positive `error_fix` entries from `code-patterns`
- Idempotent — safe to run multiple times
- Supports `--dry-run` for preview

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

[Unreleased]: https://github.com/Hidden-History/ai-memory/compare/v2.0.8...HEAD
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
