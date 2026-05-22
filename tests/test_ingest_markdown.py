"""Tests for markdown ingestion script (TECH-DEBT-054)."""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add scripts/memory to path for imports
scripts_path = Path(__file__).parent.parent / "scripts" / "memory"
sys.path.insert(0, str(scripts_path))

from ingest_markdown import extract_title, ingest_file, main, parse_frontmatter


class TestParseFrontmatter:
    """Test frontmatter parsing."""

    def test_valid_frontmatter(self):
        """Parses valid YAML frontmatter."""
        content = """---
title: Test Doc
tags: python, testing
type: guideline
---

# Content here"""

        frontmatter, body = parse_frontmatter(content)

        assert frontmatter["title"] == "Test Doc"
        assert frontmatter["tags"] == "python, testing"
        assert frontmatter["type"] == "guideline"
        assert "# Content here" in body

    def test_no_frontmatter(self):
        """Returns empty dict when no frontmatter."""
        content = "# Just a heading\n\nSome content."

        frontmatter, body = parse_frontmatter(content)

        assert frontmatter == {}
        assert body == content

    def test_invalid_yaml_frontmatter(self):
        """Handles invalid YAML gracefully."""
        content = """---
invalid: yaml: here:
---

Content"""

        frontmatter, body = parse_frontmatter(content)

        assert frontmatter == {}
        assert "Content" in body


class TestExtractTitle:
    """Test title extraction."""

    def test_title_from_frontmatter(self):
        """Prefers frontmatter title."""
        frontmatter = {"title": "Frontmatter Title"}
        content = "# Heading Title\n\nContent"

        title = extract_title(content, frontmatter)

        assert title == "Frontmatter Title"

    def test_title_from_h1_heading(self):
        """Falls back to first H1 heading."""
        frontmatter = {}
        content = "# My Document\n\nContent here"

        title = extract_title(content, frontmatter)

        assert title == "My Document"

    def test_untitled_when_no_title(self):
        """Returns 'Untitled' when no title found."""
        frontmatter = {}
        content = "Just some content without heading."

        title = extract_title(content, frontmatter)

        assert title == "Untitled"


class TestIngestFile:
    """Test file ingestion."""

    @pytest.fixture
    def mock_storage(self):
        """Mock storage that tracks calls."""
        storage = Mock()
        storage.store.return_value = "test-memory-id"
        return storage

    @pytest.fixture
    def mock_chunker(self):
        """Mock chunker returning predictable chunks."""
        from memory.chunking import ChunkMetadata, ChunkResult

        chunker = Mock()
        chunker.chunk.return_value = [
            ChunkResult(
                content="Chunk 1",
                metadata=ChunkMetadata(
                    chunk_type="prose",
                    chunk_index=0,
                    total_chunks=2,
                    chunk_size_tokens=10,
                    overlap_tokens=2,
                    source_file=None,
                ),
            ),
            ChunkResult(
                content="Chunk 2",
                metadata=ChunkMetadata(
                    chunk_type="prose",
                    chunk_index=1,
                    total_chunks=2,
                    chunk_size_tokens=10,
                    overlap_tokens=2,
                    source_file=None,
                ),
            ),
        ]
        return chunker

    def test_ingest_stores_chunks(self, mock_storage, mock_chunker, tmp_path):
        """Ingests file and stores chunks."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent here.")

        count = ingest_file(md_file, mock_storage, mock_chunker, "test-project")

        assert count == 2
        assert mock_storage.store.call_count == 2

    def test_dry_run_does_not_store(self, mock_storage, mock_chunker, tmp_path):
        """Dry run doesn't call storage."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent here.")

        count = ingest_file(
            md_file, mock_storage, mock_chunker, "test-project", dry_run=True
        )

        assert count == 2
        assert mock_storage.store.call_count == 0

    def test_handles_missing_file(self, mock_storage, mock_chunker, tmp_path):
        """Returns 0 for missing file."""
        missing = tmp_path / "missing.md"

        count = ingest_file(missing, mock_storage, mock_chunker, "test-project")

        assert count == 0

    def test_empty_file_returns_zero(self, mock_storage, mock_chunker, tmp_path):
        """Empty file returns 0 chunks."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        mock_chunker.chunk.return_value = []
        count = ingest_file(empty_file, mock_storage, mock_chunker, "test-project")

        assert count == 0
        mock_storage.store.assert_not_called()

    def test_binary_file_skipped(self, mock_storage, mock_chunker, tmp_path):
        """Binary file is skipped gracefully."""
        binary_file = tmp_path / "binary.md"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe")

        count = ingest_file(binary_file, mock_storage, mock_chunker, "test-project")

        assert count == 0
        mock_storage.store.assert_not_called()

    def test_dict_tags_converted_to_list(self):
        """Tags as dict are converted to list of keys."""
        content = """---
title: Test
tags:
  python: true
  testing: false
---
Content"""

        frontmatter, _body = parse_frontmatter(content)
        # Test the tag conversion logic
        tags = frontmatter.get("tags", [])
        if isinstance(tags, dict):
            tags = list(tags.keys())

        assert "python" in tags
        assert "testing" in tags


class TestMainDryRun:
    """Tests for main() --dry-run entry point."""

    def test_dry_run_notice_does_not_crash(self, tmp_path, monkeypatch, caplog):
        """--dry-run must not raise: 'notice' extra key avoids LogRecord collision.

        Python's logging.makeRecord explicitly forbids 'message' as an extra
        key — it raises KeyError("Attempt to overwrite 'message' in LogRecord").
        The dry_run_notice log event previously used extra={"message": ...},
        causing every --dry-run invocation to crash. The fix renames the key
        to 'notice'. This test confirms the code path completes without error.

        caplog.set_level forces INFO on the ai_memory.ingest logger so that
        makeRecord is actually called and extra keys are validated. Without
        this, pytest's pre-existing root handler makes basicConfig a no-op,
        leaving the logger at WARNING and short-circuiting info() calls
        before makeRecord runs — making the test vacuous.
        """
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent.")

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "ingest_markdown",
                "--file",
                str(md_file),
                "--group-id",
                "test-project",
                "--dry-run",
            ],
        )

        mock_chunk = MagicMock()
        mock_chunk.content = "chunk content"
        mock_chunker_instance = MagicMock()
        mock_chunker_instance.chunk.return_value = [mock_chunk]

        # Force INFO so the dry_run_notice log call reaches makeRecord and
        # extra keys are validated — the actual regression guard.
        caplog.set_level(logging.INFO, logger="ai_memory.ingest")

        with (
            patch("ingest_markdown.get_config", return_value=MagicMock()),
            patch("ingest_markdown.MemoryStorage", return_value=MagicMock()),
            patch("ingest_markdown.ProseChunker", return_value=mock_chunker_instance),
        ):
            main()  # must not raise KeyError
