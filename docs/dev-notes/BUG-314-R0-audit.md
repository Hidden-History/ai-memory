# BUG-314 §R0 — File-Wide Project-ID Resolution Audit

Authoritative design: BUG-314 "CORRECTION 2" (DEC-PM314-D2) + BP-166. Baseline: `main @ 1d85476`.

Goal: enumerate every site that resolves a project id or calls store/search, record its
current resolution order, and confirm **no consumer depends on `run-with-env.sh` forcing the
install-global `AI_MEMORY_PROJECT_ID`** (the confused-deputy injection at the root of the bug).

## Canonical contract (target)

`resolve_project_id(cwd=None, *, explicit=None)` — precedence: `explicit` → `AI_MEMORY_PROJECT_ID`
env → `detect_project(cwd)` (git-remote slug / edge sentinels) → fail-loud `ValueError`. It is a
thin shim over the already-env-first `detect_project`; it adds the explicit-arg tier and a
non-fatal warning when the env id disagrees with the cwd-derived id (OQ-1: warn + prefer the
explicit per-invocation signal; fail-loud only when nothing resolves).

`detect_project()` is already env-first internally, so any site calling `detect_project(cwd)`
already honors the env; routing it through `resolve_project_id` adds the explicit tier + mismatch
warning and removes per-file inline drift.

## Class 1 — Primary scope-determining resolution → CONVERT to `resolve_project_id`

The id produced here feeds `store_*`/`search`. These re-implement the env-or-cwd dance inline (the
drift surface F4 targets) or call `detect_project` directly.

### scripts/memory/ (operator scripts; run via `run-with-env.sh`) — the BUG-314 blast zone
| File | Current order |
|------|---------------|
| parzival_save_handoff.py | env → `detect_project(cwd)` → friendly-fail |
| parzival_save_insight.py | env → `detect_project(cwd)` → fail |
| parzival_save_decision.py | env → `detect_project(cwd)` → friendly-fail |
| pre-work-search.py | env → `detect_project(cwd or getcwd)` |
| search_cli.py | `--group-id` → env → `detect_project(cwd)` |
| store-chat-memory.py | env → `detect_project(cwd)` |
| post_work_store_async.py | explicit arg → env → `detect_project(cwd)` |
| memory_status.py | `detect_project(cwd)` (env-first internal) |
| process_retry_queue.py | `detect_project(cwd)` (env-first internal) |
| ingest_markdown.py | `--group-id` → env → fail (no `detect_project`) |
| seed_best_practices.py | `--group-id` → env → fail (no `detect_project`) |

### .claude/hooks/scripts/ (Claude-native; NOT via the wrapper) — primary resolution
agent_response_store_async.py · best_practices_retrieval.py · context_injection_tier2.py ·
error_detection.py · error_store_async.py · first_edit_trigger.py · new_file_trigger.py ·
pre_compact_save.py · session_start.py · store_async.py · user_prompt_store_async.py ·
manual_save_memory.py — all `env → detect_project(cwd)`.

### src/memory/adapters/ (codex/cursor/gemini)
context_injection.py / error_detection.py / session_start.py (codex), error_detection.py /
session_start.py (cursor + gemini) — all `env → detect_project(event["cwd"])`.

### src/memory/
agent_sdk_wrapper.py `_resolve_group_id` — `env → detect_project(self.cwd)`.

### Inline skill embeds (.claude/skills/, _ai-memory/skills/)
parzival-save-handoff/insight/decision SKILL.md and aim-save SKILL.md embed the same inline dance.

## Class 2 — Metric-label-only best-effort → LEAVE (documented)

These resolve a project **label for a metric/trace only** and intentionally degrade to `"unknown"`
(NOT fail-loud). They do not determine storage/search scope. Converting them to the fail-loud
resolver would crash observability paths — wrong. Sites: agent_response_capture.py,
user_prompt_capture.py, error_pattern_capture.py, post_tool_capture.py, the metric-label blocks in
agent_response_store_async.py / user_prompt_store_async.py, classifier/llm_classifier.py, and
`detect_project(project)`-normalization helpers in error_store_async.py / store_async.py.

## Class 3 — Library floor / composition helpers → LEAVE (unchanged per brief)

project.py (defines the resolver), group_ids.py (`build_group_id_plan` takes an explicit
`project_id`, uses `detect_project` only as a typed fallback), storage.py / search.py (require a
non-empty `group_id` — the enforcement floor, explicitly OUT of scope), trace_buffer.py (env
fallback for a trace label).

## Class 4 — Bootstrap READ path → EXTRACT + route through resolver

`_ai-memory/pov/skills/aim-parzival-bootstrap/SKILL.md` uses `detect_project(os.getcwd())`. Per
CORRECTION 2 this already honors the env (not a read-path bug). It is extracted to a standalone
script (TD-590 slice) and switched to `resolve_project_id(os.getcwd())` for one-resolver
consistency.

## VERDICT — Part D dependency check

**No operator script run via `run-with-env.sh` depends on the install-global
`AI_MEMORY_PROJECT_ID` injection.** Every consumer resolves per-workspace (caller env from the
workspace `.claude/settings.json` / shell → cwd/git → fail-loud). `github_sync` scopes via
`config.github_repo`, not `AI_MEMORY_PROJECT_ID`. The long-running Docker services consume the
install-global value via `docker compose env_file`, **not** this wrapper. Therefore the wrapper's
`load_env_var "AI_MEMORY_PROJECT_ID"` export is safe to remove (scoped Part D) — it only injects a
machine-wide constant into operator scripts run from a foreign workspace, which is the
confused-deputy root cause. **No BLOCKER.**

Secrets/connectivity keys (`QDRANT_API_KEY`, `GITHUB_REPO`, `GITHUB_BRANCH`, `GITHUB_TOKEN`,
`GITHUB_SYNC_ENABLED`) are genuinely needed by operator scripts and are retained, preserving the
BUG-292 secrets-first/.env-fallback dual-source pattern.
