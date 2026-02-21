#!/usr/bin/env python3
# scripts/memory/seed_conventions.py
"""Seed conventions collection from validated JSON templates.

2026 Best Practices Applied:
- Pydantic validation for template security
- httpx with explicit timeouts and error handling
- Batch upsert for Qdrant performance (100 points per batch)
- uuid4() for secure random IDs
- Structured logging with extras
- Dry-run support for safety
- Graceful degradation (no crashes)

Sources:
- HTTPX Timeouts: https://www.python-httpx.org/advanced/timeouts/
- Qdrant Bulk Upload: https://qdrant.tech/documentation/database-tutorials/bulk-upload/
- UUID Security: https://thelinuxcode.com/generating-random-ids-with-pythons-uuid-module-2026-playbook/
- JSON Injection Prevention: https://www.invicti.com/learn/json-injection
"""

import argparse
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.config import get_config
from memory.deduplication import compute_content_hash
from memory.qdrant_client import get_qdrant_client
from memory.template_models import BestPracticeTemplate, load_templates_from_file

# Configure structured logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def generate_embedding(
    text: str, embedding_url: str, timeout: float = 30.0
) -> list[float] | None:
    """Generate embedding for text using embedding service.

    2026 Pattern: Explicit timeouts per httpx best practices
    Source: https://www.python-httpx.org/advanced/timeouts/

    Args:
        text: Text to embed
        embedding_url: Base URL of embedding service
        timeout: Request timeout in seconds (default 30s)

    Returns:
        768-dimensional embedding vector, or None on failure
    """
    try:
        # 2026: Explicit timeout configuration
        timeout_config = httpx.Timeout(
            connect=5.0,  # Connection timeout
            read=timeout,  # Read timeout
            write=5.0,  # Write timeout
            pool=5.0,  # Pool timeout
        )

        response = httpx.post(
            f"{embedding_url}/embed",
            json={"texts": [text]},
            timeout=timeout_config,
        )
        response.raise_for_status()

        data = response.json()
        embeddings = data.get("embeddings", [])

        if not embeddings:
            logger.error(
                "embedding_generation_failed",
                extra={"error": "No embeddings in response", "text_preview": text[:50]},
            )
            return None

        embedding = embeddings[0]

        # Validate embedding dimensions
        if len(embedding) != 768:
            logger.error(
                "embedding_invalid_dimensions",
                extra={"expected": 768, "actual": len(embedding)},
            )
            return None

        logger.debug(
            "embedding_generated",
            extra={"text_length": len(text), "dimensions": len(embedding)},
        )

        return embedding

    except httpx.TimeoutException as e:
        logger.error(
            "embedding_timeout", extra={"timeout_seconds": timeout, "error": str(e)}
        )
        return None

    except httpx.HTTPStatusError as e:
        logger.error(
            "embedding_http_error",
            extra={"status_code": e.response.status_code, "error": str(e)},
        )
        return None

    except Exception as e:
        logger.error(
            "embedding_unexpected_error",
            extra={"error_type": type(e).__name__, "error": str(e)},
        )
        return None


def create_point_from_template(
    template: BestPracticeTemplate, embedding: list[float]
) -> PointStruct:
    """Create Qdrant point from validated template with optional timestamp fields.

    TECH-DEBT-028: Adds optional timestamp fields to payload:
    - timestamp: Auto-generated from current UTC time (existing field)
    - source_date: From template.source_date if provided (NEW)
    - last_verified: From template.last_verified if provided (NEW)

    2026 Pattern: uuid4() for secure random IDs
    Source: https://thelinuxcode.com/generating-random-ids-with-pythons-uuid-module-2026-playbook/

    Args:
        template: Validated BestPracticeTemplate with optional source_date/last_verified
        embedding: 768-dimensional embedding vector from Jina v2

    Returns:
        PointStruct ready for Qdrant upsert with all payload fields
    """
    # 2026: uuid4() for secure random IDs (not uuid1 which exposes MAC)
    point_id = str(uuid.uuid4())

    # Compute content hash for deduplication (HIGH-1 fix)
    content_hash = compute_content_hash(template.content)

    # Create payload following project-context.md snake_case rules
    payload = {
        "content": template.content,
        "content_hash": content_hash,  # Required for deduplication
        "type": template.type,
        "domain": template.domain,
        "importance": template.importance,
        "tags": template.tags,
        "source_hook": "seed_script",
        "group_id": "shared",  # conventions are shared across projects
        "embedding_status": "complete",
        "embedding_model": "jina-embeddings-v2-base-en",
        # Timestamp fields (TECH-DEBT-028)
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),  # Existing field (backwards compatible)
        "source_date": (
            template.source_date.isoformat() if template.source_date else None
        ),  # TECH-DEBT-028: NEW optional field
        "last_verified": (
            template.last_verified.isoformat() if template.last_verified else None
        ),  # TECH-DEBT-028: NEW optional field
    }

    # Add optional source if present
    if template.source:
        payload["source"] = template.source

    return PointStruct(id=point_id, vector=embedding, payload=payload)


