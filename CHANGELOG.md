# Changelog

All notable changes to AI Memory Module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[Unreleased]: https://github.com/Hidden-History/ai-memory/compare/v2.0.5...HEAD
[2.0.5]: https://github.com/Hidden-History/ai-memory/compare/v2.0.4...v2.0.5
[2.0.4]: https://github.com/Hidden-History/ai-memory/compare/v2.0.3...v2.0.4
[2.0.3]: https://github.com/Hidden-History/ai-memory/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/Hidden-History/ai-memory/compare/v2.0.0...v2.0.2
[2.0.0]: https://github.com/Hidden-History/ai-memory/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/Hidden-History/ai-memory/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Hidden-History/ai-memory/releases/tag/v1.0.0
