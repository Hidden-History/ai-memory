# Model-Dispatch — Agent Reference

Internal technical reference for executing agents. Workflow step files handle dispatch logic — this file provides supporting details that steps may reference.

---

## Wrapper Behavior

Each wrapper guarantees clean environment isolation:

| Wrapper | Unsets | Sets | Key behavior |
|---------|--------|------|-------------|
| `claude-dispatch` | CLAUDECODE, ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN | (nothing) | Does NOT unset ANTHROPIC_API_KEY |
| `provider-dispatch` | CLAUDECODE | ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN per provider (reads providers.json); sets ANTHROPIC_API_KEY="" for OpenRouter (emptyApiKey) | Handles all non-claude backends (openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow) |

All wrappers end with `exec claude "$@"`.

---

## SKILL_DIR Resolution

**Each Bash call is a fresh shell. SKILL_DIR does NOT persist between calls.**

Always resolve inline in every command:
```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && python3 "${SKILL_DIR}/scripts/..." [args]
```

Never use bare `${SKILL_DIR}` — it will be empty.

---

## Inbox Injection (Teammate Communication)

When running inside a Claude Code team, inject messages into the team lead inbox so results appear as teammate messages — delivered within ~1 second.

### How it works

Claude Code teammates communicate via JSON mailbox files at `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`. The main session polls these every 1 second. Any message with `"read": false` is delivered as a new conversation turn.

### Finding the inbox

```bash
TEAM_DIR=$(ls -td ~/.claude/teams/*/config.json 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
if [ -n "$TEAM_DIR" ]; then
  INBOX="${TEAM_DIR}/inboxes/team-lead.json"
fi
```

### Injecting a message

```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
  --inbox "$INBOX" \
  --from "dispatch-agent" \
  --message "Task complete. Here are my findings: ..." \
  --color "purple"
```

The inbox-inject.py script uses atomic writes (`fcntl.flock` + `tempfile.mkstemp` + `os.replace`) and symlink protection for safe concurrent access.

### Capture + inject pattern

```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch"
RESULT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -50 2>/dev/null | \
  sed 's/\x1b\[[0-9;]*[mGKHF]//g' | grep -v "^$")

python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
  --inbox "$INBOX" \
  --from "dispatch-agent" \
  --message "$RESULT" \
  --color "purple"
```

### Without a team

If not in a team context, skip inbox injection. Capture results directly via `tmux capture-pane`.

---

## Timing Reference

| Step | Wait time | Why |
|------|-----------|-----|
| After launching wrapper | 5 seconds | Claude Code loads project context, MCP servers, settings |
| After typing prompt text | 2 seconds | Let the UI render the prompt before submitting |
| Enter once to submit | -- | One Enter only. A second Enter creates blank spaces instead of submitting |
| Between monitoring polls | 5-10 seconds | Avoid excessive capture overhead |
| BMAD Phase 1 → Phase 2 | 8-10 seconds | Agent needs time to load persona, display menu |

Increase the init wait to 8-10 seconds if Claude Code loads many MCP servers or has a large CLAUDE.md.

---

## Permission Handling

Dispatched agents run in visible TUI panes, but permission dialogs block them until approved.

### Option A: CLI flags (default, recommended)

| Flag | Effect | Use when |
|------|--------|----------|
| `--allowedTools "Edit" "Write" "Read" "Glob" "Grep" "Bash(*)"` | Pre-approve common tools (`Bash(*)` grants unrestricted shell) | **Default** — standard dev work |
| `--permission-mode acceptEdits` | Auto-accept all file edits | Agent only reads/writes files |
| `--dangerously-skip-permissions` | Skip ALL permission prompts | Fully trusted, you are watching |
| No flags | Agent prompts for every tool | Maximum control |

To narrow Bash permissions:
```bash
--allowedTools "Bash(npm *)" "Bash(docker *)" "Bash(python3 *)"
```

### Option B: PermissionRequest hook (auto-approve + notify)

