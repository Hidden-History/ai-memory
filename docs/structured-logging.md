# Structured Logging Guide

**Version:** 1.0.0
**Last Updated:** 2026-01-14
**Status:** Canonical Reference

Comprehensive guide to structured logging patterns in BMAD Memory Module. Established in Story 6.2 (Logging Infrastructure) and required for all Python code.

---

## 1. Overview

### Why Structured Logging?

Structured logging outputs machine-parseable JSON instead of human-only text strings. This enables:

- **Queryable logs**: Filter and aggregate by field (e.g., "all errors from project X")
- **Observability stack integration**: Works with Loki, ELK, Splunk, Datadog
- **Correlation**: Link logs to Prometheus metrics via shared fields (`session_id`, `project`)
- **Automation**: Trigger alerts, dashboards, and reports from log fields

### JSON Output Format

All logs use JSON structured format by default:

```json
{
  "timestamp": "2026-01-14T15:30:45.123Z",
  "level": "INFO",
  "logger": "bmad.memory.storage",
  "message": "memory_stored",
  "context": {
    "memory_id": "uuid-123",
    "project": "bmad-memory-module",
    "type": "implementation",
    "duration_ms": 42.5
  }
}
```

**Configuration:**
- `BMAD_LOG_FORMAT=json` (default) - Machine-parseable JSON
- `BMAD_LOG_FORMAT=text` - Human-readable text for local development

---

## 2. Core Patterns

### ❌ WRONG - F-Strings in Log Messages

```python
# ANTI-PATTERN: F-string embeds data in message string
logger.info(f"Stored memory {memory_id} for project {project}")

# Problem: Can't query by memory_id or project
# Grep for specific project? Must parse string. Unreliable.
```

### ✅ CORRECT - Structured Extras

```python
# BEST PRACTICE: Separate message from data
logger.info("memory_stored", extra={
    "memory_id": memory_id,
    "project": project,
    "type": "implementation",
    "duration_ms": 42.5
})

# Benefit: Query logs by project="bmad-memory-module" in Loki/ELK
```

**Rule:** Message is operation name. Data goes in `extra` dict.

### Message Naming Convention

Use `snake_case` verbs describing operations:

```python
# Operations
logger.info("memory_stored", extra={...})
logger.info("search_completed", extra={...})
logger.info("embedding_generated", extra={...})

# Events
logger.info("background_forked", extra={...})
logger.warning("service_unavailable", extra={...})
logger.error("validation_failed", extra={...})
```

**Avoid:**
- `logger.info("Success")` - Too vague
- `logger.info("Storing memory...")` - Use present perfect tense
- `logger.info("memory-stored")` - Use underscores, not hyphens

---

## 3. Timing and Performance Logging

### Manual Timing Pattern

Current pattern using `time.perf_counter()`:

```python
import time
from memory.metrics import hook_duration_seconds

start_time = time.perf_counter()

# ... perform operation ...

duration_seconds = time.perf_counter() - start_time

# Log the duration
logger.info("operation_completed", extra={
    "operation": "session_retrieval",
    "duration_ms": duration_seconds * 1000
})

# Record to Prometheus histogram
hook_duration_seconds.labels(hook_type="SessionStart").observe(duration_seconds)
```

**Real Example** from `.claude/hooks/scripts/session_start.py:146-162`:

```python
start_time = time.perf_counter()

# Search both collections
implementations = search.search(...)
best_practices = search.search(...)

# Calculate duration
duration_ms = (time.perf_counter() - start_time) * 1000
duration_seconds = duration_ms / 1000.0

# Structured logging with timing
logger.info("session_retrieval_completed", extra={
    "session_id": session_id,
    "project": project,
    "results_count": len(all_results),
    "duration_ms": round(duration_ms, 2)
})

# Prometheus metrics (dual recording)
retrieval_duration_seconds.observe(duration_seconds)
hook_duration_seconds.labels(hook_type="SessionStart").observe(duration_seconds)
```

