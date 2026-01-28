#!/usr/bin/env python3
"""
AI Memory Module - Queue Repair Script

Purpose: Repair corrupt pending_queue.jsonl file by extracting valid entries
Usage: python scripts/memory/repair_queue.py [--dry-run] [--verbose]

Exit codes:
    0 - Success (queue repaired or already valid)
    1 - Error during repair
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Exit code constants
EXIT_SUCCESS = 0
EXIT_ERROR = 1

# Default queue path
DEFAULT_QUEUE_PATH = Path.home() / ".claude-memory" / "pending_queue.jsonl"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Repair corrupt pending_queue.jsonl file"
    )
    parser.add_argument(
        "--queue-path",
        type=Path,
        default=DEFAULT_QUEUE_PATH,
        help=f"Path to queue file (default: {DEFAULT_QUEUE_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    return parser.parse_args()


def validate_entry(entry: dict) -> bool:
    """Validate that an entry has required fields."""
    required_fields = ["content", "group_id", "memory_type"]
    return all(field in entry for field in required_fields)


def repair_queue(queue_path: Path, dry_run: bool, verbose: bool) -> tuple[int, int, int]:
    """
    Repair the queue file by extracting valid JSON entries.

    Returns:
        Tuple of (valid_count, corrupt_count, recovered_count)
    """
    if not queue_path.exists():
        print(f"Queue file not found: {queue_path}")
        print("Nothing to repair.")
        return (0, 0, 0)

    valid_entries = []
    corrupt_lines = []
    recovered_count = 0

    # Read and validate each line
    with open(queue_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
                if validate_entry(entry):
                    valid_entries.append(line)
                    if verbose:
                        print(f"  Line {line_num}: Valid entry")
                else:
                    corrupt_lines.append((line_num, line, "Missing required fields"))
                    if verbose:
                        print(f"  Line {line_num}: Missing required fields")
            except json.JSONDecodeError as e:
                corrupt_lines.append((line_num, line, str(e)))
                if verbose:
                    print(f"  Line {line_num}: JSON error - {e}")

                # Attempt recovery for truncated JSON
                if line.startswith("{") and not line.endswith("}"):
                    try:
                        # Try to recover by closing the JSON object
                        recovered = json.loads(line + "}")
                        if validate_entry(recovered):
                            valid_entries.append(json.dumps(recovered))
                            recovered_count += 1
                            if verbose:
                                print(f"    → Recovered by closing brace")
                    except json.JSONDecodeError:
                        pass

    valid_count = len(valid_entries)
    corrupt_count = len(corrupt_lines)

    # Report findings
    print(f"\nQueue Analysis:")
    print(f"  Valid entries:   {valid_count}")
    print(f"  Corrupt entries: {corrupt_count}")
    print(f"  Recovered:       {recovered_count}")

    if corrupt_count == 0:
        print("\n✓ Queue file is valid. No repair needed.")
        return (valid_count, corrupt_count, recovered_count)

    if dry_run:
        print(f"\n[DRY RUN] Would write {valid_count} entries to repaired queue")
        print(f"[DRY RUN] Would backup original to {queue_path}.corrupt")
        return (valid_count, corrupt_count, recovered_count)

    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = queue_path.with_suffix(f".backup.{timestamp}")
    corrupt_backup = queue_path.with_suffix(".corrupt")

    try:
        # Backup original
        shutil.copy2(queue_path, backup_path)
        print(f"\n✓ Backup created: {backup_path}")

        # Write repaired queue
        repaired_path = queue_path.with_suffix(".repaired")
        with open(repaired_path, "w", encoding="utf-8") as f:
            for entry in valid_entries:
                f.write(entry + "\n")

        # Atomic replace
        queue_path.rename(corrupt_backup)
        repaired_path.rename(queue_path)

        print(f"✓ Corrupt file moved to: {corrupt_backup}")
        print(f"✓ Repaired queue written: {queue_path}")
        print(f"\nRepair complete. {valid_count} valid entries preserved.")

        if corrupt_count > 0:
            print(f"\n⚠ {corrupt_count} corrupt entries lost. Check {corrupt_backup} if needed.")

    except Exception as e:
        print(f"\n✗ Error during repair: {e}")
        # Restore backup if possible
        if backup_path.exists() and not queue_path.exists():
            shutil.copy2(backup_path, queue_path)
            print(f"  Restored original from backup")
        return (valid_count, corrupt_count, recovered_count)

    return (valid_count, corrupt_count, recovered_count)


def main() -> int:
    """Main entry point."""
    args = parse_args()

    print("=== AI Memory Queue Repair ===")
    print(f"Queue path: {args.queue_path}")
    if args.dry_run:
        print("[DRY RUN MODE]")
    print()

    try:
        valid, corrupt, recovered = repair_queue(
            args.queue_path,
            args.dry_run,
            args.verbose
        )

        # Return success if no errors occurred
        return EXIT_SUCCESS

    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
