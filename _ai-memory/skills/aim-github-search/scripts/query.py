#!/usr/bin/env python3
"""Query GitHub content from the Qdrant discussions collection.

Parameterized replacement for the inline Python blocks in aim-github-search/SKILL.md.
Always applies source=github + group_id filters; optional type/state/limit/format.

Usage:
    python3 query.py --group-id "hidden-history/ai-memory"
    python3 query.py --group-id "hidden-history/ai-memory" --type github_pr --state merged
    python3 query.py --group-id "hidden-history/ai-memory" --format count
    python3 query.py --group-id "hidden-history/ai-memory" --type github_issue --limit 20 --format json

Run via run-with-env.sh so memory.* and QDRANT_API_KEY are available:
    bash ~/.ai-memory/scripts/memory/run-with-env.sh ~/.ai-memory/skills/aim-github-search/scripts/query.py \\
        --group-id "hidden-history/ai-memory" --type github_pr --state merged
"""

from __future__ import annotations

import argparse
import json
import os
import sys

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: E402

from memory.config import get_config  # noqa: E402
from memory.qdrant_client import get_qdrant_client  # noqa: E402

_DEFAULT_COLLECTION = "discussions"
_DEFAULT_LIMIT = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query GitHub content from Qdrant discussions collection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--group-id",
        required=True,
        help="GitHub repo group_id (e.g. hidden-history/ai-memory).",
    )
    parser.add_argument(
        "--type",
        dest="type_filter",
        metavar="TYPE",
        help=(
            "Filter by document type: github_issue, github_pr, github_commit, "
            "github_ci_result, github_code_blob, github_issue_comment, "
            "github_pr_review, github_pr_diff"
        ),
    )
    parser.add_argument(
        "--state",
        dest="state_filter",
        metavar="STATE",
        help="Filter by state: open, closed, merged",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"Max results to return for table/json formats (default: {_DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["table", "json", "count"],
        default="table",
        help="Output format: table (default), json, count",
    )
    parser.add_argument(
        "--collection",
        default=_DEFAULT_COLLECTION,
        help=f"Qdrant collection name (default: {_DEFAULT_COLLECTION})",
    )
    return parser.parse_args()


def build_filter(
    group_id: str,
    type_filter: str | None,
    state_filter: str | None,
) -> Filter:
    """Build a Qdrant Filter for GitHub content queries.

    Always includes source=github and group_id conditions.
    Appends type and state conditions when provided.

    Args:
        group_id: GitHub repo group_id (e.g. "hidden-history/ai-memory").
        type_filter: Optional document type (e.g. "github_pr").
        state_filter: Optional state (e.g. "merged").

    Returns:
        Filter with must conditions matching the documented query forms.
    """
    must = [
        FieldCondition(key="source", match=MatchValue(value="github")),
        FieldCondition(key="group_id", match=MatchValue(value=group_id)),
    ]
    if type_filter:
        must.append(FieldCondition(key="type", match=MatchValue(value=type_filter)))
    if state_filter:
        must.append(FieldCondition(key="state", match=MatchValue(value=state_filter)))
    return Filter(must=must)


def main() -> int:
    args = parse_args()

    config = get_config()
    client = get_qdrant_client(config)

    query_filter = build_filter(args.group_id, args.type_filter, args.state_filter)

    if args.output_format == "count":
        result = client.count(
            collection_name=args.collection,
            count_filter=query_filter,
            exact=True,
        )
        print(f"GitHub points: {result.count}")
        return 0

    points, _ = client.scroll(
        collection_name=args.collection,
        scroll_filter=query_filter,
        limit=args.limit,
        with_payload=True,
        with_vectors=False,
    )

    if args.output_format == "json":
        output = [{"id": str(p.id), "payload": p.payload} for p in points]
        print(json.dumps(output, indent=2, default=str))
    else:
        # table format
        print(f"Found {len(points)} points")
        for p in points:
            pl = p.payload or {}
            print(
                f"  [{pl.get('type', '?')}] {pl.get('state', '?')} "
                f"- {pl.get('url', '?')} "
                f"- {pl.get('content', '')[:80]}..."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
