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
# Exit codes: 0 = workspace-root markers present, or present except _bmad/ (degraded)
#             1 = workspace-root markers absent (strict only)
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

    # _bmad/ is shipped by BMAD, not by AI-Memory, so its absence is the normal
    # state of a correct workspace root on a machine without BMAD. It is a
    # degraded state, not CWD drift: reporting it as drift names the wrong
    # cause, offers no remedy, and aborts dispatches that never needed BMAD.
    local root_ok="false" bmad_present="false"
    if test -d "$ai_memory_dir" && test -d "$oversight_dir"; then
        root_ok="true"
    fi
    if test -d "$bmad_dir"; then
        bmad_present="true"
    fi

    if [[ "$variant" == "strict" ]]; then
        # Matches Forms 1+2: stdout parity preserved (inline forms used plain echo).
        if [[ "$root_ok" != "true" ]]; then
            echo "FAIL: CWD is not workspace root. Expected _ai-memory/ and oversight/ present (_bmad/ is BMAD's own and is not required here)."
            echo "CWD: $(pwd)"
            echo "Aborting dispatch. cd to workspace root and re-invoke."
            return 1
        fi
        if [[ "$bmad_present" != "true" ]]; then
            echo "DEGRADED: dependency 'bmad' is unavailable (no ${bmad_dir}). Workspace root is correct; dispatch that does not need BMAD is unaffected."
            echo "Install BMAD to enable BMAD-dependent dispatch (upstream source: DEPENDENCIES.md in the Parzival tree)."
            return 0
        fi
        echo "OK: workspace root ($(pwd))"
    else
        # loose: matches Form 3; stdout parity preserved. Always returns 0.
        if [[ "$root_ok" != "true" ]]; then
            echo "FAIL: not workspace root (missing _ai-memory/ or oversight/; _bmad/ is not required here)"
        elif [[ "$bmad_present" != "true" ]]; then
            echo "DEGRADED: dependency 'bmad' is unavailable (no ${bmad_dir}); workspace root is correct."
            echo "Install BMAD to enable BMAD-dependent dispatch (upstream source: DEPENDENCIES.md)."
        else
            echo "OK: workspace root"
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
