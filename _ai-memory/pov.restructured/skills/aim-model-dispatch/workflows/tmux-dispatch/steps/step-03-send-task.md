---
name: 'step-03-send-task'
description: 'Send user task to initialized Claude session'
nextStepFile: './step-04-monitor-and-capture.md'
---

# Step 3: Send Task to Claude

## STEP GOAL
Send the user's task description to the initialized Claude session in the tmux pane.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps
- Use single Enter only — never double Enter

## CONTEXT BOUNDARIES
- Available context: PANE_TARGET from step-02, TASK_INPUT from step-01
- Limits: Do not send task before Claude is initialized. Do not send multiple Enters.

## MANDATORY SEQUENCE

### 1. Send Task Input

```bash
# TASK_INPUT is from step-01, the user's task description
tmux send-keys -t "$PANE_TARGET" "${TASK_INPUT}"
```

### 2. Submit with Single Enter

```bash
# Pause 2 seconds for the TUI to render the text
sleep 2

# Submit with Enter once
tmux send-keys -t "$PANE_TARGET" Enter
```

**CRITICAL**: One Enter only. A second Enter would be interpreted as blank input.

### 3. Wait for Processing Start

```bash
# Wait for Claude to begin processing the task
sleep 3
```

## CRITICAL STEP COMPLETION NOTE
ONLY when task has been sent with single Enter, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Task input sent to pane
- Single Enter used to submit
- 3-second post-submit wait completed
- Claude begins processing task

### FAILURE:
- Task sent before initialization complete
- Multiple Enters after task input
- Pane no longer exists (check PANE_TARGET)
- Not waiting for processing to start
