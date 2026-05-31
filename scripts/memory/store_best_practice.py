#!/usr/bin/env python3
# scripts/memory/store_best_practice.py
"""Store a single best practice to the conventions collection.

Externalizes the "Phase 4: Store to Database" inline Python block from
aim-best-practices-researcher, routing project-scope resolution through the
canonical resolve_project_id helper (RISK-021 fix).

**Deliberate behaviour change (RISK-021 / DEC-108 C-1 / DEC-106 carve-out)**:
The skill previously resolved scope via env-only lookup with a ``RuntimeError``
on unset. This script routes through ``resolve_project_id(cwd=os.getcwd(),
explicit=args.group_id)``, which supports four tiers (explicit flag →
AI_MEMORY_PROJECT_ID env → .ai-memory-project marker → git remote) before
raising ``ValueError``. This is a correctness-restoration change per DEC-106,
not a silent behaviour change.

Invoke via:
    scripts/memory/run-with-env.sh store_best_practice.py \\
        --content "..." --session-id "..." [options]
"""

import argparse
import logging
import os
import sys

from memory.project import resolve_project_id
from memory.storage import store_best_practice

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Entry point for storing a single best practice.

    Returns:
        0 on success (stored or duplicate).
        2 on project-scope resolution failure or storage validation error.
        1 on unexpected storage error.
    """
    parser = argparse.ArgumentParser(
        description="Store a best practice to the conventions collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./run-with-env.sh store_best_practice.py \\
      --content "Use type hints in Python 3.10+" \\
      --session-id "sess-abc123" \\
      --domain python --tags typing hints

  # Explicit project scope:
  ./run-with-env.sh store_best_practice.py \\
      --content "..." --session-id "..." --group-id my-project
""",
    )
    parser.add_argument(
        "--content",
        required=True,
        help="Best practice text content",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        dest="session_id",
        help="Current Claude session ID",
    )
    parser.add_argument(
        "--group-id",
        default=None,
        dest="group_id",
        help=(
            "Project group ID (optional — resolves via full-precedence chain: "
            "explicit flag → AI_MEMORY_PROJECT_ID env → .ai-memory-project marker "
            "→ git remote → fail-loud ValueError)"
        ),
    )
    parser.add_argument(
        "--source-hook",
        default="manual",
        dest="source_hook",
        help="Hook that captured this best practice (default: manual)",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Topic domain (e.g. python, testing, architecture)",
    )
    parser.add_argument(
        "--tags",
        nargs="*",
        default=None,
        help="Tags (space-separated list)",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Source URL",
    )
    parser.add_argument(
        "--source-date",
        default=None,
        dest="source_date",
        help="Source date (YYYY-MM-DD)",
    )

    args = parser.parse_args()

    try:
        group_id = resolve_project_id(cwd=os.getcwd(), explicit=args.group_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        result = store_best_practice(
            content=args.content,
            session_id=args.session_id,
            source_hook=args.source_hook,
            group_id=group_id,
            domain=args.domain,
            tags=args.tags,
            source=args.source,
            source_date=args.source_date,
            auto_seeded=True,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        logger.error(
            "store_failed",
            extra={"error_type": type(exc).__name__, "error": str(exc)},
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if result.get("status") == "stored":
        print(f"Stored: {result['memory_id']}")
    elif result.get("status") == "duplicate":
        print("Duplicate skipped")
    else:
        print(
            f"WARNING: unexpected status {result.get('status')!r} — {result}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
