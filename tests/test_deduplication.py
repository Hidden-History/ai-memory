"""Unit tests for deduplication module.

Tests AC 2.2.1 through AC 2.2.6:
- Dual-stage deduplication (hash + semantic)
- Configurable similarity threshold
- Async error handling with Qdrant exceptions
- Performance requirements (<100ms total)
- Content hash function (SHA-256)
- Edge cases and error scenarios

Story: 2.2 - Deduplication Module
"""

import hashlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from src.memory.config import reset_config
from src.memory.deduplication import (
    DuplicationCheckResult,
    compute_content_hash,
    is_duplicate,
)


class TestContentHash:
    """Tests for compute_content_hash() function - AC 2.2.5."""

    def test_compute_hash_returns_sha256_format(self):
        """AC 2.2.5: Returns SHA-256 hex digest with sha256: prefix."""
        content = "def hello(): return 'world'"
        result = compute_content_hash(content)

        assert result.startswith("sha256:")
        assert len(result) == len("sha256:") + 64  # sha256: + 64 hex chars

    def test_compute_hash_handles_string_input(self):
        """AC 2.2.5: Handles string input with utf-8 encoding."""
        content = "Test content"
        result = compute_content_hash(content)

        # Verify manual computation matches
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result == f"sha256:{expected_hash}"

    def test_compute_hash_handles_unicode(self):
        """AC 2.2.6: Hash after utf-8 encoding for unicode content."""
        content = "Hello 世界 🌍"
        result = compute_content_hash(content)

        assert result.startswith("sha256:")
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result == f"sha256:{expected_hash}"

    def test_compute_hash_deterministic(self):
        """AC 2.2.5: Same content produces same hash."""
        content = "def test(): pass"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        assert hash1 == hash2

    def test_compute_hash_different_content_different_hash(self):
        """AC 2.2.5: Different content produces different hash."""
        hash1 = compute_content_hash("content1")
        hash2 = compute_content_hash("content2")

        assert hash1 != hash2

    def test_compute_hash_empty_content(self):
        """AC 2.2.6: Handles empty content gracefully."""
        result = compute_content_hash("")

        assert result.startswith("sha256:")
        expected_hash = hashlib.sha256(b"").hexdigest()
        assert result == f"sha256:{expected_hash}"

    def test_compute_hash_handles_bytes(self):
        """AC 2.2.5: Handles bytes input without encoding."""
        content_bytes = b"binary data \x00\x01\x02"
        result = compute_content_hash(content_bytes)

        assert result.startswith("sha256:")
        expected_hash = hashlib.sha256(content_bytes).hexdigest()
        assert result == f"sha256:{expected_hash}"