### Timing Context Manager (Future Enhancement)

Recommended pattern for complex operations:

```python
from contextlib import contextmanager
import time
import logging

logger = logging.getLogger("bmad.memory")

@contextmanager
def log_timing(operation: str, **extra_fields):
    """Context manager for automatic duration logging.

    Usage:
        with log_timing("memory_search", project="my-project"):
            results = search.search(query)
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"{operation}_completed", extra={
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            **extra_fields
        })
```

**Note:** Not yet implemented. Use manual timing pattern until Story 6.7 (Logging Enhancements).

---

## 4. Sensitive Data Redaction

### Automatic Redaction

The `StructuredFormatter` automatically redacts sensitive keys:

```python
# From src/memory/logging_config.py:21-25
SENSITIVE_KEYS = {
    "password", "token", "secret", "apikey", "api_key",
    "authorization", "credential", "auth", "key", "bearer",
}
```

**Example:**

```python
# Code
logger.info("api_request", extra={
    "url": "https://api.example.com/embed",
    "api_key": "sk-live-abc123def456",  # ⚠️ Sensitive!
    "status_code": 200
})

# Logged JSON
{
  "message": "api_request",
  "context": {
    "url": "https://api.example.com/embed",
    "api_key": "[REDACTED]",  # 🔒 Automatically redacted
    "status_code": 200
  }
}
```

### Adding New Sensitive Fields

Edit `SENSITIVE_KEYS` in `src/memory/logging_config.py`:

```python
SENSITIVE_KEYS = {
    "password", "token", "secret", "apikey", "api_key",
    "authorization", "credential", "auth", "key", "bearer",

    # Add your sensitive field names here
    "qdrant_api_key",
    "webhook_secret",
    "encryption_key",
}
```

**Case-Insensitive:** Redaction uses `.lower()` matching (`api_key` == `API_KEY` == `Api_Key`).

---

## 5. Log Levels

Use log levels to indicate severity and operational status:

### DEBUG

**When:** Detailed diagnostic information for troubleshooting.

```python
logger.debug("embedding_request_payload", extra={
    "text_length": len(text),
    "model": "jinaai/jina-embeddings-v2-base-en",
    "dimensions": 768
})
```

**Enabled:** `BMAD_LOG_LEVEL=DEBUG`

### INFO

**When:** Normal operations, successful completions.

```python
# Successful operations
logger.info("memory_stored", extra={
    "memory_id": memory_id,
    "project": project,
    "type": "implementation"
})

# Background tasks
logger.info("background_forked", extra={
    "tool_name": "Write",
    "session_id": session_id
})

# Search results
logger.info("search_completed", extra={
    "collection": "implementations",
    "results_count": 5,
    "duration_ms": 145.2
})
```

### WARNING

**When:** Recoverable issues, graceful degradation, unusual conditions.

```python
# Service temporarily unavailable
logger.warning("service_unavailable", extra={
    "service": "qdrant",
    "retry_in_seconds": 30
})

# No results (not an error)
logger.warning("session_retrieval_empty", extra={
    "session_id": session_id,
    "project": project,
    "reason": "no_memories"
})

# Metrics module unavailable (graceful degradation)
logger.warning("metrics_module_unavailable")
```

### ERROR

**When:** Failures requiring attention, operations that cannot complete.

```python
# Validation failures
logger.error("validation_failed", extra={
    "reason": "missing_required_field_tool_name",
    "tool_name": hook_input.get("tool_name")
})

# Hook execution failures
logger.error("hook_failed", extra={
    "error": str(e),
    "error_type": type(e).__name__,
    "hook": "PostToolUse"
})

# Qdrant connection failures
logger.error("qdrant_connection_failed", extra={
    "host": config.qdrant_host,
    "port": config.qdrant_port,
    "error": str(e)
})
```

**Never use ERROR for:** Expected empty results, graceful degradation, user input validation (use WARNING or INFO).

---

