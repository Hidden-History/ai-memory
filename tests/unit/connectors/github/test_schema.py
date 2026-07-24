"""Tests for GitHub data schema and collection setup (SPEC-005).

Tests MemoryType enum additions, content hash computation, source authority
mapping, and collection constants. Payload-index creation for the github
collection is exercised via ``memory.qdrant_client.ensure_payload_indexes``
(TD-874 — the single authoring site; see tests/unit/test_payload_index_helper.py),
not this module.
"""

import pytest

from memory.connectors.github.schema import (
    AUTHORITY_TIER_MAP,
    GITHUB_COLLECTION,
    SOURCE_AUTHORITY_MAP,
    compute_content_hash,
    get_authority_tier,
    get_source_authority,
)
from memory.models import MemoryType

# -- MemoryType Tests ----------------------------------------------------------


def test_github_memory_types_exist():
    """All 9 GitHub MemoryType values defined."""
    github_types = [
        MemoryType.GITHUB_ISSUE,
        MemoryType.GITHUB_ISSUE_COMMENT,
        MemoryType.GITHUB_PR,
        MemoryType.GITHUB_PR_DIFF,
        MemoryType.GITHUB_PR_REVIEW,
        MemoryType.GITHUB_COMMIT,
        MemoryType.GITHUB_CODE_BLOB,
        MemoryType.GITHUB_CI_RESULT,
        MemoryType.GITHUB_RELEASE,
    ]
    assert len(github_types) == 9


def test_github_type_values():
    """GitHub type .value matches expected payload string."""
    assert MemoryType.GITHUB_ISSUE.value == "github_issue"
    assert MemoryType.GITHUB_ISSUE_COMMENT.value == "github_issue_comment"
    assert MemoryType.GITHUB_PR.value == "github_pr"
    assert MemoryType.GITHUB_PR_DIFF.value == "github_pr_diff"
    assert MemoryType.GITHUB_PR_REVIEW.value == "github_pr_review"
    assert MemoryType.GITHUB_COMMIT.value == "github_commit"
    assert MemoryType.GITHUB_CODE_BLOB.value == "github_code_blob"
    assert MemoryType.GITHUB_CI_RESULT.value == "github_ci_result"
    assert MemoryType.GITHUB_RELEASE.value == "github_release"


def test_total_memory_type_count():
    """Total MemoryType count is 32 (18 existing + 9 GitHub + 4 agent + 1 sot_entry)."""
    assert len(MemoryType) == 32


def test_existing_types_unchanged():
    """Existing MemoryType values not affected."""
    assert MemoryType.IMPLEMENTATION.value == "implementation"
    assert MemoryType.ERROR_PATTERN.value == "error_pattern"
    assert MemoryType.REFACTOR.value == "refactor"
    assert MemoryType.FILE_PATTERN.value == "file_pattern"
    assert MemoryType.RULE.value == "rule"
    assert MemoryType.DECISION.value == "decision"
    assert MemoryType.SESSION.value == "session"
    assert MemoryType.JIRA_ISSUE.value == "jira_issue"
    assert MemoryType.JIRA_COMMENT.value == "jira_comment"


# -- Content Hash Tests --------------------------------------------------------


def test_content_hash_consistency():
    """Same content produces same hash."""
    content = "Fix storage.py bug in store_memory()"
    h1 = compute_content_hash(content)
    h2 = compute_content_hash(content)
    assert h1 == h2


def test_content_hash_different_content():
    """Different content produces different hash."""
    h1 = compute_content_hash("content A")
    h2 = compute_content_hash("content B")
    assert h1 != h2


def test_content_hash_format():
    """Content hash is 64-char hex string (SHA-256)."""
    h = compute_content_hash("test content")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_content_hash_unicode():
    """Content hash handles Unicode content."""
    h = compute_content_hash("Unicode: \u00e9\u00e8\u00ea \u2603 \U0001f4a9")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_content_hash_empty_string():
    """Content hash handles empty string."""
    h = compute_content_hash("")
    assert len(h) == 64
    # SHA-256 of empty string is a well-known constant
    assert h == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_content_hash_whitespace_sensitivity():
    """Content hash distinguishes between whitespace variations."""
    h1 = compute_content_hash("hello world")
    h2 = compute_content_hash("hello  world")
    assert h1 != h2


def test_discussions_collection_constant():
    """Collection constant points to github."""
    assert GITHUB_COLLECTION == "github"


# -- Source Authority Tests -----------------------------------------------------


def test_source_authority_descriptive_types():
    """Descriptive (human-written) types get source_authority=0.4."""
    descriptive_types = [
        "github_issue",
        "github_issue_comment",
        "github_pr",
        "github_pr_review",
        "github_commit",
        "github_release",
    ]
    for t in descriptive_types:
        assert get_source_authority(t) == 0.4, f"{t} should be 0.4 (descriptive)"


def test_source_authority_factual_types():
    """Factual/verifiable (machine-generated) types get source_authority=1.0."""
    factual_types = ["github_pr_diff", "github_code_blob", "github_ci_result"]
    for t in factual_types:
        assert get_source_authority(t) == 1.0, f"{t} should be 1.0 (factual)"


def test_source_authority_all_github_types_mapped():
    """All 9 GitHub types have source authority mapping."""
    github_type_values = [
        "github_issue",
        "github_issue_comment",
        "github_pr",
        "github_pr_diff",
        "github_pr_review",
        "github_commit",
        "github_code_blob",
        "github_ci_result",
        "github_release",
    ]
    for t in github_type_values:
        assert t in SOURCE_AUTHORITY_MAP, f"{t} missing from SOURCE_AUTHORITY_MAP"


def test_source_authority_unknown_type_raises():
    """Unknown type raises KeyError."""
    with pytest.raises(KeyError):
        get_source_authority("unknown_type")


def test_backward_compat_authority_tier_map_alias():
    """AUTHORITY_TIER_MAP is a backward-compatible alias for SOURCE_AUTHORITY_MAP."""
    assert AUTHORITY_TIER_MAP is SOURCE_AUTHORITY_MAP


def test_backward_compat_get_authority_tier_alias():
    """get_authority_tier is a backward-compatible alias for get_source_authority."""
    assert get_authority_tier is get_source_authority
