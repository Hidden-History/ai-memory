#!/usr/bin/env python3
"""
Pre-Work Memory Search for BMAD Workflows

Searches for relevant implementation memories and best practices before starting
development work. Designed for integration with BMAD workflow hooks.

Usage:
    python pre-work-search.py --story-id "story-2-1" --component "auth" --agent "dev"
    python pre-work-search.py --query "custom search query"
    python pre-work-search.py --story-id "story-2-1" --cwd /path/to/project

Output Format:
    {
        "memories": [
            {
                "content": "...",
                "type": "implementation",
                "similarity": 0.89,
                "collection": "implementations"
            }
        ],
        "count": N
    }

Graceful Degradation:
    - Returns empty array on any error
    - Writes warnings to stderr for debugging
    - Always exits with code 0 (never blocks workflow)

Created: 2026-01-17
BMAD Memory Module - Workflow Integration
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Try to import from installed location first, fall back to relative
try:
    from memory.search import MemorySearch
    from memory.config import get_config
except ImportError:
    # Running from dev repo
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from memory.search import MemorySearch
    from memory.config import get_config


def build_search_query(story_id: str, component: str, agent: str) -> str:
    """
    Build semantic search query from workflow context.

    Args:
        story_id: User story identifier (e.g., "story-2-1")
        component: Component name (e.g., "auth", "api")
        agent: Agent type (e.g., "dev", "test")

    Returns:
        Semantic search query string optimized for memory retrieval
    """
    query_parts = []

    if story_id:
        query_parts.append(f"story {story_id}")
    if component:
        query_parts.append(f"{component} component")
    if agent:
        query_parts.append(f"{agent} work")

    return " ".join(query_parts)


def search_memories(
    query: str,
    cwd: str = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Search for relevant memories in implementations and best_practices.

    Uses MemorySearch.search_both_collections() which:
    - Searches implementations (filtered by project if cwd provided)
    - Searches best_practices (shared across all projects)

    Args:
        query: Semantic search query
        cwd: Optional working directory for project detection
        limit: Maximum results per collection

    Returns:
        Dictionary with "memories" list and "count" integer.
        Returns empty structure on error (graceful degradation).
    """
    try:
        config = get_config()
        search = MemorySearch(config=config)

        # Search both collections (implementations + best_practices)
        # Returns: {"implementations": [...], "best_practices": [...]}
        results = search.search_both_collections(
            query=query,
            cwd=cwd,  # Auto-detects group_id if provided
            limit=limit
        )

        # Flatten results from both collections
        all_memories = []

        # Add implementations
        for mem in results.get("implementations", []):
            all_memories.append({
                "content": mem.get("content", ""),
                "type": mem.get("type", "unknown"),
                "similarity": round(mem.get("score", 0.0), 2),
                "collection": mem.get("collection", "implementations"),
            })

        # Add best_practices
        for mem in results.get("best_practices", []):
            all_memories.append({
                "content": mem.get("content", ""),
                "type": mem.get("type", "unknown"),
                "similarity": round(mem.get("score", 0.0), 2),
                "collection": mem.get("collection", "best_practices"),
            })

        # Sort by similarity (highest first)
        all_memories.sort(key=lambda x: x["similarity"], reverse=True)

        return {
            "memories": all_memories,
            "count": len(all_memories)
        }

    except Exception as e:
        # Graceful degradation: Return empty result on any error
        # Write error to stderr for debugging, but don't fail the workflow
        print(f"Warning: Memory search failed: {e}", file=sys.stderr)
        return {
            "memories": [],
            "count": 0
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Search for relevant memories before starting dev work"
    )

    parser.add_argument(
        "--story-id",
        help="User story identifier (e.g., 'story-2-1')"
    )
    parser.add_argument(
        "--component",
        help="Component name (e.g., 'auth', 'api')"
    )
    parser.add_argument(
        "--agent",
        help="Agent type (e.g., 'dev', 'test')"
    )
    parser.add_argument(
        "--query",
        help="Custom search query (overrides auto-generated query)"
    )
    parser.add_argument(
        "--cwd",
        help="Working directory for project detection (optional)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum results per collection (default: 5)"
    )

    args = parser.parse_args()

    # Build or use custom query
    if args.query:
        query = args.query
    else:
        # Build query from story context
        if not args.story_id and not args.component and not args.agent:
            print("Error: Must provide --query OR at least one of --story-id, --component, --agent", file=sys.stderr)
            # Graceful degradation: Return empty result instead of exit 1
            print(json.dumps({"memories": [], "count": 0}, indent=2))
            sys.exit(0)

        query = build_search_query(
            story_id=args.story_id or "",
            component=args.component or "",
            agent=args.agent or ""
        )

    # Search memories
    result = search_memories(query=query, cwd=args.cwd, limit=args.limit)

    # Output JSON to stdout for workflow injection
    print(json.dumps(result, indent=2))

    # Always exit 0 for graceful degradation
    sys.exit(0)


if __name__ == "__main__":
    main()
