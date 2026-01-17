# Hooks E2E Verification Script

## Overview

`verify_hooks_e2e.py` is a comprehensive end-to-end verification tool that tests the entire BMAD Memory hooks system to ensure all components work together correctly.

## Features

### 1. **Hook Scripts Existence Check**
- Verifies all hook scripts exist in `.claude/hooks/scripts/`
- Checks executable permissions (Unix-like systems)
- Reports missing or inaccessible scripts

### 2. **Configuration Validation**
- Validates `.claude/settings.json` structure
- Checks all hook configurations are present
- Verifies environment variables (QDRANT_HOST, QDRANT_PORT, etc.)

### 3. **Docker Services Health Check**
- Tests Qdrant connectivity and collections
- Verifies Embedding service responsiveness
- Reports service status and configuration

### 4. **Individual Hook Tests**
- **SessionStart**: Tests memory retrieval with mock session data
- **PreToolUse**: Tests best practices retrieval before code modifications
- **PostToolUse**: Tests memory capture after tool usage
- **Error Capture**: Tests error pattern detection and storage

### 5. **Full Workflow Test**
- End-to-end workflow verification:
  - Store test memory → Generate embedding → Search memory → Verify retrieval
- Tests deduplication (prevents duplicate storage)
- Validates content hash matching

### 6. **Comprehensive Report**
- Color-coded test results (PASS/FAIL/WARN/SKIP)
- Detailed failure reasons
- Performance metrics (test duration)
- Critical vs non-critical failure detection

## Usage

### Basic Verification (All Tests)
```bash
python scripts/memory/verify_hooks_e2e.py
```

### Quick Check (Scripts + Config Only)
```bash
python scripts/memory/verify_hooks_e2e.py --quick
```
Skips Docker services and workflow tests. Useful for quick validation.

### Verbose Output
```bash
python scripts/memory/verify_hooks_e2e.py --verbose
```
Shows detailed information for each test including:
- File paths
- Configuration values
- Memory IDs and scores
- Hook output previews

### Offline Mode (Skip Docker Checks)
```bash
python scripts/memory/verify_hooks_e2e.py --skip-docker
```
Useful when Docker services are not available (laptop, CI without Docker, etc.)

### Combined Options
```bash
python scripts/memory/verify_hooks_e2e.py --verbose --skip-docker
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All checks passed |
| `1` | Some non-critical checks failed |
| `2` | Critical failures (Docker services down, core components broken) |

## Example Output

```
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║    BMAD Memory Module - Hooks System E2E Verification             ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

======================================================================
1. Hook Scripts Existence Check
======================================================================

✓ [PASS] Hooks directory
✓ [PASS] All hook scripts (8 scripts found)

======================================================================
2. Claude Code Settings Configuration
======================================================================

✓ [PASS] Settings file
✓ [PASS] Settings JSON (Valid JSON)
✓ [PASS] All hooks configured (5 hooks)

======================================================================
3. Docker Services Health Check
======================================================================

✓ [PASS] Qdrant service (localhost:26350, 3 collections)
✓ [PASS] Embedding service (localhost:28080)

======================================================================
Verification Report
======================================================================

Summary:
  Total tests:   15
  ✓ Passed:       15
  ✗ Failed:       0
  ⚠ Warnings:     0
  ○ Skipped:      0
  Duration:      2.34s

✓ ALL CHECKS PASSED
BMAD Memory hooks system is fully functional!
```

## Troubleshooting

### Script Not Found Errors
If you see "Script not found" errors:
1. Verify you're running from project root
2. Check that `.claude/hooks/scripts/` exists
3. Ensure all required scripts are present (see list below)

### Docker Service Failures
If Docker checks fail:
1. Start Docker services: `docker compose -f docker/docker-compose.yml up -d`
2. Wait 10-15 seconds for services to initialize
3. Verify ports are not in use: `netstat -an | grep 26350`
4. Use `--skip-docker` flag to bypass service checks

### Hook Execution Failures
If individual hook tests fail:
1. Check hook script has execute permissions: `chmod +x .claude/hooks/scripts/*.py`
2. Verify Python path: `which python3`
3. Check dependencies: `pip install -r requirements.txt`
4. Run hook manually: `echo '{}' | python3 .claude/hooks/scripts/session_start.py`

### Import Errors
If you see Python import errors:
1. Ensure `src/` directory exists
2. Verify `src/memory/` modules are present
3. Check PYTHONPATH: `export PYTHONPATH=$PWD/src:$PYTHONPATH`

## Required Hook Scripts

The verification script expects these files to exist:

```
.claude/hooks/scripts/
├── session_start.py              # SessionStart hook
├── session_stop.py               # Stop hook
├── pre_compact_save.py           # PreCompact hook
├── post_tool_capture.py          # PostToolUse (Edit/Write)
├── best_practices_retrieval.py   # PreToolUse (Edit/Write)
├── error_pattern_capture.py      # PostToolUse (Bash errors)
├── store_async.py                # Background storage for post_tool_capture
└── error_store_async.py          # Background storage for error_pattern_capture
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Verify Hooks System
  run: |
    python scripts/memory/verify_hooks_e2e.py --skip-docker
  continue-on-error: false
```

### Pre-commit Hook
```bash
#!/bin/bash
# .git/hooks/pre-commit
python scripts/memory/verify_hooks_e2e.py --quick
if [ $? -ne 0 ]; then
  echo "Hooks verification failed. Commit aborted."
  exit 1
fi
```

## What Gets Tested

### SessionStart Hook
- ✓ Parses JSON input from stdin
- ✓ Detects project context
- ✓ Searches agent-memory and best_practices collections
- ✓ Returns JSON with hookSpecificOutput
- ✓ Completes within timeout (10s)

### Best Practices Hook
- ✓ Extracts file path from tool_input
- ✓ Detects component/domain from path
- ✓ Searches best_practices collection
- ✓ Formats output for Claude context
- ✓ Completes within timeout (10s)

### PostToolUse Capture Hook
- ✓ Parses tool input (Edit/Write)
- ✓ Extracts implementation content
- ✓ Forks background storage process
- ✓ Returns immediately (non-blocking)
- ✓ Exit code 0 (graceful degradation)

### Error Pattern Capture Hook
- ✓ Detects errors in tool_result
- ✓ Extracts error patterns
- ✓ Forks background storage
- ✓ Handles various error formats
- ✓ Exit code 0 (graceful degradation)

### Full Workflow
- ✓ Store → Embedding → Search → Retrieve
- ✓ Deduplication prevents duplicates
- ✓ Content hash matching works
- ✓ Group ID filtering works
- ✓ Memory searchable within seconds

## Related Documentation

- [CLAUDE.md](../../CLAUDE.md) - Project overview and coding conventions
- [TROUBLESHOOTING.md](../../TROUBLESHOOTING.md) - Common issues and solutions
- [docs/claude-code-hooks-best-practices.md](../../docs/claude-code-hooks-best-practices.md) - Hook configuration guide
- [docs/structured-logging.md](../../docs/structured-logging.md) - Logging patterns
