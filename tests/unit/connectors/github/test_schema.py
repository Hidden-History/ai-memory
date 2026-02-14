"""Tests for GitHub data schema and collection setup (SPEC-005).

Tests MemoryType enum additions, content hash computation, index definitions,
authority tier mapping, and collection constants.
"""

import pytest

from unittest.mock import MagicMock

from memory.connectors.github.schema import (
    AUTHORITY_TIER_MAP,
    DISCUSSIONS_COLLECTION,
    GITHUB_INDEXES,
    compute_content_hash,
    create_github_indexes,
    get_authority_tier,
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
    """Total MemoryType count is 26 (17 existing + 9 GitHub)."""
    assert len(MemoryType) == 26


def test_existing_types_unchanged():
    """Existing MemoryType values not affected."""
    assert MemoryType.IMPLEMENTATION.value == "implementation"
    assert MemoryType.ERROR_FIX.value == "error_fix"
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


# -- Index Definition Tests ----------------------------------------------------


def test_github_indexes_count():
    """Exactly 10 GitHub indexes defined."""
    assert len(GITHUB_INDEXES) == 10


def test_source_index_is_tenant():
    """source index has is_tenant=True (BP-075)."""
    source_idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "source")
    assert source_idx.get("is_tenant") is True


def test_only_source_is_tenant():
    """Only source index is marked as tenant."""
    tenant_indexes = [i for i in GITHUB_INDEXES if i.get("is_tenant")]
    assert len(tenant_indexes) == 1
    assert tenant_indexes[0]["field_name"] == "source"


def test_all_required_indexes_defined():
    """All required index fields are present."""
    field_names = {i["field_name"] for i in GITHUB_INDEXES}
    required = {
        "source",
        "github_id",
        "file_path",
        "sha",
        "state",
        "last_synced",
        "content_hash",
        "is_current",
        "authority_tier",
        "update_batch_id",
    }
    assert field_names == required


def test_discussions_collection_constant():
    """Collection constant points to discussions."""
    assert DISCUSSIONS_COLLECTION == "discussions"


def test_all_indexes_have_schema():
    """Every index definition has a schema field."""
    for idx in GITHUB_INDEXES:
        assert "schema" in idx, f"Missing schema for {idx['field_name']}"
        assert "field_name" in idx


def test_no_duplicate_index_fields():
    """No duplicate field names in index definitions."""
    field_names = [i["field_name"] for i in GITHUB_INDEXES]
    assert len(field_names) == len(set(field_names))


# -- Authority Tier Tests ------------------------------------------------------


def test_authority_tier_human_types():
    """Human-written types get authority_tier=1."""
    human_types = [
        "github_issue",
        "github_issue_comment",
        "github_pr",
        "github_pr_review",
        "github_commit",
        "github_release",
    ]
    for t in human_types:
        assert get_authority_tier(t) == 1, f"{t} should be tier 1 (human)"


def test_authority_tier_automated_types():
    """Automated types get authority_tier=3."""
    automated_types = ["github_pr_diff", "github_code_blob", "github_ci_result"]
    for t in automated_types:
        assert get_authority_tier(t) == 3, f"{t} should be tier 3 (automated)"


def test_authority_tier_all_github_types_mapped():
    """All 9 GitHub types have authority tier mapping."""
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
        assert t in AUTHORITY_TIER_MAP, f"{t} missing from AUTHORITY_TIER_MAP"


def test_authority_tier_unknown_type_raises():
    """Unknown type raises KeyError."""
    with pytest.raises(KeyError):
        get_authority_tier("unknown_type")


# -- Index Schema Type Tests ---------------------------------------------------


def test_source_index_is_keyword():
    """source index uses KEYWORD schema type."""
    from qdrant_client.models import PayloadSchemaType

    source_idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "source")
    assert source_idx["schema"] == PayloadSchemaType.KEYWORD


def test_is_current_index_is_bool():
    """is_current index uses BOOL schema type."""
    from qdrant_client.models import PayloadSchemaType

    idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "is_current")
    assert idx["schema"] == PayloadSchemaType.BOOL


def test_last_synced_index_is_datetime():
    """last_synced index uses DATETIME schema type."""
    from qdrant_client.models import PayloadSchemaType

    idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "last_synced")
    assert idx["schema"] == PayloadSchemaType.DATETIME


def test_integer_indexes():
    """github_id and authority_tier use INTEGER schema type."""
    from qdrant_client.models import PayloadSchemaType

    int_fields = {"github_id", "authority_tier"}
    for idx in GITHUB_INDEXES:
        if idx["field_name"] in int_fields:
            assert idx["schema"] == PayloadSchemaType.INTEGER, (
                f"{idx['field_name']} should be INTEGER"
            )


# -- create_github_indexes() Function Tests -----------------------------------


class TestCreateGitHubIndexes:
    """Tests for create_github_indexes() function logic."""

    def test_creates_all_10_indexes(self):
        """create_github_indexes creates all 10 indexes on clean collection."""
        mock_client = MagicMock()
        result = create_github_indexes(mock_client)
        assert result == {"created": 10, "skipped": 0}
        assert mock_client.create_payload_index.call_count == 10

    def test_idempotent_skips_existing(self):
        """Running create_github_indexes twice doesn't error — skips existing."""
        mock_client = MagicMock()
        # Simulate "already exists" error for all indexes
        mock_client.create_payload_index.side_effect = Exception("already exists")
        result = create_github_indexes(mock_client)
        assert result == {"created": 0, "skipped": 10}

    def test_is_tenant_passed_for_source_only(self):
        """is_tenant=True is only passed for the source index."""
        mock_client = MagicMock()
        create_github_indexes(mock_client)

        # Find the call for 'source' field
        for call in mock_client.create_payload_index.call_args_list:
            kwargs = call[1] if call[1] else {}
            if "field_name" in kwargs and kwargs["field_name"] == "source":
                assert kwargs.get("is_tenant") is True
            elif "field_name" in kwargs:
                assert "is_tenant" not in kwargs or kwargs.get("is_tenant") is None

    def test_returns_correct_counts_mixed(self):
        """Mixed success/failure returns correct created/skipped counts."""
        mock_client = MagicMock()
        # First 5 succeed, last 5 fail
        side_effects = [None] * 5 + [Exception("already exists")] * 5
        mock_client.create_payload_index.side_effect = side_effects
        result = create_github_indexes(mock_client)
        assert result == {"created": 5, "skipped": 5}

    def test_unexpected_exception_propagates(self):
        """Non-'already exists' exceptions are re-raised."""
        mock_client = MagicMock()
        mock_client.create_payload_index.side_effect = RuntimeError("connection refused")
        with pytest.raises(RuntimeError, match="connection refused"):
            create_github_indexes(mock_client)
