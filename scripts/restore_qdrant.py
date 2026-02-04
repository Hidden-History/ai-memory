#!/usr/bin/env python3
"""
Restore script for AI Memory Qdrant database.

Restores Qdrant collections from backup snapshots created by backup_qdrant.py.
Supports selective restoration and config file recovery.

Usage:
    python scripts/restore_qdrant.py /path/to/backup/2026-02-02_123456
    python scripts/restore_qdrant.py /path/to/backup --restore-config
    python scripts/restore_qdrant.py /path/to/backup --force

2026 Best Practices:
- Verify backup integrity via manifest before restore
- Upload snapshots via Qdrant REST API
- Support for selective collection restore
- Granular httpx timeouts
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print(
        "Error: httpx library not found. Install with: pip install httpx",
        file=sys.stderr,
    )
    sys.exit(1)

# Default configuration
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)

# Qdrant configuration
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "26350"))
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")

# Timeouts
SNAPSHOT_UPLOAD_TIMEOUT = 300  # 5 minutes for large uploads
SNAPSHOT_RECOVER_TIMEOUT = 120  # 2 minutes for recovery

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"


@dataclass
class CollectionBackup:
    """Metadata for a single collection backup."""

    name: str
    records: int
    snapshot_file: str
    size_bytes: int
    created_at: str


@dataclass
class BackupManifest:
    """Complete backup manifest for verification during restore."""

    backup_date: str
    ai_memory_version: str
    qdrant_host: str
    qdrant_port: int
    collections: dict  # name -> CollectionBackup dict
    config_files: list
    includes_logs: bool


def get_headers() -> dict:
    """Get HTTP headers including API key if set."""
    if QDRANT_API_KEY:
        return {"api-key": QDRANT_API_KEY}
    return {}


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def verify_backup(backup_dir: Path) -> BackupManifest:
    """
    Verify backup directory and parse manifest.

    Returns: BackupManifest object
    Raises: RuntimeError if verification fails
    """
    manifest_path = backup_dir / "manifest.json"

    if not manifest_path.exists():
        raise RuntimeError(f"manifest.json not found in {backup_dir}")

    try:
        with open(manifest_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid manifest.json: {e}") from e

    manifest = BackupManifest(
        backup_date=data.get("backup_date", "unknown"),
        ai_memory_version=data.get("ai_memory_version", "unknown"),
        qdrant_host=data.get("qdrant_host", "localhost"),
        qdrant_port=data.get("qdrant_port", 26350),
        collections=data.get("collections", {}),
        config_files=data.get("config_files", []),
        includes_logs=data.get("includes_logs", False),
    )

    # Verify all snapshot files exist
    qdrant_dir = backup_dir / "qdrant"
    for name, info in manifest.collections.items():
        snapshot_file = info.get("snapshot_file", f"{name}.snapshot")
        snapshot_path = qdrant_dir / snapshot_file
        if not snapshot_path.exists():
            raise RuntimeError(f"Missing snapshot file: {snapshot_path}")

    return manifest


def collection_exists(collection_name: str) -> bool:
    """Check if a collection exists in Qdrant."""
    timeout_config = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)

    try:
        response = httpx.get(
            f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}",
            headers=get_headers(),
            timeout=timeout_config,
        )
        return response.status_code == 200
    except Exception:
        return False


def delete_collection(collection_name: str) -> bool:
    """Delete a collection from Qdrant."""
    timeout_config = httpx.Timeout(connect=3.0, read=30.0, write=5.0, pool=3.0)

    response = httpx.delete(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}",
        headers=get_headers(),
        timeout=timeout_config,
    )

    return response.status_code == 200


def create_collection_for_restore(collection_name: str) -> bool:
    """
    Create an empty collection for snapshot restore (fresh install case).

    Uses AI Memory default vector configuration. The snapshot recover
    operation will replace collection data with the backup contents.

    Args:
        collection_name: Name of the collection to create

    Returns:
        True if collection created successfully
    """
    timeout_config = httpx.Timeout(connect=3.0, read=30.0, write=5.0, pool=3.0)

    response = httpx.put(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}",
        headers=get_headers(),
        json={
            "vectors": {
                "size": 1536,  # AI Memory default (OpenAI text-embedding-ada-002)
                "distance": "Cosine",
            }
        },
        timeout=timeout_config,
    )

    return response.status_code == 200


def upload_snapshot(collection_name: str, snapshot_path: Path) -> bool:
    """
    Upload a snapshot file to Qdrant using multipart form data.

    Qdrant 1.16+ requires POST with multipart/form-data for snapshot upload.

    Returns: True if successful
    """
    timeout_config = httpx.Timeout(
        connect=3.0,
        read=float(SNAPSHOT_UPLOAD_TIMEOUT),
        write=float(SNAPSHOT_UPLOAD_TIMEOUT),
        pool=3.0,
    )

    headers = get_headers()
    # Note: Don't set Content-Type - httpx sets it automatically for multipart

    with open(snapshot_path, "rb") as f:
        response = httpx.post(
            f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}/snapshots/upload",
            headers=headers,
            files={"snapshot": (snapshot_path.name, f, "application/octet-stream")},
            timeout=timeout_config,
        )

    return response.status_code == 200


def recover_collection(collection_name: str, snapshot_name: str) -> bool:
    """
    Recover a collection from an uploaded snapshot.

    Qdrant 1.16+ requires the snapshot location in the request body.
    Uploaded snapshots are stored at /qdrant/snapshots/{collection}/{snapshot}

    Returns: True if successful
    """
    timeout_config = httpx.Timeout(
        connect=3.0, read=float(SNAPSHOT_RECOVER_TIMEOUT), write=5.0, pool=3.0
    )

    headers = get_headers()
    headers["Content-Type"] = "application/json"

    # Uploaded snapshots are stored in /qdrant/snapshots/{collection_name}/
    snapshot_location = f"file:///qdrant/snapshots/{collection_name}/{snapshot_name}"

    response = httpx.put(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}/snapshots/recover",
        headers=headers,
        json={"location": snapshot_location},
        timeout=timeout_config,
    )

    return response.status_code == 200


def restore_config_files(
    backup_dir: Path, target_dir: Path, force: bool = False
) -> tuple[list[str], list[str]]:
    """
    Restore configuration files from backup.

    Args:
        backup_dir: Path to backup directory
        target_dir: Path to installation directory
        force: If True, overwrite existing .env file

    Returns:
        Tuple of (restored filenames, skipped filenames)

    Note: .env files contain credentials and are only overwritten with --force
    to prevent accidental credential replacement.
    """
    import shutil

    config_source = backup_dir / "config"
    restored = []
    skipped = []

    if not config_source.exists():
        return restored, skipped

    # Restore settings.json (safe to overwrite - no credentials)
    settings_src = config_source / "settings.json"
    if settings_src.exists():
        settings_dest = target_dir / ".claude" / "settings.json"
        settings_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings_src, settings_dest)
        restored.append("settings.json")

    # Restore .env (requires --force if exists - contains credentials)
    env_src = config_source / ".env"
    if env_src.exists():
        env_dest = target_dir / ".env"
        if env_dest.exists() and not force:
            skipped.append(".env (exists, use --force to overwrite)")
        else:
            shutil.copy2(env_src, env_dest)
            restored.append(".env")

    return restored, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore AI Memory from backup")
    parser.add_argument("backup_dir", type=str, help="Path to backup directory")
    parser.add_argument(
        "--restore-config", action="store_true", help="Also restore configuration files"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing collections without confirmation",
    )
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)

    if not backup_dir.exists():
        print(f"{RED}Error: Backup directory not found: {backup_dir}{RESET}")
        return 1

    print(f"\n{'='*60}")
    print("  AI Memory Restore")
    print(f"{'='*60}\n")
    print(f"  Backup: {backup_dir}")

    # Verify backup
    print()
    print("  Verifying backup...")
    try:
        manifest = verify_backup(backup_dir)
        print(f"    {GREEN}✓{RESET} manifest.json valid")

        # Parse and display backup date
        try:
            backup_date = datetime.fromisoformat(
                manifest.backup_date.replace("Z", "+00:00")
            )
            print(f"  Backup date: {backup_date.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            print(f"  Backup date: {manifest.backup_date}")

        print(f"  Version: {manifest.ai_memory_version}")
        print()

        # Verify snapshot files
        qdrant_dir = backup_dir / "qdrant"
        for name, info in manifest.collections.items():
            snapshot_file = info.get("snapshot_file", f"{name}.snapshot")
            snapshot_path = qdrant_dir / snapshot_file
            size = snapshot_path.stat().st_size
            print(f"    {GREEN}✓{RESET} {snapshot_file} ({format_size(size)})")

    except RuntimeError as e:
        print(f"    {RED}✗ {e}{RESET}")
        return 2

    # Check Qdrant connectivity
    print()
    print(f"  Connecting to Qdrant ({QDRANT_HOST}:{QDRANT_PORT})...")
    try:
        timeout_config = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
        response = httpx.get(
            f"http://{QDRANT_HOST}:{QDRANT_PORT}/healthz",
            headers=get_headers(),
            timeout=timeout_config,
        )
        if response.status_code != 200:
            print(
                f"    {RED}✗ Qdrant not responding (HTTP {response.status_code}){RESET}"
            )
            return 3  # Exit code 3 = Qdrant connection failed
        print(f"    {GREEN}✓{RESET} Connected")
    except Exception as e:
        print(f"    {RED}✗ Cannot connect to Qdrant: {e}{RESET}")
        return 3  # Exit code 3 = Qdrant connection failed

    # Check for existing collections
    existing_collections = []
    for name in manifest.collections:
        if collection_exists(name):
            existing_collections.append(name)

    if existing_collections and not args.force:
        print()
        print(f"  {YELLOW}!{RESET} Existing collections found: {existing_collections}")
        print(f"  {GRAY}Use --force to overwrite{RESET}")

        try:
            response = input("\n  Continue and overwrite? [y/N]: ").strip().lower()
            if response != "y":
                print("  Restore cancelled.")
                return 0
        except KeyboardInterrupt:
            print("\n  Restore cancelled.")
            return 0

    # Restore collections with rollback on failure
    print()
    print("  Restoring collections...")
    total_records = 0
    restored_collections = []  # Track for rollback on failure

    for name, info in manifest.collections.items():
        records = info.get("records", 0)
        total_records += records
        snapshot_file = info.get("snapshot_file", f"{name}.snapshot")
        snapshot_path = backup_dir / "qdrant" / snapshot_file

        print(f"    Restoring {name} ({records} records)...")

        try:
            # Note: We don't delete existing collections before restore.
            # Qdrant's snapshot recover replaces collection data in-place.
            # Deleting first would cause upload to fail with 404.

            # If collection doesn't exist (fresh install), create it first
            if name not in existing_collections:
                print("      Creating collection...")
                if not create_collection_for_restore(name):
                    print(f"      {RED}✗ Failed to create collection{RESET}")
                    # Rollback previously restored collections
                    if restored_collections:
                        print(
                            f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                        )
                        for restored in restored_collections:
                            delete_collection(restored)
                    return 4
                print(f"      {GREEN}✓{RESET} Collection created")

            # Upload snapshot (collection must exist)
            if not upload_snapshot(name, snapshot_path):
                print(f"      {RED}✗ Snapshot upload failed{RESET}")
                # Rollback previously restored collections
                if restored_collections:
                    print(
                        f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                    )
                    for restored in restored_collections:
                        delete_collection(restored)
                return 4
            print(f"      {GREEN}✓{RESET} Snapshot uploaded")

            # Get the uploaded snapshot name (it's the filename)
            uploaded_name = snapshot_file

            # Recover collection from snapshot
            if not recover_collection(name, uploaded_name):
                print(f"      {RED}✗ Collection recovery failed{RESET}")
                # Rollback previously restored collections
                if restored_collections:
                    print(
                        f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                    )
                    for restored in restored_collections:
                        delete_collection(restored)
                return 4
            print(f"      {GREEN}✓{RESET} Collection recovered")

            # Track successful restoration for potential rollback
            restored_collections.append(name)

        except Exception as e:
            print(f"      {RED}✗ Error: {e}{RESET}")
            # Rollback previously restored collections
            if restored_collections:
                print(
                    f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                )
                for restored in restored_collections:
                    delete_collection(restored)
            return 4

    # Optionally restore config files
    if args.restore_config:
        print()
        print("  Restoring config files...")
        try:
            restored, skipped = restore_config_files(
                backup_dir, Path(INSTALL_DIR), force=args.force
            )
            for f in restored:
                print(f"    {GREEN}✓{RESET} {f}")
            for f in skipped:
                print(f"    {YELLOW}!{RESET} {f}")
            if not restored and not skipped:
                print(f"    {YELLOW}!{RESET} No config files in backup")
        except Exception as e:
            print(f"    {RED}✗ Failed: {e}{RESET}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  {GREEN}✓ Restore complete{RESET}")
    print()
    print(f"  Collections restored: {len(manifest.collections)}")
    print(f"  Total records: {total_records}")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
