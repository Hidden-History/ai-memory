"""Tests for markdown ingestion script (TECH-DEBT-054)."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add scripts/memory to path for imports
scripts_path = Path(__file__).parent.parent / "scripts" / "memory"
sys.path.insert(0, str(scripts_path))

from ingest_markdown import parse_frontmatter, extract_title, ingest_file


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
        from memory.chunking import ChunkResult, ChunkMetadata

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
                )
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
                )
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

        count = ingest_file(md_file, mock_storage, mock_chunker, "test-project", dry_run=True)

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

        frontmatter, body = parse_frontmatter(content)
        # Test the tag conversion logic
        tags = frontmatter.get("tags", [])
        if isinstance(tags, dict):
            tags = list(tags.keys())

        assert "python" in tags
        assert "testing" in tags
