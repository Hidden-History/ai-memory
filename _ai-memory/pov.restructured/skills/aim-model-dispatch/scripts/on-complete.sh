#!/bin/bash
# on-complete.sh — Write signal file when Claude Code session completes
set -uo pipefail
# Called as Claude Code hook or at session end
# Writes signal file for auto-reply-monitor to detect completion
#
# Usage: on-complete.sh <pane-id> [skill-dir] [agent-name]
#
# Environment variables:
#   MODEL_DISPATCH_SIGNAL_DIR - Override signal file directory (default: /tmp)
#   MODEL_DISPATCH_INBOX_INJECT - If set, also inject result to inbox

PANE_ID="${1:?Usage: on-complete.sh <pane-id> [skill-dir] [agent-name]}"
SKILL_DIR="${2:-}"
AGENT_NAME="${3:-model-agent}"

if ! [[ "$PANE_ID" =~ ^%[0-9]+$ ]]; then
    echo "Error: Invalid pane ID format: $PANE_ID (expected %N)" >&2
    exit 1
fi

SIGNAL_DIR="${MODEL_DISPATCH_SIGNAL_DIR:-/tmp}"
SIGNAL_FILE="${SIGNAL_DIR}/model-dispatch-signal-${PANE_ID}"

# Write completion signal
echo "DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$SIGNAL_FILE"
echo "Signal written to $SIGNAL_FILE"

# Optionally inject completion message to inbox
if [ -n "$SKILL_DIR" ] && [ -n "$AGENT_NAME" ] && [ -f "${SKILL_DIR}/scripts/inbox-inject.py" ]; then
  TEAM_DIR=$(ls -td ~/.claude/teams/*/config.json 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
  if [ -n "$TEAM_DIR" ]; then
    INBOX="${TEAM_DIR}/inboxes/team-lead.json"
    if [ -f "$INBOX" ]; then
      python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
        --inbox "$INBOX" \
        --from "${AGENT_NAME}" \
        --message "Session complete for pane ${PANE_ID}" \
        --color "green" 2>/dev/null || true
    fi
  fi
fi
