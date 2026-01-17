# Error Context Retrieval

**Status**: Implemented
**Hook Type**: PreToolUse (Bash)
**Performance**: <500ms hook execution, synchronous retrieval

## Overview

The error context retrieval system proactively retrieves relevant error patterns BEFORE executing build/test commands in Claude Code. This enables:

1. **Preventive Guidance**: See known errors before they occur
2. **Faster Debugging**: Solutions appear before you hit the error
3. **Pattern Awareness**: Learn from past mistakes automatically
4. **Reduced Iteration**: Avoid repeating known failures

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code prepares to execute Bash command                │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ PreToolUse Hook: error_context_retrieval.py (<500ms)        │
│  1. Validate tool is Bash                                   │
│  2. Parse command from tool_input                           │
│  3. Detect if build/test command                            │
│  4. Build semantic query                                    │
│  5. Search error_pattern collection                         │
│  6. Format and output to stdout                             │
│  7. Exit 0 (context injected into Claude)                   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Claude sees error patterns in context                       │
│ Bash command executes with awareness of potential issues    │
└─────────────────────────────────────────────────────────────┘
```

## Complementary System

This hook works in tandem with `error_pattern_capture.py`:

| Hook | Trigger | Purpose | Timing |
|------|---------|---------|--------|
| **error_context_retrieval.py** | PreToolUse | Retrieve error patterns | Before execution |
| **error_pattern_capture.py** | PostToolUse | Capture error patterns | After execution |

Together they form a complete error learning loop:

```
Execute Bash → PostToolUse captures error → Store error pattern
                                                      ↓
Next session → PreToolUse retrieves pattern → Claude avoids error
```

## Build/Test Command Detection

The hook activates ONLY for build/test commands to avoid noise on simple commands like `ls` or `cat`.

### Supported Command Types

```python
BUILD_TEST_PATTERNS = {
    # Package managers
    "npm": ["npm test", "npm run test", "npm run build", "npm ci"],
    "yarn": ["yarn test", "yarn build", "yarn install"],
    "pnpm": ["pnpm test", "pnpm build", "pnpm install"],

    # Python
    "pytest": ["pytest", "python -m pytest", "python3 -m pytest"],
    "python": ["python setup.py", "python -m unittest"],
    "pip": ["pip install", "pip3 install"],

    # Make/Build tools
    "make": ["make", "make test", "make build", "make install"],
    "cmake": ["cmake", "ctest"],
    "gradle": ["gradle test", "gradle build", "./gradlew"],
    "maven": ["mvn test", "mvn build", "mvn install"],

    # Go
    "go": ["go test", "go build", "go install", "go mod"],

    # Rust
    "cargo": ["cargo test", "cargo build", "cargo check"],

    # Docker
    "docker": ["docker build", "docker-compose up", "docker compose up"],

    # JavaScript/TypeScript
    "jest": ["jest", "npm run jest"],
    "mocha": ["mocha", "npm run mocha"],
    "vitest": ["vitest", "npm run vitest"],

    # Linters/Formatters
    "eslint": ["eslint", "npm run lint"],
    "pylint": ["pylint"],
    "black": ["black"],
    "mypy": ["mypy"],
}
```

### Detection Logic

```python
# Example: "npm test" → command_type = "npm"
# Example: "pytest tests/" → command_type = "pytest"
# Example: "ls -la" → command_type = None (skipped)
```

## Semantic Query Building

The hook builds intelligent queries from the command:

```python
# Input: "npm test"
# Query: "npm errors failures common issues"

# Input: "pytest tests/test_auth.py"
# Query: "pytest errors failures test authentication common issues"

# Input: "docker build -t myapp:latest ."
# Query: "docker build errors failures common issues"
```

### Query Construction Rules

1. **Command Type**: Always include (npm, pytest, docker, etc.)
2. **Error Keywords**: Add "errors", "failures"
3. **Meaningful Parts**: Extract up to 3 substantive command parts
4. **Generic Context**: Add "common issues" for broader matching

## Search Parameters

```python
search.search(
    query=query,
    collection="implementations",
    group_id=project_name,  # Filter to current project
    limit=3,  # Up to 3 patterns (requirement)
    score_threshold=0.4,  # Lower threshold (cast wider net)
    filters={
        "must": [
            {
                "key": "type",
                "match": {"value": "error_pattern"}
            }
        ]
    }
)
```

**Key Decisions:**
- **Project-scoped**: Only show errors from current project (avoid cross-contamination)
- **Lower threshold**: 0.4 vs 0.5 for best practices (errors need broader matching)
- **Limit 3**: Balance between useful context and information overload

## Output Format

When relevant error patterns are found:

```
======================================================================
⚠️  RELEVANT ERROR PATTERNS
======================================================================
Command: npm test
Type: npm

Known issues that might occur:

1. Error: ENOENT: no such file or directory, open 'package.json' | Relevance: 87%
   Command: npm test
   Solution: Ensure package.json exists in project root. Run 'npm init' if missing.

2. Error: Test suite failed to run - Cannot find module 'jest' | Relevance: 72%
   Command: npm test
   Solution: Install dependencies with 'npm install' before running tests.

3. Error: ELIFECYCLE Command failed with exit code 1 | Relevance: 65%
   Command: npm run test:unit

======================================================================
```

This appears in Claude's context BEFORE the command executes.

## Configuration

### Hook Setup

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/.claude/hooks/scripts/error_context_retrieval.py"
          }
        ]
      }
    ]
  }
}
```

### Combined Configuration

