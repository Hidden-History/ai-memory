#!/usr/bin/env python3
"""Store BP-088: Qdrant Payload Index Migration for Live Collections to conventions collection.

This script stores the payload index migration best practices research
to the database for semantic retrieval.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.storage import store_best_practice

# Condensed version for storage (optimized for semantic search)
# Full document: oversight/knowledge/best-practices/BP-088-qdrant-payload-index-migration-live-collections-2026.md
CONTENT = """
Qdrant Payload Index Migration for Live Collections (2026)

ADDING INDEXES TO EXISTING COLLECTIONS:
- Safe, non-destructive, non-blocking operation on Qdrant >= v1.11.1 (PR #4941)
- Qdrant scans existing points and builds index from stored payload values
- Queries continue working during construction (just no filter optimization until built)
- No data modification occurs — purely an index structure operation
- On Qdrant < v1.11.1: BLOCKING — freezes reads AND writes (avoid for live collections)

API ENDPOINT:
- PUT /collections/{collection_name}/index
- Headers: api-key (required on ALL endpoints), Content-Type: application/json
- Body: {"field_name": "source", "field_schema": "keyword"}
- Query params: wait=true (blocks until built), wait=false (returns immediately)
- Python: client.create_payload_index(collection_name, field_name, field_schema, wait=True)

SUPPORTED INDEX TYPES:
- keyword (PayloadSchemaType.KEYWORD): String matching, most common
- integer (PayloadSchemaType.INTEGER): Numeric matching and range
- float (PayloadSchemaType.FLOAT): Floating point range
- bool (PayloadSchemaType.BOOL): Boolean matching (v1.4.0+)
- datetime (PayloadSchemaType.DATETIME): Timestamp range (v1.8.0+)
- text (TextIndexParams): Full-text search with tokenizer config
- uuid (v1.11.0+): Optimized UUID matching
- geo: Bounding box and radius filtering

PARTIAL FAILURE AND RECOVERY:
- Successfully created indexes persist even if script crashes mid-migration
- Qdrant does NOT roll back created indexes on failure
- Missing indexes cause full payload scan (slower but functional)
- Recovery: re-run migration script — it skips existing indexes

IDEMPOTENT MIGRATION PATTERN:
1. Check health: client.get_collections() or check_qdrant_health()
2. Verify collection exists: client.collection_exists(name)
3. Get existing indexes: client.get_collection(name).payload_schema.keys()
4. Create only missing indexes with wait=True
5. Validate all required indexes present after creation
6. Log results: created, existing, failed

LISTING EXISTING INDEXES:
- GET /collections/{collection_name} → response.result.payload_schema
- Python: collection_info = client.get_collection(name); collection_info.payload_schema
- Returns dict of field_name → PayloadIndexInfo(data_type, params)

DELETING AN INDEX:
- DELETE /collections/{collection_name}/index/{field_name}
- Python: client.delete_payload_index(collection_name, field_name, wait=True)
- Use for corrupted indexes before re-creation

PERFORMANCE IMPACT:
- Qdrant >= v1.11.1: Non-blocking, queries and writes continue normally
- CPU: Moderate spike during construction
- Memory: ~50-100 bytes per unique value per keyword index
- Duration: Proportional to collection size, seconds for <100K points
- Post-creation: Filter queries become O(1) lookup instead of full scan
- HNSW note: Existing graph edges NOT rebuilt for new indexes

ANTI-PATTERNS:
- NEVER delete and recreate collection to add indexes (destroys data!)
- NEVER use wait=False in migration scripts (validation may see missing indexes)
- NEVER index every payload field (wastes memory, slows writes marginally)
- NEVER skip post-migration validation (network errors cause silent failures)
- NEVER use setup-collections.py pattern (delete+create) for live migrations

VERSION REQUIREMENTS:
- Bool index: Qdrant >= v1.4.0
- Datetime index: Qdrant >= v1.8.0
- UUID index: Qdrant >= v1.11.0
- Non-blocking construction: Qdrant >= v1.11.1
- On-disk indexes: Qdrant >= v1.11.0
- Tenant index (is_tenant): Qdrant >= v1.11.0

MIGRATION SAFETY CHECKLIST:
Pre: health check, collection exists, version check, dry-run first
During: one index at a time, wait=True, log results, continue on failure
Post: re-read payload_schema, verify point count, test filter queries
Recovery: re-run script (idempotent), delete corrupted indexes, restore from snapshot

Sources: Qdrant docs (indexing, collections, security), GitHub #4934, #1890, v1.11.1 release,
Qdrant Python client docs, Discussion #6332, Qdrant FAQ database-optimization
""".strip()


def main():
    """Store BP-088 to conventions collection."""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "bp-088-storage")

    print("Storing BP-088 to conventions collection...")
    print(f"Session ID: {session_id}")
    print(f"Content length: {len(CONTENT)} chars")

    try:
        result = store_best_practice(
            content=CONTENT,
            session_id=session_id,
            source_hook="manual",
            domain="qdrant-migration",
            tags=[
                "qdrant",
                "payload-index",
                "migration",
                "schema-migration",
                "live-collection",
                "non-destructive",
                "idempotent",
                "vector-database",
                "index-creation",
                "production-safety",
            ],
            source="oversight/knowledge/best-practices/BP-088-qdrant-payload-index-migration-live-collections-2026.md",
            source_date="2026-02-13",
            auto_seeded=True,
            type="guideline",
        )

        print("\nStorage Result:")
        print(f"  Status: {result.get('status')}")
        print(f"  Memory ID: {result.get('memory_id')}")
        print(f"  Embedding Status: {result.get('embedding_status')}")
        print(f"  Collection: {result.get('collection')}")
        print(f"  Group ID: {result.get('group_id')}")

        if result.get("status") == "stored":
            print("\nSUCCESS: BP-088 stored to conventions collection")
            return 0
        elif result.get("status") == "duplicate":
            print("\nDUPLICATE: BP-088 already exists in database")
            return 0
        else:
            print(f"\nWARNING: Unexpected status: {result.get('status')}")
            return 1

    except Exception as e:
        print("\nERROR: Failed to store BP-088")
        print(f"  Error: {e!s}")
        print(f"  Type: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
