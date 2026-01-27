"""Tests for ProseChunker (TECH-DEBT-053)."""

import pytest
from memory.chunking import ProseChunker, ProseChunkerConfig


class TestProseChunker:
    """Test semantic prose chunking."""

    @pytest.fixture
    def chunker(self):
        """Default prose chunker."""
        return ProseChunker()

    @pytest.fixture
    def small_chunk_config(self):
        """Config with small chunks for testing."""
        return ProseChunkerConfig(max_chunk_size=100, min_chunk_size=20)

    def test_empty_text_returns_empty_list(self, chunker):
        """Empty or whitespace text returns empty list."""
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []
        assert chunker.chunk("\n\n") == []

    def test_short_text_returns_single_chunk(self, chunker):
        """Text under max size returns single chunk."""
        text = "This is a short paragraph."
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_paragraph_splitting(self):
        """Text with paragraphs splits on paragraph boundaries."""
        # Use smaller chunk size to force splitting
        config = ProseChunkerConfig(max_chunk_size=50)
        chunker = ProseChunker(config)

        text = """First paragraph here with some extra text.

Second paragraph here with some extra text.

Third paragraph here with some extra text."""

        chunks = chunker.chunk(text)

        assert len(chunks) == 3
        assert "First paragraph" in chunks[0].content
        assert "Second paragraph" in chunks[1].content
        assert "Third paragraph" in chunks[2].content

    def test_sentence_splitting_for_large_paragraphs(self):
        """Large paragraphs split on sentence boundaries."""
        config = ProseChunkerConfig(max_chunk_size=60)
        chunker = ProseChunker(config)

        text = "First sentence here with some extra words. Second sentence here with extra words. Third sentence here with extra words. Fourth sentence here."
        chunks = chunker.chunk(text)

        assert len(chunks) >= 2
        assert all(len(c.content) <= 150 for c in chunks)  # Allow some overflow for overlap

    def test_overlap_between_chunks(self):
        """Consecutive chunks have overlap for context."""
        config = ProseChunkerConfig(max_chunk_size=100, overlap_ratio=0.2)
        chunker = ProseChunker(config)

        # Create text with paragraph boundaries to trigger chunking
        text = "A " * 40 + "\n\n" + "B " * 40 + "\n\n" + "C " * 40
        chunks = chunker.chunk(text)

        assert len(chunks) >= 2
        # Second chunk should start with "..." indicating overlap
        if len(chunks) > 1:
            # Overlap is only added if there's room (CRIT-2 fix)
            # Check that either overlap is present or chunks are at max size
            second_has_overlap = chunks[1].content.startswith("...")
            second_at_max = len(chunks[1].content) >= 95  # Close to max
            assert second_has_overlap or second_at_max

    def test_chunk_metadata_includes_source(self, chunker):
        """Chunks include source in metadata."""
        chunks = chunker.chunk("Test content", source="docs/readme.md")

        # Note: shared model uses source_file, not source
        assert chunks[0].metadata.source_file == "docs/readme.md"
        assert chunks[0].metadata.chunk_type == "prose"

    def test_chunk_metadata_includes_index(self):
        """Chunks have sequential indices."""
        config = ProseChunkerConfig(max_chunk_size=50)
        chunker = ProseChunker(config)

        text = "Word " * 100
        chunks = chunker.chunk(text)

        indices = [c.metadata.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_custom_metadata_passed_through(self, chunker):
        """Custom metadata used for section_header."""
        metadata = {"title": "Test Document"}
        chunks = chunker.chunk("Test content", metadata=metadata)

        # With shared model, metadata is used for section_header
        assert chunks[0].metadata.section_header == "Test Document"

    def test_word_splitting_for_very_long_sentences(self):
        """Very long sentences without punctuation split on words."""
        config = ProseChunkerConfig(max_chunk_size=50)
        chunker = ProseChunker(config)

        # No punctuation - forces word-level splitting
        text = "word " * 50
        chunks = chunker.chunk(text)

        assert len(chunks) >= 2
        assert all(len(c.content) <= 100 for c in chunks)  # Allow overlap

    def test_handles_markdown_formatting(self, chunker):
        """Handles markdown text without breaking."""
        text = """# Header

This is **bold** and *italic* text.

- List item 1
- List item 2

```python
code block
```"""

        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        # Should not error on markdown syntax

    def test_abbreviations_not_split(self, chunker):
        """Abbreviations like Dr., Mr., U.S.A. don't cause sentence splits."""
        text = "Dr. Smith visited the U.S.A. yesterday. Mr. Jones agreed."
        chunks = chunker.chunk(text)

        # Should be 1-2 chunks, not split after each abbreviation
        assert len(chunks) <= 2
        # "Dr." should not be isolated
        assert not any(c.content.strip() == "Dr." for c in chunks)
        # First chunk should contain "Dr. Smith"
        assert "Dr. Smith" in chunks[0].content

    def test_numbered_lists_not_split(self, chunker):
        """Numbered lists like '1. First' don't split after number."""
        text = "Steps:\n1. First step\n2. Second step\n3. Third step"
        chunks = chunker.chunk(text)

        # "1." should not be isolated
        assert not any(c.content.strip() == "1." for c in chunks)

    def test_overlap_never_exceeds_max_size(self):
        """Overlap + content never exceeds max_chunk_size."""
        config = ProseChunkerConfig(max_chunk_size=100, overlap_ratio=0.5)
        chunker = ProseChunker(config)

        # Create text that forces multiple chunks with large overlap
        text = "Word " * 100  # 500 chars, forces many small chunks
        chunks = chunker.chunk(text)

        for chunk in chunks:
            assert len(chunk.content) <= 100, f"Chunk exceeded max: {len(chunk.content)}"

    def test_very_long_word_split(self):
        """Words longer than max_chunk_size are split."""
        config = ProseChunkerConfig(max_chunk_size=50)
        chunker = ProseChunker(config)

        # 100-char "word" (like a URL or hash)
        long_word = "a" * 100
        text = f"Before {long_word} after"
        chunks = chunker.chunk(text)

        # No chunk should exceed max size (allowing some buffer for "...")
        for chunk in chunks:
            assert len(chunk.content) <= 60, f"Chunk exceeded max: {len(chunk.content)}"

    def test_unicode_and_emoji(self, chunker):
        """Unicode and emoji content handled correctly."""
        text = "Hello 👋 World 🌍. This is a test. 日本語テキスト。"
        chunks = chunker.chunk(text)

        assert len(chunks) >= 1
        # Emoji should be preserved
        combined = "".join(c.content for c in chunks)
        assert "👋" in combined
        assert "🌍" in combined
