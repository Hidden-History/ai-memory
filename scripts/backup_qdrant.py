#!/usr/bin/env python3
"""
Backup script for AI Memory Qdrant database.

Creates snapshots of all collections and downloads them to host filesystem.
Snapshots are stored OUTSIDE Docker to survive container deletion.

Usage:
    python scripts/backup_qdrant.py
    python scripts/backup_qdrant.py --output /custom/backup/path
    python scripts/backup_qdrant.py --include-logs

2026 Best Practices:
- Qdrant REST API for snapshots (most reliable method)
- Download snapshots to host filesystem (survives Docker wipe)
- Manifest file for restore verification
- Granular httpx timeouts
"""

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print(
        "Error: httpx library not found. Install with: pip install httpx",
        file=sys.stderr,
    )
    sys.exit(1)

# Default configuration
# Backup to repo directory (survives reinstall), not install directory
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent  # scripts/ -> repo root
DEFAULT_BACKUP_DIR = os.environ.get("AI_MEMORY_BACKUP_DIR", str(REPO_DIR / "backups"))
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)

# Qdrant configuration
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "26350"))
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")

# Collections to backup (must match config.py)
COLLECTIONS = ["discussions", "conventions", "code-patterns"]

# Timeouts
SNAPSHOT_CREATE_TIMEOUT = 60  # Creating snapshot can take time for large collections
SNAPSHOT_DOWNLOAD_TIMEOUT = 300  # 5 minutes for large downloads

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
    collections: dict  # name -> CollectionBackup
    config_files: list
    includes_logs: bool


def get_headers() -> dict:
    """Get HTTP headers including API key if set."""
    if QDRANT_API_KEY:
        return {"api-key": QDRANT_API_KEY}
    return {}


def get_ai_memory_version() -> str:
    """Get AI Memory version from package or default."""
    try:
        version_file = Path(INSTALL_DIR) / "version.txt"
        if version_file.exists():
            return version_file.read_text().strip()
    except Exception:
        pass
    return "unknown"


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def check_disk_space(backup_dir: Path, estimated_size: int) -> tuple[bool, int]:
    """
    Check if sufficient disk space is available for backup.

    Args:
        backup_dir: Path where backup will be stored
        estimated_size: Estimated backup size in bytes

    Returns:
        Tuple of (has_space, free_bytes)
    """
    # Ensure parent directory exists for disk_usage check
    check_path = backup_dir.parent if not backup_dir.exists() else backup_dir
    if not check_path.exists():
        check_path = Path.home()  # Fallback to home directory

    total, used, free = shutil.disk_usage(check_path)

    # Require 2x estimated size for safety margin
    required = estimated_size * 2
    return free >= required, free


def delete_server_snapshot(collection_name: str, snapshot_name: str) -> bool:
    """
    Delete snapshot from Qdrant server after successful download.

    Prevents snapshot accumulation on server which consumes disk space.

    Args:
        collection_name: Name of the collection
        snapshot_name: Name of the snapshot to delete

    Returns:
        True if deletion succeeded
    """
    timeout_config = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)

    try:
        response = httpx.delete(
            f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}/snapshots/{snapshot_name}",
            headers=get_headers(),
            timeout=timeout_config,
        )
        return response.status_code == 200
    except Exception:
        return False


def get_collection_info(collection_name: str) -> dict:
    """
    Get collection information including record count.

    Returns: {"name": str, "points_count": int, "vectors_count": int}
    """
    timeout_config = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)

    response = httpx.get(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}",
        headers=get_headers(),
        timeout=timeout_config,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to get collection info: HTTP {response.status_code}"
        )

    data = response.json()
    result = data.get("result", {})

    return {
        "name": collection_name,
        "points_count": result.get("points_count", 0),
        "vectors_count": result.get("vectors_count", 0),
    }


def create_snapshot(collection_name: str) -> str:
    """
    Create a snapshot of the collection.

    Returns: snapshot name string (e.g., "snapshot-xxx.snapshot")
    """
    timeout_config = httpx.Timeout(
        connect=3.0, read=float(SNAPSHOT_CREATE_TIMEOUT), write=5.0, pool=3.0
    )

    response = httpx.post(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}/snapshots",
        headers=get_headers(),
        timeout=timeout_config,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to create snapshot: HTTP {response.status_code}")

    data = response.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"Snapshot creation failed: {data}")

    return data["result"]["name"]


def download_snapshot(
    collection_name: str, snapshot_name: str, output_path: Path
) -> int:
    """
    Download a snapshot to the specified path.

    Returns: file size in bytes
    """
    timeout_config = httpx.Timeout(
        connect=3.0, read=float(SNAPSHOT_DOWNLOAD_TIMEOUT), write=5.0, pool=3.0
    )

    url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}/snapshots/{snapshot_name}"

    with httpx.stream(
        "GET", url, headers=get_headers(), timeout=timeout_config
    ) as response:
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to download snapshot: HTTP {response.status_code}"
            )

        with open(output_path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)

    return output_path.stat().st_size


def backup_config_files(backup_dir: Path) -> list[str]:
    """
    Copy configuration files to backup directory.

    Returns: list of copied filenames
    """
    config_dir = backup_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    copied_files = []

    # Settings file
    settings_path = Path(INSTALL_DIR) / ".claude" / "settings.json"
    if settings_path.exists():
        shutil.copy2(settings_path, config_dir / "settings.json")
        copied_files.append("settings.json")

    # Environment file
    env_path = Path(INSTALL_DIR) / ".env"
    if env_path.exists():
        shutil.copy2(env_path, config_dir / ".env")
        copied_files.append(".env")

    return copied_files


