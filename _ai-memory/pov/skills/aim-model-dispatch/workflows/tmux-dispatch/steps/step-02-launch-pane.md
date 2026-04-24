---
name: 'step-02-launch-pane'
description: 'Launch tmux pane with backend-appropriate wrapper command'
nextStepFile: './step-03-send-task.md'
---

# Step 2: Launch Pane and Initialize Claude

## STEP GOAL
Create a tmux pane, launch Claude Code with the backend-appropriate wrapper command, and wait for initialization.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps
- Use -P -F '#{pane_id}' for pane creation (race-safe)

## CONTEXT BOUNDARIES
- Available context: Dispatch plan from step-01 (WRAPPER_CMD, MODEL, TASK_INPUT)
- Limits: Do NOT send task input yet — wait for Claude to initialize.

## MANDATORY SEQUENCE

### 0a. Verify Workspace Root (CWD Sentinel)

Run BEFORE any pane creation. The sentinel requires the co-presence of
`_ai-memory/`, `_bmad/`, and `oversight/` — a single-marker check is
insufficient because a nested source repo (e.g., `ai-memory/`) also contains
`_ai-memory/` and would pass.

```bash
# Scope: dev workspace dispatches only. End-user installs (~/.ai-memory/) launch
# via skill installer wrappers and do not require this sentinel.
# Enforced on every spawn, not just the first in a session.
if ! (test -d _ai-memory && test -d _bmad && test -d oversight); then
  echo "FAIL: CWD is not workspace root. Expected _ai-memory/, _bmad/, oversight/ all present."
  echo "CWD: $(pwd)"
  echo "Aborting dispatch. cd to workspace root and re-invoke."
  exit 1
fi
echo "OK: workspace root ($(pwd))"
```

If this check fails, stop — do not proceed to pane creation.

### 0b. Pre-Spawn Model Validation

Validate MODEL against the catalog BEFORE creating a tmux pane. An invalid
model name wastes a pane slot and produces a cryptic runtime error. Fail-fast
here with a clear catalog-reference message.

```bash
# Skip validation when MODEL is empty (native Claude default) or BACKEND=gemini
# (Gemini CLI handles its own model selection interactively).
if [ -n "${MODEL}" ] && [ "${BACKEND}" != "gemini" ]; then
  SKILL_DIR="$(pwd)/_ai-memory/pov/skills/aim-model-dispatch"
  CATALOG_FILE=""
  case "${BACKEND}" in
    ollama)      CATALOG_FILE="${SKILL_DIR}/references/models-ollama.md" ;;
    openrouter)  CATALOG_FILE="${SKILL_DIR}/references/models-openrouter.md" ;;
  esac
  if [ -n "${CATALOG_FILE}" ]; then
    if [ ! -f "${CATALOG_FILE}" ]; then
      echo "FAIL: catalog file for backend '${BACKEND}' expected at ${CATALOG_FILE} but not found."
      echo "This is a deployment issue — reinstall or verify model-dispatch wrappers are installed."
      exit 1
    fi
    if ! grep -Fq "\`${MODEL}\`" "${CATALOG_FILE}"; then
      echo "FAIL: model '${MODEL}' not found in catalog ${CATALOG_FILE}."
      echo "Available models listed in that file. Correct the dispatch plan and re-invoke."
      exit 1
    fi
    echo "OK: model '${MODEL}' validated against ${BACKEND} catalog"
  else
    echo "WARN: no catalog file for backend '${BACKEND}' -- skipping pre-spawn validation"
  fi
fi
```

If validation fails, stop — do not create a pane.

### 0. Verify Wrapper Command Exists

```bash
# WRAPPER_CMD is from step-01 dispatch plan
if ! command -v "${WRAPPER_CMD%% *}" &>/dev/null; then
  echo "ERROR: Wrapper command '${WRAPPER_CMD}' not found in PATH."
  echo "Install it by running: bash _ai-memory/pov/skills/aim-model-dispatch/scripts/install.sh"
  echo "Aborting dispatch."
  exit 1
fi
echo "Wrapper verified: ${WRAPPER_CMD}"
```

If this check fails, stop — do not proceed to pane creation.

### 1. Get Current Tmux Session

```bash
TMUX_SESSION=$(tmux display-message -p '#S')
```

### 2. Create Pane and Capture ID

```bash
# Create pane with exact pane ID capture
PANE_TARGET=$(tmux split-window -t "$TMUX_SESSION" -h -d -P -F '#{pane_id}')
```

Record `PANE_TARGET` — it is needed for all subsequent tmux commands.

### 3. Launch CLI in Pane

There are two launch paths depending on the backend:

**Gemini CLI (BACKEND=gemini):**
The Gemini CLI is a standalone tool with its own auth (Google account) and model selection. Launch it directly without `--model` or `--allowedTools` flags — those are Claude Code concepts that don't apply here.

```bash
# Gemini CLI launch — no model/allowedTools flags
tmux send-keys -t "$PANE_TARGET" "gemini" Enter
```

**All other backends (Claude Code with wrappers):**
```bash
# Build the command
# For provider backends: provider-dispatch <provider> --model ${MODEL} --allowedTools "Edit" "Write" "Read" "Glob" "Grep" "Bash(*)"
# For claude/openrouter: wrapper command with allowed tools

if [ -n "${MODEL}" ]; then
  tmux send-keys -t "$PANE_TARGET" "${WRAPPER_CMD} --model ${MODEL} --allowedTools \"Edit\" \"Write\" \"Read\" \"Glob\" \"Grep\" \"Bash(*)\"" Enter
else
  tmux send-keys -t "$PANE_TARGET" "${WRAPPER_CMD} --allowedTools \"Edit\" \"Write\" \"Read\" \"Glob\" \"Grep\" \"Bash(*)\"" Enter
fi
```

**IMPORTANT:** The command is submitted with Enter.

### 4. Wait for Initialization

```bash
# Gemini CLI initializes faster than Claude Code
if [ "${BACKEND}" = "gemini" ]; then
  sleep 3
else
  # Wait for Claude Code to initialize (loads project context, MCP servers, settings)
  sleep 5
fi
```

### 5. Verify Pane is Alive

```bash
# Verify pane exists
if ! tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -q "^${PANE_TARGET}$"; then
  echo "ERROR: Pane $PANE_TARGET no longer exists. Launch failed."
  # Abort -- do not proceed
fi

# Quick peek at pane state
tmux capture-pane -t "$PANE_TARGET" -p -S -5 2>/dev/null | \
  sed 's/\x1b\[[0-9;]*[mGKHF]//g' | grep -v "^$"
```

If this check fails, stop — do not proceed to the next step.

## CRITICAL STEP COMPLETION NOTE
ONLY when pane is created, Claude launched, 5-second init wait completed, and pane verified alive, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Workspace root sentinel passed (`_ai-memory/` + `_bmad/` + `oversight/` all present)
- Model validated against the catalog for the selected backend
- Pane created with captured PANE_TARGET ID
- Wrapper command executed with allowedTools flags
- 5-second initialization wait completed
- Pane verified alive after initialization
- PANE_TARGET available for subsequent steps

### FAILURE:
- CWD sentinel failed (one of the workspace-root markers missing)
- MODEL not present in catalog for the backend (spawn must not proceed)
- Pane creation failed (check tmux session exists)
- Wrapper command not found (check PATH)
- Initialization timeout (increase sleep duration)
- Not recording PANE_TARGET
