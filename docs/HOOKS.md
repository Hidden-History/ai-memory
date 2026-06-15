# 🔧 Claude Code Hooks Reference

> Comprehensive guide to all AI Memory Module hooks

## 📋 Table of Contents

- [Overview](#overview)
- [Core Memory Hooks](#core-memory-hooks)
  - [SessionStart](#sessionstart)
  - [PostToolUse](#posttooluse)
  - [PreCompact](#precompact)
  - [Stop](#stop)
- [Tier 2 Per-Turn Context Injection](#tier-2-per-turn-context-injection)
- [Activity Logging Hooks](#activity-logging-hooks)
  - [SessionEnd](#sessionend)
  - [UserPromptSubmit](#userpromptsubmit)
  - [Notification](#notification)
  - [SubagentStop](#subagentstop)
  - [PreToolUse](#pretooluse)
- [Error Handling Hooks](#error-handling-hooks)
  - [Error Pattern Capture](#error-pattern-capture)
  - [Error Context Retrieval](#error-context-retrieval)
- [Best Practices Hooks](#best-practices-hooks)
  - [Best Practices Retrieval](#best-practices-retrieval)
- [Manual Operations](#manual-operations)
  - [Manual Save Memory](#manual-save-memory)
- [Configuration Examples](#configuration-examples)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

The AI Memory Module uses Claude Code hooks to automatically capture and retrieve knowledge across sessions. Hooks are Python scripts that execute in response to Claude Code events.

### Hook Categories

| Category | Hooks | Purpose |
|----------|-------|---------|
| **Core Memory** | SessionStart, PostToolUse, PreCompact, Stop | Automatic memory capture/retrieval |
| **Activity Logging** | SessionEnd, UserPromptSubmit, Notification, SubagentStop, PreToolUse | Session tracking and analytics |
| **Error Handling** | Error Capture, Error Context | Error pattern learning |
| **Best Practices** | Best Practices Retrieval | Cross-project pattern sharing |

### Performance Requirements

| Hook | Max Duration | Pattern | Exit Code |
|------|-------------|---------|-----------|
| SessionStart | <3s | Synchronous (blocks startup) | 0 = success, 1 = non-blocking error |
| PostToolUse | <500ms | Fork to background | 0 = success, 1 = graceful degradation |
| PreCompact | <10s | Synchronous (blocks compaction) | 0 = success, 1 = non-blocking error |
| Activity Logging | <100ms | Async write to log file | Always 0 |

---

## 🧠 Core Memory Hooks

### SessionStart

**📥 The "Aha Moment" - Claude remembers your previous sessions**

#### Purpose
Loads relevant memories from previous sessions and injects them as context when Claude Code starts, resumes, or compacts.

#### Trigger
- **startup**: New Claude Code session begins
- **resume**: Session resumed after pause
- **compact**: Context compaction triggered (auto or manual `/compact`)

#### Configuration

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/session_start.py"
          }
        ]
      }
    ]
  }
}
```

> **Critical:** The `matcher` field is **required** for SessionStart hooks. Without it, the hook will not fire.

#### Input (Hook Payload)

```json
{
  "session_id": "sess-abc123",
  "cwd": "/path/to/project",
  "source": "startup",  // or "resume", "compact", "clear"
  "agent": "default"    // Optional: BMAD agent name
}
```

#### Output (Context Injection)

Hook writes JSON to stdout with `hookSpecificOutput` format:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "## Relevant Memories\n\n### session_summary (95%)\nLast session we implemented user authentication...\n\n### implementation (87%)\nUsed JWT tokens stored in httpOnly cookies..."
  }
}
```

#### Process Flow

```
SessionStart Hook
    ↓
1. Parse hook input (session_id, cwd, source)
2. Detect project from cwd → group_id
3. Check Qdrant health (graceful degradation if down)
4. Build semantic query from project context
5. Search discussions collection (last 48 hours)
6. Apply token budget per agent type
7. Format results with tiered relevance
8. Inject as context via stdout
    ↓
Claude sees memories as part of initial context
```

#### Example Output

```markdown
## Relevant Memories for my-project

### High Relevance (>90%)

**session** (95%) [discussions]
Session Summary: Implementing user authentication with JWT tokens
- Created login endpoint with email/password validation
- Implemented token refresh mechanism
- Added middleware for protected routes

### Medium Relevance (50-90%)

**implementation** (78%) [code-patterns]
```python
# src/auth/middleware.py
def require_auth(request):
    token = request.cookies.get('auth_token')
    if not verify_jwt(token):
        raise Unauthorized()
```
```

#### Troubleshooting

<details>
<summary><strong>Hook not firing on session start</strong></summary>

**Diagnosis:**
```bash
# Check if matcher is present
grep -A 5 "SessionStart" .claude/settings.json
```

**Solution:**
SessionStart hooks **require** a `matcher` field:
```json
{
  "matcher": "startup|resume|compact",
  "hooks": [...]
}
```
</details>

<details>
<summary><strong>No memories injected despite hook running</strong></summary>

**Diagnosis:**
```bash
# Check if memories exist for this project
curl http://localhost:26350/collections/discussions/points/scroll | jq '.result.points[] | select(.payload.group_id == "my-project")'
```

**Possible Causes:**
1. No previous sessions captured (first time using this project)
2. Project group_id mismatch (check logs for detected group_id)
3. Similarity threshold too high (memories exist but don't match query)

**Solution:**
```bash
# Check hook logs for project detection
grep "project_detected" ~/.ai-memory/logs/hooks.log

# Lower similarity threshold temporarily
export MEMORY_SIMILARITY_THRESHOLD=0.3
```
</details>

<details>
<summary><strong>Hook timeout or slow startup</strong></summary>

**Performance Targets:**
- Embedding generation: <2s
- Qdrant search: <500ms
- Total SessionStart: <3s

**Diagnosis:**
```bash
# Check hook duration logs
grep "hook_duration" ~/.ai-memory/logs/hooks.log | tail -20
```

**Solution:**
1. Reduce `MAX_RETRIEVALS` if returning too many results
2. Check network latency to Qdrant (should be localhost)
3. Verify embedding service is pre-warmed
</details>

---

### PostToolUse

**💾 Captures implementations automatically after code changes**

#### Purpose
Captures implementation patterns in the background (<500ms overhead) when Claude uses Write, Edit, or NotebookEdit tools.

#### Trigger
Fires after successful completion of file modification tools:
- **Write**: New file created
- **Edit**: Existing file modified
- **NotebookEdit**: Jupyter notebook cell edited

#### Configuration

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/post_tool_capture.py"
          }
        ]
      }
    ]
  }
}
```

#### Input (Hook Payload)

```json
{
  "session_id": "sess-abc123",
  "cwd": "/path/to/project",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/path/to/project/src/auth.py",
    "old_string": "...",
    "new_string": "..."
  },
  "tool_response": {
    "filePath": "/path/to/project/src/auth.py",
    "success": true
  }
}
```

#### Output
No stdout output (runs in background). Logs to stderr for diagnostics.

#### Process Flow (Fork Pattern)

```
PostToolUse Hook (<500ms)
    ↓
1. Validate hook input
2. Extract file path and language
3. Fork to background process (subprocess.Popen)
4. Exit 0 immediately
    ↓
Background Process (async)
    ↓
1. Detect project from cwd → group_id
2. Extract content from tool_input/tool_response
3. Compute content_hash for deduplication
4. Check if duplicate (hash + group_id)
5. Generate embedding (graceful degradation if fails)
6. Store in code-patterns collection
7. Log activity for Streamlit visibility
```

#### Performance Pattern

The fork pattern ensures Claude Code isn't blocked:

```python
# Main process (blocks Claude): <500ms
process = subprocess.Popen(
    [sys.executable, "store_async.py"],
    stdin=subprocess.PIPE,
    start_new_session=True  # Full detachment
)
process.stdin.write(json.dumps(hook_input).encode())
process.stdin.close()
sys.exit(0)  # Return immediately

# Background process (async): 2-5s
# - Embedding generation: ~2s
# - Qdrant storage: <500ms
```

#### Example Storage Result

```json
{
  "id": "mem-xyz789",
  "vector": [0.123, 0.456, ...],
  "payload": {
    "content": "def authenticate(email, password):\n    ...",
    "content_hash": "sha256:abc...",
    "group_id": "my-project",
    "type": "implementation",
    "source_hook": "PostToolUse",
    "session_id": "sess-abc123",
    "file_path": "src/auth.py",
    "language": "python",
    "embedding_status": "complete",
    "timestamp": "2026-01-17T10:30:00Z"
  }
}
```

#### Troubleshooting

<details>
<summary><strong>Hook fires but nothing stored</strong></summary>

**Diagnosis:**
```bash
# Check background process logs
grep "background_forked" ~/.ai-memory/logs/hooks.log
grep "memory_stored" ~/.ai-memory/logs/hooks.log

# Check for deduplication
grep "duplicate_memory_skipped" ~/.ai-memory/logs/hooks.log
```

**Possible Causes:**
1. **Duplicate content** - Hash already exists for this project
2. **Qdrant unavailable** - Background process couldn't connect
3. **Embedding service timeout** - Falls back to pending status with zero vector

**Solution:**
```bash
# Verify Qdrant is running
curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/health

# Check Qdrant for duplicate hash
curl http://localhost:26350/collections/code-patterns/points/scroll \
  | jq '.result.points[] | select(.payload.content_hash == "sha256:...")'
```
</details>

<details>
<summary><strong>Performance degradation (>500ms)</strong></summary>

**Diagnosis:**
```bash
# Check hook duration
grep "post_tool_duration" ~/.ai-memory/logs/hooks.log | tail -10
```

**Performance Targets:**
- Validation + fork: <100ms
- Background spawn: <50ms
- Total PostToolUse: <500ms

**Common Issues:**
1. Slow subprocess.Popen (disk I/O)
2. Large tool_input payload (rare)

**Solution:**
Hook should always return in <500ms due to fork pattern. If not:
```bash
# Check system I/O
iostat -x 1

# Check for disk thrashing
vmstat 1
```
</details>

---

### PreCompact

**💾 Session Continuity - Saves summary before compaction**

#### Purpose
Saves session summary to discussions collection before Claude Code compacts context. This enables the "aha moment" when starting a new session - Claude remembers what you worked on.

#### Trigger
- **auto**: Automatic compaction (context limit reached)
- **manual**: User runs `/compact` command

#### Configuration

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/pre_compact_save.py",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

> **Critical:** Timeout of 10000ms (10s) recommended - session summarization takes time.

#### Input (Hook Payload)

```json
{
  "session_id": "sess-abc123",
  "cwd": "/path/to/project",
  "source": "auto",  // or "manual"
  "context_size": 95000,
  "tools_used": ["Edit", "Write", "Read"],
  "files_modified": ["src/auth.py", "tests/test_auth.py"]
}
```

#### Output
Writes status to stdout (not displayed to user):

```json
{
  "status": "success",
  "memory_id": "mem-summary-123",
  "session_id": "sess-abc123"
}
```

#### Process Flow

```
PreCompact Hook (<10s)
    ↓
1. Parse hook input
2. Detect project from cwd → group_id
3. Build session summary from context:
   - Tools used
   - Files modified
   - Decisions made
   - Errors encountered
4. Store in discussions collection
5. Return success/failure
    ↓
Claude compacts context (hook blocks until done)
```

#### Session Summary Format

```markdown
Session Summary: my-project
Session ID: sess-abc123
Compaction Trigger: auto

Tools Used: Edit, Write, Read, Bash
Files Modified (5):
- src/auth.py (authentication logic)
- src/middleware.py (auth middleware)
- tests/test_auth.py (auth tests)
- src/models.py (User model)
- README.md (updated auth docs)

User Interactions: 12 prompts

Key Activities:
1. Implemented JWT-based authentication
   - Email/password login endpoint
   - Token refresh mechanism
   - httpOnly cookie storage

2. Added auth middleware
   - Protected route decorator
   - Token verification
   - User session management

3. Wrote comprehensive tests
   - Login flow tests
   - Token refresh tests
   - Middleware tests

Technical Decisions:
- Chose JWT over sessions for stateless auth
- Used httpOnly cookies to prevent XSS
- Implemented refresh token rotation

Errors Encountered:
- TypeError in token verification (fixed)
- Test fixture setup issues (resolved)
```

#### Troubleshooting

<details>
<summary><strong>Hook blocks compaction too long</strong></summary>

**Performance Targets:**
- Summary generation: <5s
- Qdrant storage: <1s
- Total PreCompact: <10s

**Diagnosis:**
```bash
# Check hook duration
grep "pre_compact_duration" ~/.ai-memory/logs/hooks.log
```

**Solution:**
1. Increase timeout if consistently hitting limit:
   ```json
   {"timeout": 15000}  // 15 seconds
   ```
2. Check Qdrant latency (should be <500ms)
</details>

<details>
<summary><strong>Session summaries not appearing in SessionStart</strong></summary>

**Diagnosis:**
```bash
# Check if summary was stored
curl http://localhost:26350/collections/discussions/points/scroll \
  | jq '.result.points[] | select(.payload.type == "session")'

# Check timestamp (must be within 48 hours)
```

**Possible Causes:**
1. **Stored in wrong collection** - Should be `discussions`, not `code-patterns`
2. **Wrong group_id** - Project detection mismatch
3. **Older than 48 hours** - SessionStart filters to recent sessions

**Solution:**
```bash
# Verify PreCompact hook configuration
grep -A 10 "PreCompact" .claude/settings.json

# Check logs for storage confirmation
grep "session_summary_stored" ~/.ai-memory/logs/hooks.log
```
</details>

---

### Stop

**🧹 Optional cleanup hook (rarely used)**

#### Purpose
Optional per-response cleanup. Unlike PreCompact (which saves summaries), Stop is for cleanup operations.

#### Trigger
Fires after each response Claude generates.

#### Configuration

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/stop_hook.py"
          }
        ]
      }
    ]
  }
}
```

> **Note:** This hook is **optional** and not required for core functionality.

#### Input (Hook Payload)

```json
{
  "session_id": "sess-abc123",
  "cwd": "/path/to/project",
  "response_id": "resp-xyz789"
}
```

#### Use Cases
- Cleanup temporary files
- Flush logs
- Per-response metrics

> **Recommendation:** Most installations don't need the Stop hook. PreCompact handles session summaries.

---

## 🔍 Tier 2 Per-Turn Context Injection

**Adaptive semantic retrieval injected before each Claude response**

### Overview

The AI Memory Module uses a two-tier injection model:

| Tier | Hook | Trigger | Purpose | Typical Token Budget |
|------|------|---------|---------|----------------------|
| **Tier 1 — Bootstrap** | `session_start.py` | `SessionStart` | Conventions + recent decisions, once per session | ~2–3 K tokens |
| **Tier 2 — Per-turn** | `context_injection_tier2.py` | `UserPromptSubmit` | Adaptive semantic retrieval before every user turn | 500–1500 tokens |

Tier 1 seeds the session with stable context at startup; Tier 2 keeps context fresh turn-by-turn by retrieving what is most relevant to the current prompt. Both tiers cooperate: point IDs injected by Tier 1 are tracked in `InjectionSessionState` so Tier 2 skips already-seen results on subsequent turns.

### Trigger

**Event:** `UserPromptSubmit` — fires before each user prompt is processed.

**Script:** `.claude/hooks/scripts/context_injection_tier2.py`

**Performance target:** <500ms total (NFR-P1, NFR-P5). Exit code always 0 — graceful degradation on any error, never blocks Claude.

**Skip conditions (no injection, empty `additionalContext` returned):**
- Prompt is empty or whitespace
- Prompt is a slash command (matches `/[\w:./-]+`)
- `injection_enabled = false` in config
- Qdrant health check fails
- Project ID cannot be resolved from `cwd`

### Configuration

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/activity_logger.py --event user_prompt"
          },
          {
            "type": "command",
            "command": ".claude/hooks/scripts/context_injection_tier2.py"
          }
        ]
      }
    ]
  }
}
```

### Process Flow

```
UserPromptSubmit fires
    ↓
1.  Parse hook payload → prompt, session_id, cwd
2.  resolve_project_id(cwd) → project group_id
3.  Qdrant health check → graceful skip if unavailable
4.  Skip if prompt is empty or a slash command
5.  Load InjectionSessionState (cross-turn dedup + drift tracking)
6.  route_collections(prompt) → target collection list
7.  MemorySearch.search() per collection (fast_mode=True)
8.  Apply freshness penalty to code-patterns results (score × penalty factor)
9.  Re-sort all results by score descending
10. Confidence gating → determine gating_mode
11. compute_topic_drift(current_embedding, last_query_embedding)
12. compute_adaptive_budget(best_score, results, session_state, config)
13. Halve budget if gating_mode == "soft_gate" (min 50 tokens)
14. select_results_greedy(results, budget, excluded_ids, ...)
15. format_injection_output(selected, tier=2) → additionalContext
16. Prepend remaining= reject marker if agent_handoff was budget-rejected
17. log_injection_event(...) → .audit/logs/injection-log.jsonl
18. Save updated InjectionSessionState
    ↓
Claude receives context via hookSpecificOutput.additionalContext
```

### Collection Routing (`route_collections`)

`route_collections(prompt)` maps each prompt to one or more target collections, evaluated in priority order:

| Priority | Condition | Collections targeted |
|----------|-----------|----------------------|
| 1. Keyword triggers | Decision / session / best-practices keyword detected | `discussions` and/or `conventions` |
| 2. File path | Prompt contains a file path or recognized source extension | `code-patterns` |
| 3. Intent detection | HOW / WHAT / WHY intent resolved | Intent-matched collection |
| 4. Cascade (unknown) | None of the above match | `discussions` → `code-patterns` → `conventions` |

When multiple keyword triggers resolve to the same collection (e.g., both a decision keyword and a session keyword match `discussions`), the duplicate route is deduplicated before searching. Keyword-trigger routing is backward-compatible with the old `unified_keyword_trigger.py` hook — no regression.

### Adaptive Token Budget (`compute_adaptive_budget`)

Budget is computed fresh each turn from three weighted signals:

| Signal | Weight | Description |
|--------|--------|-------------|
| `quality_signal` | 50% | Best retrieval score (cosine similarity, 0–1) |
| `density_signal` | 30% | Fraction of results above `injection_confidence_threshold` |
| `drift_signal` | 20% | Topic drift from previous query — higher drift means a new topic and more context needed |

```
budget = floor + int((ceiling − floor) × (0.5 × quality + 0.3 × density + 0.2 × drift))
```

Result is clamped to `[injection_budget_floor, injection_budget_ceiling]` (configured in `MemoryConfig`). Typical range: 500–1500 tokens.

### Confidence Gating Modes

Before computing budget, the best retrieval score is evaluated against configured per-collection thresholds to determine the gating mode:

| Mode | Condition | Effect |
|------|-----------|--------|
| `hard_skip` | `best_score < injection_hard_floor` | No injection; exit with empty context |
| `soft_skip` | `best_score < threshold − 0.05` | No injection; exit with empty context |
| `soft_gate` | `best_score < threshold` | Inject with budget halved (minimum 50 tokens) |
| `full` | `best_score ≥ threshold` | Inject with full computed budget |

The threshold compared against is collection-specific — `injection_threshold_discussions`, `injection_threshold_code_patterns`, or `injection_threshold_conventions` — falling back to `injection_confidence_threshold` when the best-scoring collection is unknown.

### Topic Drift (`compute_topic_drift`)

```python
drift = compute_topic_drift(current_embedding, previous_embedding)
# Returns float in [0.0, 1.0]
# 0.0 → same topic as previous turn (cosine similarity = 1.0)
# 1.0 → completely different topic (orthogonal embeddings)
# 0.5 → neutral default (first turn, or zero-norm vectors)
```

Computed as cosine distance (1 − cosine_similarity) between the current prompt's 768-dim embedding and the previous turn's embedding stored in `InjectionSessionState`. High drift increases the adaptive budget so the model receives more re-orientation context when conversation topics shift sharply.

### Greedy Fill (`select_results_greedy`)

Results are packed into the budget from highest score to lowest. Individual results are never truncated — each chunk is fully included or fully skipped. Skip-and-continue allows smaller results to fill remaining budget after an oversized one is rejected.

**Selection logic per candidate (in order):**
1. Skip if point ID is in `InjectionSessionState.injected_point_ids` (cross-turn dedup — includes IDs from Tier 1)
2. Skip if content is empty
3. Skip if content hash already selected this turn (BUG-172 cross-type dedup)
4. Skip if `result_score < best_score × score_gap_threshold` (BUG-173 low-relevance gap filter)
5. If `tokens_used + result_tokens ≤ budget`: select; else skip-and-continue

**Score gap filter:** Default threshold 0.7 (results more than 30% below the best semantic score are dropped as noise). Configurable via `INJECTION_SCORE_GAP_THRESHOLD` env var.

**Freshness penalty:** `code-patterns` results marked stale receive a score multiplier before gating and gap filtering. Candidates driven to score 0.0 by the penalty are dropped at the gap filter step and logged with reason `freshness_block` (not `score_gap`) in reject records for accurate attribution.

### Reject Marker (`remaining=`)

When an `agent_handoff`-type result is rejected by `select_results_greedy` due to `budget_exceeded` or `ceiling_exceeded`, a diagnostic comment is prepended to the injected context:

```
# [tier-2 fallback: handoff-class result rejected reason=budget_exceeded tokens=3200 remaining=180 budget=900]
```

| Field | Description |
|-------|-------------|
| `reason` | `budget_exceeded` or `ceiling_exceeded` |
| `tokens` | Token count of the rejected result |
| `remaining` | Unused budget at rejection time (`budget − tokens_used`) |
| `budget` | Total adaptive budget computed for this turn |

This is observe-only — it does not change which results are selected. Tier 2 has no filesystem fallback path. The rejected `agent_handoff` becomes eligible again after the next `/compact` resets `InjectionSessionState.injected_point_ids`.

### Audit Log (`injection-log.jsonl`)

Every turn — including skipped injections — is appended to `.audit/logs/injection-log.jsonl` by `log_injection_event()`. Each line is a self-contained JSON object.

**Top-level fields:**

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 UTC timestamp |
| `tier` | int | `2` for all Tier 2 events |
| `trigger` | string | `"UserPromptSubmit"` |
| `project` | string | Resolved project `group_id` |
| `session_id` | string | Claude Code session identifier |
| `results_considered` | int | Total candidates returned across all searched collections |
| `results_selected` | int | Results that passed greedy fill |
| `tokens_used` | int | Tokens actually injected this turn |
| `budget` | int | Adaptive budget computed for this turn |
| `utilization_pct` | int | `tokens_used / budget × 100` |
| `best_score` | float | Highest retrieval score (4 decimal places) |
| `skipped_confidence` | bool | `true` when gating mode is `hard_skip` or `soft_skip` |
| `topic_drift` | float | Cosine drift from previous query (4 decimal places) |
| `collections_searched` | list[str] | Collections queried this turn |
| `gap_threshold` | float | Score gap filter multiplier used |
| `gating_mode` | string | `"hard_skip"`, `"soft_skip"`, `"soft_gate"`, or `"full"` |
| `rejects` | list[object] | Per-drop reject records (see below) |
| `fallback_signaled` | bool | `true` if an `agent_handoff` was budget/ceiling rejected |
| `per_source` | object | Per-collection budget ledger (see below) |

**Reject record shape** (each entry in `rejects[]`):

| Field | Description |
|-------|-------------|
| `type` | Memory type of the rejected result (e.g., `"decision"`, `"agent_handoff"`) |
| `tokens` | Token count — present only for `budget_exceeded`, otherwise `null` |
| `score` | Retrieval score at rejection time |
| `reason` | One of: `already_injected`, `empty_content`, `dedup`, `score_gap`, `freshness_block`, `budget_exceeded` |
| `tier` | `"2_injection"` |
| `collection` | Source collection name |

**Per-collection budget ledger (`per_source` object):**

Keyed by collection name.

| Field | Description |
|-------|-------------|
| `requested_tokens` | Sum of token counts for candidates that passed all pre-budget filters (`already_injected`, `empty_content`, `dedup`, `score_gap`, `freshness_block`) and reached the budget check |
| `loaded_tokens` | Tokens actually selected from this collection |
| `dropped` | Per-reason map accumulating **all** reject reasons: `already_injected`, `empty_content`, `dedup`, `score_gap`, `freshness_block` (`count` only); `budget_exceeded` (`count` + `tokens`) |

Reconciliation per collection (budget-class only): `loaded_tokens + dropped["budget_exceeded"]["tokens"] == requested_tokens`.

**Example entry:**

```json
{
  "timestamp": "2026-06-14T10:30:00Z",
  "tier": 2,
  "trigger": "UserPromptSubmit",
  "project": "my-project",
  "session_id": "sess-abc123",
  "results_considered": 12,
  "results_selected": 3,
  "tokens_used": 820,
  "budget": 1100,
  "utilization_pct": 74,
  "best_score": 0.8821,
  "skipped_confidence": false,
  "topic_drift": 0.3142,
  "collections_searched": ["discussions", "code-patterns"],
  "gap_threshold": 0.7,
  "gating_mode": "full",
  "rejects": [
    {
      "type": "decision",
      "tokens": null,
      "score": 0.521,
      "reason": "score_gap",
      "tier": "2_injection",
      "collection": "discussions"
    }
  ],
  "fallback_signaled": false,
  "per_source": {
    "discussions": {
      "requested_tokens": 650,
      "loaded_tokens": 650,
      "dropped": {}
    },
    "code-patterns": {
      "requested_tokens": 510,
      "loaded_tokens": 170,
      "dropped": {"score_gap": {"count": 2}, "budget_exceeded": {"count": 1, "tokens": 340}}
    }
  }
}
```

### Troubleshooting

<details>
<summary><strong>No context injected despite relevant session history</strong></summary>

**Diagnosis:**
```bash
# Check gating mode and scores for recent turns
tail -5 ~/.ai-memory/.audit/logs/injection-log.jsonl | jq '{gating_mode, best_score, results_selected, skipped_confidence}'
```

**Possible Causes:**
1. `gating_mode: "hard_skip"` or `"soft_skip"` — retrieval scores below threshold
2. `results_selected: 0` after dedup — all candidates were already injected this session
3. Slash command prompt — injection skipped for `/...` invocations

**Solution:**
```bash
# Check configured thresholds
grep "injection_confidence_threshold\|injection_hard_floor" ~/.ai-memory/.env
```
</details>

<details>
<summary><strong>Seeing the <code>remaining=</code> marker in injected context</strong></summary>

The `# [tier-2 fallback: handoff-class result rejected ...]` comment means an `agent_handoff` result was too large to fit the computed token budget. It is observe-only — no recovery action is needed on your part.

**Diagnosis:**
```bash
tail -1 ~/.ai-memory/.audit/logs/injection-log.jsonl | jq '{budget, tokens_used, fallback_signaled, per_source}'
```

After the next `/compact`, `InjectionSessionState.injected_point_ids` resets and the handoff becomes eligible again.
</details>

<details>
<summary><strong>Hook exceeds 500ms performance target</strong></summary>

**Diagnosis:**
```bash
grep "tier2_injection_complete" ~/.ai-memory/logs/hooks.log | tail -5 | python3 -c "import sys,json; [print(json.loads(l).get('duration_ms')) for l in sys.stdin]"
```

**Solutions:**
1. Reduce `MAX_RETRIEVALS` — fewer candidates fetched per collection
2. Verify Qdrant is on localhost (network latency dominates over embedding time)
3. Check embedding service is pre-warmed; cold start adds ~2s on first call
</details>

---

## 📊 Activity Logging Hooks

Activity logging hooks track session events for analytics and debugging. They write to `~/.ai-memory/logs/activity.log` asynchronously.

### SessionEnd

**Purpose:** Log session end events for analytics

**Configuration:**
```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/activity_logger.py --event session_end"
          }
        ]
      }
    ]
  }
}
```

**Logged Data:**
- Session ID
- Duration
- Total prompts
- Tools used
- Files modified

---

### UserPromptSubmit

**Purpose:** Two hooks run on this event:

1. **`activity_logger.py --event user_prompt`** — logs session tracking data (turn count, prompt length, project). This is the activity-logging side documented here.
2. **`context_injection_tier2.py`** — performs per-turn semantic retrieval and injects relevant memories as context before Claude responds. See [Tier 2 Per-Turn Context Injection](#tier-2-per-turn-context-injection) for the full injection pipeline.

> **Common misconception:** `UserPromptSubmit` is not only a logging hook. The Tier 2 semantic retrieval hook also fires here on every turn.

**Configuration (activity logging):**
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/activity_logger.py --event user_prompt"
          },
          {
            "type": "command",
            "command": ".claude/hooks/scripts/context_injection_tier2.py"
          }
        ]
      }
    ]
  }
}
```

**Logged Data (activity_logger.py):**
- Timestamp
- Session ID
- Prompt length
- Project

---

### Notification

**Purpose:** Log Claude Code notifications

**Logged Data:**
- Notification type
- Message content
- Severity

---

### SubagentStop

**Purpose:** Log subagent completion (for BMAD workflows)

**Logged Data:**
- Subagent type
- Duration
- Success/failure

---

### PreToolUse

**Purpose:** Log tool invocations before execution

**Logged Data:**
- Tool name
- Input parameters
- Timestamp

---

## 🚨 Error Handling Hooks

### Error Pattern Capture

**Purpose:** Capture error patterns and their resolutions for future reference

**Hook:** `error_pattern_capture.py`

**Storage:** `code-patterns` collection (type=`error_pattern`)

**Example Pattern:**
```json
{
  "error_type": "TypeError",
  "error_message": "Cannot read property 'token' of undefined",
  "context": "JWT token verification in auth middleware",
  "resolution": "Added null check before token.verify()",
  "file": "src/middleware/auth.js:42"
}
```

---

### Error Context Retrieval

**Purpose:** Retrieve similar error patterns when an error occurs

**Hook:** `error_context_retrieval.py`

**Process:**
1. Detect error in Claude's context
2. Search error_patterns collection
3. Inject similar errors + resolutions

---

## 🎓 Best Practices Hooks

### Best Practices Retrieval

**Purpose:** Retrieve universal patterns shared across all projects

**Hook:** `best_practices_retrieval.py`

**Collection:** `conventions` (group_id="shared")

**Example:**
```markdown
## Best Practice: Python Type Hints (95%)

