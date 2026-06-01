#!/usr/bin/env bash
# shellcheck shell=bash
# check_api_key.sh — verify or load a provider's API key into the environment.
#
# Usage (sourced):   source check_api_key.sh; check_api_key --provider <name>
# Usage (executed):  bash check_api_key.sh --provider <name>
#
# Behavior (consolidates 5 inline forms from api-dispatch/**/step-*-execute.md):
#   - If the provider's env var is already set (non-empty): no-op, return/exit 0.
#   - If the env var is unset/empty but ~/.{provider}-token exists: load it, return/exit 0.
#   - Otherwise: echo error to stdout (byte-identical to inline forms), return/exit 1.
#
# Return/exit codes:
#   0  key available (already in env or loaded from token file)
#   1  key not found
#   2  bad arguments
#
# Output routing (TASK-071-wide rule):
#   stdout — inline-equivalent output (error message); parity with inline forms.
#   stderr — net-new output only (arg validation errors; no inline equivalent).
#
# Supported providers (explicit mapping for exact label parity):
#   openrouter  ->  OPENROUTER_API_KEY / ~/.openrouter-token / "OpenRouter"
#   (generic fallback: <UPPER>_API_KEY / ~/.{provider}-token / raw name)

# ---------------------------------------------------------------------------
# check_api_key ARGS... — main logic; safe to source (uses return, not exit).
# When the key is loaded from a token file, it is set as a global exported
# variable so it persists in the calling shell after the source call.
# ---------------------------------------------------------------------------
check_api_key() {
    local _ck_provider=""
    local _ck_var _ck_file _ck_label _ck_val

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --provider)
                if [[ $# -lt 2 ]]; then
                    echo "check_api_key.sh: --provider requires a value" >&2
                    return 2
                fi
                _ck_provider="$2"
                shift 2
                ;;
            *)
                echo "check_api_key.sh: unknown argument: $1" >&2
                return 2
                ;;
        esac
    done

    if [[ -z "$_ck_provider" ]]; then
        echo "check_api_key.sh: --provider required" >&2
        return 2
    fi

    case "$_ck_provider" in
        openrouter)
            _ck_var="OPENROUTER_API_KEY"
            _ck_file="$HOME/.openrouter-token"
            _ck_label="OpenRouter"
            ;;
        *)
            _ck_var="$(printf '%s' "$_ck_provider" | tr '[:lower:]' '[:upper:]')_API_KEY"
            _ck_file="$HOME/.${_ck_provider}-token"
            _ck_label="$_ck_provider"
            ;;
    esac

    if [[ -z "${!_ck_var:-}" ]]; then
        if [[ -f "$_ck_file" ]]; then
            _ck_val="$(cat "$_ck_file")"
            # declare -gx: create/update at global scope so the variable persists
            # in the calling shell when this script is sourced.
            # shellcheck disable=SC2163
            declare -gx "${_ck_var}=${_ck_val}"
        else
            # Inline-equivalent output: echo to stdout to match the 5 inline forms.
            echo "Error: No ${_ck_label} API key. Run: model-dispatch install"
            return 1
        fi
    fi
}

# ---------------------------------------------------------------------------
# Execute-only path: strict mode + IFS scoped to this block; never leaks to
# a calling shell. Non-zero return from check_api_key exits via set -e.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
    IFS=$'\n\t'
    check_api_key "$@"
fi
