#!/usr/bin/env bash
# shellcheck shell=bash
# check_bmad_commands.sh — verify every /bmad-* command referenced in the
# aim-agent-dispatch tables resolves to an installed skill.
#
# Fire-only-if-missing: SILENT when all referenced commands resolve, fires loud
# (and non-zero) listing only the unresolved ones. There is no BMAD version
# manifest to compare against, so this checks command RESOLUTION, not versions.
#
# Graceful degrade: if NO bmad-* skills exist at the resolution root at all,
# BMAD is simply not installed here — report that once and exit 0 rather than
# flag every command as broken.
#
# Usage: check_bmad_commands.sh [--skill-md <file>] [--skills-dir <dir>]
#
# --skill-md <file>
#     SKILL.md whose tables are scanned for /bmad-* tokens.
#     Default: the aim-agent-dispatch SKILL.md next to this script.
# --skills-dir <dir>
#     Directory where installed skills live (one subdir per skill).
#     Default: ./.claude/skills (relative to CWD — the project/workspace root).
#
# Exit codes: 0 = all referenced commands resolve, or BMAD not installed (skip)
#             1 = one or more referenced commands do not resolve
#             2 = bad argument / missing input file
#
# Output routing: all output is net-new -> stderr; stdout stays empty.

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

skill_md="${SCRIPT_DIR}/../SKILL.md"
skills_dir="./.claude/skills"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skill-md)
            [[ $# -ge 2 ]] || { echo "check_bmad_commands: --skill-md requires a file" >&2; exit 2; }
            skill_md="$2"; shift 2 ;;
        --skills-dir)
            [[ $# -ge 2 ]] || { echo "check_bmad_commands: --skills-dir requires a dir" >&2; exit 2; }
            skills_dir="$2"; shift 2 ;;
        *)
            echo "check_bmad_commands: unknown argument: $1" >&2
            echo "Usage: check_bmad_commands.sh [--skill-md <file>] [--skills-dir <dir>]" >&2
            exit 2 ;;
    esac
done

if [[ ! -f "$skill_md" ]]; then
    echo "check_bmad_commands: SKILL.md not found: $skill_md" >&2
    exit 2
fi

# Extract referenced /bmad-* commands. Trailing-dash tokens (e.g. the
# "/bmad-agent-<name>" prose placeholder -> "/bmad-agent-") are placeholders,
# not commands — drop them.
mapfile -t commands < <(
    grep -oE '/bmad-[a-z0-9-]+' "$skill_md" \
        | grep -vE -- '-$' \
        | sort -u
)

# Graceful degrade: if the resolution root has no bmad-* skills at all, BMAD is
# not installed here — do not flag every command.
if ! compgen -G "${skills_dir}/bmad-*" >/dev/null 2>&1; then
    echo "check_bmad_commands: BMAD not installed at expected path (${skills_dir}/bmad-*) — skipping command-resolution check." >&2
    exit 0
fi

unresolved=()
for cmd in "${commands[@]}"; do
    name="${cmd#/}"
    if [[ ! -d "${skills_dir}/${name}" ]]; then
        unresolved+=("$cmd")
    fi
done

if [[ ${#unresolved[@]} -gt 0 ]]; then
    echo "check_bmad_commands: ${#unresolved[@]} referenced BMAD command(s) do not resolve to an installed skill under ${skills_dir}/:" >&2
    for cmd in "${unresolved[@]}"; do
        echo "  unresolved: ${cmd}  (expected ${skills_dir}/${cmd#/}/)" >&2
    done
    echo "Fix the table row(s) in ${skill_md} or install the missing skill(s)." >&2
    exit 1
fi

exit 0