def get_existing_hashes(
    client: QdrantClient, collection: str = "conventions"
) -> set[str]:
    """Get all existing content_hash values from collection.

    Used for deduplication check before seeding (MED-3 fix).

    Args:
        client: Qdrant client instance
        collection: Collection name

    Returns:
        Set of content_hash strings already in collection
    """
    try:
        # Scroll through all points to get content_hash values
        existing_hashes = set()
        offset = None

        while True:
            records, offset = client.scroll(
                collection_name=collection,
                limit=1000,
                offset=offset,
                with_payload=["content_hash"],
                with_vectors=False,
            )

            for record in records:
                if record.payload and "content_hash" in record.payload:
                    existing_hashes.add(record.payload["content_hash"])

            if offset is None:
                break

        logger.info(
            "existing_hashes_loaded",
            extra={"count": len(existing_hashes), "collection": collection},
        )

        return existing_hashes

    except Exception as e:
        logger.warning(
            "failed_to_load_existing_hashes",
            extra={"error": str(e)},
        )
        return set()


def seed_templates(
    templates: list[BestPracticeTemplate],
    config,
    dry_run: bool = False,
    batch_size: int = 100,
    skip_duplicates: bool = True,
) -> int:
    """Seed conventions collection with templates.

    2026 Pattern: Batch upsert for performance
    Source: https://qdrant.tech/documentation/database-tutorials/bulk-upload/

    Qdrant recommends batch sizes of 1000-10000 for optimal performance.
    Default batch_size=100 provides progress feedback; use larger batches
    for bulk imports.

    Args:
        templates: List of validated templates
        config: MemoryConfig instance
        dry_run: If True, don't actually insert (just validate)
        batch_size: Points per batch (default 100, max recommended 10000)
        skip_duplicates: If True, skip templates with existing content_hash

    Returns:
        Number of templates successfully seeded (excludes duplicates)

    Raises:
        ConnectionError: If Qdrant is unreachable (graceful degradation)
    """
    if not templates:
        logger.warning("no_templates_to_seed")
        return 0

    embedding_url = config.get_embedding_url()

    # Connect to Qdrant (BUG-102: use shared client for warning suppression)
    try:
        client = get_qdrant_client(config)

        # Verify collection exists
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if "conventions" not in collection_names:
            logger.error(
                "collection_not_found",
                extra={"collection": "conventions", "available": collection_names},
            )
            raise ConnectionError(
                "Collection 'conventions' not found. " "Run setup-collections.py first."
            )

    except Exception as e:
        logger.error(
            "qdrant_connection_failed",
            extra={
                "host": config.qdrant_host,
                "port": config.qdrant_port,
                "error": str(e),
            },
        )
        raise ConnectionError(f"Cannot connect to Qdrant: {e}") from e

    # Load existing hashes for deduplication (MED-3 fix)
    existing_hashes: set[str] = set()
    if skip_duplicates and not dry_run:
        existing_hashes = get_existing_hashes(client)

    # Process templates in batches
    points_created = 0
    skipped_duplicates = 0

    for i in range(0, len(templates), batch_size):
        batch = templates[i : i + batch_size]
        batch_points = []

        for template in batch:
            # Check for duplicate content (MED-3 fix)
            content_hash = compute_content_hash(template.content)
            if skip_duplicates and content_hash in existing_hashes:
                skipped_duplicates += 1
                logger.debug(
                    "skipping_duplicate_template",
                    extra={
                        "domain": template.domain,
                        "content_hash": content_hash[:16] + "...",
                    },
                )
                continue

            # Generate embedding
            embedding = generate_embedding(template.content, embedding_url)

            if embedding is None:
                logger.warning(
                    "skipping_template_no_embedding",
                    extra={
                        "domain": template.domain,
                        "content_preview": template.content[:50],
                    },
                )
                continue

            # Create point
            point = create_point_from_template(template, embedding)
            batch_points.append(point)

        # Upsert batch to Qdrant
        if batch_points:
            if dry_run:
                logger.info(
                    "dry_run_would_upsert",
                    extra={
                        "count": len(batch_points),
                        "batch": f"{i // batch_size + 1}",
                    },
                )
            else:
                try:
                    client.upsert(
                        collection_name="conventions",
                        points=batch_points,
                        wait=True,  # Wait for indexing to complete
                    )

                    points_created += len(batch_points)

                    # Track inserted hashes for subsequent deduplication
                    for point in batch_points:
                        if point.payload and "content_hash" in point.payload:
                            existing_hashes.add(point.payload["content_hash"])

                    logger.info(
                        "batch_seeded",
                        extra={
                            "count": len(batch_points),
                            "total_so_far": points_created,
                            "batch": f"{i // batch_size + 1}",
                        },
                    )

                except Exception as e:
                    logger.error(
                        "batch_upsert_failed",
                        extra={"batch": f"{i // batch_size + 1}", "error": str(e)},
                    )
                    # Continue with next batch (graceful degradation)

    # Log deduplication summary
    if skipped_duplicates > 0:
        logger.info(
            "deduplication_summary",
            extra={"skipped": skipped_duplicates, "inserted": points_created},
        )

    return points_created


