"""Tests for GitHub data schema and collection setup (SPEC-005).

Tests MemoryType enum additions, content hash computation, index definitions,
source authority mapping, and collection constants.
"""

from unittest.mock import MagicMock

import pytest

from memory.connectors.github.schema import (
    AUTHORITY_TIER_MAP,
    DISCUSSIONS_COLLECTION,
    GITHUB_INDEXES,
    SOURCE_AUTHORITY_MAP,
    compute_content_hash,
    create_github_indexes,
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
    """Total MemoryType count is 30 (17 existing + 9 GitHub + 4 agent)."""
    assert len(MemoryType) == 30


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
    """source index has is_tenant=True via KeywordIndexParams (BP-075, BUG-116)."""
    from qdrant_client.models import KeywordIndexParams

    source_idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "source")
    assert isinstance(source_idx["schema"], KeywordIndexParams)
    assert source_idx["schema"].is_tenant is True


def test_only_source_is_tenant():
    """Only source index uses KeywordIndexParams with is_tenant."""
    from qdrant_client.models import KeywordIndexParams

    tenant_indexes = [
        i
        for i in GITHUB_INDEXES
        if isinstance(i["schema"], KeywordIndexParams)
        and getattr(i["schema"], "is_tenant", False)
    ]
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
        "source_authority",
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


# -- Index Schema Type Tests ---------------------------------------------------


def test_source_index_is_keyword():
    """source index uses KeywordIndexParams with type='keyword' (BUG-116)."""
    from qdrant_client.models import KeywordIndexParams

    source_idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "source")
    assert isinstance(source_idx["schema"], KeywordIndexParams)
    assert source_idx["schema"].type == "keyword"


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
    """github_id uses INTEGER schema type."""
    from qdrant_client.models import PayloadSchemaType

    idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "github_id")
    assert idx["schema"] == PayloadSchemaType.INTEGER


def test_source_authority_index_is_float():
    """source_authority uses FLOAT schema type (canonical v2.0.6 field)."""
    from qdrant_client.models import PayloadSchemaType

    idx = next(i for i in GITHUB_INDEXES if i["field_name"] == "source_authority")
    assert idx["schema"] == PayloadSchemaType.FLOAT


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

    def test_is_tenant_encoded_in_schema_not_kwarg(self):
        """BUG-116: is_tenant is in KeywordIndexParams, not a direct kwarg."""
        from qdrant_client.models import KeywordIndexParams

        mock_client = MagicMock()
        create_github_indexes(mock_client)

        # Verify NO call passes is_tenant as a direct keyword argument
        for call in mock_client.create_payload_index.call_args_list:
            kwargs = call[1] if call[1] else {}
            assert (
                "is_tenant" not in kwargs
            ), f"is_tenant should not be a direct kwarg (field: {kwargs.get('field_name')})"

        # Verify source field_schema is KeywordIndexParams with is_tenant=True
        for call in mock_client.create_payload_index.call_args_list:
            kwargs = call[1] if call[1] else {}
            if kwargs.get("field_name") == "source":
                assert isinstance(kwargs["field_schema"], KeywordIndexParams)
                assert kwargs["field_schema"].is_tenant is True

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
        mock_client.create_payload_index.side_effect = RuntimeError(
            "connection refused"
        )
        with pytest.raises(RuntimeError, match="connection refused"):
            create_github_indexes(mock_client)

    def test_timeout_retries_once_then_succeeds(self):
        """BUG-116/TASK-023: Timeout on first attempt retries once and succeeds."""
        mock_client = MagicMock()
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            # First call: timeout, retry succeeds, rest succeed
            if call_count == 1:
                raise TimeoutError("Connection timed out")
            return None

        mock_client.create_payload_index.side_effect = side_effect

        result = create_github_indexes(mock_client)

        # First index: timeout + retry = 2 calls, then 9 more = 11 total
        assert mock_client.create_payload_index.call_count == 11
        assert result["created"] == 10
        assert result["skipped"] == 0

    def test_timeout_retry_also_fails_raises(self):
        """If retry after timeout also fails, should raise."""
        mock_client = MagicMock()
        mock_client.create_payload_index.side_effect = TimeoutError(
            "Connection timed out"
        )

        with pytest.raises(TimeoutError):
            create_github_indexes(mock_client)

    def test_timeout_string_match_retries(self):
        """Errors containing 'timeout' in message also trigger retry."""
        mock_client = MagicMock()
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Request timeout after 30s")
            return None

        mock_client.create_payload_index.side_effect = side_effect

        result = create_github_indexes(mock_client)

        assert result["created"] == 10

    def test_return_dict_keys_are_created_and_skipped(self):
        """BUG-116: Return dict has 'created' and 'skipped', NOT 'existing'."""
        mock_client = MagicMock()
        result = create_github_indexes(mock_client)

        assert "created" in result
        assert "skipped" in result
        assert "existing" not in result
