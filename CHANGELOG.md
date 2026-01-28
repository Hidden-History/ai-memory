# Changelog

All notable changes to AI Memory Module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Comprehensive hook documentation**: Created `docs/HOOKS.md` documenting all 12+ hooks (SessionStart, PostToolUse, PreCompact, Stop, activity logging, error handling, best practices)
- **Slash commands reference**: Created `docs/COMMANDS.md` documenting `/memory-status`, `/save-memory`, and `/search-memory` commands
- **Configuration guide**: Created `docs/CONFIGURATION.md` with complete environment variables reference and agent token budgets
- **Expandable troubleshooting sections**: Added inline `<details>` blocks in INSTALL.md for common issues

### Changed
- **README.md**: Applied 2026 documentation best practices with consistent emoji icons, added PreCompact hook to architecture diagram, updated manual commands from `/bmad-memory:*` to `/search-memory` format, improved multi-project explanation
- **INSTALL.md**: Added PreCompact hook configuration examples, SessionStart matcher requirement clarification, updated repository URLs, applied visual hierarchy improvements
- **TROUBLESHOOTING.md**: Added dedicated sections for Hook Issues, Memory & Search Issues, Command Issues, Performance Issues, and Configuration Issues with links to detailed documentation
- **Repository URLs**: Updated all documentation from `wbsolutions-ca/bmad-memory` to `Hidden-History/ai-memory`

### Fixed
- **PreCompact hook documentation**: Added missing PreCompact hook throughout README.md and INSTALL.md (critical for session summary persistence before context compaction)
- **SessionStart matcher requirement**: Explicitly documented that SessionStart hooks require `matcher` field (`startup|resume|compact`)

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

[1.0.1]: https://github.com/Hidden-History/ai-memory/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Hidden-History/ai-memory/releases/tag/v1.0.0