Always use type hints in Python 3.10+ for better IDE support:

```python
def authenticate(email: str, password: str) -> dict[str, str]:
    return {"token": generate_jwt(email)}
```

Benefits:
- IDE autocomplete
- Early error detection
- Better documentation
```

---

## 🎯 Manual Operations

### Manual Save Memory

**Command:** `/aim-save`

**Purpose:** Manually save current session state without waiting for compaction

**Hook:** `manual_save_memory.py`

**Use Cases:**
- Before ending session without compacting
- After completing a major milestone
- Testing memory system

---

## ⚙️ Configuration Examples

### Minimal Configuration (Core Hooks Only)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/session_start.py"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/post_tool_capture.py"}
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/pre_compact_save.py", "timeout": 10000}
        ]
      }
    ]
  }
}
```

### Full Configuration (All Hooks)

See the hook scripts in `.claude/hooks/scripts/` for complete examples.

---

## 🔧 Troubleshooting

### Common Issues

<details>
<summary><strong>Hooks not firing at all</strong></summary>

**Diagnosis:**
1. Check `.claude/settings.json` exists and is valid JSON
2. Verify hook scripts are executable:
   ```bash
   chmod +x .claude/hooks/scripts/*.py
   ```
3. Check Claude Code is using correct project directory

**Solution:**
```bash
# Validate JSON
jq . .claude/settings.json

# Test hook manually
python3 .claude/hooks/scripts/session_start.py <<< '{"session_id": "test", "cwd": "'$(pwd)'", "source": "startup"}'
```
</details>

