#!/usr/bin/env python3
"""Clean up empty session summaries from discussions collection.

Deletes entries where:
- content contains "Tools Used: None"
- AND "Files Modified (0)"
- AND "User Interactions: 0 prompts"
- AND "Key Activities:" followed by empty line (no activities)

Usage:
    python3 scripts/memory/cleanup_empty_sessions.py --dry-run  # Preview
    python3 scripts/memory/cleanup_empty_sessions.py            # Execute
"""

import argparse
import os
import sys
from typing import Dict, List

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from qdrant_client.models import FieldCondition, Filter, MatchValue

from memory.config import get_config
from memory.qdrant_client import get_qdrant_client


def is_empty_session_summary(content: str) -> bool:
    """Check if content is an empty session summary.

    Args:
        content: Memory content string

    Returns:
        True if this is an empty session summary (no tools, files, or activities)
    """
    indicators = [
        "Tools Used: None",
        "Files Modified (0)",
        "User Interactions: 0 prompts",
    ]

    # Must have all indicators
    if not all(indicator in content for indicator in indicators):
        return False

    # Check if Key Activities section is empty
    if "Key Activities:" in content:
        # Get text after "Key Activities:"
        after_activities = content.split("Key Activities:")[-1].strip()
        # If nothing after or only whitespace, it's empty
        if not after_activities or after_activities == "":
            return True

    return False


def find_empty_sessions(client, collection_name: str = "discussions") -> List[Dict]:
    """Find all empty session summaries in collection.

    Args:
        client: Qdrant client instance
        collection_name: Collection to search (default: discussions)

    Returns:
        List of point dicts with id and content
    """
    # Scroll through all points in collection
    # Use scroll API for efficient full collection scan
    offset = None
    limit = 100
    empty_sessions = []

    while True:
        results, next_offset = client.scroll(
            collection_name=collection_name,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,  # Don't need vectors for cleanup
        )

        if not results:
            break

        for point in results:
            content = point.payload.get("content", "")
            if is_empty_session_summary(content):
                empty_sessions.append(
                    {
                        "id": point.id,
                        "content": content[:200],  # Preview
                        "group_id": point.payload.get("group_id", "unknown"),
                        "session_id": point.payload.get("session_id", "unknown"),
                    }
                )

        # Check if there are more results
        if next_offset is None:
            break
        offset = next_offset

    return empty_sessions


def delete_points(client, collection_name: str, point_ids: List[str]) -> None:
    """Delete points from collection.

    Args:
        client: Qdrant client instance
        collection_name: Collection name
        point_ids: List of point IDs to delete
    """
    client.delete(collection_name=collection_name, points_selector=point_ids)


def main():
    parser = argparse.ArgumentParser(description="Clean up empty session summaries")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--collection",
        default="discussions",
        help="Collection to clean (default: discussions)",
    )
    args = parser.parse_args()

    # Get Qdrant client
    config = get_config()
    client = get_qdrant_client(config)

    print(f"🔍 Scanning {args.collection} collection for empty session summaries...")

    # Find empty sessions
    empty_sessions = find_empty_sessions(client, args.collection)

    if not empty_sessions:
        print("✓ No empty session summaries found")
        return

    print(f"\n📋 Found {len(empty_sessions)} empty session summaries:")
    print("=" * 80)

    for i, session in enumerate(empty_sessions, 1):
        print(f"\n{i}. ID: {session['id']}")
        print(f"   Project: {session['group_id']}")
        print(f"   Session: {session['session_id']}")
        print(f"   Preview: {session['content']}...")

    print("\n" + "=" * 80)

    if args.dry_run:
        print("\n🔍 DRY RUN - No changes made")
        print(f"Would delete {len(empty_sessions)} empty session summaries")
    else:
        # Confirm deletion
        response = input(
            f"\n⚠️  Delete {len(empty_sessions)} empty session summaries? (yes/no): "
        )
        if response.lower() != "yes":
            print("❌ Cancelled")
            return

        # Delete points
        point_ids = [s["id"] for s in empty_sessions]
        delete_points(client, args.collection, point_ids)

        print(
            f"✓ Deleted {len(empty_sessions)} empty session summaries from {args.collection}"
        )


if __name__ == "__main__":
    main()
