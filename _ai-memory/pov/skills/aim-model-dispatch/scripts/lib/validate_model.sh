#!/usr/bin/env bash
# shellcheck shell=bash
# validate_model.sh — pre-spawn model validation for aim-model-dispatch
#
# Validates MODEL against the backend catalog BEFORE creating a tmux pane.
# An invalid model name wastes a pane slot and produces a cryptic runtime error.
# Fail-fast here with a clear catalog-reference message.
#
# Usage:
#   validate_model.sh --model <id> --backend <name> [--skill-dir <path>]
#
# Exit codes:
#   0  validation passed, or skipped (empty model / gemini backend / no catalog for backend)
#   1  catalog file missing from disk, or model not found in catalog
#   2  usage error (missing required argument)

_vm_die() {
  echo "$*" >&2
  exit 2
}

_vm_run() {
  local model="" backend="" skill_dir=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --model)     model="$2";     shift 2 ;;
      --backend)   backend="$2";   shift 2 ;;
      --skill-dir) skill_dir="$2"; shift 2 ;;
      *) _vm_die "ERROR: unknown argument '$1'" ;;
    esac
  done

  [[ -n "${backend}" ]] || _vm_die "ERROR: --backend is required"

  # Default skill_dir: 2 levels up from this script (scripts/lib/ -> scripts/ -> skill root)
  if [[ -z "${skill_dir}" ]]; then
    local _script_dir
    _script_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
    skill_dir="$(dirname "$(dirname "${_script_dir}")")"
  fi

  # Skip validation when model is empty (native Claude default) or backend=gemini
  # (Gemini CLI handles its own model selection interactively).
  if [[ -n "${model}" ]] && [[ "${backend}" != "gemini" ]]; then
    local catalog_file=""
    case "${backend}" in
      ollama)      catalog_file="${skill_dir}/references/models-ollama.md" ;;
      openrouter)  catalog_file="${skill_dir}/references/models-openrouter.md" ;;
    esac
    if [[ -n "${catalog_file}" ]]; then
      if [[ ! -f "${catalog_file}" ]]; then
        echo "FAIL: catalog file for backend '${backend}' expected at ${catalog_file} but not found."
        echo "This is a deployment issue — reinstall or verify model-dispatch wrappers are installed."
        exit 1
      fi
      if ! grep -Fq "\`${model}\`" "${catalog_file}"; then
        echo "FAIL: model '${model}' not found in catalog ${catalog_file}."
        echo "Available models listed in that file. Correct the dispatch plan and re-invoke."
        exit 1
      fi
      echo "OK: model '${model}' validated against ${backend} catalog"
    else
      echo "WARN: no catalog file for backend '${backend}' -- skipping pre-spawn validation"
    fi
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail
  IFS=$'\n\t'
  _vm_run "$@"
fi