Use both hooks for complete error learning:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/.claude/hooks/scripts/error_context_retrieval.py"
          }
        ]
      }
    ],
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

## Performance Characteristics

| Metric | Target | Implementation |
|--------|--------|----------------|
| Hook Execution | <500ms | Synchronous search with timeout |
| Command Detection | <5ms | Simple pattern matching |
| Query Building | <5ms | String manipulation |
| Qdrant Search | <300ms | Limited to 3 results, filtered |
| Output Formatting | <10ms | String concatenation |

**No Background Forking**: PreToolUse is informational and completes synchronously.

## Graceful Degradation

The system fails silently at every level:

1. **Malformed JSON**: Log and exit 0 (non-blocking)
2. **Not Bash Tool**: Skip processing, exit 0
3. **No Command**: Skip processing, exit 0
4. **Not Build/Test**: Skip processing, exit 0 (avoid noise)
5. **Qdrant Unavailable**: Log warning, exit 0
6. **No Results**: Log debug message, exit 0
7. **Search Error**: Log error, exit 0

**Key Principle**: Claude works without memory. Memory is an enhancement, not a requirement.

## Solution Hint Extraction

The hook attempts to extract solution hints from error pattern content:

```python
# Look for solution indicators
solution_keywords = [
    "solution:", "fix:", "resolved by:", "workaround:",
    "to fix:", "fixed by:", "solved by:"
]

# Extract solution and next 2 lines (max 200 chars)
# Display in formatted output
```

**Example:**

```
Error: ModuleNotFoundError: No module named 'requests'
Solution: Install the requests library with 'pip install requests'
```

## Use Cases

### 1. Avoiding Known Test Failures

```bash
# Before: Claude runs 'pytest tests/' blindly
# After: Claude sees "Last time pytest failed with missing fixtures"
#        Claude fixes fixture setup BEFORE running tests
```

### 2. Build Configuration Issues

```bash
# Before: 'npm run build' fails with webpack error
# After: Claude sees "webpack config missing devtool property"
#        Claude checks config BEFORE building
```

### 3. Environment Problems

```bash
# Before: 'docker build' fails with network timeout
# After: Claude sees "Docker build failed - proxy configuration needed"
#        Claude suggests proxy settings BEFORE building
```

### 4. Dependency Conflicts

```bash
# Before: 'pip install' fails with version conflict
# After: Claude sees "dependency resolver backtracking - use constraints file"
#        Claude creates constraints.txt BEFORE installing
```

## Testing

Create test script to validate hook behavior:

```bash
#!/bin/bash
# Test error context retrieval hook

# Setup: Store some error patterns first
pytest tests/test_foo.py  # Intentionally fail
# PostToolUse captures error

# Test: Run build command again
# PreToolUse should show captured error
npm test
```

**Expected Output**: Error pattern displayed before npm executes.

## Metrics

Prometheus metrics (if enabled):

```
# Hook execution duration
hook_duration_seconds{hook_type="PreToolUse_Error"}

# Retrieval success/failure/empty
memory_retrievals_total{collection="implementations",status="success|failed|empty"}

# Retrieval duration
retrieval_duration_seconds
```

## Limitations

1. **Project-Scoped Only**: Doesn't share errors across projects
   - **Why**: Avoid false positives from different contexts
   - **Future**: Consider opt-in cross-project error sharing

2. **Build/Test Commands Only**: Skips simple file operations
   - **Why**: Reduce noise and improve signal-to-noise ratio
   - **Alternative**: Extend BUILD_TEST_PATTERNS if needed

3. **No Solution Validation**: Shows hints, doesn't verify they work
   - **Why**: Hook executes before command, can't validate
   - **Future**: Track solution effectiveness via feedback loop

4. **Limited to 3 Results**: May miss some relevant patterns
   - **Why**: Balance context size with usefulness
   - **Tuning**: Adjust `limit` parameter if needed

## Best Practices

1. **Capture First, Retrieve Second**: Run commands at least once to populate error patterns
2. **Review Patterns**: Periodically audit stored patterns for accuracy
3. **Adjust Threshold**: Tune `score_threshold` based on result quality
4. **Filter by Type**: Always filter `type="error_pattern"` to avoid noise
5. **Monitor Performance**: Track hook execution time in logs

## Future Enhancements

1. **Solution Effectiveness Tracking**: Mark solutions as "worked" or "didn't work"
2. **Cross-Project Learning**: Opt-in sharing of generic error patterns
3. **Temporal Relevance**: Weight recent errors higher than old ones
4. **Command Similarity**: Use fuzzy matching for similar commands
5. **Interactive Mode**: Let Claude ask "Should I apply known fix?"
6. **Error Categories**: Classify errors (dependency, config, syntax, etc.)

## Related Files

| File | Purpose |
|------|---------|
| `.claude/hooks/scripts/error_context_retrieval.py` | Main hook (PreToolUse) |
| `.claude/hooks/scripts/error_pattern_capture.py` | Complementary capture hook (PostToolUse) |
| `.claude/hooks/scripts/error_store_async.py` | Background storage for captured errors |
| `.claude/settings.json` | Hook configuration |

## See Also

- [error-pattern-capture.md](error-pattern-capture.md) - PostToolUse error capture system
- [CLAUDE.md](../CLAUDE.md) - Project overview and conventions
- [structured-logging.md](structured-logging.md) - Logging patterns
- [claude-code-hooks-best-practices.md](claude-code-hooks-best-practices.md) - Hook development guide
- [prometheus-queries.md](prometheus-queries.md) - Metrics and monitoring
