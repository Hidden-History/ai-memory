# Archived Hooks

This directory contains hooks that have been deprecated and replaced by better implementations.

## Deprecation History

### session_stop.py (Archived: 2026-01-17)

**Reason**: Duplicated PreCompact functionality. Superseded by Claude Agent SDK integration.

**Original Purpose**: Captured session summaries at Stop hook and stored to `discussions` collection.

**Problems Identified**:
- Duplicated PreCompact hook functionality (created noise and duplicate memories)
- User preferred manual `/save-memory` skill over automatic session saves
- Stop hook executed on every exit, creating redundant session summaries

**Replacement Strategy**:
- **PreCompact hook** (`pre_compact_save.py`): Automatic session saves before context compaction with full transcript analysis
- **Claude Agent SDK** (`src/memory/agent_sdk_wrapper.py`): Direct message stream access for agent response capture (Stop hook integration, lines 397-474)
- **/save-memory skill**: Manual on-demand session saves when user explicitly requests

**Key Improvements in Replacement**:
- SDK provides real-time capture via message stream (no file parsing)
- Better error handling and retry logic
- Integrated fire-and-forget storage pattern
- No timing issues or synchronization problems

**Migration Path**: Projects using SDK wrapper get automatic agent response capture. No configuration needed.

**Timeline**:
- 2026-01-17: TECH-DEBT-012 - Archived original, replaced with placeholder
- 2026-01-21: TECH-DEBT-035 Phase 5.1 - Removed placeholder, documented deprecation

**Reference**:
- Phase 5 Audit: `oversight/specs/tech-debt-035/phase-5-hook-inventory.md` (lines 458-476)
- SDK Wrapper: `src/memory/agent_sdk_wrapper.py`
- PreCompact Hook: `.claude/hooks/scripts/pre_compact_save.py`

---

## Archive Maintenance

**Do Not Delete**: This directory preserves historical implementations for:
- Reference and comparison
- Rollback capability if needed
- Understanding evolution of memory capture patterns
- Debugging legacy behavior

**Structure**:
```
archived/
├── README.md (this file)
└── session_stop.py (original implementation before deprecation)
```
