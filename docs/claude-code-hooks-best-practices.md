# Claude Code Hooks Best Practices (2026)

This document captures best practices for implementing Claude Code hooks, based on official documentation and extensive debugging experience from the AI Memory Module project.

## Table of Contents

1. [Hook Configuration Structure](#hook-configuration-structure)
2. [SessionStart Hooks](#sessionstart-hooks)
3. [PostToolUse Hooks](#posttooluse-hooks)
4. [Stop Hooks](#stop-hooks)
5. [Hook Output Formats](#hook-output-formats)
6. [Environment Variables](#environment-variables)
7. [Settings File Locations](#settings-file-locations)
8. [Common Pitfalls](#common-pitfalls)
9. [Debugging Hooks](#debugging-hooks)
10. [Known Issues and Workarounds](#known-issues-and-workarounds)
11. [Troubleshooting Checklist](#troubleshooting-checklist)

---

## Hook Configuration Structure

Hooks are configured in `settings.json` files. The structure varies by hook type.

### General Structure

```json
{
  "hooks": {
    "HookEventName": [
      {
        "matcher": "pattern",
        "hooks": [
          {
            "type": "command",
            "command": "your-command-here",
            "timeout": 60000
          }
        ]
      }
    ]
  }
}
```

### Key Points

- Each hook event contains an **array** of hook configurations
- Each configuration has a `hooks` array with the actual commands
- The `matcher` field is **required** for some hook types
- `timeout` is optional (default: 60000ms / 60 seconds)

---

## SessionStart Hooks

**CRITICAL: SessionStart hooks REQUIRE a `matcher` field.**

### Available Matchers

| Matcher | Triggers When |
|---------|---------------|
| `startup` | New session starts |
| `resume` | Session resumed via `--resume`, `--continue`, or `/resume` |
| `clear` | After `/clear` command |
| `compact` | After auto or manual context compaction |

### Correct Configuration (Recommended: Pipe-Separated Matchers)

**IMPORTANT**: Use pipe-separated matchers in a single entry rather than separate entries per matcher. This format is more reliable and ensures hooks appear correctly in the `/hooks` menu.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/session_start.py",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

### Alternative: Separate Entries (Less Reliable)

This format may cause issues with hook registration:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/session_start.py"
          }
        ]
      },
      {
        "matcher": "resume",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/session_start.py"
          }
        ]
      },
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/session_start.py"
          }
        ]
      }
    ]
  }
}
```

### Input Schema

SessionStart hooks receive JSON via stdin:

```typescript
type SessionStartHookInput = {
  hook_event_name: 'SessionStart';
  session_id: string;
  cwd: string;
  transcript_path: string;
  permission_mode: 'default' | 'plan' | 'acceptEdits' | 'dontAsk' | 'bypassPermissions';
  source: 'startup' | 'resume' | 'clear' | 'compact';
}
```

### Output Format

SessionStart hooks should output JSON to stdout:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Your context string here"
  }
}
```

**Important**: The `additionalContext` is added to Claude's context but is **NOT displayed** to the user in the UI. Use `CTRL+R` (transcript mode) to view hook output.

### Special Environment Variable

`CLAUDE_ENV_FILE` - Only available for SessionStart hooks. Provides a file path where you can persist environment variables for subsequent bash commands.

---

## PostToolUse Hooks

PostToolUse hooks trigger after Claude uses a tool.

### Matcher Pattern

The `matcher` field uses regex to match tool names:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/post_tool_capture.py"
          }
        ]
      }
    ]
  }
}
```

### Input Schema

```typescript
type PostToolUseHookInput = {
  hook_event_name: 'PostToolUse';
  session_id: string;
  cwd: string;
  tool_name: string;
  tool_input: object;
  tool_response: object;
}
```

### Key Insight: Tool Response Validation

**Claude Code does NOT send `success: true` in tool_response.**

Success is indicated by:
- Presence of `filePath` field (for Write/Edit operations)
- Absence of `error` field
- Presence of expected content in response

```python
# CORRECT validation
tool_response = data.get("tool_response", {})
if "error" in tool_response:
    return "tool_had_error"
