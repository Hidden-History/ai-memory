# Changelog

All notable changes to AI Memory Module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[Unreleased]: https://github.com/Hidden-History/ai-memory/compare/v2.2.1...HEAD
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
