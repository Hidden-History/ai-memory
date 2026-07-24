"""GitHub data schema and collection setup for github collection.

Defines payload schemas and creates required payload indexes on the
github collection for GitHub data isolation (PLAN-010, BP-075).

Spec: SPEC-005 (PLAN-006)
"""

import hashlib

from memory.config import COLLECTION_GITHUB as GITHUB_COLLECTION  # noqa: F401

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
