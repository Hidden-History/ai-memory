#!/usr/bin/env bash
# shellcheck shell=bash
# cwd_sentinel.sh — workspace root guard for aim-model-dispatch dispatchers.
# Dual-use: source for cwd_sentinel(); execute directly as CLI.
#
# Usage: cwd_sentinel [--required-root <path>] [--variant strict|loose]
#
# --required-root <path>
#     Directory to test for workspace-root markers (_ai-memory/, _bmad/, oversight/).
#     Omit to test markers relative to the current working directory.
# --variant strict  (default)
#     Exit 1 on failure; 3 lines to stdout. Matches Forms 1+2:
#       bmad-dispatch/steps/step-02-launch-and-activate.md:35-41
#       tmux-dispatch/steps/step-02-launch-pane.md:35-41 (byte-identical)
# --variant loose
#     Always exits 0; 1 informational line to stdout. Matches Form 3:
#       claude-native/workflow.md:65-67
#
# Exit codes: 0 = markers present (both variants)
#             1 = markers absent (strict only)
#             2 = bad argument
#
# Output routing (TASK-071-wide rule):
#   stdout — inline-equivalent output (OK/FAIL messages); parity with inline forms.
#   stderr — net-new output only (arg validation errors; no inline equivalent).
#
# Scope: dev workspace dispatches only. End-user installs (~/.ai-memory/) launch
# via skill installer wrappers and do not require this sentinel.

# --------------------------------------------------------------------------
# cwd_sentinel — main guard function (safe to source; uses return, not exit).
# --------------------------------------------------------------------------
cwd_sentinel() {
    local required_root=""
    local variant="strict"
    local ai_memory_dir bmad_dir oversight_dir

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --required-root)
                if [[ $# -lt 2 ]]; then
                    echo "cwd_sentinel: --required-root requires a path argument" >&2
                    echo "Usage: cwd_sentinel [--required-root <path>] [--variant strict|loose]" >&2
                    return 2
                fi
                required_root="$2"
                shift 2
                ;;
            --variant)
                if [[ $# -lt 2 ]]; then
                    echo "cwd_sentinel: --variant requires strict or loose" >&2
                    echo "Usage: cwd_sentinel [--required-root <path>] [--variant strict|loose]" >&2
                    return 2
                fi
                variant="$2"
                shift 2
                ;;
            *)
                echo "cwd_sentinel: unknown argument: $1" >&2
                echo "Usage: cwd_sentinel [--required-root <path>] [--variant strict|loose]" >&2
                return 2
                ;;
        esac
    done

    if [[ "$variant" != "strict" && "$variant" != "loose" ]]; then
        echo "cwd_sentinel: unknown --variant '${variant}': must be strict or loose" >&2
        echo "Usage: cwd_sentinel [--required-root <path>] [--variant strict|loose]" >&2
        return 2
    fi

    # Resolve marker paths: absolute when --required-root given, relative to CWD otherwise.
    if [[ -n "$required_root" ]]; then
        ai_memory_dir="${required_root}/_ai-memory"
        bmad_dir="${required_root}/_bmad"
        oversight_dir="${required_root}/oversight"
    else
        ai_memory_dir="_ai-memory"
        bmad_dir="_bmad"
        oversight_dir="oversight"
    fi

    if [[ "$variant" == "strict" ]]; then
        # Matches Forms 1+2: stdout parity preserved (inline forms used plain echo).
        if ! { test -d "$ai_memory_dir" && test -d "$bmad_dir" && test -d "$oversight_dir"; }; then
            echo "FAIL: CWD is not workspace root. Expected _ai-memory/, _bmad/, oversight/ all present."
            echo "CWD: $(pwd)"
            echo "Aborting dispatch. cd to workspace root and re-invoke."
            return 1
        fi
        echo "OK: workspace root ($(pwd))"
    else
        # loose: matches Form 3; stdout parity preserved. Always returns 0.
        if test -d "$ai_memory_dir" && test -d "$bmad_dir" && test -d "$oversight_dir"; then
            echo "OK: workspace root"
        else
            echo "FAIL: not workspace root (missing one of _ai-memory/, _bmad/, oversight/)"
        fi
    fi
}

# --------------------------------------------------------------------------
# Execute-only path: strict mode + IFS scoped here, never leaks to a caller.
# --------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
    IFS=$'\n\t'
    cwd_sentinel "$@"
fi
