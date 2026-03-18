#!/usr/bin/env bash
# Auto-reply monitor v8: inotifywait signal + diff-based idle detection
#
# Combines instant signal file detection via inotifywait with polling fallback.
# Also detects permission dialogs and forwards them to team lead.
#
# Usage: auto-reply-monitor.sh <pane-target> <skill-dir> [agent-name] [backend]

set -uo pipefail

# Graceful shutdown on signals
trap 'echo "Monitor received signal, exiting."; exit 0' SIGTERM SIGINT SIGHUP

PANE_TARGET="$1"
SKILL_DIR="$2"
# Validate and canonicalize SKILL_DIR
if [ ! -d "${SKILL_DIR}" ]; then
  echo "Error: SKILL_DIR is not a directory" >&2
  exit 1
fi
SKILL_DIR=$(cd "${SKILL_DIR}" && pwd) || {
  echo "Error: Cannot resolve SKILL_DIR" >&2
  exit 1
}
if [ ! -f "${SKILL_DIR}/scripts/inbox-inject.py" ]; then
  echo "Error: Invalid SKILL_DIR - missing scripts/inbox-inject.py" >&2
  exit 1
fi
AGENT_NAME="${3:-model-agent}"
BACKEND="${4:-claude}"

# Validate AGENT_NAME format
if [[ ! "$AGENT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Error: Invalid agent name. Use only letters, numbers, hyphens, and underscores." >&2
  exit 1
fi

# Validate BACKEND format
if [[ ! "$BACKEND" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Error: Invalid backend. Use only letters, numbers, hyphens, and underscores." >&2
  exit 1
fi

POLL_INTERVAL="${POLL_INTERVAL:-5}"
IDLE_CHECKS_NEEDED=2
idle_count=0
has_seen_activity=false
permission_notified=false
PREV_CAPTURE=""
SIGNAL_FILE="/tmp/model-dispatch-signal-${PANE_TARGET}"

if [ -z "$PANE_TARGET" ] || [ -z "$SKILL_DIR" ]; then
  echo "Usage: $0 <pane_id> <skill_dir> [agent_name] [backend]"
  exit 1
fi

# Validate pane ID format (tmux uses %N format)
if [[ ! "$PANE_TARGET" =~ ^%[0-9]+$ ]]; then
  echo "Error: Invalid pane ID format '${PANE_TARGET}'. Expected %N (e.g., %42)." >&2
  exit 1
fi

# Find team inbox
TEAM_DIR=$(ls -td ~/.claude/teams/*/config.json 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
INBOX=""
if [ -n "$TEAM_DIR" ]; then
  INBOX="${TEAM_DIR}/inboxes/team-lead.json"
else
  echo "No team context found. Will save result to file only."
fi

inject_message() {
  local from="$1"
  local message="$2"
  local color="${3:-purple}"
  # Validate color against allowlist
  case "$color" in
    blue|green|orange|purple|red|yellow) ;;
    *) color="purple" ;;
  esac
  if [ -n "$INBOX" ] && [ -f "$INBOX" ] && [ -f "${SKILL_DIR}/scripts/inbox-inject.py" ]; then
    python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
      --inbox "$INBOX" --from "$from" --message "$message" --color "$color"
  fi
}

echo "Monitoring pane $PANE_TARGET (backend: $BACKEND) for completion..."

while true; do
  # ─── INOTIFYWAIT SIGNAL DETECTION (instant, ~2 sec timeout) ─────────
  if command -v inotifywait &>/dev/null; then
    if [ -f "$SIGNAL_FILE" ]; then
      # Signal file exists - agent may have completed
      SIGNAL_CONTENT=$(cat "$SIGNAL_FILE" 2>/dev/null || echo "")
      if echo "$SIGNAL_CONTENT" | grep -q "^DONE"; then
        echo "Signal file detected: agent completed"
        # Small delay to ensure pane has finished writing output
        sleep 0.5
        # Fall through to capture result below
      fi
    else
      # No signal file yet - try inotifywait with 2-second timeout
      mkdir -p "$(dirname "$SIGNAL_FILE")" && touch "$SIGNAL_FILE" 2>/dev/null
      if inotifywait -t 2 -e close_write "$SIGNAL_FILE" 2>/dev/null; then
        SIGNAL_CONTENT=$(cat "$SIGNAL_FILE" 2>/dev/null || echo "")
        if echo "$SIGNAL_CONTENT" | grep -q "^DONE"; then
          echo "Signal file detected via inotifywait: agent completed"
          sleep 0.5
          # Fall through to capture result
        fi
      fi
      # inotifywait timeout or no signal - continue to polling
    fi
  fi

  # ─── DIFF-BASED IDLE DETECTION (fallback) ─────────────────────────
  sleep "$POLL_INTERVAL"

  # Capture current pane state
  CURRENT=$(timeout 5 tmux capture-pane -t "$PANE_TARGET" -p 2>/dev/null | \
    sed 's/\x1b\[[0-9;]*[mGKHF]//g') || true

  # If capture failed or empty and we never saw activity, pane may be gone
  if [ -z "$CURRENT" ]; then
    if ! tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -q "^${PANE_TARGET}$"; then
      echo "Pane $PANE_TARGET no longer exists. Exiting."
      exit 1
    fi
  fi

  # ─── PERMISSION DIALOG DETECTION ────────────────────────────────
  if echo "$CURRENT" | grep -qE '(Esc to cancel|Tab to amend)' 2>/dev/null; then
    has_seen_activity=true
    idle_count=0

    if [ "$permission_notified" = false ]; then
      PERM_TEXT=$(echo "$CURRENT" | grep -B2 -A2 -E '(Esc to cancel|Tab to amend)' | head -5)
      echo "Permission dialog detected. Notifying team lead."
      inject_message "${AGENT_NAME}@${BACKEND}" "PERMISSION NEEDED in pane $PANE_TARGET ($BACKEND backend):

$PERM_TEXT

Approve from team lead: send Enter to pane $PANE_TARGET" "orange"
      permission_notified=true
    fi

    PREV_CAPTURE="$CURRENT"
    continue
  else
    if [ "$permission_notified" = true ]; then
      echo "Permission dialog cleared."
      permission_notified=false
    fi
  fi

  # ─── DIFF-BASED IDLE DETECTION ─────────────────────────────────
  if [ -z "$PREV_CAPTURE" ]; then
    PREV_CAPTURE="$CURRENT"
    continue
  fi

  if [ "$CURRENT" = "$PREV_CAPTURE" ]; then
    # Pane content unchanged — might be idle
    idle_count=$((idle_count + 1))
  else
    # Content changed — agent is working
    idle_count=0
    if [ "$has_seen_activity" = false ]; then
      has_seen_activity=true
      echo "Activity detected."
    fi
  fi

  PREV_CAPTURE="$CURRENT"

  # Must have seen activity before declaring done
  if [ "$has_seen_activity" = false ]; then
    continue
  fi

  # Need consecutive unchanged captures to confirm done
  if [ "$idle_count" -ge "$IDLE_CHECKS_NEEDED" ]; then
    echo "Pane unchanged for $((idle_count * POLL_INTERVAL))s after activity. Agent done."

    # Capture the full pane content for result
    RESULT=$(tmux capture-pane -t "$PANE_TARGET" -p -S -200 2>/dev/null | \
      sed 's/\x1b\[[0-9;]*[mGKHF]//g' | grep -v "^$")

    # Save to secure temp file (mktemp prevents symlink attacks, chmod 600 restricts access)
    cleanup_temp() { rm -f "$RESULT_FILE" 2>/dev/null; }
    trap cleanup_temp EXIT
    RESULT_FILE=$(mktemp "/tmp/model-dispatch-result-${AGENT_NAME}-${BACKEND}-XXXXXX.txt") || {
      echo "Error: Failed to create temp file"
      exit 1
    }
    chmod 600 "$RESULT_FILE"
    echo "$RESULT" > "$RESULT_FILE"
    echo "Result saved to ${RESULT_FILE}"

    # Inject final result into team lead inbox
    inject_message "${AGENT_NAME}@${BACKEND}" "$RESULT" "purple"
    echo "Result injected to team lead inbox"

    break
  fi
done

echo "Auto-reply monitor complete."
