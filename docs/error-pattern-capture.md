# Error Pattern Capture

**Status**: Implemented
**Hook Type**: PostToolUse (Bash)
**Performance**: <500ms hook execution, async background storage

## Overview

The error pattern capture system automatically detects and stores error patterns from failed Bash commands executed by Claude Code. This enables:

1. **Error Learning**: Build a knowledge base of errors encountered in the project
2. **Context-Aware Debugging**: Search for similar errors when troubleshooting
3. **Pattern Recognition**: Identify recurring error patterns across sessions
4. **File:Line References**: Extract precise error locations for quick navigation

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code executes Bash command                           │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ PostToolUse Hook: error_pattern_capture.py (<500ms)         │
│  1. Validate tool is Bash                                   │
│  2. Detect error indicators (exit code, error strings)      │
│  3. Extract error context                                   │
│  4. Fork to background process                              │
│  5. Exit 0 immediately                                      │
└────────────────────────────┬────────────────────────────────┘
                             │ fork (non-blocking)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Background: error_store_async.py (no time constraint)       │
│  1. Format error content for embedding                      │
│  2. Generate embedding (Nomic Embed Code)                   │
│  3. Store to Qdrant with type="error_pattern"               │
│  4. Graceful degradation on failure (queue to file)         │
└─────────────────────────────────────────────────────────────┘
```

## Error Detection

### Primary Indicators

1. **Exit Code**: `exitCode != 0` (most reliable)
2. **Structured Error Patterns** (v2.0.9 rewrite — eliminates false positives from filenames):
   - `TypeError:`, `ValueError:`, `KeyError:`, `AttributeError:`, `ImportError:`
   - `Traceback (most recent call last):`
   - `SyntaxError:`, `IndentationError:`
   - `npm ERR!`, `ENOENT`, `EACCES`
   - `FAILED`, `FATAL`, `panic:`
   - `exit code [1-9]`, `exited with [1-9]`
   - `permission denied`, `command not found`, `no such file or directory`
   - `segmentation fault`, `core dumped`

> **v2.0.9 Change:** The error detection was rewritten to use structured patterns instead of bare keyword matching. Previously, matching on the substring "error" caused false positives when filenames like `error-handling.md` appeared in `find`/`ls` output. The new detection first checks if output is a directory listing (file-path-only lines) and skips it entirely.

### Context Extraction

The system extracts:

- **Command**: The Bash command that failed
- **Exit Code**: Numeric exit code (if available)
- **Error Message**: Concise error summary
- **Output**: First 1000 chars of command output
- **File References**: Extracted file:line patterns
- **Stack Trace**: Full stack trace if present
- **Working Directory**: Project context
- **Session ID**: For correlation

## File:Line Reference Patterns

Supports multiple error format conventions:

```python
# Pattern 1: file.py:42 or file.py:42:10
"tests/test_foo.py:25" → {file: "tests/test_foo.py", line: 25}
"src/main.py:142:8"   → {file: "src/main.py", line: 142, column: 8}

# Pattern 2: Python traceback
'File "script.py", line 42' → {file: "script.py", line: 42}

# Pattern 3: Stack trace format
"at module.py:156" → {file: "module.py", line: 156}
```

## Qdrant Payload Schema

Error patterns are stored with:

```json
{
  "content": "[error_pattern]\nCommand: pytest tests/\nError: AssertionError...",
  "content_hash": "sha256:...",
  "group_id": "ai-memory",
  "type": "error_pattern",
  "source_hook": "PostToolUse_ErrorCapture",
  "session_id": "sess_abc123",
  "embedding_status": "complete",
  "command": "pytest tests/test_foo.py",
  "error_message": "AssertionError: expected 42, got 24",
  "exit_code": 1,
  "file_path": "tests/test_foo.py",
  "file_references": [
    {"file": "tests/test_foo.py", "line": 25}
  ],
  "has_stack_trace": true,
  "tags": ["error", "bash_failure"]
}
```

## Content Format for Embedding

Error patterns are formatted for semantic search:

```
[error_pattern]
Command: python3 /path/to/script.py
Error: ZeroDivisionError: division by zero
Exit Code: 1

File References:
  /path/to/script.py:42
  /path/to/script.py:15

Stack Trace:
Traceback (most recent call last):
  File "/path/to/script.py", line 42, in <module>
    result = divide(10, 0)
  File "/path/to/script.py", line 15, in divide
    return a / b
