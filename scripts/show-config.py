#!/usr/bin/env python3
"""Display current BMAD Memory Module configuration.

2026 Best Practices:
- Read-only operation (no side effects)
- Clear, formatted output
- Shows both values and sources (env var or default)
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.config import get_config


def main() -> None:
    """Display current configuration."""
    try:
        config = get_config()
    except Exception as e:
        print(f"\n❌ Configuration Error: {e}\n", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  BMAD Memory Module Configuration")
    print("=" * 70 + "\n")

    print("  Core Thresholds:")
    print(f"    SIMILARITY_THRESHOLD:      {config.similarity_threshold}")
    print(f"    DEDUP_THRESHOLD:           {config.dedup_threshold}")
    print(f"    MAX_RETRIEVALS:            {config.max_retrievals}")
    print(f"    TOKEN_BUDGET:              {config.token_budget}")

    print("\n  Service Endpoints:")
    print(f"    Qdrant:     {config.get_qdrant_url()}")
    print(f"    Embedding:  {config.get_embedding_url()}")
    print(f"    Monitoring: {config.get_monitoring_url()}")

    print("\n  Logging:")
    print(f"    Level:  {config.log_level}")
    print(f"    Format: {config.log_format}")

    print("\n  Collection Thresholds:")
    print(f"    Warning:  {config.collection_size_warning:,} memories")
    print(f"    Critical: {config.collection_size_critical:,} memories")

    print("\n  Paths:")
    print(f"    Install dir:  {config.install_dir}")
    print(f"    Queue file:   {config.queue_path}")
    print(f"    Session logs: {config.session_log_path}")

    print("\n" + "=" * 70 + "\n")
    print("  To modify configuration:")
    print("    1. Copy .env.example to .env")
    print("    2. Edit .env with your values")
    print("    3. Restart Claude Code session")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