def backup_logs(backup_dir: Path) -> bool:
    """
    Copy logs directory to backup.

    Returns: True if successful
    """
    logs_source = Path(INSTALL_DIR) / "logs"
    if not logs_source.exists():
        return False

    logs_dest = backup_dir / "logs"
    try:
        shutil.copytree(logs_source, logs_dest)
        return True
    except Exception:
        return False


def create_manifest(
    backup_dir: Path,
    collections: list[CollectionBackup],
    config_files: list,
    includes_logs: bool,
) -> None:
    """Write manifest.json to backup directory."""
    manifest = BackupManifest(
        backup_date=datetime.now(timezone.utc).isoformat(),
        ai_memory_version=get_ai_memory_version(),
        qdrant_host=QDRANT_HOST,
        qdrant_port=QDRANT_PORT,
        collections={c.name: asdict(c) for c in collections},
        config_files=config_files,
        includes_logs=includes_logs,
    )

    manifest_path = backup_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(asdict(manifest), f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup AI Memory Qdrant database")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=DEFAULT_BACKUP_DIR,
        help="Backup output directory",
    )
    parser.add_argument(
        "--include-logs", action="store_true", help="Include logs directory in backup"
    )
    args = parser.parse_args()

    # Create timestamped backup directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_dir = Path(args.output) / timestamp

    # Create directory structure
    (backup_dir / "qdrant").mkdir(parents=True, exist_ok=True)
    (backup_dir / "config").mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  AI Memory Backup")
    print(f"{'='*60}\n")
    print(f"  Backup directory: {backup_dir}")
    print(f"  Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    print()

    # Check Qdrant connectivity
    try:
        timeout_config = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
        response = httpx.get(
            f"http://{QDRANT_HOST}:{QDRANT_PORT}/healthz",
            headers=get_headers(),
            timeout=timeout_config,
        )
        if response.status_code != 200:
            print(
                f"  {RED}✗ Qdrant not responding (HTTP {response.status_code}){RESET}"
            )
            return 1
    except Exception as e:
        print(f"  {RED}✗ Cannot connect to Qdrant: {e}{RESET}")
        return 1

    # Estimate backup size and check disk space
    print("  Checking disk space...")
    try:
        total_points = 0
        for collection in COLLECTIONS:
            info = get_collection_info(collection)
            total_points += info["points_count"]

        # Rough estimate: 1KB per point (embeddings + payload)
        estimated_size = total_points * 1024
        has_space, free_bytes = check_disk_space(backup_dir, estimated_size)

        if not has_space:
            print(f"  {RED}✗ Insufficient disk space{RESET}")
            print(
                f"    Estimated: {format_size(estimated_size)}, Available: {format_size(free_bytes)}"
            )
            return 3
        print(f"    {GREEN}✓{RESET} {format_size(free_bytes)} available")
    except Exception as e:
        print(f"  {YELLOW}!{RESET} Could not check disk space: {e}")

    # Backup each collection
    collection_backups = []
    total_records = 0
    total_size = 0

    for collection in COLLECTIONS:
        print(f"  Backing up {collection}...")

        try:
            # 1. Get collection info
            info = get_collection_info(collection)
            records = info["points_count"]
            total_records += records

            # 2. Create snapshot
            snapshot_name = create_snapshot(collection)

            # 3. Download snapshot
            output_path = backup_dir / "qdrant" / f"{collection}.snapshot"
            size_bytes = download_snapshot(collection, snapshot_name, output_path)
            total_size += size_bytes

            # 4. Clean up server-side snapshot to prevent accumulation
            if delete_server_snapshot(collection, snapshot_name):
                pass  # Silent success
            else:
                print(
                    f"    {YELLOW}!{RESET} Could not delete server snapshot (non-critical)"
                )

            # 5. Store metadata
            backup = CollectionBackup(
                name=collection,
                records=records,
                snapshot_file=f"{collection}.snapshot",
                size_bytes=size_bytes,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            collection_backups.append(backup)

            print(
                f"    {GREEN}✓{RESET} {records} records, snapshot created ({format_size(size_bytes)})"
            )

        except Exception as e:
            print(f"    {RED}✗ Failed: {e}{RESET}")
            return 2

    print()

    # Backup config files
    print("  Backing up config files...")
    try:
        config_files = backup_config_files(backup_dir)
        for f in config_files:
            print(f"    {GREEN}✓{RESET} {f}")
        if not config_files:
            print(f"    {YELLOW}!{RESET} No config files found")
    except Exception as e:
        print(f"    {RED}✗ Failed: {e}{RESET}")
        return 4

    # Optionally backup logs
    includes_logs = False
    if args.include_logs:
        print()
        print("  Backing up logs...")
        includes_logs = backup_logs(backup_dir)
        if includes_logs:
            print(f"    {GREEN}✓{RESET} Logs copied")
        else:
            print(f"    {YELLOW}!{RESET} No logs found or copy failed")

    # Create manifest
    create_manifest(backup_dir, collection_backups, config_files, includes_logs)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  {GREEN}✓ Backup complete: {backup_dir}{RESET}")
    print()
    print(f"  Total size: {format_size(total_size)}")
    print(f"  Collections: {len(collection_backups)}")
    print(f"  Records: {total_records}")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