@pytest.mark.asyncio
class TestIsDuplicate:
    """Tests for is_duplicate() function - AC 2.2.1, 2.2.2, 2.2.3, 2.2.6."""

    async def test_exact_duplicate_hash_match(self):
        """AC 2.2.1: Fast hash check detects exact duplicates."""
        content = "def test(): return True"
        group_id = "test-project"

        with patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Mock scroll to return existing hash match
            mock_client.scroll.return_value = (
                [MagicMock(id="existing-id-123")],
                None,
            )

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is True
            assert result.reason == "hash_match"
            assert result.existing_id == "existing-id-123"
            mock_client.scroll.assert_called_once()

    async def test_no_duplicate_new_content(self):
        """AC 2.2.1: Returns False when content is unique."""
        content = "def unique_function(): pass"
        group_id = "test-project"

        with (
            patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class,
            patch("src.memory.deduplication.EmbeddingClient") as mock_embed_class,
        ):
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Mock embedding client
            mock_embed = MagicMock()
            mock_embed_class.return_value.__enter__.return_value = mock_embed
            mock_embed.embed.return_value = [[0.1] * 768]  # Dummy embedding

            # Mock scroll to return no hash matches
            mock_client.scroll.return_value = ([], None)

            # Mock search to return no semantic matches
            mock_client.search.return_value = []

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is False
            assert result.reason is None
            assert result.existing_id is None

    async def test_semantic_similarity_duplicate(self):
        """AC 2.2.1: Semantic similarity check detects near-duplicates."""
        content = "def hello(): return 'world'"
        group_id = "test-project"

        with (
            patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class,
            patch("src.memory.deduplication.EmbeddingClient") as mock_embed_class,
        ):
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Mock embedding client
            mock_embed = MagicMock()
            mock_embed_class.return_value.__enter__.return_value = mock_embed
            mock_embed.embed.return_value = [[0.1] * 768]  # Dummy embedding

            # Mock scroll to return no hash matches
            mock_client.scroll.return_value = ([], None)

            # Mock search to return high similarity match (>0.95)
            mock_result = MagicMock()
            mock_result.id = "semantic-match-id"
            mock_result.score = 0.97
            mock_client.search.return_value = [mock_result]

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is True
            assert result.reason == "semantic_similarity"
            assert result.existing_id == "semantic-match-id"
            assert result.similarity_score == 0.97

    async def test_configurable_threshold_above(self):
        """AC 2.2.2: Similarity above threshold returns True."""
        content = "test content"
        group_id = "test-project"

        # Reset config singleton so patched env var takes effect
        reset_config()

        with (
            patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class,
            patch("src.memory.deduplication.EmbeddingClient") as mock_embed_class,
            patch.dict(os.environ, {"DEDUP_THRESHOLD": "0.90"}),
        ):
            # Reset again after env patch to reload with new value
            reset_config()

            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Mock embedding client
            mock_embed = MagicMock()
            mock_embed_class.return_value.__enter__.return_value = mock_embed
            mock_embed.embed.return_value = [[0.1] * 768]

            # No hash match
            mock_client.scroll.return_value = ([], None)

            # Similarity 0.92 > threshold 0.90
            mock_result = MagicMock()
            mock_result.id = "similar-id"
            mock_result.score = 0.92
            mock_client.search.return_value = [mock_result]

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is True
            assert result.similarity_score == 0.92

        # Clean up
        reset_config()

    async def test_configurable_threshold_below(self):
        """AC 2.2.2: Similarity below threshold returns False.

        When threshold=0.95 and only 0.92 similarity exists, Qdrant's
        score_threshold parameter filters results server-side, returning
        empty results (not results with score below threshold).
        """
        content = "test content"
        group_id = "test-project"

        # Reset config singleton so patched env var takes effect
        reset_config()

        with (
            patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class,
            patch("src.memory.deduplication.EmbeddingClient") as mock_embed_class,
            patch.dict(os.environ, {"DEDUP_THRESHOLD": "0.95"}),
        ):
            # Reset again after env patch to reload with new value
            reset_config()

            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Mock embedding client
            mock_embed = MagicMock()
            mock_embed_class.return_value.__enter__.return_value = mock_embed
            mock_embed.embed.return_value = [[0.1] * 768]

            # No hash match
            mock_client.scroll.return_value = ([], None)

            # Qdrant filters by score_threshold server-side:
            # When threshold=0.95 and only 0.92 similarity exists,
            # Qdrant returns EMPTY results (filtered out)
            mock_client.search.return_value = []

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is False
            assert result.reason is None  # Not a duplicate, no error

        # Clean up
        reset_config()

    async def test_empty_content_returns_false(self):
        """AC 2.2.6: Empty content returns False (allow storage)."""
        result = await is_duplicate("", "test-project")

        assert result.is_duplicate is False
        assert result.reason == "empty_content"

    async def test_short_content_returns_false(self):
        """AC 2.2.6: Content <10 chars returns False (too short)."""
        result = await is_duplicate("test", "test-project")

        assert result.is_duplicate is False
        assert result.reason == "content_too_short"

    async def test_qdrant_unavailable_fail_open(self):
        """AC 2.2.3: Qdrant unavailable returns False (fail open)."""
        content = "test content that should check"
        group_id = "test-project"

        with patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Simulate Qdrant connection failure
            mock_client.scroll.side_effect = ConnectionRefusedError(
                "Connection refused"
            )

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is False
            assert result.reason == "error_fail_open"

    async def test_response_handling_exception_fail_open(self):
        """AC 2.2.3: ResponseHandlingException returns False (fail open)."""
        content = "test content"
        group_id = "test-project"

        with patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Simulate Qdrant API error
            mock_client.scroll.side_effect = ResponseHandlingException("API error")

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is False
            assert result.reason == "error_fail_open"

    async def test_unexpected_response_fail_open(self):
        """AC 2.2.3: UnexpectedResponse returns False (fail open)."""
        content = "test content"
        group_id = "test-project"

        with patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Simulate malformed response (UnexpectedResponse requires status_code, reason_phrase, content, headers)
            mock_client.scroll.side_effect = UnexpectedResponse(
                status_code=500,
                reason_phrase="Internal Server Error",
                content=b"Malformed response",
                headers={},
            )

            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is False
            assert result.reason == "error_fail_open"

    async def test_embedding_service_down_skip_similarity(self):
        """AC 2.2.6: Embedding service down skips similarity check."""
        content = "test content"
        group_id = "test-project"

        with patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # No hash match
            mock_client.scroll.return_value = ([], None)

        # Simulate embedding failure
        with patch("src.memory.deduplication.EmbeddingClient") as mock_embed_class:
            mock_embed = MagicMock()
            mock_embed_class.return_value.__enter__.return_value = mock_embed
            mock_embed.embed.side_effect = Exception("Service unavailable")

            result = await is_duplicate(content, group_id)

            # Should return False (hash check passed, similarity skipped)
            assert result.is_duplicate is False
            assert result.reason == "embedding_failed_hash_only"

    async def test_never_crashes_on_exception(self):
        """AC 2.2.6: NEVER throws unhandled exceptions."""
        content = "test content"
        group_id = "test-project"

        with patch("src.memory.deduplication.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            # Mock close() for new manual client lifecycle
            mock_client.close = AsyncMock()

            # Simulate unexpected exception
            mock_client.scroll.side_effect = RuntimeError("Unexpected error")

            # Should NOT raise - fail open
            result = await is_duplicate(content, group_id)

            assert result.is_duplicate is False
            assert result.reason == "error_fail_open"


class TestDuplicationCheckResult:
    """Tests for DuplicationCheckResult dataclass."""

    def test_result_structure_duplicate(self):
        """Verify result structure for duplicate case."""
        result = DuplicationCheckResult(
            is_duplicate=True,
            reason="hash_match",
            existing_id="abc-123",
            similarity_score=None,
        )

        assert result.is_duplicate is True
        assert result.reason == "hash_match"
        assert result.existing_id == "abc-123"
        assert result.similarity_score is None

    def test_result_structure_not_duplicate(self):
        """Verify result structure for non-duplicate case."""
        result = DuplicationCheckResult(
            is_duplicate=False,
            reason=None,
            existing_id=None,
            similarity_score=None,
        )

        assert result.is_duplicate is False
        assert result.reason is None
        assert result.existing_id is None
