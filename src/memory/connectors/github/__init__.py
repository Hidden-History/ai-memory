"""GitHub integration package.

Provides async API client for GitHub REST API v3 with rate limiting and ETag caching,
plus schema definitions, content hashing, and index management for GitHub data
stored in the discussions collection namespace (AD-1).

Includes sync engine (SPEC-006) for orchestrating GitHub data ingestion.
"""

from .client import GitHubClient, GitHubClientError, RateLimitExceeded
from .code_sync import CodeBlobSync, CodeSyncResult
from .schema import (
    AUTHORITY_TIER_MAP,
    DISCUSSIONS_COLLECTION,
    GITHUB_INDEXES,
    compute_content_hash,
    create_github_indexes,
    get_authority_tier,
)
from .sync import GitHubSyncEngine, SyncResult

__all__ = [
    "AUTHORITY_TIER_MAP",
    "CodeBlobSync",
    "CodeSyncResult",
    "DISCUSSIONS_COLLECTION",
    "GITHUB_INDEXES",
    "GitHubClient",
    "GitHubClientError",
    "GitHubSyncEngine",
    "RateLimitExceeded",
    "SyncResult",
    "compute_content_hash",
    "create_github_indexes",
    "get_authority_tier",
]
