#!/usr/bin/env python3
"""Jira synchronization CLI.

Command-line tool for syncing Jira issues and comments to AI Memory.

Usage:
    jira_sync.py --full                    # Full sync all projects
    jira_sync.py --incremental             # Incremental sync (default)
    jira_sync.py --project PROJ            # Sync specific project only
    jira_sync.py --status                  # Show sync status

Implements PLAN-004 Phase 2: CLI interface for manual and cron-based sync.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.config import get_config
from memory.connectors.jira.sync import JiraSyncEngine


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Sync Jira issues and comments to AI Memory Module",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --full                    # Full sync all configured projects
  %(prog)s --incremental             # Incremental sync (since last sync)
  %(prog)s --project PROJ            # Sync single project only
  %(prog)s --status                  # Display sync status

Modes:
  --full:        Complete backfill (all issues including closed/resolved)
  --incremental: Since last sync (uses jira_sync_state.json timestamps)

Configuration:
  Set JIRA_SYNC_ENABLED=true and configure credentials in .env:
    JIRA_INSTANCE_URL=https://company.atlassian.net
    JIRA_EMAIL=user@example.com
    JIRA_API_TOKEN=your_api_token
    JIRA_PROJECTS=PROJ1,PROJ2
        """,
    )

    # Mode flags (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Full sync (all issues including closed/resolved)",
    )
    mode_group.add_argument(
        "--incremental",
        action="store_true",
        default=True,
        help="Incremental sync since last sync (default)",
    )

    # Project filter
    parser.add_argument(
        "--project",
        type=str,
        metavar="KEY",
        help="Sync specific project only (e.g., PROJ)",
    )

    # Status display
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display sync status and exit (no sync performed)",
    )

    args = parser.parse_args()

    # Check if Jira sync is enabled
    try:
        config = get_config()
    except Exception as e:
        print(f"Error: Failed to load configuration: {e}", file=sys.stderr)
        sys.exit(1)

    if not config.jira_sync_enabled:
        print("Error: Jira sync is not enabled.", file=sys.stderr)
        print("", file=sys.stderr)
        print("To enable:", file=sys.stderr)
        print("  1. Set JIRA_SYNC_ENABLED=true in .env", file=sys.stderr)
        print("  2. Configure credentials:", file=sys.stderr)
        print("     JIRA_INSTANCE_URL=https://company.atlassian.net", file=sys.stderr)
        print("     JIRA_EMAIL=user@example.com", file=sys.stderr)
        print("     JIRA_API_TOKEN=your_api_token", file=sys.stderr)
        print("     JIRA_PROJECTS=PROJ1,PROJ2", file=sys.stderr)
        sys.exit(1)

    # Run async main
    try:
        asyncio.run(run_sync(args, config))
    except KeyboardInterrupt:
        print("\nSync interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


async def run_sync(args, config):
    """Async main function.

    Args:
        args: Parsed command-line arguments
        config: MemoryConfig instance
    """
    # Initialize sync engine
    try:
        engine = JiraSyncEngine(config)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.status:
            # Display status only (no sync)
            display_status(engine)
            return

        # Determine sync mode
        mode = "full" if args.full else "incremental"

        print("=" * 70)
        print("  Jira Sync")
        print("=" * 70)
        print(f"Mode: {mode}")
        print("")

        if args.project:
            # Sync single project
            print(f"Project: {args.project}")
            print("")
            result = await engine.sync_project(args.project, mode)
            print_result(args.project, result)
        else:
            # Sync all configured projects
            if not config.jira_projects:
                print("Error: No projects configured (JIRA_PROJECTS is empty)", file=sys.stderr)
                sys.exit(1)

            print(f"Projects: {', '.join(config.jira_projects)}")
            print("")
            results = await engine.sync_all_projects(mode)

            # Print results for each project
            for project_key, result in results.items():
                print_result(project_key, result)
                print("")

        print("=" * 70)

    finally:
        await engine.close()


def display_status(engine: JiraSyncEngine):
    """Display sync status from state file.

    Args:
        engine: JiraSyncEngine instance
    """
    state = engine._load_state()

    print("=" * 70)
    print("  Jira Sync Status")
    print("=" * 70)
    print("")

    projects = state.get("projects", {})
    if not projects:
        print("No sync history found.")
        print("")
        print("Run a sync to populate history:")
        print("  jira_sync.py --full")
        return

    for project_key, data in projects.items():
        print(f"Project: {project_key}")
        print(f"  Last synced: {data.get('last_synced', 'Never')}")
        print(f"  Issues synced: {data.get('last_issue_count', 0)}")
        print(f"  Comments synced: {data.get('last_comment_count', 0)}")
        print("")

    print("=" * 70)


def print_result(project_key: str, result):
    """Print sync result for a project.

    Args:
        project_key: Project key
        result: SyncResult instance
    """
    print(f"Project: {project_key}")
    print(f"  Issues synced: {result.issues_synced}")
    print(f"  Comments synced: {result.comments_synced}")
    print(f"  Duration: {result.duration_seconds:.1f}s")

    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        print("")
        print("  Error details:")
        for error in result.errors[:5]:  # Show first 5 errors
            print(f"    - {error}")
        if len(result.errors) > 5:
            print(f"    ... and {len(result.errors) - 5} more")


if __name__ == "__main__":
    main()