<details>
<summary><strong>Hooks execute but errors occur</strong></summary>

**Diagnosis:**
```bash
# Check hook logs
tail -f ~/.ai-memory/logs/hooks.log

# Check Python errors
python3 .claude/hooks/scripts/session_start.py <<< '...' 2>&1
```

**Common Errors:**
1. **Import errors** - Python path issues
2. **Connection errors** - Qdrant unavailable
3. **Permission errors** - File access issues
</details>

<details>
<summary><strong>Performance issues (hooks too slow)</strong></summary>

**Benchmarks:**
- SessionStart: <3s
- PostToolUse: <500ms (fork pattern)
- PreCompact: <10s

**Diagnosis:**
```bash
# Check hook durations
grep "duration" ~/.ai-memory/logs/hooks.log | tail -20
```

**Solutions:**
1. Reduce `MAX_RETRIEVALS` (default 10)
2. Increase `SIMILARITY_THRESHOLD` (filter low-relevance results)
3. Check Qdrant performance:
   ```bash
   curl http://localhost:26350/metrics
   ```
</details>

---

## Trigger Keyword Reference

The following keywords automatically activate memory retrieval when detected in user prompts. Keywords are case-insensitive. Only structured patterns trigger retrieval to avoid false positives on casual conversation.

### Decision Keywords (20 patterns) — searches `discussions` for past decisions

