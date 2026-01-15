#!/usr/bin/env python3
# scripts/memory/query_session_logs.py
"""Query session retrieval logs for analysis and debugging.

Usage:
    python scripts/memory/query_session_logs.py --project my-project
    python scripts/memory/query_session_logs.py --since 2026-01-09
    python scripts/memory/query_session_logs.py --min-results 3
    python scripts/memory/query_session_logs.py --project my-project --since 2026-01-12 --format json

Examples:
    # Show all sessions for a project
    python scripts/memory/query_session_logs.py --project bmad-memory-module

    # Sessions with 5+ results in last 7 days
    python scripts/memory/query_session_logs.py --min-results 5 --since 2026-01-06

    # Export to JSON for external analysis
    python scripts/memory/query_session_logs.py --format json > sessions.json

Best Practices (2026):
- Support gzipped archived logs automatically
- ISO 8601 date filtering
- Multiple output formats (table, json, csv)
- Colorized terminal output for readability
"""

import argparse
import json
import gzip
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


def iter_log_files(log_path: Path) -> Iterator[Path]:
    """Iterate over log files including gzipped archives.

    Yields files in reverse chronological order (newest first).
    """
    log_dir = log_path.parent
    log_name = log_path.name

    # Current log file
    if log_path.exists():
        yield log_path

    # Archived logs (sessions.jsonl.1.gz, sessions.jsonl.2.gz, ...)
    for i in range(1, 91):  # Up to 90 backups
        archive = log_dir / f"{log_name}.{i}.gz"
        if archive.exists():
            yield archive
        else:
            break


def read_jsonl(file_path: Path) -> Iterator[dict]:
    """Read JSONL file, handling gzip compression automatically."""
    if file_path.suffix == '.gz':
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        # Skip malformed lines gracefully
                        continue
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        # Skip malformed lines gracefully
                        continue


def query_sessions(
    log_path: Path,
    project: Optional[str] = None,
    since: Optional[str] = None,
    min_results: Optional[int] = None
) -> list[dict]:
    """Query session logs with filters.

    Args:
        log_path: Path to sessions.jsonl file
        project: Filter by project name (group_id)
        since: ISO 8601 date string (e.g., "2026-01-09")
        min_results: Minimum result count

    Returns:
        List of matching session log entries
    """
    matches = []

    # Parse since date if provided
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            print(f"Warning: Invalid date format '{since}', ignoring since filter")

    # Iterate through all log files
    for log_file in iter_log_files(log_path):
        for entry in read_jsonl(log_file):
            # Extra fields are at root level (python-json-logger format)
            # NOT nested under "context"

            # Apply filters
            if project and entry.get("project") != project:
                continue

            if since_dt:
                timestamp = entry.get("timestamp", "")
                if timestamp:
                    try:
                        # Handle both ISO formats with and without timezone
                        ts_clean = timestamp.rstrip("Z").replace("+00:00", "")
                        entry_time = datetime.fromisoformat(ts_clean)
                        if entry_time < since_dt:
                            continue
                    except ValueError:
                        # Skip entries with invalid timestamps
                        continue

            if min_results and entry.get("results_count", 0) < min_results:
                continue

            matches.append(entry)

    return matches


def format_table(sessions: list[dict]):
    """Format sessions as terminal table."""
    print(f"\n{'Session ID':<20} {'Project':<25} {'Results':<8} {'Duration':<10} {'Timestamp':<20}")
    print("-" * 90)

    for entry in sessions:
        # Extra fields are at root level (python-json-logger format)
        session_id = str(entry.get("session_id", "unknown"))[:20]
        project = str(entry.get("project", "unknown"))[:25]
        results = entry.get("results_count", 0)
        duration = f"{entry.get('duration_ms', 0):.0f}ms"
        timestamp = str(entry.get("timestamp", ""))[:19]

        print(f"{session_id:<20} {project:<25} {results:<8} {duration:<10} {timestamp:<20}")

    print(f"\nTotal: {len(sessions)} sessions")


def main():
    parser = argparse.ArgumentParser(
        description="Query session retrieval logs"
    )
    parser.add_argument("--project", help="Filter by project name")
    parser.add_argument("--since", help="Filter by date (ISO 8601: YYYY-MM-DD)")
    parser.add_argument("--min-results", type=int, help="Minimum result count")
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format"
    )
    parser.add_argument(
        "--log-path",
        default="~/.claude-memory/sessions.jsonl",
        help="Path to session log file"
    )

    args = parser.parse_args()

    log_path = Path(args.log_path).expanduser()

    if not log_path.exists():
        print(f"Error: Log file not found: {log_path}")
        print("Tip: Enable session logging with SESSION_LOG_ENABLED=true")
        return 1

    # Query sessions
    sessions = query_sessions(
        log_path=log_path,
        project=args.project,
        since=args.since,
        min_results=args.min_results
    )

    # Output in requested format
    if args.format == "json":
        print(json.dumps(sessions, indent=2))
    elif args.format == "csv":
        print("session_id,project,results_count,duration_ms,timestamp")
        for entry in sessions:
            # Extra fields are at root level (python-json-logger format)
            print(f"{entry.get('session_id')},{entry.get('project')},{entry.get('results_count')},{entry.get('duration_ms')},{entry.get('timestamp')}")
    else:
        format_table(sessions)

    return 0


if __name__ == "__main__":
    exit(main())
