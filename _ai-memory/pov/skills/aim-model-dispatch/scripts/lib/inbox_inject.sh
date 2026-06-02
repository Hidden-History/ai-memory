#!/usr/bin/env bash
# shellcheck shell=bash
# inbox_inject.sh — inject a message into a Claude Code teammate inbox.
#
# Usage:
#   inbox_inject.sh --inbox-path PATH --mode {capture|deliver} \
#                   --from NAME [--message TEXT] [--color COLOR]
#
# Modes:
#   deliver  Always injects; inbox directory+file are created if absent.
#   capture  Injects only when the inbox file already exists; no-op otherwise.
#
# Message source: --message TEXT, or stdin when --message is omitted.
#
# Exit codes:
#   0  Success, or silent no-op (capture + absent inbox)
#   1  Argument/usage error
#   N  inbox-inject.py exit code propagated on inject failure

# ---------------------------------------------------------------------------
# Execute-guard: strict mode + main logic only when run directly, not sourced.
# Unconditional set -euo pipefail at file scope would mutate the caller's shell.
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
    IFS=$'\n\t'

    # die: write diagnostic to stderr and exit 1.
    # Defined inside execute-guard (BP-016 D1): no file-scope exit when sourced.
    _inbox_inject_die() {
        printf 'inbox_inject.sh: %s\n' "$*" >&2
        exit 1
    }

    # Locate sibling inbox-inject.py relative to this script's directory
    _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    _INJECT_PY="${_SCRIPT_DIR}/../inbox-inject.py"
    [[ -f "${_INJECT_PY}" ]] || _inbox_inject_die "inbox-inject.py not found: ${_INJECT_PY}"

    # ---- Argument parsing ----
    _inbox_path=""
    _mode=""
    _from=""
    _message=""
    _message_given=0
    _color="blue"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --inbox-path)
                [[ $# -ge 2 ]] || _inbox_inject_die "--inbox-path requires a value"
                _inbox_path="$2"
                shift 2 ;;
            --mode)
                [[ $# -ge 2 ]] || _inbox_inject_die "--mode requires a value"
                _mode="$2"
                shift 2 ;;
            --from)
                [[ $# -ge 2 ]] || _inbox_inject_die "--from requires a value"
                _from="$2"
                shift 2 ;;
            --message)
                [[ $# -ge 2 ]] || _inbox_inject_die "--message requires a value"
                _message="$2"
                _message_given=1
                shift 2 ;;
            --color)
                [[ $# -ge 2 ]] || _inbox_inject_die "--color requires a value"
                _color="$2"
                shift 2 ;;
            *)
                _inbox_inject_die "unknown argument: $1" ;;
        esac
    done

    # ---- Required-arg validation ----
    [[ -n "${_inbox_path}" ]] || _inbox_inject_die "missing required argument: --inbox-path"
    [[ -n "${_mode}" ]]       || _inbox_inject_die "missing required argument: --mode"
    [[ -n "${_from}" ]]       || _inbox_inject_die "missing required argument: --from"

    case "${_mode}" in
        capture|deliver) ;;
        *) _inbox_inject_die "invalid --mode '${_mode}': must be 'capture' or 'deliver'" ;;
    esac

    # ---- Message source: --message or stdin ----
    if [[ "${_message_given}" -eq 0 ]]; then
        _message="$(cat)"
    fi

    # ---- capture mode: no-op when inbox file is absent ----
    if [[ "${_mode}" == "capture" ]] && [[ ! -f "${_inbox_path}" ]]; then
        exit 0
    fi

    # ---- Delegate JSON write to inbox-inject.py ----
    python3 "${_INJECT_PY}" \
        --inbox   "${_inbox_path}" \
        --from    "${_from}" \
        --message "${_message}" \
        --color   "${_color}"
fi
