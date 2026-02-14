#!/usr/bin/env python3
"""GitHub synchronization CLI.

Command-line tool for syncing GitHub data to AI Memory.

Usage:
    github_sync.py --full                   # Full sync (all data)
    github_sync.py --incremental            # Incremental sync (default)
    github_sync.py --code-only              # Sync only code blobs
    github_sync.py --status                 # Show sync status

Implements PLAN-006 Phase 1a: CLI interface for manual and cron-based sync.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.config import get_config
from memory.connectors.github.client import GitHubClient
from memory.connectors.github.sync import GitHubSyncEngine
from memory.connectors.github.code_sync import CodeBlobSync


def show_status(config):
    """Display sync status from state files.

    State file location: Path.cwd() / ".audit" / "state" / "github_sync_state.json"
    Note: config.project_path does NOT exist — engine uses Path.cwd() fallback.
    CodeBlobSync does not maintain state files (stateless per run).
    """
    # Mirror sync.py state resolution: Path.cwd() / ".audit" / "state"
    state_dir = Path.cwd() / ".audit" / "state"
    sync_state_file = state_dir / "github_sync_state.json"

    print("GitHub Sync Status")
    print("=" * 50)
    print(f"Repository: {config.github_repo}")
    print(f"Sync enabled: {config.github_sync_enabled}")
    print(f"Code blobs enabled: {config.github_code_blob_enabled}")
    print(f"Sync interval: {config.github_sync_interval}s")
    print(f"State directory: {state_dir}")
    print()

    if sync_state_file.exists():
        state = json.loads(sync_state_file.read_text())
        print("Last sync state (issues/PRs/commits/CI):")
        for key, val in state.items():
            if isinstance(val, dict) and "last_synced" in val:
                print(f"  {key}: last_synced={val['last_synced']}, count={val.get('last_count', '?')}")
    else:
        print("No sync state found (never synced)")

    print()
    print("Code blob sync: stateless (no persistent state file)")


async def run_sync(config, full: bool = False, code_only: bool = False):
    """Run GitHub sync."""
    mode = "full" if full else "incremental"

    if not code_only:
        print(f"Syncing GitHub data from {config.github_repo} (mode={mode})...")
        engine = GitHubSyncEngine(config)
        result = await engine.sync(mode=mode)
        print(f"  Issues: {result.issues_synced} synced, Comments: {result.comments_synced}")
        print(f"  PRs: {result.prs_synced}, Reviews: {result.reviews_synced}, Diffs: {result.diffs_synced}")
        print(f"  Commits: {result.commits_synced}, CI results: {result.ci_results_synced}")
        print(f"  Skipped (dedup): {result.items_skipped}, Errors: {result.errors}")
        print(f"  Duration: {result.duration_seconds:.1f}s")

    if code_only or config.github_code_blob_enabled:
        print(f"\nSyncing code blobs from {config.github_repo} ({config.github_branch} branch)...")
        client = GitHubClient(
            token=config.github_token.get_secret_value(),
            repo=config.github_repo,
        )
        async with client:
            code_sync = CodeBlobSync(client, config)
            batch_id = GitHubClient.generate_batch_id()
            code_result = await code_sync.sync_code_blobs(batch_id)
        print(f"  Files synced: {code_result.files_synced}")
        print(f"  Files skipped: {code_result.files_skipped}")
        print(f"  Files deleted: {code_result.files_deleted}")
        print(f"  Errors: {code_result.errors}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Sync GitHub data to AI Memory Module",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --full                    # Full sync all GitHub data
  %(prog)s --incremental             # Incremental sync (since last sync)
  %(prog)s --code-only               # Sync only code blobs
  %(prog)s --status                  # Display sync status

Configuration:
  Set GITHUB_SYNC_ENABLED=true and configure in .env:
    GITHUB_TOKEN=ghp_your_token_here
    GITHUB_REPO=owner/repo
        """,
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--full", action="store_true", help="Full sync (all data)")
    mode_group.add_argument("--incremental", action="store_true", help="Incremental sync (default)")
    mode_group.add_argument("--code-only", action="store_true", help="Sync only code blobs")
    mode_group.add_argument("--status", action="store_true", help="Display sync status")

    args = parser.parse_args()

    config = get_config()

    if not config.github_sync_enabled:
        print("ERROR: GITHUB_SYNC_ENABLED is not true")
        print("Enable GitHub sync in your .env file")
        sys.exit(1)

    if args.status:
        show_status(config)
        return

    asyncio.run(run_sync(config, full=args.full, code_only=args.code_only))
    print("\nDone.")


if __name__ == "__main__":
    main()
