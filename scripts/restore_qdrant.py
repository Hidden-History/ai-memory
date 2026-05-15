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
import contextlib
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

# BUG-275: load split env files before module-level os.environ.get() reads (BP-153 §3)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env_loader import load_install_env

load_install_env()

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
    """Metadata for a single collection backup.

    TD-517 B-1: ``schema`` is the captured Qdrant fingerprint
    (vectors_config + sparse_vectors_config + hnsw_config +
    quantization_config + on_disk_payload + shard_number +
    payload_schema). Present on manifests produced by v2.4.1+ backups;
    absent on legacy manifests. Restore treats absence as a fail-fast
    condition rather than silently defaulting to a single-vector prefab.
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

    TD-517 B-7: ``runtime_flags`` carries diagnostic feature-flag context
    captured at backup time. Not consulted for schema decisions.
    """

    backup_date: str
    ai_memory_version: str
    qdrant_host: str
    qdrant_port: int
    collections: dict  # name -> CollectionBackup dict
    config_files: list
    includes_logs: bool
    runtime_flags: dict | None = None


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
        runtime_flags=data.get("runtime_flags") or {},
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


def create_collection_from_manifest_schema(
    target_name: str, schema_payload: dict
) -> tuple[bool, str]:
    """Recreate a collection from a manifest schema fingerprint (TD-517 R-1).

    Replaces the legacy hardcoded single-vector ``create_collection_for_restore``
    helper. Provides Qdrant with the full original collection configuration
    (named vectors, sparse vectors, multivector config, HNSW, quantization,
    on-disk payload, shard number) so the subsequent snapshot upload sees a
    byte-equivalent target. Then recreates every payload index captured in the
    manifest's ``payload_schema`` so multi-tenancy, full-text, and freshness
    filters survive the round-trip.

    Returns:
        Tuple of (success, error_message). On success, error_message is "".
    """
    params = (schema_payload or {}).get("params") or {}
    vectors = params.get("vectors")
    if vectors is None:
        return False, "schema fingerprint missing config.params.vectors"

    body: dict = {"vectors": vectors}
    sparse = params.get("sparse_vectors")
    if sparse:
        body["sparse_vectors"] = sparse
    if params.get("shard_number") is not None:
        body["shard_number"] = params["shard_number"]
    if params.get("on_disk_payload") is not None:
        body["on_disk_payload"] = params["on_disk_payload"]
    if schema_payload.get("hnsw_config"):
        body["hnsw_config"] = schema_payload["hnsw_config"]
    if schema_payload.get("quantization_config"):
        body["quantization_config"] = schema_payload["quantization_config"]

    timeout_config = httpx.Timeout(connect=3.0, read=30.0, write=5.0, pool=3.0)
    headers = {**get_headers(), "Content-Type": "application/json"}

    response = httpx.put(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{target_name}",
        headers=headers,
        json=body,
        timeout=timeout_config,
    )
    if response.status_code != 200:
        return (
            False,
            f"create_collection HTTP {response.status_code}: {response.text[:300]}",
        )

    # Recreate payload indexes from the captured payload_schema. Mirrors the
    # `recreate_payload_indices` helper in scripts/migrate_v221_hybrid_vectors.py:
    # prefer ``params`` (carries is_tenant, tokenizer settings, etc.) and fall
    # back to bare ``data_type`` when no params block was captured.
    payload_schema = schema_payload.get("payload_schema") or {}
    for field_name, field_info in payload_schema.items():
        if not isinstance(field_info, dict):
            continue
        field_schema = field_info.get("params") or field_info.get("data_type")
        if not field_schema:
            continue
        # Best-effort: keep recreating remaining indexes if one errors. A
        # missing payload index degrades search but does not prevent restore;
        # surfaced indirectly via post-restore count + sample checks.
        with contextlib.suppress(Exception):
            httpx.put(
                f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{target_name}/index",
                headers=headers,
                json={"field_name": field_name, "field_schema": field_schema},
                timeout=timeout_config,
            )

    return True, ""


# TD-517 R-2: schema-fingerprint helpers. Mirror the distillation in
# scripts/backup_qdrant.py:_build_schema_fingerprint so a live collection can
# be compared against a manifest entry without importing across scripts. The
# shared-helper refactor is tracked as a separate post-merge low-severity TD.


def _build_schema_fingerprint(get_collection_result: dict) -> dict:
    """Distill GET /collections/{name} into the same shape backup_qdrant.py records."""
    config = (get_collection_result or {}).get("config", {}) or {}
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
        "payload_schema": (get_collection_result or {}).get("payload_schema") or {},
    }


def _fingerprint_signature(schema: dict | None) -> str:
    """Stable JSON encoding of a schema fingerprint for diff display."""
    return json.dumps(schema or {}, sort_keys=True, separators=(",", ":"))


