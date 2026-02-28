# 🔧 Claude Code Hooks Reference

> Comprehensive guide to all AI Memory Module hooks

## 📋 Table of Contents

- [Overview](#overview)
- [Core Memory Hooks](#core-memory-hooks)
  - [SessionStart](#sessionstart)
  - [PostToolUse](#posttooluse)
  - [PreCompact](#precompact)
  - [Stop](#stop)
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

**Purpose:** Log each user prompt for session tracking

**Configuration:**
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/activity_logger.py --event user_prompt"
          }
        ]
      }
    ]
  }
}
```

**Logged Data:**
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

**Storage:** `error_patterns` collection

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

See [claude-code-hooks-best-practices.md](claude-code-hooks-best-practices.md) for complete examples.

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
1. Reduce `MAX_RETRIEVALS` (default 5)
2. Increase `SIMILARITY_THRESHOLD` (filter low-relevance results)
3. Check Qdrant performance:
   ```bash
   curl http://localhost:26350/metrics
   ```
</details>

---

## 📚 See Also

- [claude-code-hooks-best-practices.md](claude-code-hooks-best-practices.md) - Complete hook configuration guide
- [AI_MEMORY_ARCHITECTURE.md](AI_MEMORY_ARCHITECTURE.md) - System architecture
- [prometheus-queries.md](prometheus-queries.md) - Hook performance metrics
- [structured-logging.md](structured-logging.md) - Hook logging patterns

---

**2026 Best Practices Applied:**
- Comprehensive examples with expected outputs
- Expandable troubleshooting sections
- Performance benchmarks clearly stated
- Visual hierarchy with consistent icons
- Real-world use cases documented
