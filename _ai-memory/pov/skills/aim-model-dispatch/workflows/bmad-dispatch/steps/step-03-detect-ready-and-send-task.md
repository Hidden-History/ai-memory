---
name: 'step-03-detect-ready-and-send-task'
description: 'Detect agent menu, then send task directions'
nextStepFile: './step-04-monitor-and-capture.md'
---

# Step 3: Detect Ready State and Send Task

## STEP GOAL
Poll the tmux pane until the BMAD agent's menu has appeared, then send the task directions from the dispatch plan.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: PANE_TARGET from step-02, dispatch plan from step-01 (TASK_INPUT, TASK_FOLLOW_UP)
- Limits: Do not send task directions until menu detection succeeds.

## MANDATORY SEQUENCE

### 1. Poll for Menu Appearance

All BMAD agents display standard menu items after activation. The universal detection markers are:
- `[MH]` — Menu Help (present in every agent menu)
- `[DA]` — Dismiss Agent (present in every agent menu)

Poll the pane every 2 seconds for up to 20 seconds (10 attempts). Step-02 already waits ~10 seconds for initialization, so the menu typically appears on the first or second check:

```bash
MAX_ATTEMPTS=10
POLL_INTERVAL=2
MENU_DETECTED=false

for i in $(seq 1 $MAX_ATTEMPTS); do
  PANE_TEXT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -30 2>/dev/null | \
    sed 's/\x1b\[[0-9;]*[mGKHF]//g')

  # Check for universal menu markers
  if echo "$PANE_TEXT" | grep -q '\[MH\]' && echo "$PANE_TEXT" | grep -q '\[DA\]'; then
    MENU_DETECTED=true
    echo "Menu detected after $((i * POLL_INTERVAL)) seconds."
    break
  fi

  echo "Waiting for menu... attempt ${i}/${MAX_ATTEMPTS}"
  sleep "$POLL_INTERVAL"
done

if [ "$MENU_DETECTED" = false ]; then
  echo "WARNING: Menu not detected after $((MAX_ATTEMPTS * POLL_INTERVAL))s."
  echo "Pane content:"
  tmux capture-pane -t "$PANE_TARGET" -p -S -20 2>/dev/null | \
    sed 's/\x1b\[[0-9;]*[mGKHF]//g' | grep -v "^$"
fi
```

### 2. Handle Detection Failure

If the menu is not detected after 20 seconds:

**Check A — Agent error:** Look for error messages in pane output. If errors present, capture them and report back. Do not proceed.

**Check B — Wrong command:** Verify the activation command was correct. Check pane output for "Not recognized" or similar.

If all checks fail: capture pane output, report the failure, and do NOT send task directions to a pane in an unknown state.

### 3. Send Task Directions

Once the menu is confirmed, send the task input from the dispatch plan.

```bash
# Send the menu code or task text
# TASK_INPUT from step-01
tmux send-keys -t "$PANE_TARGET" "${TASK_INPUT}"

# Pause 2 seconds, then Enter once
sleep 2
tmux send-keys -t "$PANE_TARGET" Enter
```

### 4. Send Follow-Up Input (if needed)

Some menu selections prompt for additional input.

```bash
# Wait for the agent to process the menu selection
sleep 5

# Send follow-up if prepared
if [ -n "${TASK_FOLLOW_UP}" ]; then
  tmux send-keys -t "$PANE_TARGET" "${TASK_FOLLOW_UP}"
  sleep 2
  tmux send-keys -t "$PANE_TARGET" Enter
fi
```

## CRITICAL STEP COMPLETION NOTE
ONLY when the menu has been detected AND the task directions (plus any follow-up) have been sent, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Menu detected via `[MH]` + `[DA]` markers before timeout
- Task directions sent only AFTER menu confirmation
- Single Enter used after task input
- Follow-up input sent if prepared
- Detection failure handled gracefully (abort, not blind-send)

### FAILURE:
- Sending task directions before menu is confirmed
- Giving up too early on detection
- Sending task to a pane in error state
- Multiple Enters after task input
- Ignoring TASK_FOLLOW_UP when it was prepared
