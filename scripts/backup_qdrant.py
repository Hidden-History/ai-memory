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
import hashlib
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    print(
        "Error: httpx library not found. Install with: pip install httpx",
        file=sys.stderr,
    )
    sys.exit(1)

# BUG-275: load split env files before module-level os.environ.get() reads (BP-153 §3)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env_loader import load_install_env

load_install_env()

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

# Collections to backup (must match config.py — includes jira-data from v2.0.5, github from v2.0.9)
COLLECTIONS = ["discussions", "conventions", "code-patterns", "jira-data", "github"]

# Timeouts (TD-517 B-3: bumped default to 300s; env-overridable)
SNAPSHOT_CREATE_TIMEOUT = int(os.environ.get("BACKUP_SNAPSHOT_CREATE_TIMEOUT", "300"))
SNAPSHOT_DOWNLOAD_TIMEOUT = int(
    os.environ.get("BACKUP_SNAPSHOT_DOWNLOAD_TIMEOUT", "300")
)

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"


@dataclass
class CollectionBackup:
    """Metadata for a single collection backup.

    TD-517 B-1: ``schema`` captures the full Qdrant collection fingerprint
    (vectors_config + sparse_vectors_config + multivector_config + hnsw_config
    + quantization_config + on_disk_payload + shard_number + payload_schema)
    so the restore path can recreate the target collection with byte-equivalent
    structure before snapshot upload. Absent on pre-v2.4.1 manifests; restore
    treats absence as a fail-fast condition.
    """

    name: str
    records: int
    snapshot_file: str
    size_bytes: int
    created_at: str
    schema: dict | None = None


