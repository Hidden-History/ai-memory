#!/usr/bin/env python3
"""Jira-data collection query CLI.

Executes filtered scroll queries against the jira-data Qdrant collection.
Invoked by the aim-jira-search skill via run-with-env.sh; auth and connection
are resolved through the standard memory.* config layer (no inline grep).

Usage:
    query.py [--project P] [--issue-type T] [--status S] [--issue-key K]
             [--doc-type D] [--limit N] [--format table|json]
             [--collection jira-data]
    query.py --count

Examples:
    # Search by project key
    query.py --project BMAD --limit 10

    # Filter by issue type and status
    query.py --project BMAD --issue-type Bug --status Done --limit 20

    # Count points and vectors in the collection
    query.py --count

    # Get all comments for a specific issue
    query.py --issue-key BMAD-42 --doc-type jira_comment --limit 50

    # JSON output for programmatic use
    query.py --project BMAD --format json
"""

import argparse
import json
import sys
from pathlib import Path

# sys.path.insert precedes memory.* imports so the script is importable from
# the source checkout (dev/test). run-with-env.sh sets the venv in production.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from qdrant_client.models import FieldCondition, Filter, MatchValue

from memory.config import COLLECTION_JIRA_DATA, get_config
from memory.qdrant_client import get_qdrant_client


def build_filter(
    project: str | None = None,
    issue_type: str | None = None,
    status: str | None = None,
    issue_key: str | None = None,
    doc_type: str | None = None,
) -> Filter | None:
    """Build a Qdrant scroll Filter from named flag values.

    Each non-None argument appends a FieldCondition to the must list,
    mirroring the documented jira-data scroll forms exactly.

    Returns:
        Filter with must=[FieldCondition(...)] per non-None arg, or None
        when all args are absent.
    """
    must = []
    if project:
        must.append(FieldCondition(key="jira_project", match=MatchValue(value=project)))
    if issue_type:
        must.append(
            FieldCondition(key="jira_issue_type", match=MatchValue(value=issue_type))
        )
    if status:
        must.append(FieldCondition(key="jira_status", match=MatchValue(value=status)))
    if issue_key:
        must.append(
            FieldCondition(key="jira_issue_key", match=MatchValue(value=issue_key))
        )
    if doc_type:
        must.append(FieldCondition(key="type", match=MatchValue(value=doc_type)))
    return Filter(must=must) if must else None


def _print_table(points: list) -> None:
    print(f"Found {len(points)} point(s)")
    for p in points:
        pl = p.payload or {}
        key = pl.get("jira_issue_key", "?")
        tp = pl.get("type", "?")
        status = pl.get("jira_status", "?")
        content = pl.get("content", "")[:80]
        print(f"  {key} [{tp}] {status} — {content}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Query the jira-data Qdrant collection via filtered scroll."
    )
    parser.add_argument(
        "--collection",
        default=COLLECTION_JIRA_DATA,
        help="Collection name (default: jira-data)",
    )
    parser.add_argument("--project", default=None, help="Filter by Jira project key")
    parser.add_argument(
        "--issue-type", default=None, help="Filter by issue type (Bug, Story, Task…)"
    )
    parser.add_argument(
        "--status", default=None, help="Filter by issue status (To Do, In Progress…)"
    )
    parser.add_argument(
        "--issue-key", default=None, help="Filter by full issue key (e.g. BMAD-42)"
    )
    parser.add_argument(
        "--doc-type",
        default=None,
        help="Filter by document type (jira_issue or jira_comment)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max points to return (default: 10)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format — json for programmatic use, table for readability (default: table)",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help="Return collection points_count and vectors_count; skip scroll",
    )
    args = parser.parse_args(argv)

    config = get_config()
    client = get_qdrant_client(config)

    if args.count:
        info = client.get_collection(args.collection)
        print(f"Points: {info.points_count}, Vectors: {info.vectors_count}")
        return

    qdrant_filter = build_filter(
        project=args.project,
        issue_type=args.issue_type,
        status=args.status,
        issue_key=args.issue_key,
        doc_type=args.doc_type,
    )
    points, _next_page = client.scroll(
        collection_name=args.collection,
        scroll_filter=qdrant_filter,
        limit=args.limit,
        with_payload=True,
        with_vectors=False,
    )

    if args.format == "json":
        output = [{"id": str(p.id), "payload": p.payload} for p in points]
        print(json.dumps(output, indent=2, default=str))
    else:
        _print_table(points)


if __name__ == "__main__":
    main()
