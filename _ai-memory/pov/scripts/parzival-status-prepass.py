#!/usr/bin/env python3
"""
parzival-status-prepass.py — Extract structured project state as JSON.

Reads project-status.md and blockers-log.md and outputs
a single JSON object to stdout. Replaces LLM-driven file reads at session start.

Outputs:
  {
    "phase":                    string | null,
    "active_task":              string | null,
    "open_issues_count":        int,
    "open_blockers_count":      int,
    "last_session_summary":     string | null,
    "active_plan_file":         string | null,
    "baseline_complete":        bool,
    "latest_handoff_path":      string | null,   # L6-F5
    "recommended_next_workflow": string | null    # L6-F6
  }

Usage:
  python parzival-status-prepass.py [--root <project_root>]

Integration: session start step-01-load-context.md, before file reads.
Savings: 800-1,500 tokens/session.
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Phase -> workflow file path (relative to pov/ root)
# Source: dev_ai-memory_Copy/pov/workflows/WORKFLOW-MAP.md
PHASE_WORKFLOW_MAP = {
    "discovery":    "workflows/phases/discovery/workflow.md",
    "architecture": "workflows/phases/architecture/workflow.md",
    "planning":     "workflows/phases/planning/workflow.md",
    "execution":    "workflows/phases/execution/workflow.md",
    "integration":  "workflows/phases/integration/workflow.md",
    "release":      "workflows/phases/release/workflow.md",
    "maintenance":  "workflows/phases/maintenance/workflow.md",
    "complete":     None,   # prompt user: new feature, bug, or new project?
}

# YAML scalar values that represent null
_YAML_NULL_VALUES = frozenset(("null", "~", "none", ""))


def _normalize_yaml_null(val):
    """Return None if val is a YAML null representation, else return val unchanged."""
    if val is not None and val.lower().strip() in _YAML_NULL_VALUES:
        return None
    return val


def _extract_block_scalar(content, field_name):
    """Extract a YAML block scalar (field: |\\n  indented text...).

    Stops at the next top-level YAML key (non-indented word followed by colon)
    or end of string to prevent over-capture.
    """
    pattern = rf'^{re.escape(field_name)}:\s*\|\s*\n(.*?)(?=^\w[\w _-]*:|\Z)'
    m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not m:
        return None
    raw_lines = m.group(1).split('\n')
    # Detect minimum indent from non-empty lines
    non_empty = [line for line in raw_lines if line.strip()]
    if not non_empty:
        return None
    min_indent = min(len(line) - len(line.lstrip()) for line in non_empty)
    stripped = [line[min_indent:] if len(line) >= min_indent else line for line in raw_lines]
    return '\n'.join(stripped).strip()


def parse_project_status(path):
    """Parse project-status.md and return a dict of extracted fields."""
    result = {
        "phase": None,
        "active_task": None,
        "open_issues_count": 0,
        "last_session_summary": None,
        "baseline_complete": False,
        "active_plan_file": None,
    }

    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        print(f"ERROR: Cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)

    m = re.search(r'^current_phase:\s*(.+)$', content, re.MULTILINE)
    if m:
        result["phase"] = _normalize_yaml_null(m.group(1).strip())

    m = re.search(r'^active_task:\s*(.+)$', content, re.MULTILINE)
    if m:
        result["active_task"] = _normalize_yaml_null(m.group(1).strip())

    m = re.search(r'^open_issues:\s*(\d+)', content, re.MULTILINE)
    if m:
        result["open_issues_count"] = int(m.group(1))

    m = re.search(r'^baseline_complete:\s*(true|false|yes|no|on|off)', content, re.MULTILINE | re.IGNORECASE)
    if m:
        result["baseline_complete"] = m.group(1).lower() in ("true", "yes", "on")

    result["last_session_summary"] = _extract_block_scalar(content, "last_session_summary")

    # active_plan_file: scan notes block for PLAN-*.md references; take last (most recent).
    # Design choice: autodiscovery avoids requiring a dedicated YAML field, keeping
    # project-status.md schema flexible across project phases.
    notes_text = _extract_block_scalar(content, "notes") or ""
    plan_refs = re.findall(r'PLAN-[\w\-]+\.md', notes_text)
    if plan_refs:
        result["active_plan_file"] = plan_refs[-1]

    return result


def count_open_blockers(blockers_path):
    """Count active (unresolved) blockers in oversight/tracking/blockers-log.md."""
    if not blockers_path.exists():
        return 0

    try:
        content = blockers_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return 0

    # Isolate the ## Active Blockers section
    m = re.search(r'## Active Blockers\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
    if not m:
        return 0
    section = m.group(1).strip()

    # Explicit "None" signal
    if not section or re.search(r'\*None', section, re.IGNORECASE):
        return 0

    # Count BLK-NNN references (table rows or detail headers)
    blk_ids = set(re.findall(r'BLK-\d+', section))
    if blk_ids:
        return len(blk_ids)

    # Fallback: count non-empty, non-separator content lines
    lines = [line for line in section.split('\n')
             if line.strip() and not line.startswith('#')
             and not re.match(r'\|[-|: ]+\|', line)]
    return len(lines)


def find_latest_handoff(session_logs_dir):
    """Return absolute path of the most recently modified SESSION_HANDOFF_*.md file."""
    path = Path(session_logs_dir)
    if not path.exists():
        return None
    handoffs = list(path.glob("SESSION_HANDOFF_*.md"))
    if not handoffs:
        return None
    return str(max(handoffs, key=lambda p: p.stat().st_mtime))


def recommend_next_workflow(phase, baseline_complete):
    """Return the recommended next workflow path for the current phase."""
    if not baseline_complete:
        return "workflows/init/existing/workflow.md"
    if phase is None:
        return "workflows/init/existing/workflow.md"
    phase_key = phase.lower().strip()
    wf = PHASE_WORKFLOW_MAP.get(phase_key)
    if wf is None and phase_key == "complete":
        return None   # caller should prompt user
    return wf or "workflows/init/existing/workflow.md"


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured project state as JSON (parzival-status-prepass)"
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root directory (default: current directory)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()

    # Graceful degradation: init workflows may run before project-status.md exists.
    # Return a null-state JSON rather than failing, so session-start can offer init routing.
    status_path = root / "project-status.md"
    if not status_path.exists():
        print(json.dumps({
            "phase":                    None,
            "active_task":              None,
            "open_issues_count":        0,
            "open_blockers_count":      0,
            "last_session_summary":     None,
            "active_plan_file":         None,
            "baseline_complete":        False,
            "latest_handoff_path":      None,
            "recommended_next_workflow": "init-existing-or-new",
            "status_file_missing":      True
        }))
        sys.exit(0)

    status = parse_project_status(status_path)
    open_blockers = count_open_blockers(root / "oversight" / "tracking" / "blockers-log.md")
    latest_handoff = find_latest_handoff(root / "oversight" / "session-logs")
    recommended_wf = recommend_next_workflow(status["phase"], status["baseline_complete"])

    output = {
        "phase":                     status["phase"],
        "active_task":               status["active_task"],
        "open_issues_count":         status["open_issues_count"],
        "open_blockers_count":       open_blockers,
        "last_session_summary":      status["last_session_summary"],
        "active_plan_file":          status["active_plan_file"],
        "baseline_complete":         status["baseline_complete"],
        "latest_handoff_path":       latest_handoff,
        "recommended_next_workflow": recommended_wf,
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
