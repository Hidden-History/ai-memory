"""GitHub data schema and collection setup for github collection.

Defines payload schemas and creates required payload indexes on the
github collection for GitHub data isolation (PLAN-010, BP-075).

Spec: SPEC-005 (PLAN-006)
"""

import hashlib
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import KeywordIndexParams, PayloadSchemaType

from memory.config import COLLECTION_GITHUB as GITHUB_COLLECTION

logger = logging.getLogger("ai_memory.github.schema")

# GitHub-specific indexes to create on github collection.
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
    {"field_name": "source_authority", "schema": PayloadSchemaType.FLOAT},
    {"field_name": "update_batch_id", "schema": PayloadSchemaType.KEYWORD},
]

# Source authority mapping per Section 9 / FIX-28 (canonical float scale per SPEC-008)
# Tier 3 (factual/verifiable) → 1.0, Tier 1 (descriptive) → 0.4
SOURCE_AUTHORITY_MAP: dict[str, float] = {
    "github_issue": 0.4,  # Human-written issue descriptions
    "github_issue_comment": 0.4,  # Human-written comments
    "github_pr": 0.4,  # Human-written PR descriptions
    "github_pr_diff": 1.0,  # Machine-generated diff extraction
    "github_pr_review": 0.4,  # Human-written review comments
    "github_commit": 0.4,  # Human-written commit messages
    "github_code_blob": 1.0,  # Automated code extraction
    "github_ci_result": 1.0,  # Machine-generated CI output
    "github_release": 0.4,  # Human-written release notes
}

# Backward-compatible alias (deprecated — use SOURCE_AUTHORITY_MAP)
AUTHORITY_TIER_MAP = SOURCE_AUTHORITY_MAP


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


def get_source_authority(memory_type: str) -> float:
    """Get source authority score for a GitHub memory type.

    Args:
        memory_type: MemoryType value string (e.g., "github_issue")

    Returns:
        Source authority float: 0.4 (descriptive), 1.0 (factual/verifiable)

    Raises:
        KeyError: If memory_type is not a known GitHub type
    """
    return SOURCE_AUTHORITY_MAP[memory_type]


# Backward-compatible alias (deprecated — use get_source_authority)
get_authority_tier = get_source_authority


def create_github_indexes(client: QdrantClient) -> dict[str, int]:
    """Create GitHub namespace payload indexes on github collection.

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
                collection_name=GITHUB_COLLECTION,
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
                        collection_name=GITHUB_COLLECTION,
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
