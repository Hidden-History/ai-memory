# ARCHIVED: 2026-01-23 - Replaced by SDK wrapper

## Scripts
- agent_response_capture.py (414 lines)
- agent_response_store_async.py (307 lines)

## SDK Replacement
**SDK Component:** AgentSDKWrapper._stop_hook()
**SDK Lines:** 397-437 in src/memory/agent_sdk_wrapper.py
**Functional Equivalent:** Yes
**Coverage:** 100% - SDK reads message stream directly, no transcript parsing needed

## Reason for Deprecation
The Agent SDK wrapper provides identical functionality via the Stop hook:
- Reads transcript_path from hook input
- Extracts last assistant message
- Stores as AGENT_RESPONSE → discussions collection
- Fire-and-forget background storage
- Built-in retry logic (superior to file-based)

## Validation
**Phase:** TECH-DEBT-035 Phase 5.2.1
**Status:** SDK proven equivalent in Phase 3-4 testing (85 tests passing)
**Data Loss:** 0% - SDK uses same content_hash deduplication

## Rollback Procedure
```bash
# 1. Restore files
mv .claude/hooks/scripts/_archived/agent_response/*.py .claude/hooks/scripts/

# 2. Re-add to settings.json Stop hook:
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$BMAD_INSTALL_DIR/.claude/hooks/scripts/agent_response_capture.py\""
      }
    ]
  }
]

# 3. Restart Claude Code session
```

## Git History
**Deprecation Commit:** chore(hooks): TECH-DEBT-035 Phase 5 - Archive deprecated V1.0 hooks
**Archive Location:** .claude/hooks/scripts/_archived/agent_response/

## References
- TECH-DEBT-035 Phase 5: Hook deprecation plan
- Phase 5 Inventory: oversight/specs/tech-debt-035/phase-5-hook-inventory.md
- SDK Implementation: src/memory/agent_sdk_wrapper.py lines 397-437
