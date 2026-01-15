"""Data models for memory payloads in Qdrant.

Defines the payload schema for memories stored in Qdrant collections.
Implements Story 1.3 AC 1.3.2.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

__all__ = ["MemoryType", "EmbeddingStatus", "MemoryPayload"]


class MemoryType(str, Enum):
    """Types of memories that can be stored.

    Note: Uses (str, Enum) pattern for Python 3.10 compatibility (AMD ROCm images).
    StrEnum requires Python 3.11+. When formatting, use .value explicitly:
        f"{MemoryType.IMPLEMENTATION.value}"  # "implementation"
    """

    IMPLEMENTATION = "implementation"
    SESSION_SUMMARY = "session_summary"
    DECISION = "decision"
    PATTERN = "pattern"


class EmbeddingStatus(str, Enum):
    """Status of embedding generation for a memory."""

    COMPLETE = "complete"
    PENDING = "pending"
    FAILED = "failed"


@dataclass
class MemoryPayload:
    """Schema for memory payloads stored in Qdrant.

    Attributes:
        content: The actual memory content (10-100,000 chars)
        content_hash: SHA256 hash for deduplication
        group_id: Project identifier for multi-tenancy
        type: Type of memory (implementation, session_summary, etc.)
        source_hook: Which Claude Code hook captured this (PostToolUse, Stop, SessionStart)
        session_id: Claude session identifier
        timestamp: ISO 8601 timestamp of capture
        domain: Optional domain classification (default: "general")
        importance: Importance level: low, normal, high (default: "normal")
        embedding_status: Status of embedding generation
        embedding_model: Model used for embeddings (default: "nomic-embed-code")
        relationships: List of related memory IDs
        tags: List of tags for categorization
    """

    # Required fields
    content: str
    content_hash: str  # SHA256 for deduplication
    group_id: str  # Project identifier
    type: MemoryType

    # Provenance (FR47)
    source_hook: str  # PostToolUse, Stop, SessionStart, seed_script
    session_id: str
    timestamp: str  # ISO 8601 format

    # Optional enrichment
    domain: str = "general"
    importance: str = "normal"  # low, normal, high
    embedding_status: EmbeddingStatus = EmbeddingStatus.COMPLETE
    embedding_model: str = "nomic-embed-code"

    # Relationships and tags
    relationships: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for Qdrant storage.

        Converts enum values to strings and returns a dict suitable for
        Qdrant payload storage.

        Returns:
            Dictionary with all fields in snake_case
        """
        return {
            "content": self.content,
            "content_hash": self.content_hash,
            "group_id": self.group_id,
            "type": (
                self.type.value
                if isinstance(self.type, MemoryType)
                else self.type
            ),
            "source_hook": self.source_hook,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "domain": self.domain,
            "importance": self.importance,
            "embedding_status": (
                self.embedding_status.value
                if isinstance(self.embedding_status, EmbeddingStatus)
                else self.embedding_status
            ),
            "embedding_model": self.embedding_model,
            "relationships": self.relationships,
            "tags": self.tags,
        }
