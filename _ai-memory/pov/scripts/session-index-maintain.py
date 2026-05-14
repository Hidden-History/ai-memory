#!/usr/bin/env python3
"""
session-index-maintain.py — Append a structured session entry to SESSION_WORK_INDEX.md.

Also provides --check-sizes for GC-18 document sharding checks (L6-F3).

Usage — append session entry:
  python session-index-maintain.py \\
    --session-id Session_29 \\
    --date 2026-04-12 \\
    --phase execution \\
    --tasks "TASK-041" \\
    --decisions "DEC-XXX,DEC-YYY" \\
    --qdrant-handoff-id fcaa6868 \\
    --summary "Dual BMAD review + 13 fixes applied + 16/16 verified PASS"

Usage — GC-18 size check:
  python session-index-maintain.py --check-sizes [--root .]

Integration: session close step-01-summarize-session.md, after handoff created.
Savings: 400-800 tokens/session (F2); --check-sizes saves 200-400 tokens/self-check (F3).
"""

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path


# GC-18: oversight documents must be sharded when they exceed this many lines
GC18_LINE_LIMIT = 500

# Per-file thresholds override GC18_LINE_LIMIT (SESSION_WORK_INDEX has tighter limit per step-01)
GC18_PER_FILE_LIMITS = {
    "oversight/SESSION_WORK_INDEX.md": 80,
}

# Files monitored for GC-18 sharding (relative to project root)
GC18_WATCHED_FILES = [
    "oversight/SESSION_WORK_INDEX.md",
    "oversight/tracking/blockers-log.md",
    "oversight/tracking/task-tracker.md",
    "oversight/tracking/technical-debt.md",
    "oversight/tracking/dependencies.md",
    "oversight/tracking/scope-change-log.md",
    "oversight/knowledge/assumption-registry.md",
]


def _sanitize_cell(val):
    """Escape pipe characters and strip newlines for Markdown table cells."""
    val = str(val).replace('\r', '').replace('\n', ' ')
    val = val.replace('|', r'\|')
    return val.strip()


def check_sizes(root):
    """
    Check watched oversight files for GC-18 sharding threshold.
    Prints a report and returns exit code 1 if any file exceeds the limit.
    """
    root = Path(root).resolve()
    results = []
    any_trigger = False

    for rel in GC18_WATCHED_FILES:
        path = root / rel
        if not path.exists():
            results.append({"file": rel, "status": "NOT_FOUND", "lines": 0})
            continue
        try:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            results.append({"file": rel, "status": "READ_ERROR", "lines": 0})
            continue
        limit = GC18_PER_FILE_LIMITS.get(rel, GC18_LINE_LIMIT)
        triggered = line_count > limit  # P-7: "exceeds" means strictly greater than
        if triggered:
            any_trigger = True
        results.append({
            "file": rel,
            "status": "SHARD_REQUIRED" if triggered else "OK",
            "lines": line_count,
        })

    print(f"GC-18 Document Size Check  (default threshold: {GC18_LINE_LIMIT} lines; per-file overrides apply)")
    print("=" * 60)
    for r in results:
        if r["status"] == "SHARD_REQUIRED":
            flag = f"!!! SHARD REQUIRED ({r['lines']} lines)"
        elif r["status"] == "READ_ERROR":
            flag = "READ ERROR"
        elif r["status"] == "NOT_FOUND":
            flag = "NOT FOUND"
        else:
            flag = f"OK ({r['lines']} lines)"
        print(f"  {r['file']}: {flag}")

    print()
    if any_trigger:
        print("ACTION REQUIRED: One or more oversight files exceed the 500-line limit.")
        print("Archive older entries per GC-18-oversight-document-sharding.md.")
        return 1
    else:
        print("All monitored files are within the sharding threshold. No action needed.")
        return 0


