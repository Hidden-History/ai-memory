# aim-sot — Hook Configuration Reference

Per-CLI hook-config entries written by the installer. The SKILL.md body holds the
behavioral summary (default-on, disable flags, runtime gate); this file holds the
JSON snippets for copy-paste reference when registering or auditing hooks manually.

---

## Stop hooks

### Claude — Stop hook

The following entry is written to `.claude/settings.json` (under `hooks.Stop`) on install:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_drift_stop.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_drift_stop.py\" || true",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

Once registered, the hook fires automatically at every Claude Code session end. It invokes
`detect-propose` in propose-only mode and prints a one-line summary to stderr when drift
or new candidates are detected. It never writes any committed file.

### Codex — Stop hook

Adapter: `src/memory/adapters/codex/sot_drift.py`  
Config: `.codex/hooks.json` — add under `hooks.Stop`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_drift.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_drift.py\" || true",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Fires propose-only at every Codex session stop. Never writes any committed file.

### Cursor — stop hook

Adapter: `src/memory/adapters/cursor/sot_drift.py`  
Config: `.cursor/hooks.json` — add under `hooks.stop`:

```json
{
  "version": 1,
  "hooks": {
    "stop": [
      {
        "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_drift.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_drift.py\" || true",
        "timeout": 30
      }
    ]
  }
}
```

Fires propose-only at end-of-turn (Cursor `stop` event). Never writes any committed file.

### Gemini — AfterAgent hook

Adapter: `src/memory/adapters/gemini/sot_drift.py`  
Config: `.gemini/settings.json` — add under `hooks.AfterAgent`:

```json
{
  "hooks": {
    "AfterAgent": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_drift.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_drift.py\" || true",
            "timeout": 60000
          }
        ]
      }
    ]
  }
}
```

Fires propose-only at end-of-turn (Gemini `AfterAgent` event). Never writes any committed file.

---

## Session-start hooks

### Claude — SessionStart hook

Script: `.claude/hooks/scripts/sot_digest_session_start.py`  
Config: `.claude/settings.json` — add under `hooks.SessionStart`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.claude/hooks/scripts/sot_digest_session_start.py\" || true",
            "timeout": 30000
          }
        ]
      }
    ]
  }
}
```

Once registered, fires on every Claude Code session start and injects the SOT digest as
`additionalContext`. Requires `.sot/registry.yaml` in the project root to activate.

### Codex — SessionStart hook

Script: `src/memory/adapters/codex/sot_digest_session_start.py`  
Config: `.codex/hooks.json` — add under `hooks.SessionStart`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/codex/sot_digest_session_start.py\" || true",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Fires at Codex session start and injects the SOT digest as `systemMessage`.

### Cursor — sessionStart hook

Script: `src/memory/adapters/cursor/sot_digest_session_start.py`  
Config: `.cursor/hooks.json` — add under `hooks.sessionStart`:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/cursor/sot_digest_session_start.py\" || true",
        "timeout": 30
      }
    ]
  }
}
```

Fires at Cursor session start and injects the SOT digest as top-level `additional_context`.

### Gemini — SessionStart hook

Script: `src/memory/adapters/gemini/sot_digest_session_start.py`  
Config: `.gemini/settings.json` — add under `hooks.SessionStart`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "[ -f \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_digest_session_start.py\" ] && \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python\" \"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/src/memory/adapters/gemini/sot_digest_session_start.py\" || true",
            "timeout": 60000
          }
        ]
      }
    ]
  }
}
```

Fires at Gemini session start and injects the SOT digest as `additionalContext`.

---

## CI / pre-commit gate (`verify --strict`)

Opt-in, never auto-installed. The default `verify run` always exits 0 (the verdict is
on stdout), so a naive `verify run || exit 1` gate **silently passes a FAIL registry**.
Use `--strict` instead: it exits 1 on a `FAIL` verdict and 0 on `PASS` / `CONDITIONAL`,
so a warning-only registry does not break the build.

### GitHub Actions

```yaml
# .github/workflows/sot-verify.yml
name: SOT verify
on: [pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify .sot/registry.yaml
        run: |
          bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
            "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" \
            run --strict
```

### pre-commit (local hook)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: sot-verify
        name: aim-sot verify (strict)
        entry: bash -c 'bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_verify.py" run --strict'
        language: system
        pass_filenames: false
        files: '^\.sot/registry\.yaml$'
```

A non-zero exit blocks the commit / fails the job only on a hard `FAIL`; review a
`CONDITIONAL` (exit 0) before applying, per the HITL gate.
