# Changelog

All notable changes to AI Memory Module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- (No changes yet)

### Added
- (No additions yet)

### Fixed
- (No fixes yet)

## 2.0.3 - 2026-02-05

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

[Unreleased]: https://github.com/Hidden-History/ai-memory/compare/v2.0.2...HEAD
[2.0.2]: https://github.com/Hidden-History/ai-memory/compare/v2.0.0...v2.0.2
[1.0.1]: https://github.com/Hidden-History/ai-memory/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Hidden-History/ai-memory/releases/tag/v1.0.0
