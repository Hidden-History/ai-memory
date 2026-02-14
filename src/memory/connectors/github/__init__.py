"""GitHub integration package.

Provides async API client for GitHub REST API v3 with rate limiting and ETag caching,
plus schema definitions, content hashing, and index management for GitHub data
stored in the discussions collection namespace (AD-1).
"""

from .client import GitHubClient, GitHubClientError, RateLimitExceeded
from .schema import (
    AUTHORITY_TIER_MAP,
    DISCUSSIONS_COLLECTION,
    GITHUB_INDEXES,
    compute_content_hash,
    create_github_indexes,
    get_authority_tier,
)

__all__ = [
    "AUTHORITY_TIER_MAP",
    "DISCUSSIONS_COLLECTION",
    "GITHUB_INDEXES",
    "GitHubClient",
    "GitHubClientError",
    "RateLimitExceeded",
    "compute_content_hash",
    "create_github_indexes",
    "get_authority_tier",
]