Install `auto-approve-hook.sh` as a Claude Code hook:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/.claude/skills/model-dispatch/scripts/auto-approve-hook.sh"
          }
        ]
      }
    ]
  }
}
```

The hook returns `{"behavior": "allow"}` and injects a notification to the team lead inbox.

**Important**: Option B auto-approves ALL tool calls when active. Only use for supervised agents.

### Fallback: auto-reply monitor

The auto-reply monitor detects permission dialogs that slip through and forwards them to the team lead inbox.

---

## OpenRouter Features

Available when using the `openrouter` backend or API mode.

### Statusline

```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && bash "${SKILL_DIR}/scripts/statusline/statusline.sh"
```

Shows real-time model and token info. Only relevant for OpenRouter panes.

### Cost Tracking

```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && bash "${SKILL_DIR}/scripts/usage-report.sh"
```

Shows cost breakdown by model for the current billing period.

### Provider Routing

OpenRouter automatically routes requests to the fastest/cheapest provider. Identified via `X-OpenRouter-Title: "model-dispatch"` header.

### Response Caching

Identical requests are cached and free. Non-deterministic tasks use `temperature > 0` to bypass caching.

---

## Signal File Delivery

Completion detection uses a dual mechanism:

1. **inotifywait (preferred)** — Watches `/tmp/model-dispatch-signal-{PANE_ID}` for write events. Near-instant (~2 sec) delivery. Requires `inotifywait` (from `inotify-tools`).

2. **Polling fallback** — If `inotifywait` is unavailable, the monitor polls every 2 seconds using diff-based idle detection (pane unchanged for 2 consecutive polls after activity).

The `on-complete.sh` script writes the signal file:

```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && bash "${SKILL_DIR}/scripts/on-complete.sh" "$PANE_TARGET"
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `SKILL_DIR: No such file or directory` | SKILL_DIR not set in current shell | Set inline: `SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && ...` |
| `400 invalid model ID` | Guessed model ID from training data | Run `list-models.py --category [type]` first to get live IDs |
| `claude-dispatch: command not found` | Wrapper not installed | Run `bash "${SKILL_DIR}/scripts/install.sh"` |
| `provider-dispatch: command not found` | Wrapper not installed | Run `bash "${SKILL_DIR}/scripts/install.sh"` |
| `401 unauthorized` (OpenRouter) | Token missing or wrong | Check `~/.openrouter-token` and `chmod 600` |
| `401 unauthorized` (Ollama) | Token missing or wrong | Check `~/.ollama-token` and `chmod 600` |
| Nesting error | CLAUDECODE env var inherited | Verify wrapper has `unset CLAUDECODE` before `exec claude` |
| Prompt not submitted | Enter hit too fast | Wait 2 seconds after prompt text, then Enter once only |
| Blank pane after launch | Init wait too short | Increase sleep to 8-10 seconds |
| BMAD agent no menu | Single-phase dispatch used | Always use two-phase: activate agent first, wait for menu, then send task |
| OpenRouter `402 payment required` | Insufficient credits | Add credits at openrouter.ai/credits |
| OpenRouter `429 rate limit` | Too many requests | Wait and retry, or reduce parallel agents |
| API script `ModuleNotFoundError` | Python deps missing | Run `pip install -r "${SKILL_DIR}/scripts/openrouter-api/requirements.txt"` |
| inotifywait not found | inotify-tools not installed | Install via package manager or rely on polling fallback |

### Validate setup

```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && bash "${SKILL_DIR}/scripts/validate-setup.sh"
```

### Reading pane output

```bash
tmux capture-pane -t "$PANE_TARGET" -p -S -50 | sed 's/\x1b\[[0-9;]*[mGKHF]//g'
```

---

## Full Reference Docs

- Setup guide: `references/setup-guide.md`
- User guide: `references/user-guide.md`
- Claude models: `references/models-claude.md`
- Providers: `references/providers.md`
