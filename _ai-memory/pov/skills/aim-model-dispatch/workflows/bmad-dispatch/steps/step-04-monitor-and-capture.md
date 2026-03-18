---
name: 'step-04-monitor-and-capture'
description: 'Monitor agent progress, handle multi-turn interaction, capture final result'
nextStepFile: null
---

# Step 4: Monitor, Interact, and Capture

## STEP GOAL
Monitor the BMAD agent as it works in the tmux pane. Handle multi-turn interactions, detect completion, capture the full output, and report the result.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps
- Do not kill pane until result is captured

## CONTEXT BOUNDARIES
- Available context: PANE_TARGET, AGENT_NAME, EXPECTED_BEHAVIOR from earlier steps
- Limits: Do not send unsolicited input while agent is working. Do not kill pane prematurely.

## MANDATORY SEQUENCE

### 1. Start Auto-Reply Monitor

```bash
# SKILL_DIR must be resolved inline — it does NOT persist between Bash calls
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch"

# Start auto-reply monitor in background
bash "${SKILL_DIR}/scripts/auto-reply-monitor.sh" "$PANE_TARGET" "$SKILL_DIR" "${AGENT_NAME}" "${BACKEND}" &
MONITOR_PID=$!

echo "Auto-reply monitor started (PID: ${MONITOR_PID})"
```

The monitor handles:
- Permission dialog detection (forwards to team lead inbox)
- Completion detection (diff-based idle + signal file)
- Result capture and inbox injection

### 2. Periodic Progress Checks

Check progress every 30 seconds:

```bash
PANE_TEXT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -15 2>/dev/null | \
  sed 's/\x1b\[[0-9;]*[mGKHF]//g' | grep -v "^$")

echo "=== Agent Progress ==="
echo "$PANE_TEXT" | tail -5
```

Look for:
- **Agent actively working** — do not interrupt
- **Agent reporting a blocker** — relay to caller
- **Agent asking a question** — provide answer or relay to caller
- **Agent showing completion message** — proceed to capture

### 3. Handle Multi-Turn Interaction

**Agent asks a question:**
1. Read the question from pane capture or inbox notification
2. If you can answer, answer directly:

```bash
tmux send-keys -t "$PANE_TARGET" "Your answer here"
sleep 2
tmux send-keys -t "$PANE_TARGET" Enter
```

3. If you cannot answer, relay to caller and wait for response.

**Agent hits a permission prompt:**
The auto-reply monitor detects and notifies. To approve:

```bash
tmux send-keys -t "$PANE_TARGET" Enter
```

**Agent appears stuck:**
1. Capture pane output for diagnosis
2. Send nudge: `Continue with the task. If blocked, report what is blocking you.`
3. If still stuck after another cycle, report failure to caller

### 4. Detect Completion

The auto-reply monitor handles primary completion detection. When complete:

```bash
# Monitor saves output to /tmp/model-dispatch-result-${AGENT_NAME}.txt
# and injects into team lead inbox (if team context exists)
```

**Manual completion check** (if monitor fails):

```bash
PANE_TEXT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -30 2>/dev/null | \
  sed 's/\x1b\[[0-9;]*[mGKHF]//g')

if echo "$PANE_TEXT" | tail -15 | grep -q '\[MH\]' && \
   echo "$PANE_TEXT" | tail -15 | grep -q '\[DA\]'; then
  echo "Agent returned to menu. Task complete."
fi
```

### 5. Capture Full Result

```bash
# Capture comprehensive output (last 200 lines)
RESULT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -200 2>/dev/null | \
  sed 's/\x1b\[[0-9;]*[mGKHF]//g' | grep -v "^$")

# Save to file
echo "$RESULT" > /tmp/model-dispatch-result-${AGENT_NAME}.txt
echo "Result saved to /tmp/model-dispatch-result-${AGENT_NAME}.txt"

# Inject into team lead inbox (if in team context)
TEAM_DIR=$(ls -td ~/.claude/teams/*/config.json 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
if [ -n "$TEAM_DIR" ]; then
  INBOX="${TEAM_DIR}/inboxes/team-lead.json"
  SKILL_DIR="$(pwd)/.claude/skills/model-dispatch"
  if [ -f "$INBOX" ]; then
    python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
      --inbox "$INBOX" \
      --from "${AGENT_NAME}" \
      --message "$RESULT" \
      --color "purple"
    echo "Result injected to team lead inbox."
  fi
fi
```

### 6. Post-Task Cleanup (ALWAYS do this)

**Default — Dismiss and kill pane (REQUIRED after every task):**
Always dismiss the agent and kill the pane when done. Never reuse a pane across tasks — always create a fresh pane for each new task.

```bash
tmux send-keys -t "$PANE_TARGET" "DA"
sleep 1
tmux send-keys -t "$PANE_TARGET" Enter
sleep 3
tmux kill-pane -t "$PANE_TARGET" 2>/dev/null
```

**Exception — Leave pane open:** Only if the user explicitly asks to inspect the pane. Do NOT leave open by default.

### 7. Stop the Monitor

```bash
kill "$MONITOR_PID" 2>/dev/null
```

## CRITICAL STEP COMPLETION NOTE
This is the final step. The workflow is complete when the result has been captured and delivered.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Auto-reply monitor started immediately after task dispatch
- Multi-turn interactions handled (questions answered, permissions approved)
- Completion detected (via monitor or manual check)
- Full result captured (200-line window)
- Result delivered (inbox injection or file save)
- Monitor process cleaned up

### FAILURE:
- Not starting auto-reply monitor
- Sending unsolicited input while agent is actively working
- Not detecting completion (pane left running indefinitely)
- Capturing only partial output
- Not delivering result to caller
- Killing pane before capturing result

## FAILURE CLEANUP

If this step fails mid-execution, clean up before reporting the error:

```bash
# Stop the monitor if running
kill "$MONITOR_PID" 2>/dev/null

# Kill the pane only if YOU created it (PANE_TARGET captured this session)
tmux kill-pane -t "$PANE_TARGET" 2>/dev/null

echo "Cleanup complete. Dispatch failed — pane and monitor terminated."
```

Report the failure clearly: what step failed, what the pane output showed, and
whether the result file exists at `/tmp/model-dispatch-result-${AGENT_NAME}.txt`.
