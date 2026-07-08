#!/usr/bin/env bash
# shellcheck shell=bash
# preflight_agent_teams.sh — Agent Teams prerequisite guard for parallel-team dispatch.
# Dual-use: source for preflight_agent_teams(); execute directly as CLI.
#
# Fire-only-if-missing: SILENT on the happy path (both prerequisites satisfied),
# fires loud with remediation only when a prerequisite is missing.
#
# Enforces the parallel-team prerequisites already documented as prose in:
#   _ai-memory/pov/constraints/global/GC-19-spawn-agents-as-teammates.md:21
#   aim-model-dispatch/workflows/claude-native/workflow.md (Prerequisites)
# Turns that checklist into a runtime gate; does not invent new criteria.
#
# Usage: preflight_agent_teams [--settings <file>]
#
# --settings <file>
#     Read teammateMode from this exact settings file only (test hook).
#     Omit to resolve via the standard precedence chain (most-specific first):
#       ./.claude/settings.local.json
#       ./.claude/settings.json
#       ${HOME}/.claude/settings.json
#
# Checks:
#   1. env CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS == "1"   (hard requirement)
#   2. teammateMode is a team mode: unset (default "auto"), "auto", or "tmux".
#      Fires only on an explicit non-team mode ("in-process").
#
# Exit codes: 0 = prerequisites satisfied (silent)
#             1 = a prerequisite is missing (loud remediation on stderr)
#             2 = bad argument
#
# Output routing (TASK-071-wide rule): this check has no inline equivalent, so
# all output is net-new -> stderr. stdout stays empty in every case.

# --------------------------------------------------------------------------
# _read_teammate_mode — echo the teammateMode value from the first settings
# file (in precedence order) that defines it; empty if none define it.
# --------------------------------------------------------------------------
_read_teammate_mode() {
    local explicit="$1"
    local files=()
    if [[ -n "$explicit" ]]; then
        files=("$explicit")
    else
        files=(
            "./.claude/settings.local.json"
            "./.claude/settings.json"
            "${HOME}/.claude/settings.json"
        )
    fi

    local f line
    for f in "${files[@]}"; do
        [[ -f "$f" ]] || continue
        line=$(grep -oE '"teammateMode"[[:space:]]*:[[:space:]]*"[^"]*"' "$f" 2>/dev/null | head -n1)
        if [[ -n "$line" ]]; then
            # Extract the quoted value after the colon.
            printf '%s' "$line" | sed -E 's/.*:[[:space:]]*"([^"]*)".*/\1/'
            return 0
        fi
    done
    return 0
}

# --------------------------------------------------------------------------
# preflight_agent_teams — main guard (safe to source; uses return, not exit).
# --------------------------------------------------------------------------
preflight_agent_teams() {
    local settings_file=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --settings)
                if [[ $# -lt 2 ]]; then
                    echo "preflight_agent_teams: --settings requires a file argument" >&2
                    echo "Usage: preflight_agent_teams [--settings <file>]" >&2
                    return 2
                fi
                settings_file="$2"
                shift 2
                ;;
            *)
                echo "preflight_agent_teams: unknown argument: $1" >&2
                echo "Usage: preflight_agent_teams [--settings <file>]" >&2
                return 2
                ;;
        esac
    done

    local missing=0

    # Check 1: the experimental Agent Teams flag must be enabled.
    if [[ "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-}" != "1" ]]; then
        {
            echo "[preflight] Agent Teams not enabled: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS is not \"1\"."
            echo "  Parallel-team dispatch requires it (GC-19; claude-native workflow Prerequisites)."
            echo "  Enable it in settings.json \"env\", or export it:"
            echo "      export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"
        } >&2
        missing=1
    fi

    # Check 2: teammateMode must be a split-pane team mode (or unset -> default auto).
    local mode
    mode=$(_read_teammate_mode "$settings_file")
    if [[ -n "$mode" && "$mode" != "auto" && "$mode" != "tmux" ]]; then
        {
            echo "[preflight] teammateMode is \"${mode}\" — split-pane agent teams are disabled."
            echo "  Set \"teammateMode\": \"auto\" (or \"tmux\") in .claude/settings.json for parallel-team dispatch."
        } >&2
        missing=1
    fi

    if [[ "$missing" -ne 0 ]]; then
        return 1
    fi
    return 0
}

# --------------------------------------------------------------------------
# Execute-only path: strict mode + IFS scoped here, never leaks to a caller.
# --------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
    IFS=$'\n\t'
    preflight_agent_teams "$@"
fi
