#!/bin/bash
# Phase B Functional Tests
# Run these tests in a fresh Claude Code session to verify hook behavior

set -e

echo "================================"
echo "Phase B Functional Tests"
echo "================================"
echo ""

# Test 1: Seed test error_fix memory
echo "Test 1: Seed test error_fix memory"
python3 -c "
from memory.storage import MemoryStorage
from memory.config import get_config, COLLECTION_CODE_PATTERNS

config = get_config()
storage = MemoryStorage(config)

storage.store(
    content='Error: ModuleNotFoundError - Fix: pip install missing-module',
    collection=COLLECTION_CODE_PATTERNS,
    group_id='ai-memory-module',
    memory_type='error_fix',
    metadata={'error_signature': 'ModuleNotFoundError'}
)
storage.close()
print('✓ Test error_fix memory seeded')
"
echo ""

# Test 2: Test bash_code_context.py (PreToolUse)
echo "Test 2: Test bash_code_context.py (direct invocation)"
echo '{"tool_name":"Bash","tool_input":{"command":"python3 src/memory/config.py"},"cwd":"'$(pwd)'","session_id":"test123"}' | \
    AI_MEMORY_INSTALL_DIR=$(pwd) python3 .claude/hooks/scripts/bash_code_context.py 2>&1 | \
    head -20
echo "✓ bash_code_context.py executed (check output above)"
echo ""

# Test 3: Test error_detection.py with simulated error
echo "Test 3: Test error_detection.py (simulated error)"
echo '{"tool_name":"Bash","tool_input":{"command":"python3 broken.py"},"tool_response":{"output":"Traceback (most recent call last):\n  File \"broken.py\", line 1\nModuleNotFoundError: No module named foo","exitCode":1},"cwd":"'$(pwd)'","session_id":"test123"}' | \
    AI_MEMORY_INSTALL_DIR=$(pwd) python3 .claude/hooks/scripts/error_detection.py 2>&1 | \
    head -30
echo "✓ error_detection.py executed (should show 'SIMILAR ERROR FIXES FOUND' if seeded memory exists)"
echo ""

# Test 4: Test dedup in error_pattern_capture.py
echo "Test 4: Test dedup in error_pattern_capture.py"
ERROR_INPUT='{"tool_name":"Bash","tool_input":{"command":"python3 fail.py"},"tool_response":{"output":"Error: test error","exitCode":1},"cwd":"'$(pwd)'","session_id":"test123"}'

echo "First invocation (should store):"
echo "$ERROR_INPUT" | AI_MEMORY_INSTALL_DIR=$(pwd) python3 .claude/hooks/scripts/error_pattern_capture.py 2>&1 | grep -E "error_pattern_forked|error_duplicate_skipped" || echo "Check logs manually"

sleep 2

echo "Second invocation (should skip due to dedup):"
echo "$ERROR_INPUT" | AI_MEMORY_INSTALL_DIR=$(pwd) python3 .claude/hooks/scripts/error_pattern_capture.py 2>&1 | grep -E "error_pattern_forked|error_duplicate_skipped" || echo "Check logs manually"
echo ""

echo "================================"
echo "Functional tests complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Restart Claude Code session to reload hooks"
echo "2. Run a bash command that references a file (e.g., 'python3 src/memory/config.py')"
echo "   - Should see 'Code Context for Bash Command' output from bash_code_context.py"
echo "3. Run a bash command that fails (e.g., 'python3 nonexistent.py')"
echo "   - Should see 'SIMILAR ERROR FIXES FOUND' output from error_detection.py"
echo "   - Should see error captured in logs from error_pattern_capture.py"
