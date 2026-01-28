#!/usr/bin/env python3
"""Memory Status CLI - Display BMAD memory system health and statistics.

This script is invoked by the /memory-status slash command to show:
- Collection statistics (point counts, vectors, etc.)
- Service health (Qdrant, embedding service)
- Configuration details

Usage:
  /memory-status

Exit Codes:
- 0: Success
- 1: Error
"""

import json
import logging
import os
import sys
import requests
from typing import Dict, Any

# Add src to path for imports
INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.qdrant_client import get_qdrant_client, QdrantUnavailable
from memory.project import detect_project
from memory.logging_config import StructuredFormatter

# Configure structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.status")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False


def check_qdrant_health() -> Dict[str, Any]:
    """Check Qdrant service health and get collection stats.

    Returns:
        Dict with health status and collection info
    """
    try:
        client = get_qdrant_client()

        # Get collections
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        # Get stats for each collection
        collection_stats = {}
        for name in collection_names:
            try:
                info = client.get_collection(name)
                collection_stats[name] = {
                    "points_count": info.points_count,
                    "status": info.status.name
                }
            except Exception as e:
                collection_stats[name] = {"error": str(e)}

        return {
            "healthy": True,
            "collections": collection_stats
        }

    except QdrantUnavailable as e:
        return {
            "healthy": False,
            "error": f"Qdrant unavailable: {e}"
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }


def check_embedding_service() -> Dict[str, Any]:
    """Check embedding service health.

    Returns:
        Dict with health status
    """
    config = get_config()
    embedding_url = f"http://{config.embedding_host}:{config.embedding_port}/health"

    try:
        response = requests.get(embedding_url, timeout=2)
        if response.status_code == 200:
            return {
                "healthy": True,
                "url": embedding_url
            }
        else:
            return {
                "healthy": False,
                "error": f"HTTP {response.status_code}"
            }
    except requests.exceptions.Timeout:
        return {
            "healthy": False,
            "error": "Timeout"
        }
    except requests.exceptions.ConnectionError:
        return {
            "healthy": False,
            "error": "Connection refused"
        }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }


def format_size(count: int) -> str:
    """Format count with K/M suffixes.

    Args:
        count: Number to format

    Returns:
        Formatted string
    """
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    else:
        return str(count)


def main() -> int:
    """Memory status entry point.

    Returns:
        Exit code: 0 (success) or 1 (error)
    """
    print("\n🧠 BMAD Memory System Status")
    print("=" * 60)

    # Current project
    cwd = os.getcwd()
    project_name = detect_project(cwd)
    print(f"\n📁 Current Project: {project_name}")

    # Configuration
    config = get_config()
    print(f"\n⚙️  Configuration:")
    print(f"   Qdrant: {config.qdrant_host}:{config.qdrant_port}")
    print(f"   Embedding: {config.embedding_host}:{config.embedding_port}")
    print(f"   Similarity Threshold: {config.similarity_threshold}")

    # Qdrant Health
    print(f"\n🗄️  Qdrant Service:")
    qdrant_health = check_qdrant_health()

    if qdrant_health["healthy"]:
        print("   Status: ✅ Healthy")
        print(f"\n   Collections:")

        for name, stats in qdrant_health["collections"].items():
            if "error" in stats:
                print(f"      {name}: ❌ {stats['error']}")
            else:
                points = format_size(stats["points_count"])
                status = stats["status"]
                icon = "✅" if status == "GREEN" else "⚠️"
                print(f"      {icon} {name}: {points} points ({status})")
    else:
        print(f"   Status: ❌ Unhealthy")
        print(f"   Error: {qdrant_health.get('error', 'Unknown')}")

    # Embedding Service Health
    print(f"\n🔢 Embedding Service:")
    embedding_health = check_embedding_service()

    if embedding_health["healthy"]:
        print("   Status: ✅ Healthy")
        print(f"   URL: {embedding_health['url']}")
    else:
        print("   Status: ❌ Unhealthy")
        print(f"   Error: {embedding_health.get('error', 'Unknown')}")

    # Overall status
    print("\n" + "=" * 60)
    all_healthy = qdrant_health["healthy"] and embedding_health["healthy"]

    if all_healthy:
        print("✅ Memory system is operational")
    else:
        print("⚠️  Memory system has issues - check services above")
        print("\nTroubleshooting:")
        print("   1. Check Docker services: docker compose -f docker/docker-compose.yml ps")
        print("   2. View logs: docker compose -f docker/docker-compose.yml logs")
        print("   3. Restart services: docker compose -f docker/docker-compose.yml restart")

    return 0


if __name__ == "__main__":
    sys.exit(main())