## 6. Field Naming Convention

### Standard Fields

Use consistent `snake_case` field names across all logs:

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `memory_id` | str | Unique memory identifier | `"uuid-123-abc"` |
| `project` | str | Project name (group_id) | `"bmad-memory-module"` |
| `session_id` | str | Claude session identifier | `"sess_abc123"` |
| `operation` | str | Operation name | `"memory_search"` |
| `duration_ms` | float | Operation duration | `142.5` |
| `status` | str | Result status | `"success"`, `"failed"`, `"empty"` |
| `collection` | str | Qdrant collection name | `"implementations"` |
| `results_count` | int | Number of results | `5` |
| `error` | str | Error message | `str(e)` |
| `error_type` | str | Exception class name | `"ConnectionError"` |

### Avoid High-Cardinality Fields

**Do NOT log fields with unbounded unique values:**

❌ `content_hash` - Every memory has unique hash
❌ `query_text` - Unbounded user input (use `query_preview`)
❌ `file_path` - Many unique paths (use `file_count`)
❌ `timestamp_unix` - Every log has unique timestamp

**Why?** High-cardinality fields explode index size in Loki/ELK and slow queries.

**Instead:**

✅ `query_preview`: First 100 chars of query
✅ `query_length`: Integer length
✅ `file_count`: Count instead of list
✅ `memory_ids`: Top 5 IDs only

**Example from** `session_start.py:414-442`:

```python
logger.info("session_retrieval_completed", extra={
    "query_preview": query[:100],  # ✅ Truncated
    "query_length": len(query),     # ✅ Integer
    "results_count": len(results),  # ✅ Count
    "memory_ids": [r.get("id") for r in results[:5]],  # ✅ Top 5 only
    "scores": [round(r.get("score", 0), 3) for r in results[:5]],
    "duration_ms": round(duration_ms, 2)
})
```

---

## 7. Anti-Patterns

### 🚫 No F-Strings in Logger Calls

```python
# WRONG
logger.info(f"Stored memory {memory_id} for project {project}")

# CORRECT
logger.info("memory_stored", extra={
    "memory_id": memory_id,
    "project": project
})
```

**Why?** F-strings embed data in message, making it unparseable.

### 🚫 No print() Statements

```python
# WRONG
print(f"Searching for memories in {project}")

# CORRECT
logger.info("memory_search_started", extra={
    "project": project,
    "collection": "implementations"
})
```

**Why?** `print()` bypasses logging infrastructure. Not captured in JSON logs.

**Exception:** Hooks using stdout for context injection (SessionStart only).

### 🚫 No Logging Sensitive Data

```python
# WRONG - Sensitive data in message string
logger.info(f"API request with key {api_key}")

# CORRECT - Sensitive data redacted automatically
logger.info("api_request_sent", extra={
    "api_key": api_key  # Automatically redacted to "[REDACTED]"
})
```

**Why?** Logs are often stored long-term and accessible by multiple teams.

### 🚫 No Exception Swallowing

```python
# WRONG
try:
    store_memory(content)
except Exception:
    pass  # Silent failure!

# CORRECT
try:
    store_memory(content)
except Exception as e:
    logger.error("memory_storage_failed", extra={
        "error": str(e),
        "error_type": type(e).__name__,
        "content_length": len(content)
    })
    # Graceful degradation or re-raise
```

**Why?** Silent failures make debugging impossible.

### 🚫 No Generic Error Messages

```python
# WRONG
logger.error("Error occurred", extra={"error": str(e)})

# CORRECT
logger.error("qdrant_connection_failed", extra={
    "error": str(e),
    "error_type": type(e).__name__,
    "host": config.qdrant_host,
    "port": config.qdrant_port,
    "retry_count": retry_count
})
```

**Why?** Generic messages don't provide enough context for debugging.

---

## 8. Integration with Monitoring

### Log-Metric Correlation

Logs and Prometheus metrics use **shared label fields** for correlation:

