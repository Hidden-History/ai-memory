"""Version information for AI Memory Module.

Single source of truth for version number.
Follows PEP 440 and semantic versioning principles.
"""

__version__ = "2.8.4"
__version_info__ = tuple(int(part) for part in __version__.split("."))

# Version history:
# 2.8.0 - Embedding-service resilience (BUG-324) + 6G default & sizing guide, capped startup loaders + sanctum governance, absolute-relevance injection gate + NAME/HANDLE redaction precision, aim-tracking-rotate fix action + auto-memory-index class, connector Langfuse-shutdown hardening, BUG-322 collection routing
# 2.5.0 - Langfuse SDK V4 (4.7.1) + BUG-315 trace-flush worker hardening + BP-169 trace organization; TASK-071 skill-script externalizations (GitHub/Jira query + maintenance scripts); documentation refresh (README trim, CHANGELOG/Langfuse currency)
# 2.4.5 - TD-583/584/585/586/587: image-bake prometheus-init + langfuse-clickhouse, stack.sh unconditional rebuild, prometheus parent-dir chmod fix, streamlit restart policy, install.sh gate hardening
# 2.4.4 - TD-582: bake qdrant + grafana entrypoint shims into custom images, eliminating WSL2 single-file bind-mount cache fragility on host reboot; compose env_file: + entrypoint shims close the bare-up secret-class resolution gap (BUG-279 sibling)
# 2.4.3 - Installer hygiene: BUG-309 detection-layer .env.secrets fallback, TD-551 .env line-removal + per-file chmod, TD-552 spaCy model pin + scanner init log
# 2.4.2 - POV token-budget restructure: identity-content dedupe, step-file boilerplate collapse, lazy-loaded reference docs
# 2.4.1 - Backup/restore hardening, Langfuse install fixup, pushgateway and bootstrap fixes (TD-517, BUG-298)
# 2.4.0 - Silent-drop fix, Sanctum identity, env-secrets split, classifier resilience (BUG-297)
# 2.3.2 - Security patches, group_id normalization, Phase B live-verify fixes (PRs #110, #111, #112)
# 2.3.1 - Endpoint alignment, typed OrderBy API, documentation accuracy (PR #108)
# 2.3.0 - Stabilization: Langfuse v4, security hardening, data integrity, CI regression gate
# 2.2.8 - Multi-IDE adapter support: Gemini CLI, Cursor IDE, Codex CLI
# 2.2.7 - Per-project tokens, data quality, observability
# 2.2.6 - Multi-project installer fix: project-specific GitHub/Jira config (#85)
# 2.2.5 - Batch GitHub code blob sync, include/exclude overrides (#76/#77)
# 2.2.4 - Parzival V2.1 shim architecture, GitHub issue fixes (#73/#74/#75)
# 2.2.1 - Triple Fusion Hybrid Search (dense + sparse BM25 + ColBERT late interaction)
# 2.2.0 - Agent-activated injection architecture, Parzival V2 deployment
# 2.1.0 - Langfuse V3 SDK, agent identity, graceful shutdown
# 2.0.8 - Multi-project sync, credential hardening, Langfuse tracing
# 2.0.7 - Langfuse tracing (optional), stack.sh, 20 bug fixes
# 2.0.6 - Installation hardening, doc accuracy sprint
# 2.0.5 - CI hardening, Jira integration, security fixes
# 2.0.4 - Zero-truncation chunking, tech debt cleanup
# 2.0.3 - Bug fixes and stability improvements
# 1.0.0 - Initial release (Epic 7 complete)
