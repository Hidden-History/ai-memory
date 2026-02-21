"""GitHub data schema and collection setup for discussions namespace.

Defines payload schemas and creates required payload indexes on the
discussions collection for GitHub namespace isolation (AD-1, BP-075).

Spec: SPEC-005 (PLAN-006)
"""

import hashlib
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import KeywordIndexParams, PayloadSchemaType

logger = logging.getLogger("ai_memory.github.schema")

# Collection that GitHub data is stored in (AD-1: shared with discussions)
DISCUSSIONS_COLLECTION = "discussions"

# GitHub namespace indexes to create on discussions collection.
# These are ADDITIONAL to existing discussions indexes (group_id, type, stored_at).
GITHUB_INDEXES: list[dict] = [
    {
        "field_name": "source",
        "schema": KeywordIndexParams(type="keyword", is_tenant=True),
    },
    {"field_name": "github_id", "schema": PayloadSchemaType.INTEGER},
    {"field_name": "file_path", "schema": PayloadSchemaType.KEYWORD},
    {"field_name": "sha", "schema": PayloadSchemaType.KEYWORD},
    {"field_name": "state", "schema": PayloadSchemaType.KEYWORD},
    {"field_name": "last_synced", "schema": PayloadSchemaType.DATETIME},
    {"field_name": "content_hash", "schema": PayloadSchemaType.KEYWORD},
    {"field_name": "is_current", "schema": PayloadSchemaType.BOOL},
    {"field_name": "authority_tier", "schema": PayloadSchemaType.INTEGER},
    {"field_name": "update_batch_id", "schema": PayloadSchemaType.KEYWORD},
]

# Authority tier mapping per Section 9 / FIX-28
AUTHORITY_TIER_MAP: dict[str, int] = {
    "github_issue": 1,  # Human-written issue descriptions
    "github_issue_comment": 1,  # Human-written comments
    "github_pr": 1,  # Human-written PR descriptions
    "github_pr_diff": 3,  # Machine-generated diff extraction
    "github_pr_review": 1,  # Human-written review comments
    "github_commit": 1,  # Human-written commit messages
    "github_code_blob": 3,  # Automated code extraction
    "github_ci_result": 3,  # Machine-generated CI output
    "github_release": 1,  # Human-written release notes
}


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for deduplication.

    Hashes the COMPOSED document string (after composer transforms the API
    response), not the raw API response. This ensures that reformatting the
    composer output triggers re-embedding, while unchanged content is skipped.

    Args:
        content: The text content that will be embedded

    Returns:
        Hex-encoded SHA-256 hash (64 chars)
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_authority_tier(memory_type: str) -> int:
    """Get authority tier for a GitHub memory type.

    Args:
        memory_type: MemoryType value string (e.g., "github_issue")

    Returns:
        Authority tier: 1=human, 3=automated

    Raises:
        KeyError: If memory_type is not a known GitHub type
    """
    return AUTHORITY_TIER_MAP[memory_type]


def create_github_indexes(client: QdrantClient) -> dict[str, int]:
    """Create GitHub namespace payload indexes on discussions collection.

    Idempotent -- safe to call multiple times. Qdrant ignores create_payload_index
    if the index already exists with the same configuration.

    Args:
        client: Qdrant client instance

    Returns:
        Dict with created (int) and skipped (int) counts
    """
    created = 0
    skipped = 0

    for index_def in GITHUB_INDEXES:
        field_name = index_def["field_name"]
        try:
            # BUG-116: is_tenant is encoded in KeywordIndexParams, not as a direct kwarg.
            # Pattern: setup-collections.py:140-147 (KeywordIndexParams for tenant indexes)
            client.create_payload_index(
                collection_name=DISCUSSIONS_COLLECTION,
                field_name=field_name,
                field_schema=index_def["schema"],
            )
            created += 1
            logger.info("Created index: %s (%s)", field_name, index_def["schema"])
        except Exception as e:
            # Qdrant returns error if index exists with different config
            # but silently succeeds if identical -- handle both cases
            if "already exists" in str(e).lower():
                skipped += 1
                logger.debug("Index already exists: %s", field_name)
            elif "timeout" in str(e).lower() or isinstance(e, (TimeoutError, OSError)):
                # TASK-023: Retry once on timeout (Qdrant may be slow under load)
                try:
                    client.create_payload_index(
                        collection_name=DISCUSSIONS_COLLECTION,
                        field_name=field_name,
                        field_schema=index_def["schema"],
                    )
                    created += 1
                    logger.info("Created index on retry: %s", field_name)
                except Exception as retry_err:
                    logger.warning(
                        "Index creation failed after retry: %s (%s)",
                        field_name,
                        retry_err,
                    )
                    raise
            else:
                raise

    logger.info("GitHub indexes: %d created, %d already existed", created, skipped)
    return {"created": created, "skipped": skipped}
