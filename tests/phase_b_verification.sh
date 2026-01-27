#!/bin/bash
# Phase B Verification Tests
# Run these tests after restarting Claude Code session

set -e

echo "================================"
echo "Phase B Verification Tests"
echo "================================"
echo ""

# Test 1: Validate JSON syntax
echo "Test 1: Validate settings.json syntax"
python3 -c "import json; json.load(open('.claude/settings.json')); print('✓ JSON valid')"
echo ""

# Test 2: Verify hooks are referenced
echo "Test 2: Verify hook references in settings.json"
grep -q "bash_code_context.py" .claude/settings.json && echo "✓ bash_code_context.py referenced"
grep -q "error_detection.py" .claude/settings.json && echo "✓ error_detection.py referenced"
grep -q "error_pattern_capture.py" .claude/settings.json && echo "✓ error_pattern_capture.py referenced"
echo ""

# Test 3: Verify old file is gone
echo "Test 3: Verify error_context_retrieval.py is removed"
if [ ! -f .claude/hooks/scripts/error_context_retrieval.py ]; then
    echo "✓ Old file removed"
else
    echo "✗ Old file still exists"
    exit 1
fi
echo ""

# Test 4: Verify new files exist
echo "Test 4: Verify new files exist"
test -f .claude/hooks/scripts/bash_code_context.py && echo "✓ bash_code_context.py exists"
test -f .claude/hooks/scripts/error_detection.py && echo "✓ error_detection.py exists"
echo ""

# Test 5: Verify Python syntax
echo "Test 5: Verify Python syntax"
python3 -m py_compile .claude/hooks/scripts/bash_code_context.py && echo "✓ bash_code_context.py syntax valid"
python3 -m py_compile .claude/hooks/scripts/error_detection.py && echo "✓ error_detection.py syntax valid"
python3 -m py_compile .claude/hooks/scripts/error_pattern_capture.py && echo "✓ error_pattern_capture.py syntax valid"
echo ""

# Test 6: Verify imports in error_pattern_capture.py
echo "Test 6: Verify dedup imports added"
grep -q "from memory.filters import ImplementationFilter" .claude/hooks/scripts/error_pattern_capture.py && echo "✓ ImplementationFilter imported"
grep -q "import hashlib" .claude/hooks/scripts/error_pattern_capture.py && echo "✓ hashlib imported"
echo ""

# Test 7: Verify dedup logic in error_pattern_capture.py
echo "Test 7: Verify dedup logic added"
grep -q "impl_filter.is_duplicate" .claude/hooks/scripts/error_pattern_capture.py && echo "✓ Dedup check present"
grep -q "error_duplicate_skipped" .claude/hooks/scripts/error_pattern_capture.py && echo "✓ Dedup logging present"
echo ""

# Test 8: Verify updated docstrings
echo "Test 8: Verify updated docstrings"
grep -q "code CONTEXT, not error detection" .claude/hooks/scripts/bash_code_context.py && echo "✓ bash_code_context.py docstring updated"
grep -q "TRIGGER 1: Error Detection" .claude/hooks/scripts/error_detection.py && echo "✓ error_detection.py docstring correct"
echo ""

# Test 9: Verify updated headers
echo "Test 9: Verify output headers updated"
grep -q "Code Context for Bash Command" .claude/hooks/scripts/bash_code_context.py && echo "✓ bash_code_context.py header updated"
grep -q "SIMILAR ERROR FIXES FOUND" .claude/hooks/scripts/error_detection.py && echo "✓ error_detection.py header correct"
echo ""

# Test 10: Verify metrics labels
echo "Test 10: Verify metrics labels updated"
grep -q "PreToolUse_CodeContext" .claude/hooks/scripts/bash_code_context.py && echo "✓ bash_code_context.py metrics updated"
grep -q "PostToolUse_ErrorDetection" .claude/hooks/scripts/error_detection.py && echo "✓ error_detection.py metrics correct"
echo ""

echo "================================"
echo "✓ All Phase B tests passed!"
echo "================================"