def main() -> int:
    """Main entry point for seeding script.

    Returns:
        Exit code: 0 on success, 1 on error
    """
    # 2026 Pattern: argparse with dry-run support
    # Source: https://docs.python.org/3/howto/argparse.html
    parser = argparse.ArgumentParser(
        description="Seed conventions collection from JSON templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Seed from default directory
  python seed_conventions.py

  # Seed from custom directory
  python seed_conventions.py --templates-dir /path/to/templates

  # Dry run to validate templates without seeding
  python seed_conventions.py --dry-run

  # Verbose logging
  python seed_conventions.py -v

  # Large batch for bulk import (2026 best practice)
  python seed_conventions.py --batch-size 1000

  # Force re-seed (skip deduplication check)
  python seed_conventions.py --no-dedup
        """,
    )

    parser.add_argument(
        "--templates-dir",
        type=Path,
        help="Directory containing template JSON files (default: templates/conventions)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate templates and show what would be seeded without actually seeding",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Points per batch for Qdrant upsert (default: 100, recommended: 100-10000)",
    )

    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Skip deduplication check (insert even if content already exists)",
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine templates directory
    if args.templates_dir:
        templates_dir = args.templates_dir
    else:
        # Default: <install_dir>/templates/conventions
        try:
            config = get_config()
            templates_dir = config.install_dir / "templates" / "conventions"
        except Exception:
            # Fallback if config fails
            templates_dir = Path.home() / ".ai-memory" / "templates" / "conventions"

    logger.info(
        "seeding_started",
        extra={"templates_dir": str(templates_dir), "dry_run": args.dry_run},
    )

    # Check templates directory exists
    if not templates_dir.exists():
        logger.error(
            "templates_directory_not_found", extra={"path": str(templates_dir)}
        )
        print(f"\n❌ Templates directory not found: {templates_dir}")
        print("\nCreate templates directory and add JSON files:")
        print(f"  mkdir -p {templates_dir}")
        print(f"  # Add template files to {templates_dir}\n")
        return 1

    # Load all JSON template files
    json_files = list(templates_dir.glob("*.json"))

    if not json_files:
        logger.warning(
            "no_template_files_found", extra={"directory": str(templates_dir)}
        )
        print(f"\n⚠️  No .json files found in {templates_dir}")
        print("\nAdd template JSON files to seed best practices.\n")
        return 0

    # Load and validate all templates
    all_templates = []

    for json_file in json_files:
        try:
            templates = load_templates_from_file(json_file)
            all_templates.extend(templates)
            logger.info(
                "templates_loaded",
                extra={"file": json_file.name, "count": len(templates)},
            )
        except Exception as e:
            logger.error(
                "template_load_failed", extra={"file": json_file.name, "error": str(e)}
            )
            print(f"\n❌ Failed to load {json_file.name}: {e}\n")
            return 1

    print(f"\n{'=' * 70}")
    print("  Best Practices Seeding")
    print(f"{'=' * 70}\n")
    print(f"  Loaded {len(all_templates)} templates from {len(json_files)} files")

    if args.dry_run:
        print("\n  🔍 DRY RUN MODE - No actual seeding will occur\n")
        for i, template in enumerate(all_templates, 1):
            print(
                f"  {i}. [{template.domain}] {template.type}: {template.content[:60]}..."
            )
        print(f"\n{'=' * 70}\n")
        return 0

    # Load configuration
    try:
        config = get_config()
    except Exception as e:
        logger.error("config_load_failed", extra={"error": str(e)})
        print(f"\n❌ Configuration error: {e}\n")
        return 1

    # Seed templates
    try:
        count = seed_templates(
            all_templates,
            config,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            skip_duplicates=not args.no_dedup,
        )

        print(f"\n✅ Successfully seeded {count} best practices")
        print(f"{'=' * 70}\n")

        logger.info("seeding_completed", extra={"count": count})
        return 0

    except ConnectionError as e:
        logger.error("seeding_failed_connection", extra={"error": str(e)})
        print(f"\n❌ Seeding failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Ensure Docker services are running:")
        print("     docker compose ps")
        print("  2. Check Qdrant health:")
        print(f"     curl http://{config.qdrant_host}:{config.qdrant_port}/health")
        print("  3. Run health check:")
        print("     python scripts/health-check.py\n")
        return 1

    except Exception as e:
        logger.error(
            "seeding_failed_unexpected",
            extra={"error_type": type(e).__name__, "error": str(e)},
        )
        print(f"\n❌ Unexpected error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