def append_session_entry(index_path, session_id, date_str, phase, tasks, decisions, qdrant_id, summary):
    """
    Append a new row to the 'Last N Sessions' table and a detail block at the end
    of SESSION_WORK_INDEX.md.
    """
    if not index_path.exists():
        print(f"ERROR: {index_path} not found.", file=sys.stderr)
        return 1

    try:
        content = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"ERROR: Cannot read {index_path}: {e}", file=sys.stderr)
        return 1

    # P-5: Duplicate entry check — warn and abort if session already recorded
    if re.search(rf'(?<!\w){re.escape(session_id)}(?!\w)', content):
        print(f"WARNING: Duplicate entry — session '{session_id}' already exists in {index_path}.", file=sys.stderr)
        return 1

    # H-1/P-1: Sanitize all cell values (escape pipes, strip newlines)
    s_date      = _sanitize_cell(date_str)
    s_session   = _sanitize_cell(session_id)
    s_summary   = _sanitize_cell(summary)
    s_phase     = _sanitize_cell(phase)
    s_tasks     = _sanitize_cell(tasks)
    s_decisions = _sanitize_cell(decisions)
    s_qdrant    = _sanitize_cell(qdrant_id)

    # ------------------------------------------------------------------ #
    # 1. Insert new row into the table under "## Last N Sessions"          #
    # ------------------------------------------------------------------ #
    # Row format: | Date | Session ID | Summary | Status |
    new_row = f"| {s_date} | {s_session} | {s_summary} | Complete |"

    # H-3: Permissive table header pattern — matches any markdown table header + separator row.
    # Handles legacy "Task ID" column name and any future renames.
    table_sep_pattern = r'(\|[^\n]+\|\s*\n\|[-|: ]+\|\s*\n)'
    sep_m = re.search(table_sep_pattern, content)
    if sep_m:
        insert_pos = sep_m.end()
        content = content[:insert_pos] + new_row + "\n" + content[insert_pos:]
    else:
        # Fallback: insert before the "**Full history**" line
        hist_m = re.search(r'^(\*\*Full history\*\*)', content, re.MULTILINE)
        if hist_m:
            insert_pos = hist_m.start()
            content = content[:insert_pos] + new_row + "\n\n" + content[insert_pos:]
        else:
            # H-3: warn when neither anchor is found
            print(f"WARNING: No table anchor found in {index_path}; appending new table at end.", file=sys.stderr)
            # W-15: place row inside a valid table structure, not as a disconnected paragraph
            new_table = (
                "\n\n## Last N Sessions\n\n"
                "| Date | Session ID | Summary | Status |\n"
                "|------|------------|---------|--------|\n"
                + new_row + "\n"
            )
            content = content.rstrip() + new_table

    # ------------------------------------------------------------------ #
    # 2. Append a detail block at the end of the file                      #
    # ------------------------------------------------------------------ #
    detail_block = (
        f"\n---\n\n"
        f"### {s_session} — {s_date}\n\n"
        f"| Field | Value |\n"
        f"|-------|-------|\n"
        f"| Phase | {s_phase} |\n"
        f"| Tasks | {s_tasks} |\n"
        f"| Decisions | {s_decisions} |\n"
        f"| Qdrant Handoff | {s_qdrant} |\n"
        f"| Summary | {s_summary} |\n"
    )
    content = content.rstrip() + "\n" + detail_block

    # P-2: Atomic write — write to .tmp sibling then replace to avoid partial writes
    tmp_path = index_path.with_suffix(index_path.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, index_path)
    except (OSError, UnicodeDecodeError) as e:
        print(f"ERROR: Cannot write {index_path}: {e}", file=sys.stderr)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return 1

    print(f"Session entry appended to {index_path}")
    print(f"  Session:   {session_id} ({date_str})")
    print(f"  Phase:     {phase}")
    print(f"  Tasks:     {tasks}")
    print(f"  Decisions: {decisions}")
    print(f"  Qdrant:    {qdrant_id}")
    print(f"  Summary:   {summary}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Append session entry to SESSION_WORK_INDEX.md (session-index-maintain)"
    )
    parser.add_argument("--root", default=".",
                        help="Project root directory (default: current directory)")
    parser.add_argument("--check-sizes", action="store_true",
                        help="Run GC-18 document sharding check and exit")
    parser.add_argument("--session-id",
                        help="Session identifier, e.g. Session_29")
    parser.add_argument("--date", default=str(date.today()),
                        help="Session date YYYY-MM-DD (default: today)")
    parser.add_argument("--phase", default="execution",
                        help="Current project phase (default: execution)")
    parser.add_argument("--tasks", default="",
                        help="Comma-separated task IDs worked on this session")
    parser.add_argument("--decisions", default="",
                        help="Comma-separated decision IDs made this session")
    parser.add_argument("--qdrant-handoff-id", default="",
                        help="Qdrant vector ID for the session handoff")
    parser.add_argument("--summary", default="",
                        help="One-line session summary for the index row")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    if args.check_sizes:
        sys.exit(check_sizes(root))

    if not args.session_id:
        parser.error("--session-id is required (use --check-sizes to run size checks only)")
    if not args.summary:
        parser.error("--summary is required")

    # M-3: Validate date format
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', args.date):
        parser.error(f"--date must be YYYY-MM-DD, got: {args.date!r}")

    index_path = root / "oversight" / "SESSION_WORK_INDEX.md"
    sys.exit(append_session_entry(
        index_path,
        args.session_id,
        args.date,
        args.phase,
        args.tasks,
        args.decisions,
        args.qdrant_handoff_id,
        args.summary,
    ))


if __name__ == "__main__":
    main()
