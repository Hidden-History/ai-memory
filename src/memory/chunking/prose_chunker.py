"""Semantic prose chunking for documentation and markdown content.

Implements paragraph-aware chunking with sentence boundary detection
and configurable overlap for semantic continuity.

Reference: Chunking-Strategy-V1.md (Source of Truth)
Best Practices (2026):
- Preserve semantic units (paragraphs > sentences > words)
- 10-20% overlap for context continuity
- Max 500 chars for embedding efficiency
"""

import logging
import re
from dataclasses import dataclass

# Import shared models from base module (avoids circular imports)
from .base import CHARS_PER_TOKEN, ChunkMetadata, ChunkResult

logger = logging.getLogger("ai_memory.chunking.prose")

# Paragraph boundary - handles all newline variants (MED-1)
PARAGRAPH_PATTERN = re.compile(r"(\r\n|\r|\n)\s*(\r\n|\r|\n)")

# Common abbreviations that shouldn't trigger sentence splits (CRIT-1)
ABBREVIATIONS = {
    "Mr",
    "Mrs",
    "Ms",
    "Dr",
    "Prof",
    "Sr",
    "Jr",
    "vs",
    "etc",
    "Inc",
    "Ltd",
    "Corp",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
    "St",
    "Ave",
    "Blvd",
    "Rd",
    "Mt",
    "Ft",
    "U",
    "S",
    "A",  # Handle U.S.A.
}


