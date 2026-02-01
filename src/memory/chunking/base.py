"""Base types and constants for chunking module.

This module contains shared types, constants, and dataclasses used across
all chunker implementations to avoid circular imports.
"""

from dataclasses import dataclass
from enum import Enum

# Shared constant for token estimation (used across all chunkers)
CHARS_PER_TOKEN = 4  # Approximate: 4 characters ≈ 1 token


class ContentType(str, Enum):
    """Content type for chunking strategy selection."""

    CODE = "code"  # Python, JS, TS, etc.
    PROSE = "prose"  # Markdown, text
    CONVERSATION = "conversation"  # User/agent messages
    CONFIG = "config"  # JSON, YAML, TOML
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChunkMetadata:
    """Metadata for a single chunk."""

    chunk_type: str  # ast_code, semantic, whole, late
    chunk_index: int  # Position in document (0-indexed)
    total_chunks: int  # Total chunks from source
    chunk_size_tokens: int  # Approximate token count
    overlap_tokens: int  # Overlap with previous chunk
    source_file: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    section_header: str | None = None


@dataclass(frozen=True)
class ChunkResult:
    """Result of chunking operation."""

    content: str  # Chunk content
    metadata: ChunkMetadata  # Chunk metadata
