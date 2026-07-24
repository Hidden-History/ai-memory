#!/usr/bin/env python3
"""Migrate existing collections to add BM25 sparse vectors for hybrid search (PLAN-013).

v2.2.1 migration script. Idempotent — safe to run multiple times.
Tracks progress in _migration_state.json for resumability.

Strategy (per collection):
  Qdrant does not support adding new sparse vector configs to existing
  collections via update_collection (GitHub #4465). The fix is to recreate
  each collection with the new schema and scroll-copy all data.

  Phase 1 — Schema migration (scroll-migrate + recreate):
    1. Read existing collection config + payload indices
    2. Create temp collection with same config + BM25 sparse vectors
    3. Copy all payload indices to temp
    4. Scroll all points from old → temp
    5. Verify point counts match
    6. Delete old collection
    7. Create final collection with sparse config (original name)
    8. Copy all payload indices to final
    9. Scroll all points from temp → final
    10. Verify point counts match
    11. Delete temp

  Phase 2 — BM25 backfill (generate sparse embeddings):
    1. Scroll all points in final collection
    2. Extract content from payload
    3. Call /embed/sparse to get BM25 sparse vectors
    4. Upsert sparse vectors via update_vectors

Usage:
    python scripts/migrate_v221_hybrid_vectors.py
    python scripts/migrate_v221_hybrid_vectors.py --dry-run
    python scripts/migrate_v221_hybrid_vectors.py --collection discussions
    python scripts/migrate_v221_hybrid_vectors.py --batch-size 50
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Add src to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
# Add scripts/ for shared helpers (BUG-275)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env_loader import load_install_env
from qdrant_client.models import (
    Modifier,
    PointVectors,
    SparseVector,
    SparseVectorParams,
)

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
    get_config,
)
from memory.qdrant_client import ensure_payload_indexes, get_qdrant_client

# All 5 collections
ALL_COLLECTIONS = [
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
]

# State file for resumability
STATE_FILE = Path(__file__).resolve().parent / "_migration_state.json"

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"


def load_state() -> dict:
    """Load migration state from file for resumability."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    """Persist migration state to file."""
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError as e:
        print(f"  {YELLOW}!{RESET} Could not save state: {e}")


def collection_has_sparse(client, collection_name: str) -> bool:
    """Check if a collection already has BM25 sparse vector config."""
    try:
        info = client.get_collection(collection_name)
        sparse = getattr(info.config.params, "sparse_vectors", None)
        return bool(sparse and "bm25" in (sparse or {}))
    except Exception:
        return False


def scroll_copy(client, src: str, dst: str, batch_size: int) -> int:
    """Scroll all points from src collection and upload to dst.

    Returns:
        Number of points copied.
    """
    copied = 0
    offset = None
    while True:
        scroll_kwargs = {
            "collection_name": src,
            "limit": batch_size,
            "with_payload": True,
            "with_vectors": True,
        }
        if offset is not None:
            scroll_kwargs["offset"] = offset

        points, next_offset = client.scroll(**scroll_kwargs)

        if not points:
            break

        # upload_points accepts Record objects from scroll directly
        client.upload_points(collection_name=dst, points=points, wait=True)
        copied += len(points)

        if next_offset is None:
            break
        offset = next_offset

    return copied


def recreate_payload_indices(client, dst: str, payload_schema: dict) -> None:
    """Recreate all payload indices from source schema on destination collection."""
    for field_name, field_info in payload_schema.items():
        try:
            # Use params if available (carries is_tenant, tokenizer, etc.),
            # otherwise fall back to basic data_type
            schema = (
                field_info.params
                if field_info.params is not None
                else field_info.data_type
            )
            client.create_payload_index(
                collection_name=dst,
                field_name=field_name,
                field_schema=schema,
            )
        except Exception as e:
            print(f"    {YELLOW}!{RESET} Index '{field_name}' on '{dst}': {e}")


def ensure_canonical_payload_indices(client, collection_name: str) -> None:
    """Apply the canonical payload-index set as a backstop after recreation.

    BUG-530: ``recreate_payload_indices`` copies forward whatever the source
    collection had — which is nothing when the source was itself created by a
    path that skipped indexes. This runs *in addition to* the copy-forward so
    the recreated collection always ends up with at least the canonical set,
    while any extra user-added indexes carried by the copy-forward survive.

    Best-effort: a failure here degrades search but must not abort a migration
    that has already moved data.
    """
    try:
        ensure_payload_indexes(client, collection_name)
    except Exception as e:
        print(f"    {YELLOW}!{RESET} Canonical indexes on '{collection_name}': {e}")


def create_collection_with_sparse(
    client, name: str, src_config, sparse_config: dict
) -> None:
    """Create a collection with the source config + sparse vectors added."""
    from qdrant_client.models import (
        HnswConfigDiff,
        ScalarQuantization,
        ScalarQuantizationConfig,
        ScalarType,
    )

    # Reconstruct HNSW config from source
    src_hnsw = src_config.hnsw_config
    hnsw = HnswConfigDiff(
        m=src_hnsw.m,
        ef_construct=src_hnsw.ef_construct,
        full_scan_threshold=src_hnsw.full_scan_threshold,
        on_disk=getattr(src_hnsw, "on_disk", True),
    )

    # Reconstruct quantization config from source
    quant = None
    src_quant = src_config.quantization_config
    if src_quant is not None:
        scalar = getattr(src_quant, "scalar", None)
        if scalar is not None:
            quant = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=(
                        ScalarType(scalar.type.value)
                        if hasattr(scalar.type, "value")
                        else scalar.type
                    ),
                    quantile=scalar.quantile,
                    always_ram=scalar.always_ram,
                )
            )

    client.create_collection(
        collection_name=name,
        vectors_config=src_config.params.vectors,
        sparse_vectors_config=sparse_config,
        hnsw_config=hnsw,
        quantization_config=quant,
        shard_number=src_config.params.shard_number,
        on_disk_payload=src_config.params.on_disk_payload,
    )


def ensure_sparse_config(
    client, collection_name: str, batch_size: int, dry_run: bool
) -> bool:
    """Ensure a collection has BM25 sparse vector config.

    If the collection already has sparse config, returns True immediately.
    Otherwise, recreates the collection with sparse config using scroll-migrate.

    Qdrant does not support adding new sparse vector configs to existing
    collections via update_collection (GitHub #4465). The workaround is to
    create a new collection with the desired schema, copy all data, then
    swap in the new collection.

    Returns:
        True if collection now has sparse config, False on error.
    """
    if not client.collection_exists(collection_name):
        print(
            f"  {YELLOW}!{RESET} Collection '{collection_name}' does not exist — skipping"
        )
        return False

    # Already has sparse config — nothing to do
    if collection_has_sparse(client, collection_name):
        print(
            f"  {GREEN}✓{RESET} Collection '{collection_name}' already has BM25 config"
        )
        return True

    if dry_run:
        print(
            f"  {GRAY}[DRY RUN] Would recreate '{collection_name}' with BM25 sparse config{RESET}"
        )
        return True

    tmp_name = f"{collection_name}_migration_tmp"
    sparse_config = {"bm25": SparseVectorParams(modifier=Modifier.IDF)}

    # Get source collection info
    info = client.get_collection(collection_name)
    src_config = info.config
    src_payload_schema = info.payload_schema
    src_count = info.points_count or 0

    print(
        f"  Recreating '{collection_name}' with sparse config ({src_count} points)..."
    )

    # Clean up any leftover temp collection from a previous failed run
    if client.collection_exists(tmp_name):
        print(f"  {YELLOW}!{RESET} Cleaning up leftover temp collection '{tmp_name}'")
        client.delete_collection(tmp_name)

    try:
        # Step 1: Create temp collection with same config + sparse vectors
        print(f"    1/6 Creating temp collection '{tmp_name}'...")
        create_collection_with_sparse(client, tmp_name, src_config, sparse_config)
        recreate_payload_indices(client, tmp_name, src_payload_schema)
        ensure_canonical_payload_indices(client, tmp_name)

        # Step 2: Scroll all data from source → temp
        print(f"    2/6 Copying {src_count} points to temp...")
        copied = scroll_copy(client, collection_name, tmp_name, batch_size)
        print(f"         Copied {copied} points")

        # Step 3: Verify counts match
        tmp_count = client.count(tmp_name).count
        if tmp_count != src_count:
            raise RuntimeError(
                f"Count mismatch after copy: source={src_count}, temp={tmp_count}"
            )
        print(f"    3/6 Count verified: {tmp_count} points")

        # Step 4: Delete original collection
        print(f"    4/6 Deleting original '{collection_name}'...")
        client.delete_collection(collection_name)

        # Step 5: Create final collection with original name + sparse config
        print(f"    5/6 Creating final '{collection_name}' with sparse config...")
        create_collection_with_sparse(
            client, collection_name, src_config, sparse_config
        )
        recreate_payload_indices(client, collection_name, src_payload_schema)
        ensure_canonical_payload_indices(client, collection_name)

        # Step 6: Scroll all data from temp → final
        print(f"    6/6 Copying {tmp_count} points to final...")
        scroll_copy(client, tmp_name, collection_name, batch_size)

        # Verify final counts
        final_count = client.count(collection_name).count
        if final_count != src_count:
            raise RuntimeError(
                f"Count mismatch in final collection: expected={src_count}, got={final_count}"
            )
        print(f"         Verified: {final_count} points")

        # Clean up temp
        client.delete_collection(tmp_name)

        print(
            f"  {GREEN}✓{RESET} '{collection_name}' recreated with BM25 sparse config ({final_count} points)"
        )
        return True

    except Exception as e:
        print(f"  {RED}x Schema migration failed for '{collection_name}': {e}{RESET}")

        # Safety: if original still exists, leave it. If only temp exists, warn user.
        if not client.collection_exists(collection_name) and client.collection_exists(
            tmp_name
        ):
            print(
                f"  {RED}  IMPORTANT: Original '{collection_name}' was deleted.{RESET}"
            )
            print(
                f"  {RED}  Data is preserved in '{tmp_name}'. Manual recovery needed:{RESET}"
            )
            print(
                f"  {RED}    1. Create '{collection_name}' with setup-collections.py --force{RESET}"
            )
            print(f"  {RED}    2. Re-run this migration script{RESET}")
            print(f"  {RED}  Or rename '{tmp_name}' manually in Qdrant.{RESET}")

        return False


def get_sparse_embedding(embedding_url: str, text: str) -> dict | None:
    """Call the embedding service /embed/sparse endpoint.

    Args:
        embedding_url: Base URL of the embedding service (e.g., http://localhost:28080)
        text: Text to embed.

    Returns:
        Dict with "indices" and "values" keys, or None on failure.
    """
    try:
        resp = requests.post(
            f"{embedding_url}/embed/sparse",
            json={"texts": [text]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Response format: {"embeddings": [{"indices": [...], "values": [...]}]}
        if "embeddings" in data and len(data["embeddings"]) > 0:
            return data["embeddings"][0]
        return None
    except Exception as e:
        # Don't crash on individual failures — caller handles gracefully
        print(f"    {YELLOW}!{RESET} Sparse embedding failed: {e}")
        return None


def backfill_sparse_vectors(
    client,
    collection_name: str,
    embedding_url: str,
    batch_size: int,
    dry_run: bool,
    state: dict,
) -> dict:
    """Generate BM25 sparse vectors for all existing points in a collection.

    Phase 2 of migration: once the collection has sparse config (Phase 1),
    this function scrolls all points and adds BM25 sparse vectors via
    update_vectors.

    Returns:
        Stats dict: total, processed, skipped, errors.
    """
    stats = {"total": 0, "processed": 0, "skipped": 0, "errors": 0}

    if not client.collection_exists(collection_name):
        print(f"  {YELLOW}!{RESET} Collection '{collection_name}' not found — skipping")
        return stats

    # Get total point count
    collection_info = client.get_collection(collection_name)
    stats["total"] = collection_info.points_count or 0

    if stats["total"] == 0:
        print(
            f"  {YELLOW}!{RESET} Collection '{collection_name}' is empty — nothing to backfill"
        )
        return stats

    print(f"  Backfilling {stats['total']} points in '{collection_name}'...")

    # Track which points we've already processed (resumability)
    col_state_key = f"backfill_{collection_name}"
    processed_ids = set(state.get(col_state_key, []))

    offset = None

    while True:
        scroll_kwargs = {
            "collection_name": collection_name,
            "limit": batch_size,
            "with_payload": True,
            "with_vectors": True,
        }
        if offset is not None:
            scroll_kwargs["offset"] = offset

        try:
            points, next_offset = client.scroll(**scroll_kwargs)
        except Exception as e:
            print(f"    {RED}x Scroll failed: {e}{RESET}")
            stats["errors"] += 1
            break

        if not points:
            break

        upsert_batch = []
        batch_ids = []  # Track IDs for this batch; only mark done after success

        for point in points:
            point_id_str = str(point.id)

            # Skip already-processed points (resumability)
            if point_id_str in processed_ids:
                stats["skipped"] += 1
                continue

            # Check if point already has bm25 sparse vector
            if isinstance(point.vector, dict) and "bm25" in point.vector:
                stats["skipped"] += 1
                processed_ids.add(point_id_str)
                continue

            # Extract content from payload
            payload = point.payload or {}
            content = payload.get("content", "")

            if not content or not content.strip():
                stats["skipped"] += 1
                processed_ids.add(point_id_str)
                continue

            if dry_run:
                stats["processed"] += 1
                processed_ids.add(point_id_str)
                continue

            # Get sparse embedding
            sparse_result = get_sparse_embedding(embedding_url, content)
            if sparse_result is None:
                stats["errors"] += 1
                continue

            indices = sparse_result.get("indices", [])
            values = sparse_result.get("values", [])

            if not indices:
                stats["skipped"] += 1
                processed_ids.add(point_id_str)
                continue

            # Build the vector dict: preserve existing dense + add sparse
            # point.vector can be a list (unnamed default) or a dict (named vectors)
            if isinstance(point.vector, dict):
                # Named vectors — keep all existing, add bm25
                vector_dict = dict(point.vector)
                vector_dict["bm25"] = SparseVector(indices=indices, values=values)
            else:
                # Unnamed default dense vector — wrap in dict with "" key + bm25
                vector_dict = {
                    "": point.vector,
                    "bm25": SparseVector(indices=indices, values=values),
                }

            upsert_batch.append(
                PointVectors(
                    id=point.id,
                    vector=vector_dict,
                )
            )

            batch_ids.append(point_id_str)
            stats["processed"] += 1

        # Batch upsert using update_vectors (preserves payload, only updates vectors)
        if upsert_batch and not dry_run:
            try:
                client.update_vectors(
                    collection_name=collection_name,
                    points=upsert_batch,
                )
                # Only mark IDs as processed AFTER successful update
                processed_ids.update(batch_ids)
            except Exception as e:
                print(f"    {RED}x Batch upsert failed: {e}{RESET}")
                # Do NOT add batch_ids to processed_ids — they need retry on resume
                stats["errors"] += len(upsert_batch)
                stats["processed"] -= len(batch_ids)  # Undo premature count
        else:
            # dry_run or empty batch — IDs already handled above
            processed_ids.update(batch_ids)

        # Save state periodically for resumability
        state[col_state_key] = list(processed_ids)
        save_state(state)

        # Progress report
        done = stats["processed"] + stats["skipped"] + stats["errors"]
        print(
            f"    Progress: {done}/{stats['total']} "
            f"(processed={stats['processed']}, skipped={stats['skipped']}, errors={stats['errors']})",
            end="\r",
        )

        if next_offset is None:
            break
        offset = next_offset

    # Final newline after progress
    print()

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Add BM25 sparse vectors to existing collections for hybrid search (PLAN-013, v2.2.1)",
        epilog="Exit 0: success, Exit 1: critical error",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        choices=ALL_COLLECTIONS,
        help="Migrate a specific collection only (default: all 5)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of points to scroll per batch (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would change without mutating any data",
    )
    args = parser.parse_args()

    start_time = time.monotonic()

    print(f"\n{'=' * 60}")
    if args.dry_run:
        print("  PLAN-013 Migration: Hybrid Search Sparse Vectors (v2.2.1)  [DRY RUN]")
    else:
        print("  PLAN-013 Migration: Hybrid Search Sparse Vectors (v2.2.1)")
    print(f"{'=' * 60}\n")

    # BUG-275: load both docker/.env and docker/.env.secrets so get_config() and direct
    # os.environ reads pick up all credentials. load_install_env() uses secrets-first
    # precedence: shell env > .env.secrets > .env > defaults (BP-153 §3).
    load_install_env()

    install_dir = Path(
        os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
    )
    docker_env = install_dir / "docker" / ".env"
    docker_secrets = install_dir / "docker" / ".env.secrets"
    if docker_env.exists() or docker_secrets.exists():
        print(f"  Loaded env from: {install_dir}/docker/(.env + .env.secrets)")
    else:
        print(
            f"  {YELLOW}WARNING: neither docker/.env nor docker/.env.secrets found at {install_dir}/docker/{RESET}"
        )

    # Check for shell env override (BUG-202 pattern) — compare against merged file value
    pre_shell_key = os.environ.get("QDRANT_API_KEY")
    if pre_shell_key:
        # Determine effective file value (same precedence as load_install_env)
        file_key = None
        for env_path in [docker_secrets, docker_env]:
            if not env_path.exists():
                continue
            for line in env_path.read_text().splitlines():
                if line.strip().startswith("QDRANT_API_KEY="):
                    candidate = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if candidate:
                        file_key = candidate
                        break
            if file_key:
                break
        if file_key and pre_shell_key != file_key:
            print(
                f"  {YELLOW}WARNING: Shell QDRANT_API_KEY differs from installed env value{RESET}"
            )
            print(f"  {YELLOW}Run: unset QDRANT_API_KEY{RESET}")

    # Connect to Qdrant
    try:
        config = get_config()
        client = get_qdrant_client(config)
    except Exception as e:
        print(f"{RED}x Cannot connect to Qdrant: {e}{RESET}")
        print("  Ensure Qdrant is running:")
        print("    docker compose -f docker/docker-compose.yml up -d")
        sys.exit(1)

    # Determine embedding service URL
    embedding_url = config.get_embedding_url()
    print(f"  Embedding service: {embedding_url}")
    print(f"  Batch size: {args.batch_size}")
    print()

    # Verify embedding service has /embed/sparse endpoint
    if not args.dry_run:
        try:
            resp = requests.get(f"{embedding_url}/health", timeout=5)
            if resp.status_code != 200:
                print(
                    f"{YELLOW}WARNING: Embedding service health check returned {resp.status_code}{RESET}"
                )
        except Exception as e:
            print(
                f"{RED}x Cannot reach embedding service at {embedding_url}: {e}{RESET}"
            )
            print(
                "  Ensure the embedding service is running with sparse embedding support."
            )
            sys.exit(1)

    # Determine which collections to migrate
    collections = [args.collection] if args.collection else ALL_COLLECTIONS

    # Load resumable state
    state = load_state()

    all_stats = {}
    schema_failures = []

    for collection_name in collections:
        print(f"--- Collection: {collection_name} ---")

        # Phase 1: Ensure collection has sparse vector config
        print("  Phase 1: Schema migration (add BM25 sparse config)")
        ok = ensure_sparse_config(
            client, collection_name, args.batch_size, args.dry_run
        )
        if not ok:
            print(f"  {YELLOW}!{RESET} Skipping Phase 2 for '{collection_name}'")
            schema_failures.append(collection_name)
            continue

        # Phase 2: Backfill BM25 sparse vectors for existing points
        print("  Phase 2: BM25 sparse vector backfill")
        stats = backfill_sparse_vectors(
            client=client,
            collection_name=collection_name,
            embedding_url=embedding_url,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            state=state,
        )
        all_stats[collection_name] = stats
        print()

    # Mark state file as completed (not dry-run)
    if not args.dry_run:
        # Mark migration as complete
        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)

    # Summary
    duration = time.monotonic() - start_time
    print(f"{'=' * 60}")
    if args.dry_run:
        print(f"  {YELLOW}DRY RUN complete — no data was mutated{RESET}")
    else:
        print(f"  {GREEN}PLAN-013 sparse vector migration complete{RESET}")
    print()

    if schema_failures:
        print(
            f"  {RED}Schema migration failed for: {', '.join(schema_failures)}{RESET}"
        )
        print()

    for col, stats in all_stats.items():
        print(
            f"  {col:20s}: total={stats['total']:>6d}  "
            f"processed={stats['processed']:>6d}  "
            f"skipped={stats['skipped']:>6d}  "
            f"errors={stats['errors']:>6d}"
        )

    print(f"\n  Duration: {duration:.1f}s")
    print(f"{'=' * 60}\n")

    # Exit with error if any collection had errors
    total_errors = sum(s.get("errors", 0) for s in all_stats.values())
    if total_errors > 0 or schema_failures:
        errors_msg = f"{total_errors} backfill errors" if total_errors else ""
        schema_msg = (
            f"{len(schema_failures)} schema failures" if schema_failures else ""
        )
        combined = " + ".join(filter(None, [errors_msg, schema_msg]))
        print(f"{YELLOW}WARNING: {combined}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