| Category | Keywords |
|----------|----------|
| Decision recall | `why did we`, `why do we`, `what was decided`, `what did we decide` |
| Memory recall | `remember when`, `remember the decision`, `remember what`, `remember how`, `do you remember`, `recall when`, `recall the`, `recall how` |
| Session references | `last session`, `previous session`, `earlier we`, `before we`, `previously`, `last time we`, `what did we do`, `where did we leave off` |

### Session History Keywords (16 patterns) — searches `discussions` for session summaries

| Category | Keywords |
|----------|----------|
| Project status | `what have we done`, `what did we work on`, `project status`, `where were we`, `what's the status` |
| Continuation | `continue from`, `pick up where`, `continue where` |
| Remaining work | `what's left to do`, `remaining work`, `what's next for`, `what's next on`, `what's next in the`, `next steps`, `todo`, `tasks remaining` |

### Best Practices Keywords (27 patterns) — searches `conventions` for guidelines

| Category | Keywords |
|----------|----------|
| Standards | `best practice`, `best practices`, `coding standard`, `coding standards`, `convention`, `conventions for` |
| Patterns | `what's the pattern`, `what is the pattern`, `naming convention`, `style guide` |
| Guidance | `how should i`, `how do i`, `what's the right way`, `what is the right way` |
| Research | `research the pattern`, `research best practice`, `look up`, `find out about`, `what do the docs say` |
| Recommendations | `should i use`, `what's recommended`, `what is recommended`, `recommended approach`, `preferred approach`, `preferred way`, `industry standard`, `common pattern` |

---

## 📚 See Also

- [AI_MEMORY_ARCHITECTURE.md](AI_MEMORY_ARCHITECTURE.md) - System architecture
- [prometheus-queries.md](prometheus-queries.md) - Hook performance metrics
- [structured-logging.md](structured-logging.md) - Hook logging patterns
