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

BMAD agents display one of two menu styles after activation. Detection must match EITHER style:

Style A — Legacy universal menu. Contains:
- `[MH]` — Menu Help
- `[DA]` — Dismiss Agent

Style B — Custom numbered Intent picker. Contains a "Type something" option literal, typically rendered as a numbered line such as `5. Type something` or similar. The Intent picker appears in skills that render a custom numbered menu (e.g., `Build / Analyze / … / Type something / Chat`) and does NOT carry the `[MH]`/`[DA]` markers.

> Note: as of BMAD v6.9.0, no skill in the installed SOT presents a Style-B Intent picker (it originated in the now-removed bmb module). The Style-B detection and navigation below are retained defensively but are likely a dead branch — a candidate for future cleanup.

Detection SUCCESS = Style A matched OR Style B matched.

Poll the pane every 2 seconds for up to 20 seconds (10 attempts). Step-02 already waits ~10 seconds for initialization, so the menu typically appears on the first or second check:

```bash
MAX_ATTEMPTS=10
POLL_INTERVAL=2
MENU_DETECTED=false

for i in $(seq 1 $MAX_ATTEMPTS); do
  PANE_TEXT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -30 2>/dev/null | \
    sed 's/\x1b\[[0-9;]*[mGKHF]//g')

  # Check for Style A (legacy markers) or Style B (Intent picker)
  STYLE_A=false
  STYLE_B=false
  if echo "$PANE_TEXT" | grep -q '\[MH\]' && echo "$PANE_TEXT" | grep -q '\[DA\]'; then
    STYLE_A=true
  fi
  if echo "$PANE_TEXT" | grep -qi 'Type something'; then
    STYLE_B=true
  fi

  if [ "$STYLE_A" = true ] || [ "$STYLE_B" = true ]; then
    MENU_DETECTED=true
    if [ "$STYLE_A" = true ]; then
      MENU_STYLE=legacy
    else
      MENU_STYLE=intent_picker
    fi
    echo "Menu detected after $((i * POLL_INTERVAL)) seconds (style: $MENU_STYLE)."
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
  exit 1
fi
```

### 2. Handle Detection Failure

If the menu is not detected after 20 seconds:

**Check A — Agent error:** Look for error messages in pane output. If errors present, capture them and report back. Do not proceed.

**Check B — Wrong command:** Verify the activation command was correct. Check pane output for "Not recognized" or similar.

If all checks fail: capture pane output, report the failure, and do NOT send task directions to a pane in an unknown state.

### 2b. Navigate Intent Picker to "Type something" (if Style B)

Only runs when `MENU_STYLE=intent_picker`. Skipped for legacy menus — the legacy flow already accepts menu codes as free-form input on the first line.

BMAD Intent pickers interpret the first non-navigation input as confirmation of the currently-highlighted option. Free-form text has no navigation prefix, so it is treated as confirmation of the wrong option. The dispatch layer must navigate to the "Type something" option first.

In a typical Style-B picker, "Type something" sits partway down the list — for example option 5 of a `Build=1, Analyze=2, Edit=3, Rebuild=4, Type something=5, Chat=6` menu, reached by four Down presses followed by Enter. The actual offset is detected dynamically (below), so this is only the fallback default.

```bash
if [ "$MENU_STYLE" = "intent_picker" ]; then
  # Count the offset to the "Type something" option
  # Fallback default: in a typical Style-B picker the literal is at option 5 → 4 Down presses
  DOWN_COUNT=4

  # Derive dynamically from pane text if possible; fall back to default
  PICKER_TEXT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -30 2>/dev/null | \
    sed 's/\x1b\[[0-9;]*[mGKHF]//g')
  DETECTED_N=$(echo "$PICKER_TEXT" | grep -oiE '^[[:space:]]*([0-9]+)\.[[:space:]]+Type something' | \
    head -n1 | grep -oE '[0-9]+' | head -n1)
  if [ -n "$DETECTED_N" ] && [ "$DETECTED_N" -ge 1 ] 2>/dev/null; then
    DOWN_COUNT=$((DETECTED_N - 1))
  fi

  echo "Navigating Intent picker: $DOWN_COUNT Down press(es) + Enter to select 'Type something'."
  for _ in $(seq 1 "$DOWN_COUNT"); do
    tmux send-keys -t "$PANE_TARGET" Down
    sleep 0.3
  done
  tmux send-keys -t "$PANE_TARGET" Enter
  sleep 2
fi
```

After this substep, the picker has consumed the "Type something" selection and the pane is ready to accept free-form task text on the next line.

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
- Menu detected via Style A (`[MH]` + `[DA]` markers) OR Style B (`Type something` literal) before timeout
- If Style B detected, Intent picker navigated to `Type something` option BEFORE task input sent
- Task directions sent only AFTER menu confirmation (and navigation, if Style B)
- Single Enter used after task input
- Follow-up input sent if prepared
- Detection failure handled gracefully (abort, not blind-send)

### FAILURE:
- Sending task directions before menu is confirmed
- Sending task directions into a Style B Intent picker without navigating to `Type something` first (silent wrong-option selection)
- Giving up too early on detection
- Sending task to a pane in error state
- Multiple Enters after task input
- Ignoring TASK_FOLLOW_UP when it was prepared
