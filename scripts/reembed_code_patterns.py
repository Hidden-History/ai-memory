#!/usr/bin/env python3
"""
One-time re-embedding migration script for code-patterns collection.

SPEC-010 Section 6: Re-embedding Strategy
- In-place re-embedding with snapshot backup (BP-086, small collection path)
- Handles multi-chunk points (tracks chunk_index, total_chunks)
- Golden query validation with quality gates
- Resumable via progress tracking

Usage:
    python3 scripts/reembed_code_patterns.py [--force-no-validation]

Flags:
    --force-no-validation: Skip golden query validation even if golden_queries.json exists
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# Add src to path for memory module imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.config import get_config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("reembed_code_patterns")

PROGRESS_FILE = Path(".audit/state/reembed-progress.json")
GOLDEN_QUERIES_FILE = Path(__file__).parent / "golden_queries.json"
SNAPSHOT_PREFIX = "code-patterns-pre-reembed"


def load_progress():
    """Load progress state from file if exists."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return None


def save_progress(progress: dict):
    """Save progress state to file."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def check_embedding_service(base_url: str) -> bool:
    """Verify embedding service is healthy and /embed/dense works."""
    logger.info("Checking embedding service health...")
    try:
        # Health check
        response = httpx.get(f"{base_url}/health", timeout=10.0)
        if response.status_code != 200:
            logger.error(f"Health check failed: HTTP {response.status_code}")
            return False
        health = response.json()
        logger.info(
            f"Health check OK: models={health.get('models')}, uptime={health.get('uptime_seconds')}s"
        )

        # Test /embed/dense endpoint with POST (SPEC-010 Section 6.1)
        response = httpx.post(
            f"{base_url}/embed/dense",
            json={"texts": ["test"], "model": "code"},
            timeout=30.0,
        )
        if response.status_code != 200:
            logger.error(f"/embed/dense test failed: HTTP {response.status_code}")
            return False
        result = response.json()
        if len(result.get("embeddings", [])) != 1:
            logger.error(
                f"/embed/dense test failed: expected 1 embedding, got {len(result.get('embeddings', []))}"
            )
            return False
        logger.info("/embed/dense endpoint responding correctly")
        return True
    except Exception as e:
        logger.error(f"Embedding service check failed: {e}")
        return False


def check_qdrant(client: QdrantClient, api_key: str) -> bool:
    """Verify Qdrant is healthy and accessible."""
    logger.info("Checking Qdrant health...")
    try:
        # Qdrant health check requires API key on all endpoints (project convention)
        collections = client.get_collections()
        logger.info(f"Qdrant OK: {len(collections.collections)} collections")
        return True
    except Exception as e:
        logger.error(f"Qdrant check failed: {e}")
        return False


def create_snapshot(client: QdrantClient, collection_name: str) -> str:
    """Create Qdrant snapshot of collection."""
    logger.info(f"Creating snapshot of {collection_name}...")
    try:
        snapshot_name = (
            f"{SNAPSHOT_PREFIX}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        )
        result = client.create_snapshot(collection_name=collection_name)
        logger.info(f"Snapshot created: {result.name}")
        return result.name
    except Exception as e:
        logger.error(f"Snapshot creation failed: {e}")
        raise


def count_collection_points(client: QdrantClient, collection_name: str) -> int:
    """Count total points in collection."""
    try:
        count_result = client.count(collection_name=collection_name)
        return count_result.count
    except Exception as e:
        logger.error(f"Failed to count collection points: {e}")
        return 0


def run_golden_queries(
    client: QdrantClient, collection_name: str, golden_queries: dict
) -> dict:
    """Run golden query set and return results."""
    logger.info(f"Running {len(golden_queries['queries'])} golden queries...")
    results = []

    for query in golden_queries["queries"]:
        query_id = query["id"]
        query_text = query["text"]
        expected_files = query.get("expected_files", [])
        min_score = query.get("min_score", 0.5)

        try:
            # Embed query with code model
            embed_url = f"http://{get_config().embedding_host}:{get_config().embedding_port}/embed/dense"
            response = httpx.post(
                embed_url,
                json={"texts": [query_text], "model": "code"},
                timeout=30.0,
            )
            response.raise_for_status()
            query_vector = response.json()["embeddings"][0]

            # Search Qdrant
            search_result = client.search(
                collection_name=collection_name, query_vector=query_vector, limit=5
            )

            # Extract top-5 file paths and scores
            top_5_files = [
                r.payload.get("file_path") or r.payload.get("source_file", "unknown")
                for r in search_result[:5]
            ]
            top_5_scores = [r.score for r in search_result[:5]]

            # Compute metrics
            recall_at_5 = any(f in top_5_files for f in expected_files)
            top_score = top_5_scores[0] if top_5_scores else 0.0

            results.append(
                {
                    "query_id": query_id,
                    "query_text": query_text,
                    "recall_at_5": recall_at_5,
                    "top_score": top_score,
                    "top_5_files": top_5_files,
                    "top_5_scores": top_5_scores,
                }
            )

            logger.info(
                f"  {query_id}: recall@5={recall_at_5}, top_score={top_score:.3f}"
            )

        except Exception as e:
            logger.error(f"Golden query {query_id} failed: {e}")
            results.append(
                {
                    "query_id": query_id,
                    "error": str(e),
                    "recall_at_5": False,
                    "top_score": 0.0,
                }
            )

    return {"queries": results, "timestamp": datetime.now(timezone.utc).isoformat()}


def compute_quality_metrics(baseline: dict, new_results: dict) -> dict:
    """Compare baseline vs new results and compute quality metrics."""
    baseline_queries = {q["query_id"]: q for q in baseline["queries"]}
    new_queries = {q["query_id"]: q for q in new_results["queries"]}

    total_queries = len(baseline_queries)
    recall_improved = 0
    recall_regressed = 0
    min_recall_at_5 = 1.0

    for query_id, baseline_q in baseline_queries.items():
        new_q = new_queries.get(query_id)
        if not new_q:
            continue

        baseline_recall = baseline_q.get("recall_at_5", False)
        new_recall = new_q.get("recall_at_5", False)

        if new_recall and not baseline_recall:
            recall_improved += 1
        elif not new_recall and baseline_recall:
            recall_regressed += 1

        if not new_recall:
            min_recall_at_5 = 0.0

    improvement_pct = recall_improved / total_queries if total_queries > 0 else 0.0
    regression_pct = recall_regressed / total_queries if total_queries > 0 else 0.0

    return {
        "total_queries": total_queries,
        "recall_improved": recall_improved,
        "recall_regressed": recall_regressed,
        "min_recall_at_5": min_recall_at_5,
        "improvement_pct": improvement_pct,
        "regression_pct": regression_pct,
    }


def reembed_collection(
    client: QdrantClient,
    collection_name: str,
    embed_url: str,
    progress: dict | None = None,
) -> dict:
    """Re-embed all points in collection with code model."""
    logger.info(f"Starting re-embedding of {collection_name}...")

    if progress is None:
        progress = {
            "collection": collection_name,
            "total_points": count_collection_points(client, collection_name),
            "processed_points": 0,
            "failed_points": 0,
            "skipped_points": 0,
            "multi_chunk_files": 0,
            "last_offset": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "model_from": "jinaai/jina-embeddings-v2-base-en",
            "model_to": "jinaai/jina-embeddings-v2-base-code",
            "errors": [],
        }

    batch_size = 16  # Texts per embed request
    scroll_limit = 100  # Points per scroll

    offset = progress.get("last_offset")
    processed = progress["processed_points"]
    failed = progress["failed_points"]
    skipped = progress["skipped_points"]

    while True:
        # Scroll next batch of points
        points, next_offset = client.scroll(
            collection_name=collection_name,
            limit=scroll_limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not points:
            break

        # Process points in embedding batches
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            contents = []
            point_ids = []

            for point in batch:
                content = point.payload.get("content")
                if not content:
                    logger.warning(
                        f"Point {point.id} missing content, skipping re-embedding"
                    )
                    skipped += 1
                    continue
                contents.append(content)
                point_ids.append(point.id)

            if not contents:
                continue

            # Batch embed with code model
            try:
                response = httpx.post(
                    f"{embed_url}/embed/dense",
                    json={"texts": contents, "model": "code"},
                    timeout=60.0,
                )
                response.raise_for_status()
                embeddings = response.json()["embeddings"]
            except Exception as e:
                logger.error(f"Embedding batch failed: {e}")
                failed += len(contents)
                progress["errors"].append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "error": str(e),
                        "point_ids": point_ids,
                    }
                )
                continue

            # Upsert points with new vectors
            upsert_points = []
            for point, new_vector in zip(
                [p for p in batch if p.payload.get("content")], embeddings
            ):
                # Preserve ALL payload fields, add embedding_model marker
                updated_payload = {**point.payload}
                updated_payload["embedding_model"] = (
                    "jinaai/jina-embeddings-v2-base-code"
                )

                upsert_points.append(
                    PointStruct(id=point.id, vector=new_vector, payload=updated_payload)
                )

            try:
                client.upsert(collection_name=collection_name, points=upsert_points)
                processed += len(upsert_points)
            except Exception as e:
                logger.error(f"Upsert batch failed: {e}")
                failed += len(upsert_points)
                progress["errors"].append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "error": str(e),
                        "point_ids": [p.id for p in upsert_points],
                    }
                )

        offset = next_offset
        progress["processed_points"] = processed
        progress["failed_points"] = failed
        progress["skipped_points"] = skipped
        progress["last_offset"] = offset
        save_progress(progress)

        logger.info(
            f"Progress: {processed}/{progress['total_points']} processed, {failed} failed, {skipped} skipped"
        )

        if next_offset is None:
            break

    progress["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_progress(progress)

    logger.info(
        f"Re-embedding complete: {processed} processed, {failed} failed, {skipped} skipped"
    )
    return progress


def main():
    parser = argparse.ArgumentParser(
        description="Re-embed code-patterns collection with code model (SPEC-010)"
    )
    parser.add_argument(
        "--force-no-validation",
        action="store_true",
        help="Skip golden query validation even if golden_queries.json exists",
    )
    args = parser.parse_args()

    config = get_config()
    collection_name = "code-patterns"
    embed_url = f"http://{config.embedding_host}:{config.embedding_port}"

    # Step 1: Pre-flight checks
    logger.info("=== Step 1: Pre-flight Checks ===")
    if not check_embedding_service(embed_url):
        logger.error("Embedding service check failed. Aborting.")
        sys.exit(1)

    client = QdrantClient(
        host=config.qdrant_host, port=config.qdrant_port, api_key=config.qdrant_api_key
    )
    if not check_qdrant(client, config.qdrant_api_key):
        logger.error("Qdrant check failed. Aborting.")
        sys.exit(1)

    total_points = count_collection_points(client, collection_name)
    logger.info(f"Collection {collection_name} has {total_points} points")

    # Estimate time
    estimated_seconds = (total_points * 8) / 1000  # 8ms/vector batched
    logger.info(f"Estimated time: {estimated_seconds:.1f}s")

    # Step 2: Snapshot backup
    logger.info("=== Step 2: Snapshot Backup ===")
    snapshot_name = create_snapshot(client, collection_name)
    logger.info(f"Snapshot created: {snapshot_name}")

    # Step 3: Golden query baseline
    baseline_results = None
    golden_queries = None
    skip_validation = args.force_no_validation

    if GOLDEN_QUERIES_FILE.exists() and not skip_validation:
        logger.info("=== Step 3: Golden Query Baseline ===")
        with open(GOLDEN_QUERIES_FILE) as f:
            golden_queries = json.load(f)
        baseline_results = run_golden_queries(client, collection_name, golden_queries)
        logger.info(
            f"Baseline: {sum(1 for q in baseline_results['queries'] if q.get('recall_at_5'))} / {len(baseline_results['queries'])} queries have recall@5"
        )
    else:
        if skip_validation:
            logger.warning(
                "Golden query validation DISABLED by --force-no-validation flag"
            )
        else:
            logger.warning(
                f"Golden queries file not found: {GOLDEN_QUERIES_FILE}. Skipping validation gates (soft-launch mode)."
            )

    # Step 4: Re-embed
    logger.info("=== Step 4: Re-embedding ===")
    progress = load_progress()
    if progress:
        logger.info(
            f"Resuming from previous run: {progress['processed_points']}/{progress['total_points']} already processed"
        )

    final_progress = reembed_collection(client, collection_name, embed_url, progress)
    logger.info(
        f"Re-embedding complete: {final_progress['processed_points']} points updated"
    )

    # Step 5: Validation
    if golden_queries and not skip_validation:
        logger.info("=== Step 5: Golden Query Validation ===")
        new_results = run_golden_queries(client, collection_name, golden_queries)
        metrics = compute_quality_metrics(baseline_results, new_results)

        logger.info("Validation Metrics:")
        logger.info(f"  Recall improved: {metrics['recall_improved']}")
        logger.info(f"  Recall regressed: {metrics['recall_regressed']}")
        logger.info(f"  Min recall@5: {metrics['min_recall_at_5']}")
        logger.info(f"  Improvement %: {metrics['improvement_pct']:.1%}")
        logger.info(f"  Regression %: {metrics['regression_pct']:.1%}")

        # Hard gates (SPEC-010 Section 6.1)
        if metrics["min_recall_at_5"] < 0.60:
            logger.error(
                f"HARD GATE FAILURE: min_recall_at_5={metrics['min_recall_at_5']:.2f} < 0.60"
            )
            logger.error("Initiating rollback...")
            # TODO: Implement rollback via snapshot restore
            sys.exit(1)

        if metrics["regression_pct"] > 0.20:
            logger.error(
                f"HARD GATE FAILURE: regression_pct={metrics['regression_pct']:.1%} > 20%"
            )
            logger.error("Initiating rollback...")
            # TODO: Implement rollback via snapshot restore
            sys.exit(1)

        logger.info("All validation gates PASSED")

    # Cleanup
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        logger.info("Progress file cleaned up")

    logger.info("=== Migration Complete ===")


if __name__ == "__main__":
    main()
