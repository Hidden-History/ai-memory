"""Integration tests for storage + truncation end-to-end behavior.

Verifies the complete fix for TECH-DEBT-151:
- Hard truncation removed (_enforce_content_limit deleted)
- Smart truncation implemented for USER_MESSAGE and AGENT_RESPONSE
- No data loss on guidelines
- Proper handling of all content types

These tests require Qdrant running on port 26350.
"""

import subprocess

import pytest

from memory.chunking.truncation import count_tokens
from memory.models import MemoryType
from memory.storage import MemoryStorage


@pytest.fixture
def storage(qdrant_client):
    """Create MemoryStorage instance with test Qdrant."""
    return MemoryStorage()


class TestStorageTruncation:
    """Test storage.py routing logic with smart truncation."""

    @pytest.mark.requires_qdrant
    def test_store_user_message_under_2000_tokens(self, storage):
        """User messages under 2000 tokens should NOT be truncated."""
        # Create message with ~500 tokens (well under limit)
        content = "This is a test message. " * 100  # ~500 tokens

        result = storage.store_memory(
            content=content,
            cwd="/test",
            memory_type=MemoryType.USER_MESSAGE,
            source_hook="manual",
            session_id="test-session",
            collection="discussions",
        )

        assert result["status"] == "stored"
        assert result["embedding_status"] == "complete"

        # Verify content was not truncated
        stored = storage.get_by_id(result["memory_id"], collection="discussions")
        assert stored["content"] == content
        assert "[...]" not in stored["content"]

    @pytest.mark.requires_qdrant
    def test_store_user_message_over_2000_tokens(self, storage):
        """User messages over 2000 tokens should be smart truncated."""
        # Create message with ~3000 tokens (over 2000 limit)
        content = "This is a sentence. " * 300  # ~3000 tokens

        result = storage.store_memory(
            content=content,
            cwd="/test",
            memory_type=MemoryType.USER_MESSAGE,
            source_hook="manual",
            session_id="test-session",
            collection="discussions",
        )

        assert result["status"] == "stored"

        # Verify content was truncated
        stored = storage.get_by_id(result["memory_id"], collection="discussions")
        assert len(stored["content"]) < len(content)
        assert "[...]" in stored["content"]

        # Verify truncation was smart (at sentence boundary)
        assert stored["content"].endswith(" [...]")
        # Should have truncated after a complete sentence
        content_without_marker = stored["content"].replace(" [...]", "")
        assert content_without_marker.endswith(".")

    @pytest.mark.requires_qdrant
    def test_store_agent_response_over_3000_tokens(self, storage):
        """Agent responses over 3000 tokens should be smart truncated."""
        # Create response with ~4000 tokens (over 3000 limit)
        content = "This is a detailed response. " * 400  # ~4000 tokens

        result = storage.store_memory(
            content=content,
            cwd="/test",
            memory_type=MemoryType.AGENT_RESPONSE,
            source_hook="manual",
            session_id="test-session",
            collection="discussions",
        )

        assert result["status"] == "stored"

        # Verify content was truncated
        stored = storage.get_by_id(result["memory_id"], collection="discussions")
        assert len(stored["content"]) < len(content)
        assert "[...]" in stored["content"]

        # Verify smart truncation
        assert stored["content"].endswith(" [...]")

        # Verify token count is within limit
        tokens = count_tokens(stored["content"])
        assert tokens <= 3100  # Allow small margin for marker

    @pytest.mark.requires_qdrant
    def test_store_guideline_23k_chars_no_data_loss(self, storage):
        """23K character guidelines should NOT be truncated to 600 chars.

        This was the original bug: guidelines were hard-truncated to 600 chars
        losing 97% of content. Now they should pass through unchanged
        (chunking is handled by hooks, not storage.py).
        """
        # Create 23K character guideline (similar to BP-001)
        guideline = "# Best Practice: RAG Chunking\n\n"
        guideline += "## Introduction\n" + ("Content paragraph. " * 100) + "\n\n"
        guideline += "## Strategy\n" + ("Implementation details. " * 100) + "\n\n"
        guideline += "## Examples\n" + ("Code example here. " * 100) + "\n\n"
        guideline += "## Conclusion\n" + ("Summary points. " * 100)

        original_length = len(guideline)
        assert (
            original_length > 23000
        ), f"Guideline should be >23K, got {original_length}"

        result = storage.store_memory(
            content=guideline,
            cwd="/test",
            memory_type=MemoryType.GUIDELINE,
            source_hook="manual",
            session_id="test-session",
            collection="conventions",
        )

        assert result["status"] == "stored"

        # CRITICAL: Verify NO data loss - content should be complete
        stored = storage.get_by_id(result["memory_id"], collection="conventions")
        assert len(stored["content"]) == original_length
        assert stored["content"] == guideline

        # Verify it was NOT truncated to 600 chars (the old bug)
        assert len(stored["content"]) > 600
        assert "[TRUNCATED]" not in stored["content"]  # Old marker
        assert "[...]" not in stored["content"]  # Should not be truncated at all

    @pytest.mark.requires_qdrant
    def test_store_session_summary_8k_tokens(self, storage):
        """Session summaries up to 8192 tokens should NOT be truncated.

        Old behavior: truncated to 1600 chars (400 tokens).
        New behavior: pass through unchanged (up to 8192 token limit).
        """
        # Create session summary with ~1000 tokens (well under 8192 limit)
        summary = "Session Summary\n\n"
        summary += "## Key Points\n" + ("Important point. " * 200) + "\n\n"
        summary += "## Decisions\n" + ("Decision made. " * 200) + "\n\n"
        summary += "## Next Steps\n" + ("Action item. " * 200)

        original_length = len(summary)
        original_tokens = count_tokens(summary)
        assert (
            original_tokens < 8192
        ), f"Should be under 8192 tokens, got {original_tokens}"

        result = storage.store_memory(
            content=summary,
            cwd="/test",
            memory_type=MemoryType.SESSION,
            source_hook="manual",
            session_id="test-session",
            collection="discussions",
        )

        assert result["status"] == "stored"

        # Verify NO truncation for content under 8192 tokens
        stored = storage.get_by_id(result["memory_id"], collection="discussions")
        assert len(stored["content"]) == original_length
        assert stored["content"] == summary

        # Verify it was NOT truncated to 1600 chars (the old bug)
        assert len(stored["content"]) > 1600
        assert "[TRUNCATED]" not in stored["content"]