if not tool_response.get("filePath"):
    return "missing_file_path"

# WRONG - This field doesn't exist
# if not tool_response.get("success"):
```

---

## Stop Hooks

Stop hooks trigger when a session ends.

### Configuration

Stop hooks do NOT require a matcher:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/activity_logger.py"
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/agent_response_capture.py"
          }
        ]
      }
    ]
  }
}
```

### Input Schema

```typescript
type StopHookInput = {
  hook_event_name: 'Stop';
  session_id: string;
  cwd: string;
  transcript_path: string;
  stop_hook_active: boolean;
}
```

---

## Hook Output Formats

### Two Ways to Add Context

1. **Plain text stdout** (simpler)
   - Any non-JSON text written to stdout is added as context
   - Shown in transcript mode

2. **JSON with additionalContext** (structured)
   - More control over what goes into context
   - Added more discretely

### JSON Output Structure

```json
{
  "decision": "block",
  "reason": "Explanation for blocking",
  "hookSpecificOutput": {
    "hookEventName": "HookEventName",
    "additionalContext": "Context string"
  }
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - stdout added to context (SessionStart/UserPromptSubmit) or shown in transcript (others) |
| 2 | Block - Show reason to Claude, block the action |
| Other | Error - Hook failed, logged but doesn't block |

---

## Environment Variables

### Available to All Hooks

| Variable | Description |
|----------|-------------|
| `CLAUDE_PROJECT_DIR` | Absolute path to project root |
| `CLAUDE_CODE_REMOTE` | "true" if running remotely, empty if local |

### SessionStart Only

| Variable | Description |
|----------|-------------|
| `CLAUDE_ENV_FILE` | File path for persisting env vars |

### Using in Commands

```json
{
  "command": "cd $CLAUDE_PROJECT_DIR && python3 scripts/hook.py"
}
```

---

## Settings File Locations

### Hierarchy (lower overrides higher)

1. **User settings**: `~/.claude/settings.json`
   - Applies to all projects

2. **Project settings**: `.claude/settings.json`
   - Checked into source control
   - Shared with team

3. **Local settings**: `.claude/settings.local.json`
   - Not checked into source control
   - Personal overrides

### Recommendation

For hooks that should apply globally, configure in `~/.claude/settings.json`. For project-specific hooks, use `.claude/settings.json` in the project.

---

## Common Pitfalls

### 1. Missing Matcher for SessionStart

**Wrong:**
```json
{
  "SessionStart": [
    {
      "hooks": [{ "type": "command", "command": "..." }]
    }
  ]
}
```

**Right:**
```json
{
  "SessionStart": [
    {
      "matcher": "startup",
      "hooks": [{ "type": "command", "command": "..." }]
    }
  ]
}
```

### 2. Expecting tool_response.success

The `success` field doesn't exist. Check for `filePath` or absence of `error`.

### 3. Expecting SessionStart Output to Display

SessionStart output goes to context, not display. Use `CTRL+R` to see it.

### 4. Plain Text vs JSON Output

If outputting JSON, ensure it's valid. Invalid JSON may be treated as plain text or cause errors.

### 5. Blocking Hook Path

Don't do heavy processing in hooks. Use fork pattern for async work:

```python
subprocess.Popen([sys.executable, "async_worker.py", json.dumps(data)],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sys.exit(0)  # Return immediately
```

### 6. Using Relative Paths

**Always use absolute paths** in hook commands. Relative paths may not resolve correctly.

**Wrong:**
```json
{
  "command": ".claude/hooks/scripts/session_start.py"
}
```

**Right:**
```json
{
  "command": "python3 /home/user/project/.claude/hooks/scripts/session_start.py"
}
```

### 7. Wrong Environment Variables for AI Memory

For AI Memory Module, use separate host/port variables, NOT URL strings:

**Wrong:**
```json
{
  "env": {
    "QDRANT_URL": "http://localhost:6333"
  }
}
```

**Right:**
```json
{
  "env": {
    "QDRANT_HOST": "localhost",
    "QDRANT_PORT": "26350",
    "EMBEDDING_HOST": "localhost",
    "EMBEDDING_PORT": "28080"
  }
}
```

### 8. Missing Timeout for SessionStart

SessionStart hooks should include a timeout to prevent hanging:

```json
{
  "matcher": "startup|resume|compact",
  "hooks": [
    {
      "type": "command",
      "command": "python3 /path/to/hook.py",
      "timeout": 30000
    }
  ]
}
```

---

## Debugging Hooks

### 1. Use /hooks Command

```
/hooks
```

Shows configured hooks and their status.

### 2. Use --debug Flag

```bash
claude --debug
```

Verbose output showing hook execution.

### 3. Add Debug Logging

```python
#!/usr/bin/env python3
import pathlib, time
pathlib.Path("/tmp/hook_debug.txt").write_text(f"Called at {time.time()}\n")
# ... rest of hook
```

### 4. Check Transcript Mode

Press `CTRL+R` to see hook output that isn't displayed normally.

### 5. Test Hooks Manually

```bash
echo '{"session_id": "test", "cwd": "/path/to/project"}' | python3 /path/to/hook.py
```

### 6. Separate stdout/stderr

```bash
echo '{"session_id": "test"}' | python3 hook.py 2>/tmp/stderr.txt > /tmp/stdout.txt
```

---

## Known Issues and Workarounds

### Issue: SessionStart Context Injection Fails (CRITICAL - NOT YET VERIFIED SOLUTION)

⚠️ **WARNING**: This is a critical issue affecting memory context injection. The workaround below is **NOT YET VERIFIED** in production.

**Symptoms:**
- SessionStart hooks execute successfully (proven via debug logs)
- Manual tests show memory search retrieves correct results with good relevance scores
- Hook outputs valid JSON with `additionalContext` field
- But Claude doesn't see or use the context in live sessions
- Claude searches for files/code instead of using provided memories
- No errors in hook logs
- `/hooks` command shows hooks registered correctly

**Example:**

```bash
# Manual test - hook works perfectly
echo '{"session_id":"test","cwd":"/path/to/project","source":"startup"}' | python3 session_start.py

# Output: Valid JSON with relevant memories (e.g., "Grafana Dashboard Fix Guide" at 42% relevance)
```

But in live Claude Code session:
```
User: "Fix the Grafana dashboards showing no data"
Claude: "Let me search for the dashboard files..." [searches instead of using memory]
```

**Status:** ACTIVE INVESTIGATION (as of 2026-01-16)

**Root Cause Hypothesis:**

The SessionStart hook `additionalContext` field in JSON output does not actually inject context into Claude's reasoning process in Claude Code v2.1.9. The documentation suggests it should work, but empirical testing shows it doesn't.

**Workaround: PreToolUse with STDERR Output (NOT YET VERIFIED)**

Based on working reference architecture from `ai-memory-qdrant-knowledge-management`, use **PreToolUse hooks with STDERR output** instead of SessionStart with JSON:

**Key Differences:**
| Approach | Hook Event | Output Method | Status |
|----------|-----------|---------------|--------|
| Current (broken) | SessionStart | JSON with `additionalContext` | ❌ Doesn't work |
| Alternative (unverified) | PreToolUse | STDERR formatted text | ⚠️ NOT YET VERIFIED |

**Implementation:**

1. **Hook Script Pattern** (`/tmp/memory_context_pretool_stderr.py`):
   ```python
   #!/usr/bin/env python3
   """PreToolUse Hook - Show relevant memories BEFORE tool execution."""
   import json
   import os
   import sys

   # Add module to path
   INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
   sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

   try:
       from memory.search import MemorySearch
       from memory.config import get_config
       from memory.project import detect_project

       # Parse hook input
       data = json.load(sys.stdin)
       tool_name = data.get('tool_name', '')
       tool_input = data.get('tool_input', {})
       cwd = data.get('cwd', os.getcwd())

       # Build query from tool context
       project = detect_project(cwd)
       query = f"Working on {project} {tool_input.get('file_path', '')}"

       # Search memories
       config = get_config()
       search = MemorySearch(config)
       results = search.search(
           query=query,
           collection="implementations",
           group_id=project,
           limit=3,
           score_threshold=0.4
       )

       # Output to STDERR (Claude sees this!)
       if results:
           print(f"\n{'='*70}", file=sys.stderr)
           print(f"🧠 RELEVANT CONTEXT FOR {tool_name.upper()}", file=sys.stderr)
           print(f"{'='*70}", file=sys.stderr)

           for i, r in enumerate(results, 1):
               score = r.get("score", 0)
               content = r.get("content", "")
               memory_type = r.get("type", "unknown")

               # Show preview (first 600 chars)
               preview = content[:600] if len(content) > 600 else content

               print(f"\n{i}. [{memory_type}] (Relevance: {score:.0%})", file=sys.stderr)
               print(f"{preview}", file=sys.stderr)
               if len(content) > 600:
                   print(f"... (truncated)", file=sys.stderr)

           print(f"\n{'='*70}\n", file=sys.stderr)

   except Exception as e:
       # Fail silently - don't block Claude's tools
       pass

   # Always exit 0
   sys.exit(0)
   ```

2. **Settings Configuration**:
   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Read|Search|Bash|Edit|Write",
           "hooks": [
             {
               "type": "command",
               "command": "python3 /tmp/memory_context_pretool_stderr.py",
               "timeout": 5000
             }
           ]
         }
       ]
     }
   }
   ```

**Expected Behavior (NOT YET VERIFIED):**

When Claude is about to use a tool (Read, Search, etc.), the terminal should show:

```
======================================================================
🧠 RELEVANT CONTEXT FOR SEARCH
======================================================================

1. [implementation] (Relevance: 75%)
## Grafana Dashboard Fix Guide - AI Memory Module

### Problem Summary
The Grafana dashboards at docker/grafana/dashboards/ show "No data"...
... (truncated)

2. [implementation] (Relevance: 75%)
## AI Memory Module - Prometheus Metrics Reference
...

======================================================================
```

And Claude should reference this information in its response instead of searching blindly.

**Testing Status**: Hook implemented but **NOT YET VERIFIED** in live Claude Code session. See `oversight/TESTING_QUICK_REFERENCE.md` for test procedure.

**Related Files**:
- `oversight/session-logs/SESSION_HANDOFF_2026-01-16_HOOKS_CONTEXT_INJECTION.md` - Complete investigation
- `oversight/TESTING_QUICK_REFERENCE.md` - Step-by-step testing instructions
- `oversight/tracking/blockers-log.md` (BLK-002) - Current status

---

### Issue: Hooks Registered But Not Executing

**Symptoms:**
- Hooks appear in `/hooks` command
- Hook scripts work when run manually via stdin
- But hooks don't execute when session starts

**Status:** RESOLVED (as of 2026-01-16) - Was caused by path calculation bug

**Related GitHub Issues:**
- [#11544](https://github.com/anthropics/claude-code/issues/11544) - Hooks not loading from settings.json (CLOSED)
- [#15174](https://github.com/anthropics/claude-code/issues/15174) - SessionStart hook output not injected into context (CLOSED as duplicate)

**Investigation Steps:**
1. Create a minimal debug hook that writes to `/tmp/hook_debug.log`
2. Configure settings to use debug hook
3. Start new session and check if log file was created
4. If log file exists: problem is in your main hook script
5. If log file doesn't exist: likely Claude Code bug

**Debug Hook Template:**
```python
#!/usr/bin/env python3
"""Debug hook to test if hooks are being executed."""
import sys
import json
from datetime import datetime

# Write to file to prove execution
with open("/tmp/hook_debug.log", "a") as f:
    f.write(f"\n=== Hook executed at {datetime.now().isoformat()} ===\n")
    try:
        input_data = sys.stdin.read()
        f.write(f"Input length: {len(input_data)}\n")
        if input_data:
            f.write(f"Input: {input_data}\n")
    except Exception as e:
        f.write(f"Error reading input: {e}\n")

# Output JSON for Claude context
output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "DEBUG: Hook executed successfully at " + datetime.now().isoformat()
    }
}
print(json.dumps(output))
sys.exit(0)
```

### Issue: WSL2 Path/Permission Issues

**Symptoms:**
- Hooks work on native Linux/macOS but fail on WSL2
- Permission denied errors
- Path resolution failures

**Potential Workarounds:**
1. Ensure scripts have execute permission: `chmod +x script.py`
2. Use explicit Python interpreter: `python3 /path/to/script.py` instead of `/path/to/script.py`
3. Avoid Windows-style paths (use `/mnt/c/...` format)

### Issue: Settings Not Reloading

**Symptoms:**
- Changed settings.json but old hooks still running
- Errors reference old configuration

**Solution:**
- Settings only reload on new session start
- Use `/clear` or start a completely new session
- The `/hooks` command shows currently loaded hooks

---

## Troubleshooting Checklist

Use this checklist when hooks aren't working:

### Configuration Checklist

- [ ] **Matcher format**: Using pipe-separated matchers? (`startup|resume|compact`)
- [ ] **Absolute paths**: All hook commands use absolute paths?
- [ ] **Python prefix**: Commands include `python3` prefix?
- [ ] **Timeout set**: SessionStart hooks have `timeout` parameter?
- [ ] **Valid JSON**: Settings file passes JSON validation?
- [ ] **Correct location**: Settings in right location for scope? (global vs project)

### Environment Checklist (AI Memory)

- [ ] **QDRANT_HOST**: Set to `localhost` (not URL string)?
- [ ] **QDRANT_PORT**: Set to `26350` (not default 6333)?
- [ ] **EMBEDDING_HOST**: Set to `localhost`?
- [ ] **EMBEDDING_PORT**: Set to `28080`?
- [ ] **Docker running**: All containers up? (`docker compose ps`)

### Verification Steps

1. **Check /hooks output**: Does hook appear in menu?
   ```
   /hooks
   ```

2. **Test hook manually**: Does script work with test input?
   ```bash
   echo '{"session_id":"test","cwd":"/path","source":"startup"}' | python3 /path/to/hook.py
   ```

3. **Check debug log**: If using debug hook, was log created?
   ```bash
   cat /tmp/hook_debug.log
   ```

4. **Verify permissions**: Can script execute?
   ```bash
   ls -la /path/to/hook.py
   ```

5. **Check Docker services**: Are they responding?
   ```bash
   curl -s http://localhost:26350/collections | head -c 100
   curl -s http://localhost:28080/health
   ```

### Complete Working Example

Here's a complete, tested settings.json configuration:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "env": {
    "QDRANT_HOST": "localhost",
    "QDRANT_PORT": "26350",
    "EMBEDDING_HOST": "localhost",
    "EMBEDDING_PORT": "28080",
    "SIMILARITY_THRESHOLD": "0.4",
    "LOG_LEVEL": "INFO"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/.claude/hooks/scripts/session_start.py",
            "timeout": 30000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/.claude/hooks/scripts/post_tool_capture.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/.claude/hooks/scripts/activity_logger.py"
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/.claude/hooks/scripts/agent_response_capture.py"
          }
        ]
      }
    ]
  }
}
```

---

## References

- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)
- [GitHub Issue #9591 - SessionStart Context Not Displayed](https://github.com/anthropics/claude-code/issues/9591)
- [GitHub Issue #11544 - Hooks Not Loading](https://github.com/anthropics/claude-code/issues/11544)
- [GitHub Issue #15174 - SessionStart Hook Output Not Injected](https://github.com/anthropics/claude-code/issues/15174)

---

*Last updated: 2026-01-16*
*Based on Claude Code documentation and extensive debugging experience from AI Memory Module VAL-001 validation and BLK-002 investigation*
