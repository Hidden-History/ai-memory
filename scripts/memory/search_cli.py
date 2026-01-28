#!/usr/bin/env python3
"""Search Memory CLI - User-triggered memory search across all collections.

This script is invoked by the /search-memory slash command to allow users
to search for specific topics in their memory system.

Usage:
  /search-memory <query> [options]

Example:
  /search-memory authentication
  /search-memory JWT implementation --collection code-patterns
  /search-memory "error handling" --type error_fix --limit 5

Exit Codes:
- 0: Success
- 1: Error
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Add src to path for imports
INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.search import MemorySearch
from memory.project import detect_project
from memory.intent import detect_intent, get_target_collection
from memory.logging_config import StructuredFormatter
from memory.activity_log import log_memory_search
from memory.metrics_push import push_skill_metrics_async

# Configure structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.search")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Valid memory types by collection
VALID_TYPES = {
    "code-patterns": ["implementation", "error_fix", "refactor", "file_pattern"],
    "conventions": ["rule", "guideline", "port", "naming", "structure"],
    "discussions": ["decision", "session", "blocker", "preference", "user_message", "agent_response"],
}
ALL_VALID_TYPES = set(t for types in VALID_TYPES.values() for t in types)


def positive_int(value):
    """Validate limit is a positive integer.

    Args:
        value: String value from command line

    Returns:
        int: Validated positive integer

    Raises:
        argparse.ArgumentTypeError: If value is not a positive integer
    """
    ivalue = int(value)
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"limit must be >= 1, got {value}")
    return ivalue


def parse_args():
    """Parse command line arguments.

    Returns:
        Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Search BMAD memory system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  search_cli.py "authentication"
  search_cli.py "error handling" --collection conventions
  search_cli.py "database" --type error_fix --limit 5
  search_cli.py "why postgres" --intent why
        """
    )

    parser.add_argument("query", help="Search query text")

    parser.add_argument(
        "-c", "--collection",
        choices=["code-patterns", "conventions", "discussions", "all"],
        default="all",
        help="Target collection (default: all)"
    )

    parser.add_argument(
        "-t", "--type",
        help="Filter by memory type. Valid types: implementation, error_fix, refactor, "
             "file_pattern, rule, guideline, port, naming, structure, decision, session, "
             "blocker, preference, user_message, agent_response"
    )

    parser.add_argument(
        "-i", "--intent",
        choices=["how", "what", "why"],
        help="Use intent detection to route query"
    )

    parser.add_argument(
        "-l", "--limit",
        type=positive_int,
        default=3,
        help="Max results per collection (default: 3, must be >= 1)"
    )

    parser.add_argument(
        "-g", "--group-id",
        help="Override project detection with specific group_id"
    )

    return parser.parse_args()


def format_search_results(results: List[Dict[str, Any]], collection: str) -> str:
    """Format search results for display.

    Args:
        results: List of search results from Qdrant
        collection: Collection name (for context)

    Returns:
        Formatted string for display
    """
    if not results:
        return f"No results found in {collection}"

    lines = [f"\n📚 Results from {collection} ({len(results)} matches):"]
    lines.append("=" * 60)

    for i, result in enumerate(results, 1):
        score = result.get("score", 0.0)

        # Extract key fields (payload is flattened at top level by MemorySearch.search())
        content = result.get("content", "")[:200]  # First 200 chars
        memory_type = result.get("type", "unknown")
        source = result.get("source_hook", "unknown")
        timestamp = result.get("timestamp", "unknown")

        lines.append(f"\n{i}. [{memory_type}] Score: {score:.3f}")
        lines.append(f"   Source: {source} | {timestamp}")
        lines.append(f"   {content}...")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Search CLI entry point.

    Returns:
        Exit code: 0 (success) or 1 (error)
    """
    start_time = time.time()  # Track duration for metrics and activity log

    # Parse arguments
    args = parse_args()
    query = args.query

    # Validate type filter if provided
    if args.type and args.type not in ALL_VALID_TYPES:
        print(f"❌ Invalid type: '{args.type}'", file=sys.stderr)
        print(f"   Valid types: {', '.join(sorted(ALL_VALID_TYPES))}", file=sys.stderr)
        return 1

    # Get current project (or use override)
    cwd = os.getcwd()
    project_name = args.group_id if args.group_id else detect_project(cwd)

    # Determine target collections
    if args.intent:
        # Map user's explicit intent choice directly to collection
        intent_map = {
            "how": "code-patterns",
            "what": "conventions",
            "why": "discussions"
        }
        target_collection = intent_map[args.intent]
        collections = [target_collection]
        logger.info(
            "intent_override",
            extra={
                "user_intent": args.intent,
                "target_collection": target_collection
            }
        )
        print(f"\n🔍 Searching memory for: '{query}'")
        print(f"   Intent: {args.intent} → {target_collection}")
        print(f"   Project: {project_name}\n")
    elif args.collection != "all":
        # Search specific collection
        collections = [args.collection]
        print(f"\n🔍 Searching memory for: '{query}'")
        print(f"   Collection: {args.collection}")
        print(f"   Project: {project_name}\n")
    else:
        # Search all collections
        collections = ["discussions", "code-patterns", "conventions"]
        print(f"\n🔍 Searching memory for: '{query}'")
        print(f"   Project: {project_name}\n")

    logger.info(
        "search_started",
        extra={
            "query": query,
            "collections_searched": collections,
            "type_filter": args.type,
            "intent": args.intent,
            "limit": args.limit,
            "group_id": project_name
        }
    )

    try:
        # Initialize search
        memory_search = MemorySearch()
        all_results = []

        for collection in collections:
            try:
                # Use current project's group_id for filtering
                # conventions uses "universal" group_id
                group_id = "universal" if collection == "conventions" else project_name

                # Build search parameters
                search_params = {
                    "query": query,
                    "collection": collection,
                    "group_id": group_id,
                    "limit": args.limit
                }

                # Add type filter if specified
                if args.type:
                    search_params["memory_type"] = args.type

                # Search using MemorySearch (returns list of dicts)
                results = memory_search.search(**search_params)

                if results:
                    output = format_search_results(results, collection)
                    print(output)
                    all_results.extend(results)

            except Exception as e:
                logger.warning(
                    "collection_search_failed",
                    extra={
                        "collection": collection,
                        "error": str(e)
                    }
                )
                print(f"⚠️  Could not search {collection}: {e}", file=sys.stderr)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Summary
        if all_results:
            print("\n" + "=" * 60)
            print(f"✅ Total: {len(all_results)} memories found")
            if args.type:
                print(f"   Filtered by type: {args.type}")

            # Log to activity.log
            log_memory_search(
                project=project_name,
                query=query,
                results_count=len(all_results),
                duration_ms=duration_ms,
                results=all_results[:3]  # Top 3 for preview
            )

            # Push metrics to Pushgateway
            push_skill_metrics_async(
                skill_name="search-memory",
                status="success",
                duration_seconds=duration_ms / 1000.0
            )
        else:
            print("\n❌ No memories found matching your query")
            print("   Try different search terms or check /memory-status")

            # Log empty result
            log_memory_search(
                project=project_name,
                query=query,
                results_count=0,
                duration_ms=duration_ms
            )

            # Push empty metrics
            push_skill_metrics_async(
                skill_name="search-memory",
                status="empty",
                duration_seconds=duration_ms / 1000.0
            )

        return 0

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        # Push failure metrics
        push_skill_metrics_async(
            skill_name="search-memory",
            status="failed",
            duration_seconds=duration_ms / 1000.0
        )

        logger.error(
            "search_failed",
            extra={
                "error": str(e),
                "query": query
            }
        )
        print(f"❌ Search failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
