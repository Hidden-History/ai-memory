#!/usr/bin/env python3
"""Display collection statistics and check thresholds.

Provides human-readable output of collection statistics including:
- Total memories and disk size
- Last updated timestamp
- Per-project breakdown
- Threshold warnings (WARNING/CRITICAL)

Usage:
    python scripts/memory/collection_stats.py

Complies with:
- AC 6.6.4: Statistics Script requirements
- project-context.md: snake_case naming, structured logging
"""

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from qdrant_client import QdrantClient
from memory.config import get_config
from memory.stats import get_collection_stats
from memory.warnings import check_collection_thresholds


def format_bytes(bytes_val: int) -> str:
    """Format bytes as human-readable size.

    Args:
        bytes_val: Size in bytes

    Returns:
        Formatted string (e.g., "5.24 MB")
    """
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.2f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"


def main():
    """Display collection statistics for both collections."""
    try:
        # Initialize Qdrant client
        config = get_config()
        client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)

        print("=" * 60)
        print("BMAD Memory Collection Statistics")
        print("=" * 60)

        # Analyze both collections
        for collection_name in ["implementations", "best_practices"]:
            try:
                stats = get_collection_stats(client, collection_name)

                print(f"\n📦 {collection_name}")
                print(f"   Total memories: {stats.total_points:,}")
                print(
                    f"   Indexed memories: {stats.indexed_points:,}"
                )
                print(f"   Segments: {stats.segments_count}")
                print(f"   Disk size: {format_bytes(stats.disk_size_bytes)}")
                print(f"   Last updated: {stats.last_updated or 'N/A'}")
                print(f"   Projects: {len(stats.projects)}")

                # Per-project breakdown
                if stats.projects:
                    for project, count in sorted(stats.points_by_project.items()):
                        print(f"     - {project}: {count:,}")

                # Check thresholds
                warnings = check_collection_thresholds(stats)
                if warnings:
                    print()
                    for warning in warnings:
                        print(f"   ⚠️  {warning}")

            except Exception as e:
                print(f"\n📦 {collection_name}")
                print(f"   ❌ Error: {e}")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
