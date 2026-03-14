#!/usr/bin/env python3
# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# FORBIDDEN: Langfuse() constructor, start_span(), start_generation(), langfuse_context
# REQUIRED: get_client(), create_score(), flush()
"""CLI entry point for the LLM-as-Judge evaluation pipeline.

Fetches traces from Langfuse, applies evaluator prompts via a configurable LLM,
and attaches scores back to traces via create_score() (V3 SDK, idempotent).

Usage:
  python scripts/run_evaluations.py --config evaluator_config.yaml
  python scripts/run_evaluations.py --config evaluator_config.yaml --evaluator EV-01
  python scripts/run_evaluations.py --config evaluator_config.yaml --dry-run
  python scripts/run_evaluations.py --config evaluator_config.yaml --since 2026-03-12T00:00:00Z

PLAN-012 Phase 2 — Section 5.4
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Langfuse LLM-as-Judge evaluations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to evaluator_config.yaml",
    )
    parser.add_argument(
        "--evaluator",
        default=None,
        help="Run specific evaluator by ID (e.g., EV-01). Omit to run all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Evaluate traces but do NOT save scores to Langfuse.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Evaluate traces since this ISO datetime (default: 24h ago). "
        "Example: 2026-03-12T00:00:00Z",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Traces to fetch per pagination batch (default: 10).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Parse --since
    since: datetime | None = None
    if args.since:
        # Support duration strings like "24h", "48h", "7d" as well as ISO datetimes
        import re

        duration_match = re.match(r"^(\d+)([hd])$", args.since.strip())
        if duration_match:
            amount, unit = int(duration_match.group(1)), duration_match.group(2)
            delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
            since = datetime.now(tz=timezone.utc) - delta
        else:
            try:
                since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
            except ValueError as exc:
                print(
                    f"ERROR: Invalid --since value '{args.since}': {exc}",
                    file=sys.stderr,
                )
                return 1
    else:
        since = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    until = datetime.now(tz=timezone.utc)

    if args.dry_run:
        print("[DRY RUN] Scores will NOT be saved to Langfuse.")

    print(f"Config:     {args.config}")
    print(f"Evaluator:  {args.evaluator or 'ALL'}")
    print(f"Since:      {since.isoformat()}")
    print(f"Until:      {until.isoformat()}")
    print(f"Batch size: {args.batch_size}")
    print()

    try:
        # Import here so sys.path issues surface clearly
        import sys as _sys
        from pathlib import Path

        # Add project root to path if needed
        project_root = Path(__file__).parent.parent
        if str(project_root / "src") not in _sys.path:
            _sys.path.insert(0, str(project_root / "src"))

        from memory.evaluator import EvaluatorRunner

        runner = EvaluatorRunner(config_path=args.config)
        summary = runner.run(
            evaluator_id=args.evaluator,
            since=since,
            until=until,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )

        print("\n=== Summary ===")
        print(f"Traces fetched:   {summary['fetched']}")
        print(f"Traces sampled:   {summary['sampled']}")
        print(f"Traces evaluated: {summary['evaluated']}")
        print(f"Scores attached:  {summary['scored']}")
        if args.dry_run:
            print("(dry-run: scores were NOT saved)")

        return 0

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
