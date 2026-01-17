#!/usr/bin/env python3
"""Search Memory CLI - User-triggered memory search across all collections.

This script is invoked by the /search-memory slash command to allow users
to search for specific topics in their memory system.

Usage:
  /search-memory <query>

Example:
  /search-memory authentication
  /search-memory JWT implementation

Exit Codes:
- 0: Success
- 1: Error
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add src to path for imports
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.search import MemorySearch
from memory.project import detect_project
from memory.logging_config import StructuredFormatter

# Configure structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.search")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False


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
        payload = result.get("payload", {})
        score = result.get("score", 0.0)

        # Extract key fields
        content = payload.get("content", "")[:200]  # First 200 chars
        memory_type = payload.get("type", "unknown")
        source = payload.get("source_hook", "unknown")
        timestamp = payload.get("timestamp", "unknown")

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
    # Get query from args
    if len(sys.argv) < 2:
        print("Usage: /search-memory <query>", file=sys.stderr)
        print("Example: /search-memory authentication", file=sys.stderr)
        return 1

    query = " ".join(sys.argv[1:])

    # Get current project
    cwd = os.getcwd()
    project_name = detect_project(cwd)

    print(f"\n🔍 Searching memory for: '{query}'")
    print(f"   Project: {project_name}\n")

    try:
        # Initialize search
        memory_search = MemorySearch()

        # Search all collections
        collections = ["agent-memory", "implementations", "best_practices"]
        all_results = []

        for collection in collections:
            try:
                # Use current project's group_id for filtering
                # best_practices uses "universal" group_id
                group_id = "universal" if collection == "best_practices" else project_name

                # Search using MemorySearch (returns list of dicts)
                results = memory_search.search(
                    query=query,
                    collection=collection,
                    group_id=group_id,
                    limit=3
                )

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

        # Summary
        if all_results:
            print("\n" + "=" * 60)
            print(f"✅ Total: {len(all_results)} memories found across all collections")
        else:
            print("\n❌ No memories found matching your query")
            print("   Try different search terms or check /memory-status")

        return 0

    except Exception as e:
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
