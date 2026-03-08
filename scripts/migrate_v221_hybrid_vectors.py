#!/usr/bin/env python3
"""Migrate existing collections to add BM25 sparse vectors for hybrid search (PLAN-013).

v2.2.1 migration script. Idempotent — safe to run multiple times.
Tracks progress in _migration_state.json for resumability.

Steps per collection:
1. Call update_collection() to add sparse_vectors_config (BM25/IDF)
2. Scroll all points in batches
3. For each point, extract content from payload
4. Call embedding service /embed/sparse to get sparse vector
5. Upsert point with existing dense vector + new BM25 sparse vector

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

from qdrant_client.models import (
    NamedSparseVector,
    PointVectors,
    SparseVector,
    SparseVectorParams,
    Modifier,
)

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
    get_config,
)
from memory.qdrant_client import get_qdrant_client

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


def add_sparse_config_to_collection(client, collection_name: str, dry_run: bool) -> bool:
    """Add BM25 sparse vector config to an existing collection.

    Returns:
        True if config was added or already present, False on error.
    """
    if dry_run:
        print(f"  {GRAY}[DRY RUN] Would add BM25 sparse config to '{collection_name}'{RESET}")
        return True

    try:
        # Check if collection exists
        if not client.collection_exists(collection_name):
            print(f"  {YELLOW}!{RESET} Collection '{collection_name}' does not exist — skipping")
            return False

        # Check if sparse vectors already configured
        collection_info = client.get_collection(collection_name)
        existing_sparse = getattr(collection_info.config.params, "sparse_vectors", None)
        if existing_sparse and "bm25" in (existing_sparse or {}):
            print(f"  {YELLOW}!{RESET} Collection '{collection_name}' already has BM25 config — skipping")
            return True

        # Add sparse vector config
        client.update_collection(
            collection_name=collection_name,
            sparse_vectors_config={
                "bm25": SparseVectorParams(modifier=Modifier.IDF),
            },
        )
        print(f"  {GREEN}+{RESET} Added BM25 sparse config to '{collection_name}'")
        return True

    except Exception as e:
        print(f"  {RED}x Failed to add sparse config to '{collection_name}': {e}{RESET}")
        return False


def migrate_collection(
    client,
    collection_name: str,
    embedding_url: str,
    batch_size: int,
    dry_run: bool,
    state: dict,
) -> dict:
    """Migrate all points in a collection to include BM25 sparse vectors.

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
        print(f"  {YELLOW}!{RESET} Collection '{collection_name}' is empty — nothing to migrate")
        return stats

    print(f"  Migrating {stats['total']} points in '{collection_name}'...")

    # Track which points we've already processed (resumability)
    col_state_key = f"migrated_{collection_name}"
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

    # Check for shell env override (BUG-202 pattern)
    shell_key = os.environ.get("QDRANT_API_KEY")
    if shell_key:
        # Read from .env file
        env_file = Path(os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))) / "docker" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("QDRANT_API_KEY="):
                    file_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if shell_key != file_key:
                        print(f"  {YELLOW}WARNING: Shell QDRANT_API_KEY differs from docker/.env value{RESET}")
                        print(f"  {YELLOW}Run: unset QDRANT_API_KEY{RESET}")
                    break

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
                print(f"{YELLOW}WARNING: Embedding service health check returned {resp.status_code}{RESET}")
        except Exception as e:
            print(f"{RED}x Cannot reach embedding service at {embedding_url}: {e}{RESET}")
            print("  Ensure the embedding service is running with sparse embedding support.")
            sys.exit(1)

    # Determine which collections to migrate
    collections = [args.collection] if args.collection else ALL_COLLECTIONS

    # Load resumable state
    state = load_state()

    all_stats = {}

    for collection_name in collections:
        print(f"--- Collection: {collection_name} ---")

        # Step 1: Add sparse config to collection schema
        print(f"  Step 1: Add BM25 sparse vector config")
        ok = add_sparse_config_to_collection(client, collection_name, args.dry_run)
        if not ok:
            print(f"  {YELLOW}!{RESET} Skipping migration for '{collection_name}'")
            continue

        # Step 2: Migrate existing points
        print(f"  Step 2: Generate sparse vectors for existing points")
        stats = migrate_collection(
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
    if total_errors > 0:
        print(f"{YELLOW}WARNING: {total_errors} total errors across collections{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