class TestNoHardTruncationPatterns:
    """Verify hard truncation patterns are eliminated from codebase."""

    def test_no_hard_truncation_in_storage_py(self):
        """storage.py should have NO hard truncation patterns [:N]."""
        storage_file = "src/memory/storage.py"

        with open(storage_file) as f:
            content = f.read()

        # Check for hard truncation patterns
        assert "[:500]" not in content, "Found [:500] hard truncation in storage.py"
        assert "[:600]" not in content, "Found [:600] hard truncation in storage.py"
        assert "[:1200]" not in content, "Found [:1200] hard truncation in storage.py"
        assert "[:1600]" not in content, "Found [:1600] hard truncation in storage.py"
        assert "[: limit" not in content, "Found hard truncation with limit variable"

        # Verify the function was removed
        assert (
            "_enforce_content_limit" not in content
        ), "_enforce_content_limit() still exists!"
        assert "[TRUNCATED]" not in content, "Old [TRUNCATED] marker still present"

    def test_no_hard_truncation_in_truncation_py(self):
        """truncation.py should have NO hard truncation patterns (only smart truncation)."""
        truncation_file = "src/memory/chunking/truncation.py"

        with open(truncation_file) as f:
            content = f.read()

        # Should NOT have arbitrary character slicing
        # (except for internal algorithm work with sentence/word boundaries)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            # Skip comments and docstrings
            if line.strip().startswith("#") or '"""' in line:
                continue

            # Check for hard truncation patterns in actual code
            # Allow specific patterns like content[:last_space]
            # but flag arbitrary content[:500] patterns
            if (
                "content[:" in line
                and "content[:last" not in line
                and any(
                    f"[:{n}]" in line for n in [100, 200, 500, 600, 1000, 1200, 1600]
                )
            ):
                pytest.fail(
                    f"Line {i+1}: Found hard truncation pattern: {line.strip()}"
                )

    def test_grep_for_hard_truncation_patterns(self):
        """Use grep to find any remaining [:N] patterns in storage files."""
        # Grep for hard truncation patterns
        patterns_to_check = [
            r"\[:500\]",
            r"\[:600\]",
            r"\[:1200\]",
            r"\[:1600\]",
            r"\[: limit",
        ]

        files_to_check = [
            "src/memory/storage.py",
            "src/memory/chunking/truncation.py",
        ]

        for pattern in patterns_to_check:
            for file_path in files_to_check:
                result = subprocess.run(
                    ["grep", "-n", pattern, file_path],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    # Found pattern - fail test
                    pytest.fail(
                        f"Found hard truncation pattern '{pattern}' in {file_path}:\n"
                        f"{result.stdout}"
                    )


class TestBatchStorageTruncation:
    """Test batch storage operations with truncation."""

    @pytest.mark.requires_qdrant
    def test_store_memories_batch_with_truncation(self, storage):
        """Batch storage should apply same truncation rules."""
        memories = [
            {
                "content": "Short message.",
                "group_id": "test-project",
                "type": "user_message",
                "source_hook": "manual",
                "session_id": "test-session",
            },
            {
                "content": "This is a very long message. " * 300,  # ~3000 tokens
                "group_id": "test-project",
                "type": "user_message",
                "source_hook": "manual",
                "session_id": "test-session",
            },
        ]

        results = storage.store_memories_batch(
            memories, cwd="/test", collection="discussions"
        )

        assert len(results) == 2

        # First message should not be truncated
        stored1 = storage.get_by_id(results[0]["memory_id"], collection="discussions")
        assert stored1["content"] == "Short message."
        assert "[...]" not in stored1["content"]

        # Second message should be truncated
        stored2 = storage.get_by_id(results[1]["memory_id"], collection="discussions")
        assert len(stored2["content"]) < len(memories[1]["content"])
        assert "[...]" in stored2["content"]


class TestSmartTruncationMarkers:
    """Verify smart truncation uses correct markers."""

    @pytest.mark.requires_qdrant
    def test_truncated_content_uses_new_marker(self, storage):
        """Truncated content should use [...] not [TRUNCATED]."""
        # Create oversized user message
        content = "This is a test sentence. " * 200  # Over 2000 tokens

        result = storage.store_memory(
            content=content,
            cwd="/test",
            memory_type=MemoryType.USER_MESSAGE,
            source_hook="manual",
            session_id="test-session",
            collection="discussions",
        )

        stored = storage.get_by_id(result["memory_id"], collection="discussions")

        # Should use new [...] marker
        assert "[...]" in stored["content"]
        # Should NOT use old [TRUNCATED] marker
        assert "[TRUNCATED]" not in stored["content"]

    @pytest.mark.requires_qdrant
    def test_truncation_at_sentence_boundary(self, storage):
        """Truncated content should end at sentence boundary + marker."""
        # Create content with clear sentence boundaries
        content = "First sentence. Second sentence. Third sentence. " * 100

        result = storage.store_memory(
            content=content,
            cwd="/test",
            memory_type=MemoryType.USER_MESSAGE,
            source_hook="manual",
            session_id="test-session",
            collection="discussions",
        )

        stored = storage.get_by_id(result["memory_id"], collection="discussions")

        if "[...]" in stored["content"]:
            # Should end with " [...]"
            assert stored["content"].endswith(" [...]")
            # Content before marker should end with sentence boundary
            content_before_marker = stored["content"].replace(" [...]", "")
            assert content_before_marker.endswith((".", "!", "?"))
