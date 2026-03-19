#!/usr/bin/env bash
# auto-approve-hook.sh — PermissionRequest hook for dispatched agents
#
# Auto-approves permission requests and optionally notifies the team lead.
# Install as a PermissionRequest hook in user or project settings.
#
# NOTE: No `set -e` — hooks MUST always output valid JSON regardless of errors.
#
# What it does:
#   1. Reads the PermissionRequest JSON from stdin
#   2. Returns {"behavior": "allow"} to auto-approve
#   3. Injects a notification to the team lead inbox (if available)
#
# Install in ~/.claude/settings.json or .claude/settings.local.json:
#
#   {
#     "hooks": {
#       "PermissionRequest": [{
#         "matcher": "",
#         "hooks": [{
#           "type": "command",
#           "command": "/path/to/auto-approve-hook.sh"
#         }]
#       }]
#     }
#   }

INPUT=$(head -c 65536)
if [ ${#INPUT} -ge 65536 ]; then
  cat <<'TRUNCEOF'
{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}
TRUNCEOF
  exit 0
fi

# Only log tool_name — tool_input may contain secrets
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"' | tr -cd '[:alnum:]-_.()')

# Extract agent name from env var or default
AGENT_NAME="${AUTO_APPROVE_AGENT:-dispatch-agent}"
BACKEND_NAME="${AUTO_APPROVE_BACKEND:-claude}"

# Notify team lead inbox (best-effort, non-blocking)
TEAM_DIR=$(ls -td ~/.claude/teams/*/config.json 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)
if [ -n "$TEAM_DIR" ]; then
  INBOX="${TEAM_DIR}/inboxes/team-lead.json"
  SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
  LOG_DIR="${SKILL_DIR}/logs"
  mkdir -p "$LOG_DIR" 2>/dev/null || echo "Warning: Could not create log directory $LOG_DIR" >&2
  if [ -f "${SKILL_DIR}/scripts/inbox-inject.py" ] && [ -f "$INBOX" ]; then
    python3 "${SKILL_DIR}/scripts/inbox-inject.py" \
      --inbox "$INBOX" \
      --from "${AGENT_NAME}@${BACKEND_NAME}" \
      --message "AUTO-APPROVED: ${TOOL_NAME}" \
      --color "blue" 2>>"${LOG_DIR}/hook-errors.log" &
  fi
fi

# Auto-approve the permission request
cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "allow"
    }
  }
}
EOF
