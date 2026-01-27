# ARCHIVED: 2026-01-23 - Replaced by SDK wrapper

## Scripts
- post_tool_capture.py (342 lines) - PostToolUse Edit|Write|NotebookEdit
- store_async.py (506 lines) - Background worker
- error_pattern_capture.py (424 lines) - PostToolUse Bash
- error_store_async.py (449 lines) - Background worker

## SDK Replacement
**SDK Component:** AgentSDKWrapper._post_tool_use_hook()
**SDK Lines:** 315-395 in src/memory/agent_sdk_wrapper.py
**Functional Equivalent:** Yes
**Coverage:** 100% for core functionality

### Implementation Capture (post_tool_capture.py)
- SDK lines 325-336: Captures Write/Edit → IMPLEMENTATION → code-patterns
- SDK validates tool success before storage
- SDK uses fire-and-forget background pattern

### Error Capture (error_pattern_capture.py)
- SDK lines 337-354: Detects Bash errors (exit_code != 0) → ERROR_FIX
- SDK checks explicit error field
- SDK extracts command and result

### Background Storage (store_async.py, error_store_async.py)
- SDK lines 476-570: _store_memory_background()
- Same deduplication (content_hash)
- Same zero-vector immediate storage
- Same uuid5 deterministic IDs

## Reason for Deprecation
The Agent SDK wrapper provides equivalent capture functionality:
1. **PostToolUse Hook:** Matches on tool names (Write, Edit, NotebookEdit, Bash)
2. **Pattern Extraction:** SDK handles language detection, file paths, content formatting
3. **Error Detection:** SDK checks exit_code and error fields
4. **Async Storage:** SDK uses asyncio.create_task() for background storage
5. **Deduplication:** SDK checks content_hash before storage

## Validation
**Phase:** TECH-DEBT-035 Phase 5.2.2
**Status:** SDK proven equivalent in Phase 3-4 testing (85 tests passing)
**Data Loss:** 0% - SDK uses identical storage logic
**Pattern Quality:** 100% - SDK uses same extraction patterns

## Rollback Procedure
```bash
# 1. Restore files
mv .claude/hooks/scripts/_archived/code_capture/*.py .claude/hooks/scripts/

# 2. Re-add to settings.json PostToolUse hooks:
"PostToolUse": [
  {
    "matcher": "Edit|Write|NotebookEdit",
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$BMAD_INSTALL_DIR/.claude/hooks/scripts/post_tool_capture.py\""
      }
    ]
  },
  {
    "matcher": "Bash",
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$BMAD_INSTALL_DIR/.claude/hooks/scripts/error_pattern_capture.py\""
      },
      {
        "type": "command",
        "command": "python3 \"$BMAD_INSTALL_DIR/.claude/hooks/scripts/error_detection.py\"",
        "timeout": 2000
      }
    ]
  }
]

# 3. Restart Claude Code session
```

## Git History
**Deprecation Commit:** chore(hooks): TECH-DEBT-035 Phase 5 - Archive deprecated V1.0 hooks
**Archive Location:** .claude/hooks/scripts/_archived/code_capture/

## References
- TECH-DEBT-035 Phase 5: Hook deprecation plan
- Phase 5 Inventory: oversight/specs/tech-debt-035/phase-5-hook-inventory.md
- SDK Implementation: src/memory/agent_sdk_wrapper.py lines 315-395, 476-570