def _is_abbreviation(text: str, pos: int) -> bool:
    """Check if period at position is part of an abbreviation.

    Args:
        text: Full text content
        pos: Position of period character

    Returns:
        True if period is part of abbreviation
    """
    if pos < 1:
        return False
    # Look backwards to find the word before the period
    start = pos - 1
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    word = text[start:pos]
    return word in ABBREVIATIONS or len(word) <= 2  # Single letters like "A."


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving abbreviations.

    Handles:
    - Standard sentence endings (.!?)
    - Abbreviations (Dr., Mr., U.S.A.)
    - Numbered lists (1. First item)
    - Decimal numbers (3.14)

    Args:
        text: Text to split into sentences

    Returns:
        List of sentences
    """
    sentences = []
    current = []
    i = 0

    while i < len(text):
        char = text[i]
        current.append(char)

        # Check for sentence end
        if char in ".!?":
            # Look ahead for whitespace + capital letter
            next_i = i + 1
            while next_i < len(text) and text[next_i] in " \t\n\r":
                next_i += 1

            # Check for capital letter and NOT an abbreviation
            if (
                next_i < len(text)
                and text[next_i].isupper()
                and not _is_abbreviation(text, i)
            ):
                # It's a sentence break
                sentences.append("".join(current).strip())
                current = []
                i = next_i - 1  # Will be incremented

        i += 1

    # Don't forget remaining text
    if current:
        sentences.append("".join(current).strip())

    return [s for s in sentences if s]


@dataclass
class ProseChunkerConfig:
    """Configuration for prose chunking.

    Attributes:
        max_chunk_size: Maximum characters per chunk (default: 500)
        min_chunk_size: Minimum characters per chunk (default: 100)
        overlap_ratio: Overlap as fraction of chunk size (default: 0.15)
        preserve_paragraphs: Keep paragraphs intact when possible (default: True)
    """

    max_chunk_size: int = 500
    min_chunk_size: int = 100
    overlap_ratio: float = 0.15
    preserve_paragraphs: bool = True


class ProseChunker:
    """Semantic prose chunker for documentation and markdown.

    Chunks text by preserving semantic boundaries:
    1. First tries to split on paragraph boundaries
    2. If paragraph too large, splits on sentence boundaries
    3. If sentence too large, splits on word boundaries with overlap

    Example:
        >>> chunker = ProseChunker()
        >>> chunks = chunker.chunk("Long document text...")
        >>> len(chunks) > 0
        True
        >>> all(len(c.content) <= 500 for c in chunks)
        True
    """

    def __init__(self, config: ProseChunkerConfig | None = None):
        """Initialize prose chunker.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or ProseChunkerConfig()
        self._overlap_size = int(self.config.max_chunk_size * self.config.overlap_ratio)

    def chunk(
        self,
        text: str,
        source: str | None = None,
        metadata: dict | None = None,
    ) -> list[ChunkResult]:
        """Chunk prose text into semantic units.

        Args:
            text: Text content to chunk
            source: Optional source identifier (e.g., file path)
            metadata: Optional metadata to attach to all chunks

        Returns:
            List of ChunkResult objects with content and metadata
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        # If text fits in one chunk, return as-is
        if len(text) <= self.config.max_chunk_size:
            return [self._create_chunk(text, 0, 1, source, metadata)]

        # Split into paragraphs first
        paragraphs = PARAGRAPH_PATTERN.split(text)
        # Filter out the separator groups captured by the regex
        paragraphs = [
            p.strip() for p in paragraphs if p.strip() and p not in ("\r\n", "\r", "\n")
        ]

        chunks = []
        chunk_index = 0

        for para in paragraphs:
            if len(para) <= self.config.max_chunk_size:
                # Paragraph fits in one chunk (total_chunks unknown, use -1)
                chunks.append(
                    self._create_chunk(para, chunk_index, -1, source, metadata)
                )
                chunk_index += 1
            else:
                # Paragraph too large - split by sentences
                sentence_chunks = self._chunk_by_sentences(
                    para, chunk_index, source, metadata
                )
                chunks.extend(sentence_chunks)
                chunk_index += len(sentence_chunks)

        # Add overlap between chunks (CRIT-2: with size validation)
        if len(chunks) > 1 and self._overlap_size > 0:
            chunks = self._add_overlap(chunks, len(chunks))

        # Update total_chunks in all metadata (now that we know final count)
        final_chunks = self._update_total_chunks(chunks)

        logger.info(
            "prose_chunking_complete",
            extra={
                "source": source,
                "input_length": len(text),
                "chunk_count": len(final_chunks),
                "avg_chunk_size": (
                    sum(len(c.content) for c in final_chunks) // len(final_chunks)
                    if final_chunks
                    else 0
                ),
            },
        )

        return final_chunks

    def _chunk_by_sentences(
        self,
        text: str,
        start_index: int,
        source: str | None,
        metadata: dict | None,
    ) -> list[ChunkResult]:
        """Split text by sentence boundaries using abbreviation-aware splitter.

        Args:
            text: Text to split
            start_index: Starting chunk index
            source: Source identifier
            metadata: Metadata for chunks

        Returns:
            List of chunks split by sentences
        """
        sentences = split_sentences(text)  # CRIT-1: Use abbreviation-aware splitter

        chunks = []
        current_chunk = ""
        chunk_index = start_index

        for sentence in sentences:
            # Check if adding sentence exceeds limit
            potential_chunk = (
                f"{current_chunk} {sentence}".strip() if current_chunk else sentence
            )

            if len(potential_chunk) <= self.config.max_chunk_size:
                current_chunk = potential_chunk
            else:
                # Save current chunk if it meets minimum size
                if len(current_chunk) >= self.config.min_chunk_size:
                    chunks.append(
                        self._create_chunk(
                            current_chunk, chunk_index, -1, source, metadata
                        )
                    )
                    chunk_index += 1
                    current_chunk = sentence
                elif current_chunk:
                    # Current chunk too small, force combine
                    current_chunk = potential_chunk
                else:
                    current_chunk = sentence

                # Handle sentence larger than max chunk size
                if len(current_chunk) > self.config.max_chunk_size:
                    word_chunks = self._chunk_by_words(
                        current_chunk, chunk_index, source, metadata
                    )
                    chunks.extend(word_chunks)
                    chunk_index += len(word_chunks)
                    current_chunk = ""

        # Don't forget the last chunk
        if current_chunk and len(current_chunk) >= self.config.min_chunk_size:
            chunks.append(
                self._create_chunk(current_chunk, chunk_index, -1, source, metadata)
            )
        elif current_chunk and chunks:
            # Append to last chunk if too small
            last_chunk = chunks[-1]
            combined = f"{last_chunk.content} {current_chunk}"
            chunks[-1] = self._create_chunk(
                combined, last_chunk.metadata.chunk_index, -1, source, metadata
            )

        return chunks

    def _chunk_by_words(
        self,
        text: str,
        start_index: int,
        source: str | None,
        metadata: dict | None,
    ) -> list[ChunkResult]:
        """Split text by word boundaries, handling very long words.

        HIGH-3: Splits individual words that exceed max_chunk_size.

        Args:
            text: Text to split
            start_index: Starting chunk index
            source: Source identifier
            metadata: Metadata for chunks

        Returns:
            List of chunks split by words
        """
        words = text.split()
        chunks = []
        current_chunk = ""
        chunk_index = start_index

        for word in words:
            # HIGH-3: Handle words longer than max_chunk_size (URLs, base64, hashes)
            if len(word) > self.config.max_chunk_size:
                # Save current chunk if any
                if current_chunk:
                    chunks.append(
                        self._create_chunk(
                            current_chunk, chunk_index, -1, source, metadata
                        )
                    )
                    chunk_index += 1
                    current_chunk = ""

                # Split long word into max_chunk_size pieces
                word_chunk_size = (
                    self.config.max_chunk_size - 10
                )  # Leave room for "..."
                for i in range(0, len(word), word_chunk_size):
                    word_piece = word[i : i + word_chunk_size]
                    if i > 0:
                        word_piece = "..." + word_piece
                    if i + word_chunk_size < len(word):
                        word_piece = word_piece + "..."
                    chunks.append(
                        self._create_chunk(
                            word_piece, chunk_index, -1, source, metadata
                        )
                    )
                    chunk_index += 1
                continue

            # Normal word handling
            potential_chunk = (
                f"{current_chunk} {word}".strip() if current_chunk else word
            )

            if len(potential_chunk) <= self.config.max_chunk_size:
                current_chunk = potential_chunk
            else:
                if current_chunk:
                    chunks.append(
                        self._create_chunk(
                            current_chunk, chunk_index, -1, source, metadata
                        )
                    )
                    chunk_index += 1
                current_chunk = word

        if current_chunk:
            chunks.append(
                self._create_chunk(current_chunk, chunk_index, -1, source, metadata)
            )

        return chunks

    def _add_overlap(
        self, chunks: list[ChunkResult], total_chunks: int
    ) -> list[ChunkResult]:
        """Add overlap between consecutive chunks.

        CRIT-2: Ensures final chunk size never exceeds max_chunk_size.

        Takes the last N characters from previous chunk and prepends
        to current chunk for context continuity.

        Args:
            chunks: List of chunks to add overlap to
            total_chunks: Total number of chunks (for metadata)

        Returns:
            Chunks with overlap added
        """
        if len(chunks) <= 1:
            return chunks

        overlapped = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_content = chunks[i - 1].content
            curr_content = chunks[i].content

            # CRIT-2: Calculate available space for overlap
            # Account for "... " prefix (4 chars)
            available_space = self.config.max_chunk_size - len(curr_content) - 4

            if available_space <= 0:
                # No room for overlap - use content as-is
                overlapped.append(chunks[i])
                continue

            # Get overlap from end of previous chunk (limited to available space)
            overlap_size = min(self._overlap_size, available_space)
            overlap_text = (
                prev_content[-overlap_size:] if len(prev_content) > overlap_size else ""
            )

            # Find word boundary for clean overlap
            if overlap_text and not overlap_text.startswith(" "):
                space_idx = overlap_text.find(" ")
                if space_idx > 0:
                    overlap_text = overlap_text[space_idx + 1 :]

            # Build new content with validated size
            if overlap_text:
                new_content = f"...{overlap_text.strip()} {curr_content}"
            else:
                new_content = curr_content

            # Final validation (should never fail now, but safety check)
            if len(new_content) > self.config.max_chunk_size:
                logger.warning(
                    "overlap_exceeded_max_size",
                    extra={
                        "new_size": len(new_content),
                        "max_size": self.config.max_chunk_size,
                        "falling_back": "no_overlap",
                    },
                )
                new_content = curr_content

            # Create new chunk with overlap
            new_chunk = ChunkResult(
                content=new_content,
                metadata=ChunkMetadata(
                    chunk_type="prose",
                    chunk_index=i,
                    total_chunks=total_chunks,
                    chunk_size_tokens=len(new_content) // CHARS_PER_TOKEN,
                    overlap_tokens=int(
                        (len(new_content) // CHARS_PER_TOKEN)
                        * self.config.overlap_ratio
                    ),
                    source_file=chunks[i].metadata.source_file,
                    start_line=None,
                    end_line=None,
                    section_header=chunks[i].metadata.section_header,
                ),
            )
            overlapped.append(new_chunk)

        return overlapped

    def _update_total_chunks(self, chunks: list[ChunkResult]) -> list[ChunkResult]:
        """Update total_chunks in all metadata now that we know final count.

        Args:
            chunks: Chunks with total_chunks=-1

        Returns:
            Chunks with correct total_chunks
        """
        total = len(chunks)
        updated_chunks = []

        for chunk in chunks:
            updated_metadata = ChunkMetadata(
                chunk_type=chunk.metadata.chunk_type,
                chunk_index=chunk.metadata.chunk_index,
                total_chunks=total,
                chunk_size_tokens=chunk.metadata.chunk_size_tokens,
                overlap_tokens=chunk.metadata.overlap_tokens,
                source_file=chunk.metadata.source_file,
                start_line=chunk.metadata.start_line,
                end_line=chunk.metadata.end_line,
                section_header=chunk.metadata.section_header,
            )
            updated_chunks.append(
                ChunkResult(content=chunk.content, metadata=updated_metadata)
            )

        return updated_chunks

    def _create_chunk(
        self,
        content: str,
        index: int,
        total_chunks: int,
        source: str | None,
        metadata: dict | None,
    ) -> ChunkResult:
        """Create a ChunkResult object with metadata.

        Args:
            content: Chunk content
            index: Chunk index in sequence
            total_chunks: Total number of chunks in document (-1 if unknown)
            source: Source identifier (file path)
            metadata: Additional metadata

        Returns:
            ChunkResult object with shared metadata model
        """
        # Calculate token counts
        chunk_size_tokens = len(content) // CHARS_PER_TOKEN
        overlap_tokens = int(chunk_size_tokens * self.config.overlap_ratio)

        chunk_metadata = ChunkMetadata(
            chunk_type="prose",
            chunk_index=index,
            total_chunks=total_chunks,
            chunk_size_tokens=chunk_size_tokens,
            overlap_tokens=overlap_tokens,
            source_file=source,  # Note: field is source_file, not source
            start_line=None,
            end_line=None,
            section_header=metadata.get("title") if metadata else None,
        )

        return ChunkResult(content=content, metadata=chunk_metadata)
