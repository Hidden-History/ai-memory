# Multi-IDE Support

AI-Memory works with multiple AI coding tools through a unified adapter layer. Memories created in one IDE are available in all others — your project knowledge is shared across tools.

## Supported IDEs

| IDE | Status | Hook Events | Config Location |
|-----|--------|-------------|-----------------|
| **Claude Code** | Stable (v2.0+) | All 6 events | `.claude/settings.json` |
| **Gemini CLI** | Beta | SessionStart, AfterTool, PreCompress | `.gemini/settings.json` |
| **Cursor IDE** | Beta | sessionStart, postToolUse, preCompact | `.cursor/hooks.json` |
| **Codex CLI** | Beta | SessionStart, PostToolUse, UserPromptSubmit, Stop | `.codex/hooks.json` |

## How It Works

All four IDEs feed into the same memory pipeline through a **canonical event schema**:

```
Your IDE (Claude/Gemini/Cursor/Codex)
    |
    v
IDE-specific adapter (normalizes events)
    |
    v
Canonical event schema (shared format)
    |
    v
Existing pipeline (store, embed, classify)
    |
    v
Qdrant vector database (shared memory)
```

Each IDE has its own adapter scripts that:
1. Read the native hook payload from stdin
2. Normalize it to the canonical event format
3. Fork to the background storage pipeline
4. Return quickly so the IDE is not blocked

The Claude Code hooks are **unchanged** — they work exactly as before. The adapter layer is purely additive.

## Installation

### Automatic (Recommended)

The installer auto-detects installed IDEs and generates configs:

```bash
./scripts/install.sh <your-project-dir>
```

During installation, you'll see:
```
[INFO] Configuring additional IDE support: gemini cursor codex
[SUCCESS] Gemini CLI config written to /path/to/project/.gemini/settings.json
[SUCCESS] Cursor IDE config written to /path/to/project/.cursor/hooks.json
[SUCCESS] Codex CLI config written to /path/to/project/.codex/hooks.json
```

### Manual IDE Selection

Override auto-detection with the `--ide` flag:

```bash
# Configure specific IDEs only
./scripts/install.sh --ide gemini,cursor <your-project-dir>

# Skip all non-Claude IDE config
./scripts/install.sh --ide none <your-project-dir>

# Force overwrite existing IDE configs
./scripts/install.sh --force <your-project-dir>
```

### Adding IDEs to an Existing Installation

Re-run the installer with Option 1 (Add project to existing installation). IDE detection runs automatically and will configure any newly detected IDEs.

## IDE-Specific Details

### Gemini CLI

**Config file**: `.gemini/settings.json`

Gemini CLI hooks map to canonical events:
- `SessionStart` -> memory retrieval injected via `hookSpecificOutput.additionalContext`
- `AfterTool` (edit_file, write_file, MCP tools) -> code pattern capture
- `AfterTool` (run_shell_command) -> error detection + pattern capture
- `PreCompress` -> session summary save

**Commands**: TOML command templates are deployed to `.gemini/commands/`:
- `search-memory` — search project memories
- `memory-status` — check memory system health
- `save-memory` — manually save a memory

### Cursor IDE

**Config file**: `.cursor/hooks.json`

Cursor hooks map to canonical events:
- `sessionStart` -> memory retrieval injected via `additional_context`
- `postToolUse` (Write, Edit, MCP tools) -> code pattern capture
- `postToolUse` (Shell) -> error detection + pattern capture
- `preCompact` -> session summary save

**Skills**: SKILL.md templates are deployed to `.cursor/skills/`:
- `search-memory/SKILL.md`
- `memory-status/SKILL.md`
- `save-memory/SKILL.md`

### Codex CLI

**Config file**: `.codex/hooks.json`

Codex hooks map to canonical events:
- `SessionStart` -> memory retrieval injected via `hookSpecificOutput.systemMessage`
- `PostToolUse` (Bash only) -> error detection + pattern capture
- `UserPromptSubmit` -> per-turn context injection
- `Stop` -> session summary save

**Note**: Codex only supports Bash tool for PostToolUse — no Write/Edit hooks (platform limitation).

**Skills**: SKILL.md templates are deployed to both `.agents/skills/` and `.codex/skills/`.

## Canonical Event Schema

All adapters normalize events to this format:

```python
{
    "session_id": "string",        # Unique session identifier
    "cwd": "string",               # Working directory
    "hook_event_name": "string",   # Canonical event name (e.g., "PostToolUse")
    "ide_source": "string",        # "claude", "gemini", "cursor", "codex"
    "tool_name": "string | None",  # Canonical tool name (e.g., "Edit", "Bash")
    "tool_input": "dict | None",   # Tool input parameters
    "tool_response": "any | None", # Tool output/response
    "transcript_path": "str|None", # Session transcript location
    "user_prompt": "str | None",   # User message (UserPromptSubmit only)
    "trigger": "str | None",       # What triggered this event
    "is_background_agent": "bool", # Skip retrieval for background agents
}
```

### Event Name Mapping

| Canonical Name | Claude Code | Gemini CLI | Cursor | Codex |
|---------------|-------------|------------|--------|-------|
| `SessionStart` | SessionStart | SessionStart | sessionStart | SessionStart |
| `PostToolUse` | PostToolUse | AfterTool | postToolUse | PostToolUse |
| `PreToolUse` | PreToolUse | BeforeTool | preToolUse | - |
| `UserPromptSubmit` | UserPromptSubmit | BeforeAgent | beforeSubmitPrompt | UserPromptSubmit |
| `PreCompact` | PreCompact | PreCompress | preCompact | - |
| `Stop` | Stop | SessionEnd | stop | Stop |

### Tool Name Mapping

| Canonical Name | Claude Code | Gemini CLI | Cursor | Codex |
|---------------|-------------|------------|--------|-------|
| `Edit` | Edit | edit_file | Edit | - |
| `Write` | Write | write_file / create_file | Write | - |
| `Bash` | Bash | run_shell_command | Shell | Bash |
| `Read` | Read | - | Read | - |

MCP tools are normalized across all IDEs:
- Gemini: `mcp_server_tool` -> `mcp:server:tool`
- Cursor: `MCP:tool` -> `mcp:unknown:tool`

## Troubleshooting

### IDE not detected during installation
- Ensure the IDE CLI is in your PATH (`gemini`, `codex`, `agent`/`cursor-agent`)
- Use `--ide gemini,cursor` to skip detection and force configuration

### Hooks not firing
- Check that the config file exists (`.gemini/settings.json`, `.cursor/hooks.json`, etc.)
- Verify the Python path in the config points to your ai-memory venv: `~/.ai-memory/.venv/bin/python`
- Check stderr output for adapter errors (adapters log to stderr, not stdout)

### Memories not appearing across IDEs
- All IDEs share the same Qdrant collections — memories should be visible immediately
- Verify the `AI_MEMORY_PROJECT_ID` matches across IDE configs
- Check that Docker services (Qdrant, embedding) are running: `cd ~/.ai-memory/docker && docker compose ps`

## Architecture Reference

This multi-IDE support follows the **Strangler Fig + Provider Adapter** pattern documented in [BP-119](../oversight/knowledge/best-practices/BP-119-multi-ide-adapter-plugin-patterns-cli-tools-2026.md). Key design decisions:

- Claude Code hooks stay in `.claude/hooks/scripts/` (never moved)
- New IDE adapters live in `src/memory/adapters/{gemini,cursor,codex}/`
- Shared schema at `src/memory/adapters/schema.py`
- Each adapter is independently deployable and testable
- Graceful degradation: all adapters exit 0 on any error, logging to stderr
