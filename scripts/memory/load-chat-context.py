#!/usr/bin/env python3
"""
Chat Context Loader for BMAD Agent Session Continuity

Loads previous conversation context from discussions collection to provide
session continuity for BMAD agents. Retrieves recent chat memories filtered
by agent type and session information.

Usage:
    python load-chat-context.py --session-id sess-123 --agent dev
    python load-chat-context.py --session-id sess-456 --agent architect --limit 10
    python load-chat-context.py --agent pm  # All sessions for PM agent

Output Format:
    {
        "memories": [
            {
                "content": "User asked about authentication patterns...",
                "timestamp": "2026-01-17T10:30:00Z",
                "session_id": "sess-123",
                "agent": "dev"
            }
        ],
        "count": N
    }

Graceful Degradation:
    - Returns empty array on any error
    - Writes warnings to stderr for debugging
    - Always exits with code 0 (never blocks workflow)

Created: 2026-01-17
BMAD Memory Module - Session Continuity
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src to path for imports
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Try to import from installed location first, fall back to relative
try:
    from memory.config import get_config
    from memory.qdrant_client import get_qdrant_client
    from memory.models import MemoryType
except ImportError:
    # Running from dev repo
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from memory.config import get_config
    from memory.qdrant_client import get_qdrant_client
    from memory.models import MemoryType

from qdrant_client.models import Filter, FieldCondition, MatchValue

# Valid BMAD agents (defined locally for compatibility with older installed versions)
VALID_AGENTS = [
    "architect",
    "analyst",
    "pm",
    "dev",
    "tea",
    "tech-writer",
    "ux-designer",
    "quick-flow-solo-dev",
    "sm",
]


def load_chat_context(
    agent: str,
    session_id: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Load recent chat memories for session continuity.

    Queries discussions collection for chat_memory type, filters by agent
    and optionally session_id, sorted by timestamp (most recent first).

    Args:
        agent: BMAD agent type (dev, architect, pm, etc.)
        session_id: Optional session ID filter (None = all sessions)
        limit: Maximum number of memories to return (default: 5)

    Returns:
        Dictionary with "memories" list and "count" integer.
        Returns empty structure on error (graceful degradation).

    Example:
        >>> result = load_chat_context("dev", "sess-123", limit=3)
        >>> result["count"]
        3
        >>> result["memories"][0]["agent"]
        'dev'
    """
    try:
        # Validate agent
        if agent not in VALID_AGENTS:
            print(
                f"Warning: Invalid agent '{agent}'. Valid agents: {', '.join(VALID_AGENTS)}",
                file=sys.stderr
            )
            return {"memories": [], "count": 0}

        # Get Qdrant client
        config = get_config()
        client = get_qdrant_client(config)

        # Build filter conditions
        filter_conditions = [
            # Filter by type=chat_memory (use string value for compatibility)
            FieldCondition(
                key="type",
                match=MatchValue(value="chat_memory")
            ),
            # Filter by agent
            FieldCondition(
                key="agent",
                match=MatchValue(value=agent)
            )
        ]

        # Optionally filter by session_id
        if session_id:
            filter_conditions.append(
                FieldCondition(
                    key="session_id",
                    match=MatchValue(value=session_id)
                )
            )

        query_filter = Filter(must=filter_conditions)

        # Scroll with filter (fetch more than needed since we'll sort in Python)
        # Using scroll instead of query_points since we want recency, not similarity
        # Note: We can't use order_by without a payload index on timestamp,
        # so we fetch and sort in Python for graceful degradation
        response = client.scroll(
            collection_name="discussions",
            scroll_filter=query_filter,
            limit=limit * 2,  # Fetch extra to ensure we get recent ones after sorting
            with_payload=True,
            with_vectors=False  # Don't need embeddings for context loading
        )

        # Extract points from scroll response
        # scroll returns (points, next_page_offset)
        points = response[0]

        # Format and sort results by timestamp (most recent first)
        memories = []
        for point in points:
            payload = point.payload
            memories.append({
                "content": payload.get("content", ""),
                "timestamp": payload.get("timestamp", ""),
                "session_id": payload.get("session_id", ""),
                "agent": payload.get("agent", "")
            })

        # Sort by timestamp descending (most recent first)
        memories.sort(key=lambda x: x["timestamp"], reverse=True)

        # Limit to requested number
        memories = memories[:limit]

        return {
            "memories": memories,
            "count": len(memories)
        }

    except Exception as e:
        # Graceful degradation: Return empty result on any error
        # Write error to stderr for debugging, but don't fail the workflow
        print(f"Warning: Chat context loading failed: {e}", file=sys.stderr)
        return {
            "memories": [],
            "count": 0
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Load previous conversation context for BMAD agent session continuity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load recent chat context for dev agent in specific session
  python load-chat-context.py --session-id sess-123 --agent dev

  # Load last 10 memories for architect agent (all sessions)
  python load-chat-context.py --agent architect --limit 10

  # Load context for PM agent with default limit (5)
  python load-chat-context.py --agent pm
        """
    )

    parser.add_argument(
        "--session-id",
        help="Session ID to filter by (optional, searches all sessions if omitted)"
    )
    parser.add_argument(
        "--agent",
        required=True,
        choices=VALID_AGENTS,
        help=f"BMAD agent type. Valid agents: {', '.join(VALID_AGENTS)}"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of memories to return (default: 5)"
    )

    args = parser.parse_args()

    # Validate limit
    if args.limit < 1:
        print("Error: --limit must be at least 1", file=sys.stderr)
        print(json.dumps({"memories": [], "count": 0}, indent=2))
        sys.exit(0)

    # Load chat context
    result = load_chat_context(
        agent=args.agent,
        session_id=args.session_id,
        limit=args.limit
    )

    # Output JSON to stdout for context injection
    print(json.dumps(result, indent=2))

    # Always exit 0 for graceful degradation
    sys.exit(0)


if __name__ == "__main__":
    main()