```python
# Logging
logger.info("memory_stored", extra={
    "project": "bmad-memory-module",
    "type": "implementation",
    "status": "success"
})

# Prometheus metrics (same labels)
memory_captures_total.labels(
    project="bmad-memory-module",
    hook_type="PostToolUse",
    status="success"
).inc()
```

**Shared Fields:**
- `project`
- `status` (`success`, `failed`, `empty`)
- `collection`
- `hook_type`

### Prometheus Query Examples

See `docs/prometheus-queries.md` for detailed query patterns.

**Example:** Find logs for high-latency operations

```promql
# Prometheus: 95th percentile retrieval time by project
histogram_quantile(0.95,
  rate(bmad_retrieval_duration_seconds_bucket[5m])
)

# Then query Loki for corresponding logs:
{logger="bmad.memory.hooks"}
  | json
  | message="session_retrieval_completed"
  | duration_ms > 3000
  | project="bmad-memory-module"
```

### Loki Query Examples (Grafana Cloud)

```logql
# All errors in the last hour
{logger=~"bmad.memory.*"}
  | json
  | level="ERROR"

# Memory storage operations for specific project
{logger="bmad.memory.storage"}
  | json
  | message="memory_stored"
  | project="bmad-memory-module"

# Slow operations (>500ms)
{logger=~"bmad.memory.*"}
  | json
  | duration_ms > 500
  | line_format "{{.message}} took {{.duration_ms}}ms"

# Hook failures by type
{logger="bmad.memory.hooks"}
  | json
  | level="ERROR"
  | line_format "{{.hook}} failed: {{.error}}"
```

### Alert Integration

Combine logs and metrics for alerting:

```yaml
# Prometheus alert rule
- alert: HighMemoryFailureRate
  expr: |
    rate(bmad_failure_events_total[5m]) > 0.1
  annotations:
    summary: "High failure rate detected"
    loki_query: '{logger="bmad.memory.*"} | json | level="ERROR"'
```

**Workflow:**
1. Prometheus detects elevated `bmad_failure_events_total`
2. Alert fires with embedded Loki query
3. On-call engineer clicks Loki link
4. JSON logs show exact errors with full context

---

## Quick Reference

### Logging Setup

```python
from memory.logging_config import configure_logging

# Configure once per process
configure_logging()

# Get logger
import logging
logger = logging.getLogger("bmad.memory.mymodule")
```

### Pattern Cheatsheet

```python
# ✅ Successful operation
logger.info("memory_stored", extra={
    "memory_id": memory_id,
    "project": project
})

# ⚠️ Recoverable issue
logger.warning("service_unavailable", extra={
    "service": "qdrant"
})

# ❌ Failure requiring attention
logger.error("validation_failed", extra={
    "error": str(e),
    "error_type": type(e).__name__
})

# ⏱️ Timing operations
start_time = time.perf_counter()
# ... operation ...
duration_ms = (time.perf_counter() - start_time) * 1000
logger.info("operation_completed", extra={
    "duration_ms": round(duration_ms, 2)
})
```

---

## References

**Implementation Files:**
- `src/memory/logging_config.py` - StructuredFormatter, configure_logging()
- `.claude/hooks/scripts/session_start.py:414-442` - Comprehensive logging example
- `.claude/hooks/scripts/post_tool_capture.py:117-133` - Error handling patterns

**Related Documentation:**
- `docs/prometheus-queries.md` - Metric query patterns and histogram aggregation
- `CLAUDE.md` - Project conventions and port assignments

**External Best Practices:**
- [Python Logging Best Practices 2026](https://www.carmatec.com/blog/python-logging-best-practices-complete-guide/)
- [Structured Logging Best Practices](https://uptrace.dev/glossary/structured-logging)
- [Cybersecurity Logging in Python](https://www.apriorit.com/dev-blog/cybersecurity-logging-python)

---

**Last Updated:** 2026-01-14 by Dev Agent (ACT-006)