@dataclass
class BackupManifest:
    """Complete backup manifest for verification during restore.

    TD-517 B-7: ``runtime_flags`` records the embedding/search feature flags
    that were active at backup time. Diagnostic-only — the authoritative
    schema source is each ``CollectionBackup.schema`` fingerprint.
    """

    backup_date: str
    ai_memory_version: str
    qdrant_host: str
    qdrant_port: int
    collections: dict  # name -> CollectionBackup
    config_files: list
    includes_logs: bool
    runtime_flags: dict | None = None


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

    _total, _used, free = shutil.disk_usage(check_path)

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
    """Get collection information including record count and schema fingerprint.

    TD-517 B-1: a single GET ``/collections/{name}`` call now also yields the
    full schema fingerprint that the restore path needs to recreate the
    collection before snapshot upload. No extra round-trip vs the previous
    counts-only implementation.

    Returns:
        Dict with keys ``name``, ``points_count``, ``vectors_count``, and
        ``schema``. The ``schema`` value is the raw ``result`` payload from
        Qdrant containing ``config.params.vectors``,
        ``config.params.sparse_vectors``, ``config.params.shard_number``,
        ``config.params.on_disk_payload``, ``config.hnsw_config``,
        ``config.quantization_config`` and ``payload_schema``.
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
        "schema": _build_schema_fingerprint(result),
    }


def _normalize_payload_schema(payload_schema: dict | None) -> dict:
    """Strip volatile per-field point counts from a payload_schema block.

    Qdrant's ``payload_schema`` entries carry a ``points`` count that changes
    as data is written. Keeping it would make two structurally identical
    collections compare unequal whenever their row counts differ, so the
    fingerprint retains only the structural fields (``data_type``, ``params``).
    """
    normalized: dict = {}
    for field_name, field_info in (payload_schema or {}).items():
        if not isinstance(field_info, dict):
            normalized[field_name] = field_info
            continue
        normalized[field_name] = {k: v for k, v in field_info.items() if k != "points"}
    return normalized


def _build_schema_fingerprint(get_collection_result: dict) -> dict:
    """Distill Qdrant's GET /collections/{name} payload into a stable manifest fingerprint.

    Keeps only the fields needed to recreate the collection (vector params,
    sparse vectors, multivector config, HNSW, quantization, on-disk payload,
    shard count, and the structural payload index schema). Discards runtime
    status fields (``optimizer_status``, ``warnings``, ``segments_count``,
    ``indexed_vectors_count``) and the volatile per-field ``points`` count so
    the fingerprint stays stable across backup/restore comparison regardless
    of row count.
    """
    config = get_collection_result.get("config", {}) or {}
    params = config.get("params", {}) or {}
    return {
        "params": {
            "vectors": params.get("vectors"),
            "sparse_vectors": params.get("sparse_vectors"),
            "shard_number": params.get("shard_number"),
            "on_disk_payload": params.get("on_disk_payload"),
        },
        "hnsw_config": config.get("hnsw_config"),
        "quantization_config": config.get("quantization_config"),
        "payload_schema": _normalize_payload_schema(
            get_collection_result.get("payload_schema")
        ),
    }


def get_runtime_flags() -> dict:
    """Capture the embedding/search feature flags that were active at backup time.

    TD-517 B-7: diagnostic-only. Restore does NOT consult these for schema
    decisions (the authoritative source is each ``CollectionBackup.schema``).
    Useful when an operator inspects a manifest months later and needs to know
    which feature flags the snapshot was taken under.
    """
    flag_names = (
        "COLBERT_RERANKING_ENABLED",
        "HYBRID_SEARCH_ENABLED",
        "BM25_SPARSE_ENABLED",
    )
    return {flag: os.environ.get(flag, "") for flag in flag_names}


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
    runtime_flags: dict | None = None,
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
        runtime_flags=runtime_flags or {},
    )

    manifest_path = backup_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(asdict(manifest), f, indent=2)


def _sha256_file(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file, streaming in 1MB chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(backup_dir: Path) -> Path:
    """Write CHECKSUMS.sha256 over manifest.json and every snapshot file.

    TD-517 B-2: enables integrity verification before restore upload. The
    output format is ``sha256sum -c`` compatible (``<hex>  <relative-path>``)
    so operators can validate a backup independently of the restore script.
    """
    entries: list[tuple[str, str]] = []

    manifest_path = backup_dir / "manifest.json"
    if manifest_path.exists():
        entries.append((_sha256_file(manifest_path), "manifest.json"))

    qdrant_dir = backup_dir / "qdrant"
    if qdrant_dir.exists():
        for snapshot_path in sorted(qdrant_dir.glob("*.snapshot")):
            rel = snapshot_path.relative_to(backup_dir).as_posix()
            entries.append((_sha256_file(snapshot_path), rel))

    checksums_path = backup_dir / "CHECKSUMS.sha256"
    with open(checksums_path, "w") as f:
        for digest, rel in entries:
            f.write(f"{digest}  {rel}\n")
    return checksums_path


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
            # 1. Get collection info + schema fingerprint (TD-517 B-1)
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

            # 5. Store metadata — TD-517 B-1 includes the schema fingerprint
            #    so restore can rebuild the collection with byte-equivalent
            #    config before snapshot upload.
            backup = CollectionBackup(
                name=collection,
                records=records,
                snapshot_file=f"{collection}.snapshot",
                size_bytes=size_bytes,
                created_at=datetime.now(timezone.utc).isoformat(),
                schema=info.get("schema"),
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

    # Create manifest — TD-517 B-7 records runtime flags for diagnostic context
    create_manifest(
        backup_dir,
        collection_backups,
        config_files,
        includes_logs,
        runtime_flags=get_runtime_flags(),
    )

    # TD-517 B-2: write CHECKSUMS.sha256 for restore-time integrity verification
    try:
        checksums_path = write_checksums(backup_dir)
        print(f"  {GREEN}✓{RESET} Checksums written: {checksums_path.name}")
    except Exception as e:
        print(f"  {YELLOW}!{RESET} Could not write checksums (non-critical): {e}")

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
