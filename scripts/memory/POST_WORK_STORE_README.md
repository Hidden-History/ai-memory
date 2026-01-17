# Post-Work Memory Storage Hook

BMAD workflow hook for storing implementation memories after story completion or significant work milestones.

## Overview

The `post-work-store.py` script provides a non-blocking way to capture implementation memories from BMAD workflows. It validates content and metadata, checks for duplicates, and forks to a background process for actual storage.

## Features

- ✅ **Pre-Storage Validation** - Uses `validate_storage.py` patterns
- ✅ **Duplicate Detection** - Uses `check_duplicates.py` logic (hash + semantic)
- ✅ **File:Line References** - Validates actionable memory patterns
- ✅ **Background Storage** - Forks async process (non-blocking)
- ✅ **Graceful Degradation** - Queues on failure
- ✅ **Prometheus Metrics** - Instrumented for monitoring

## Usage

### Basic Usage (Background Mode - Recommended)

```bash
# Via file
python post-work-store.py \
  --content-file content.txt \
  --metadata-file metadata.json

# Via stdin
echo "Implementation content..." | \
  python post-work-store.py \
  --metadata '{"type":"implementation", "group_id":"my-project", ...}'
```

### Synchronous Mode (Testing)

```bash
python post-work-store.py \
  --content-file content.txt \
  --metadata-file metadata.json \
  --sync
```

### Skip Validation/Duplicate Check

```bash
# Skip validation (not recommended)
python post-work-store.py \
  --content-file content.txt \
  --metadata-file metadata.json \
  --skip-validation

# Skip duplicate check (faster but may create duplicates)
python post-work-store.py \
  --content-file content.txt \
  --metadata-file metadata.json \
  --skip-duplicate-check
```

## Metadata Schema

Required fields:

```json
{
  "type": "implementation",              // Memory type (see Valid Types below)
  "group_id": "project-name",           // Project identifier
  "source_hook": "manual",              // Hook source (see Valid Hooks below)
  "session_id": "workflow-123",         // Session identifier
  "cwd": "/path/to/project"             // Working directory for project detection
}
```

Recommended fields (BMAD enrichment):

```json
{
  "agent": "dev",                       // BMAD agent (dev, architect, pm, etc.)
  "component": "memory-storage",        // System component
  "story_id": "STORY-123",              // Story identifier
  "importance": "medium"                // critical, high, medium, low
}
```

### Valid Memory Types

- `implementation` - Code implementations
- `architecture_decision` - Architectural decisions
- `story_outcome` - Story completion summaries
- `error_pattern` - Error handling patterns
- `database_schema` - Database schemas
- `config_pattern` - Configuration patterns
- `integration_example` - Integration examples
- `best_practice` - Best practices
- `session_summary` - Session summaries
- `chat_memory` - Chat memories
- `agent_decision` - Agent decisions

### Valid Source Hooks

- `manual` - Skill-based or workflow-driven storage (RECOMMENDED)
- `PostToolUse` - After Edit/Write tools
- `Stop` - Session end
- `SessionStart` - Session start
- `seed_script` - Seed scripts

## Content Requirements

### Minimum Requirements

- **Length**: 50-50,000 characters
- **Token Budget**: <1,200 tokens per shard
- **File:Line References**: REQUIRED for implementation types (format: `file.py:10-20`)

### Example Content

```text
Implementation: Post-Work Memory Storage for BMAD Workflows

Created scripts/memory/post-work-store.py:1-400 - Main entry point
- Accepts content via stdin or --content-file
- Validates using validate_storage.py patterns
- Forks to background for non-blocking storage

Key patterns:
- subprocess.Popen with start_new_session=True (post-work-store.py:150-170)
- validate_before_storage() integration (post-work-store.py:250-270)
```

## Exit Codes

- `0` - Success (validation passed, forked to background)
- `1` - Validation failed or critical error

## BMAD Workflow Integration

### Example: Store After Story Completion

```bash
#!/bin/bash
# In your BMAD workflow script

STORY_ID="AUTH-12"
AGENT="dev"

# Capture implementation summary
cat > /tmp/impl_summary.txt << EOF
Implementation: OAuth2 Authentication Integration

Created src/auth/oauth2.py:1-150 - OAuth2 client implementation
- Implements authorization code flow
- Token refresh handling
- Secure token storage

Tests: tests/auth/test_oauth2.py:1-200
- Unit tests for OAuth2 client
- Integration tests with mock provider
EOF

# Prepare metadata
cat > /tmp/impl_metadata.json << EOF
{
  "type": "implementation",
  "group_id": "$PROJECT_NAME",
  "source_hook": "manual",
  "session_id": "workflow-$(date +%s)",
  "agent": "$AGENT",
  "component": "auth",
  "story_id": "$STORY_ID",
  "importance": "high",
  "cwd": "$(pwd)"
}
EOF

# Store memory (non-blocking)
python3 ~/.bmad-memory/scripts/memory/post-work-store.py \
  --content-file /tmp/impl_summary.txt \
  --metadata-file /tmp/impl_metadata.json

echo "✅ Memory storage initiated"
```

## Validation Patterns

The script validates:

1. **Metadata Structure** - Required fields present and valid
2. **Content Quality** - Length, token budget, placeholder text
3. **File:Line References** - Present for implementation types
4. **Code Snippets** - 3-10 lines optimal
5. **Duplicates** - Hash + semantic similarity check (>0.85)

## Performance

- **Validation Phase**: <3ms
- **Fork Overhead**: <10ms
- **Total Hook Time**: <500ms (NFR-P1 compliant)
- **Background Storage**: No blocking (fork pattern)

## Graceful Degradation

- **Embedding Service Down**: Stores with "pending" status + zero vector
- **Qdrant Unavailable**: Queues to `./.memory_queue/` for retry
- **Validation Failure**: Exits with code 1, does not store

## Monitoring

Prometheus metrics exposed (if enabled):

- `memory_captures_total{hook_type,status,project}` - Capture attempts
- `deduplication_events_total{project}` - Duplicates detected
- `failure_events_total{component,error_code}` - Failures

## Troubleshooting

### "Validation failed: Missing required fields"

Ensure metadata has: `type`, `group_id`, `source_hook`

### "Invalid source_hook"

Use one of: `manual`, `PostToolUse`, `Stop`, `SessionStart`, `seed_script`

### "Missing file:line references"

For implementation types, add references like: `src/file.py:10-20`

### "Duplicate detected"

Content already exists. Use `--skip-duplicate-check` to force storage (not recommended)

## Related Scripts

- `validate_storage.py` - Pre-storage validation
- `check_duplicates.py` - Duplicate detection
- `post_work_store_async.py` - Background storage handler (auto-called)

## Files

```
scripts/memory/
├── post-work-store.py           # Main entry point
├── post_work_store_async.py     # Background storage handler
├── validate_storage.py          # Validation patterns
└── check_duplicates.py          # Duplicate detection
```

## Created

2026-01-17 - Following patterns from existing BMAD memory hooks
