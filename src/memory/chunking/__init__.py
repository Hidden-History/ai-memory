"""Intelligent chunking orchestrator for memory content.

TECH-DEBT-051: v2.1 MVP implementation with AST-based code chunking (TECH-DEBT-052).
Routes content by type to appropriate chunking strategy.
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger("ai_memory.chunking")

# FIX-9: Shared constant for token estimation (used across all chunkers)
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
    source_file: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    section_header: Optional[str] = None


@dataclass(frozen=True)
class ChunkResult:
    """Result of chunking operation."""

    content: str  # Chunk content
    metadata: ChunkMetadata  # Chunk metadata


class IntelligentChunker:
    """Main chunking orchestrator - routes by content type.

    Routes content to appropriate chunking strategy:
    - CODE → ASTChunker (Tree-sitter) - IMPLEMENTED (TECH-DEBT-052)
    - PROSE → SemanticChunker - FUTURE (TECH-DEBT-053)
    - CONVERSATION → Whole message (no chunking)
    - CONFIG → Whole file (no chunking)
    """

    # File extension to content type mapping
    CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c", ".h"}
    PROSE_EXTENSIONS = {".md", ".txt", ".rst"}
    CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}

    def __init__(self, max_chunk_tokens: int = 512, overlap_pct: float = 0.15):
        """Initialize chunker with configuration.

        Args:
            max_chunk_tokens: Maximum tokens per chunk (must be > 0, default: 512)
            overlap_pct: Overlap percentage between chunks (must be 0.0-1.0, default: 0.15)

        Raises:
            ValueError: If parameters are out of valid range
        """
        if max_chunk_tokens <= 0:
            raise ValueError(f"max_chunk_tokens must be > 0, got {max_chunk_tokens}")
        if not (0.0 <= overlap_pct <= 1.0):
            raise ValueError(f"overlap_pct must be 0.0-1.0, got {overlap_pct}")

        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_pct = overlap_pct

        # Initialize AST chunker if available
        self._ast_chunker = None
        try:
            from .ast_chunker import ASTChunker
            self._ast_chunker = ASTChunker()
            logger.info(
                "chunker_initialized",
                extra={
                    "max_chunk_tokens": max_chunk_tokens,
                    "overlap_pct": overlap_pct,
                    "ast_chunker": "available",
                },
            )
        except ImportError as e:
            logger.warning(
                "ast_chunker_unavailable",
                extra={"reason": str(e)},
            )
            logger.info(
                "chunker_initialized",
                extra={
                    "max_chunk_tokens": max_chunk_tokens,
                    "overlap_pct": overlap_pct,
                    "ast_chunker": "unavailable",
                },
            )

    def detect_content_type(self, file_path: str, content: str) -> ContentType:
        """Detect content type from file extension and content.

        Args:
            file_path: Path to file (used for extension detection)
            content: File content (unused in v2.1 MVP)

        Returns:
            ContentType enum value
        """
        # Handle None/empty file_path
        if not file_path:
            logger.debug(
                "detect_no_file_path",
                extra={"content_length": len(content) if content else 0},
            )
            return ContentType.UNKNOWN

        # Use pathlib for robust extension extraction
        path = Path(file_path)
        ext = path.suffix.lower()  # Returns "" if no extension, ".py" if has extension

        if not ext:
            # Handle extensionless files like Makefile, Dockerfile
            filename = path.name.lower()
            if filename in ("makefile", "dockerfile", "jenkinsfile", "vagrantfile"):
                return ContentType.CONFIG
            logger.debug(
                "unknown_content_type",
                extra={"file_path": file_path, "extension": ext, "filename": filename},
            )
            return ContentType.UNKNOWN

        # Route by extension
        if ext in self.CODE_EXTENSIONS:
            return ContentType.CODE
        elif ext in self.PROSE_EXTENSIONS:
            return ContentType.PROSE
        elif ext in self.CONFIG_EXTENSIONS:
            return ContentType.CONFIG
        else:
            logger.debug(
                "unknown_content_type",
                extra={"file_path": file_path, "extension": ext, "filename": path.name},
            )
            return ContentType.UNKNOWN

    def chunk(self, content: str, file_path: str) -> List[ChunkResult]:
        """Chunk content using appropriate strategy.

        Routes to specialized chunkers based on content type:
        - CODE: AST-based chunking (if available)
        - Others: Whole content (future: semantic, late chunking)

        Args:
            content: Content to chunk
            file_path: Source file path (for content type detection)

        Returns:
            List of ChunkResult objects
        """
        # Validate inputs
        if content is None:
            logger.warning("chunk_none_content", extra={"file_path": file_path})
            return []

        if not content.strip():
            logger.debug("chunk_empty_content", extra={"file_path": file_path})
            return []

        content_type = self.detect_content_type(file_path, content)
        token_count = self.estimate_tokens(content)

        logger.info(
            "chunking_content",
            extra={
                "file_path": file_path,
                "content_type": content_type.value,
                "token_count": token_count,
            },
        )

        # Route to appropriate chunker
        if content_type == ContentType.CODE and self._ast_chunker:
            # Use AST-based chunking for code
            logger.debug("routing_to_ast_chunker", extra={"file_path": file_path})
            chunks = self._ast_chunker.chunk(content, file_path)

            # If AST chunking returned results, use them
            if chunks:
                return chunks

            # Otherwise fall through to whole-content fallback
            # FIX-8: Enhanced fallback logging with reason
            logger.info(
                "ast_chunker_fallback",
                extra={
                    "file_path": file_path,
                    "reason": "no_functions_or_classes_found",
                    "fallback_strategy": "whole_content",
                    "content_length": len(content)
                },
            )
        elif content_type == ContentType.CODE and not self._ast_chunker:
            # FIX-8: Log when AST chunker unavailable for code files
            logger.info(
                "ast_chunker_unavailable",
                extra={
                    "file_path": file_path,
                    "reason": "tree_sitter_not_installed",
                    "fallback_strategy": "whole_content"
                },
            )

        # Fallback: Return whole content as single chunk
        metadata = ChunkMetadata(
            chunk_type="whole",
            chunk_index=0,
            total_chunks=1,
            chunk_size_tokens=token_count,
            overlap_tokens=0,
            source_file=file_path,
        )

        return [ChunkResult(content=content, metadata=metadata)]

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using CHARS_PER_TOKEN constant.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // CHARS_PER_TOKEN


# Import ProseChunker (TECH-DEBT-053)
from .prose_chunker import ProseChunker, ProseChunkerConfig

# Conditional export of ASTChunker
try:
    from .ast_chunker import ASTChunker
    __all__ = [
        "IntelligentChunker",
        "ASTChunker",
        "ChunkResult",
        "ChunkMetadata",
        "ContentType",
        "CHARS_PER_TOKEN",
        "ProseChunker",
        "ProseChunkerConfig",
    ]
except ImportError:
    # Tree-sitter not available
    __all__ = [
        "IntelligentChunker",
        "ChunkResult",
        "ChunkMetadata",
        "ContentType",
        "CHARS_PER_TOKEN",
        "ProseChunker",
        "ProseChunkerConfig",
    ]