ZeroDivisionError: division by zero

Command Output:
[first 500 chars of output]
```

## Configuration

### Hook Setup

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/.claude/hooks/scripts/error_pattern_capture.py"
          }
        ]
      }
    ]
  }
}
```

### Environment Variables

Uses standard AI Memory configuration:

```bash
QDRANT_HOST=localhost
QDRANT_PORT=26350
QDRANT_COLLECTION=implementations
EMBEDDING_DIMENSION=768
HOOK_TIMEOUT=60
MEMORY_QUEUE_DIR=./.memory_queue
```

## Performance Characteristics

| Metric | Target | Implementation |
|--------|--------|----------------|
| Hook Execution | <500ms | Fork pattern (immediate exit) |
| Error Detection | <10ms | Regex-based pattern matching |
| Context Extraction | <50ms | Multiple extraction functions |
| Background Storage | <5s | Async Qdrant + embedding |
| Fork Overhead | <5ms | subprocess.Popen w/ start_new_session |

## Graceful Degradation

The system fails silently at every level:

1. **Validation Failure**: Log and exit 0 (non-blocking)
2. **No Error Detected**: Exit 0 (normal completion)
3. **Fork Failure**: Log error, continue Claude session
4. **Qdrant Unavailable**: Queue to file for retry
5. **Embedding Failure**: Use zero vector, mark pending

**Key Principle**: Claude works without memory. Memory is an enhancement, not a requirement.

## Usage Patterns

### Querying Error Patterns

```python
from memory.search import semantic_search

# Find similar errors
results = semantic_search(
    query="ZeroDivisionError in calculation",
    collection="implementations",
    limit=5,
    filter={"type": "error_pattern"}
)

for result in results:
    print(f"Command: {result.payload['command']}")
    print(f"Error: {result.payload['error_message']}")
    print(f"File: {result.payload['file_path']}")
    print(f"Score: {result.score}")
```

### PreToolUse Integration

The complementary `error_context_retrieval.py` PreToolUse hook proactively retrieves error patterns:

**Status**: ✅ Implemented - See [error-context-retrieval.md](error-context-retrieval.md)

```python
# Before executing Bash command, search for similar past errors
# Inject context: "Previously, this command failed with: ..."
```

This enables Claude to:
- Anticipate common errors before they occur
- See solutions from past failures
- Suggest preventive measures
- Learn from past mistakes automatically

Together, these hooks form a complete error learning loop:
1. `error_pattern_capture.py` (PostToolUse) captures errors after execution
2. `error_context_retrieval.py` (PreToolUse) retrieves them before next execution

## Testing

Comprehensive test suite in `tests/test_error_pattern_capture.py`:

```bash
pytest tests/test_error_pattern_capture.py -v
```

Tests cover:
- Error pattern detection (exit code, error strings)
- Successful command handling (no false positives)
- File:line reference extraction
- Malformed JSON graceful handling
- Non-Bash tool filtering

## Metrics

Prometheus metrics (if enabled):

```
# Hook execution duration
hook_duration_seconds{hook_type="PostToolUse_Error"}

# Capture success/failure
memory_captures_total{hook_type="PostToolUse_Error",status="success|failed|queued",project="ai-memory"}
```

## Future Enhancements

1. **Error Resolution Tracking**: Link error patterns to their fixes
2. **Severity Classification**: Auto-classify errors (warning, error, fatal)
3. **Root Cause Analysis**: Cluster related errors
4. **PreToolUse Context Injection**: Warn about potential errors
5. **Cross-Project Learning**: Share error patterns across projects
6. **Solution Suggestions**: Link errors to known solutions

## Related Files

| File | Purpose |
|------|---------|
| `.claude/hooks/scripts/error_pattern_capture.py` | Main hook (PostToolUse) |
| `.claude/hooks/scripts/error_context_retrieval.py` | Complementary retrieval hook (PreToolUse) |
| `.claude/hooks/scripts/error_store_async.py` | Background storage |
| `tests/test_error_pattern_capture.py` | Test suite |
| `.claude/settings.json` | Hook configuration |

## See Also

- [CLAUDE.md](../CLAUDE.md) - Project overview and conventions
- [structured-logging.md](structured-logging.md) - Logging patterns
- [claude-code-hooks-best-practices.md](claude-code-hooks-best-practices.md) - Hook development guide
- [prometheus-queries.md](prometheus-queries.md) - Metrics and monitoring