def fetch_live_schema(collection_name: str) -> dict | None:
    """Fetch the live target's schema fingerprint, or None if the collection is absent."""
    timeout_config = httpx.Timeout(connect=3.0, read=10.0, write=5.0, pool=3.0)
    response = httpx.get(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection_name}",
        headers=get_headers(),
        timeout=timeout_config,
    )
    if response.status_code != 200:
        return None
    data = response.json().get("result", {}) or {}
    return _build_schema_fingerprint(data)


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
    """Recover a collection from an uploaded snapshot.

    TD-517 R-3: passes ``priority=snapshot`` so the snapshot's data wins over
    any partial state already on the node. The default ``replica`` priority
    keeps local data and only fills missing gaps from the snapshot, which is
    the wrong semantics for an explicit operator-driven restore — operators
    expect the backup to be canonical.

    Qdrant 1.16+ requires the snapshot location in the request body.
    Uploaded snapshots are stored at /qdrant/snapshots/{collection}/{snapshot}.
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
        json={"location": snapshot_location, "priority": "snapshot"},
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
        manifest_schema = info.get("schema")

        print(f"    Restoring {name} ({records} records)...")

        # TD-517 R-1 backward-compat: legacy manifests (pre-v2.4.1) lack the
        # schema fingerprint. The pre-fix restore would silently default to a
        # single-vector 768/Cosine collection that fails snapshot upload with
        # HTTP 400 schema-incompatibility — exactly the bug this rewrite
        # closes. Fail loud with an actionable message instead.
        if manifest_schema is None:
            print(
                f"      {RED}✗ Manifest predates v2.4.1: no schema fingerprint for '{name}'{RESET}"
            )
            print(
                f"      {GRAY}  Restore cannot recreate the target collection without the captured schema.{RESET}"
            )
            print(
                f"      {GRAY}  Run scripts/setup-collections.py to provision collections first, then retry.{RESET}"
            )
            if restored_collections:
                print(
                    f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                )
                for restored in restored_collections:
                    delete_collection(restored)
            return 2

        try:
            if name in existing_collections:
                # TD-517 R-2: hard-fail on schema fingerprint drift between
                # the backup and the live target. Cross-version restore is
                # explicitly out of scope for this script; operators are
                # routed to a per-version migrate_*.py instead.
                live_schema = fetch_live_schema(name)
                manifest_sig = _fingerprint_signature(manifest_schema)
                live_sig = _fingerprint_signature(live_schema)
                if manifest_sig != live_sig:
                    print(f"      {RED}✗ Schema mismatch on '{name}'.{RESET}")
                    print(
                        f"      {GRAY}  Backup fingerprint differs from live target.{RESET}"
                    )
                    print(
                        f"      {GRAY}  Cross-version restore is not supported by backup_qdrant.py / restore_qdrant.py.{RESET}"
                    )
                    print(
                        f"      {GRAY}  Use a per-version migrate_*.py script. See oversight/specs/BACKUP-RESTORE.md.{RESET}"
                    )
                    if restored_collections:
                        print(
                            f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                        )
                        for restored in restored_collections:
                            delete_collection(restored)
                    return 4
                # Existing target with matching schema: snapshot recover will
                # replace its contents in place.
                print(f"      {GREEN}✓{RESET} Schema fingerprint match")
            else:
                # Absent target (fresh-install path): recreate the collection
                # from the manifest's schema fingerprint so the subsequent
                # snapshot upload sees a byte-equivalent target.
                print("      Creating collection from manifest schema...")
                ok, err = create_collection_from_manifest_schema(name, manifest_schema)
                if not ok:
                    print(f"      {RED}✗ Failed to create collection: {err}{RESET}")
                    if restored_collections:
                        print(
                            f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                        )
                        for restored in restored_collections:
                            delete_collection(restored)
                    return 4
                print(f"      {GREEN}✓{RESET} Collection created from manifest schema")

            # Upload snapshot (collection must exist).
            if not upload_snapshot(name, snapshot_path):
                print(f"      {RED}✗ Snapshot upload failed{RESET}")
                if restored_collections:
                    print(
                        f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                    )
                    for restored in restored_collections:
                        delete_collection(restored)
                return 4
            print(f"      {GREEN}✓{RESET} Snapshot uploaded")

            # Recover collection from the uploaded snapshot.
            uploaded_name = snapshot_file
            if not recover_collection(name, uploaded_name):
                print(f"      {RED}✗ Collection recovery failed{RESET}")
                if restored_collections:
                    print(
                        f"    {YELLOW}Rolling back {len(restored_collections)} restored collections...{RESET}"
                    )
                    for restored in restored_collections:
                        delete_collection(restored)
                return 4
            print(f"      {GREEN}✓{RESET} Collection recovered")

            # Track successful restoration for potential rollback.
            restored_collections.append(name)

        except Exception as e:
            print(f"      {RED}✗ Error: {e}{RESET}")
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
