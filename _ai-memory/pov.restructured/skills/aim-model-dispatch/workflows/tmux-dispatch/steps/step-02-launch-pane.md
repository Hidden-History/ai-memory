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

### 0. Verify Wrapper Command Exists

```bash
# WRAPPER_CMD is from step-01 dispatch plan
if ! command -v "${WRAPPER_CMD%% *}" &>/dev/null; then
  echo "ERROR: Wrapper command '${WRAPPER_CMD}' not found in PATH."
  echo "Install it by running: bash .claude/skills/model-dispatch/scripts/install.sh"
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
- Pane created with captured PANE_TARGET ID
- Wrapper command executed with allowedTools flags
- 5-second initialization wait completed
- Pane verified alive after initialization
- PANE_TARGET available for subsequent steps

### FAILURE:
- Pane creation failed (check tmux session exists)
- Wrapper command not found (check PATH)
- Initialization timeout (increase sleep duration)
- Not recording PANE_TARGET
