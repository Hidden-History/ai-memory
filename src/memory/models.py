"""Data models for memory payloads in Qdrant.

Defines the payload schema for memories stored in Qdrant collections.
Implements Story 1.3 AC 1.3.2 with BMAD agent enrichment.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

__all__ = [
    "MemoryType",
    "EmbeddingStatus",
    "ImportanceLevel",
    "MemoryPayload",
    "VALID_AGENTS",
]


# Valid BMAD agents
VALID_AGENTS = [
    "architect",
    "analyst",
    "pm",
    "dev",
    "tea",
    "tech-writer",
    "ux-designer",
    "quick-flow-solo-dev",
    "sm",
]


class MemoryType(str, Enum):
    """Types of memories that can be stored.

    Note: Uses (str, Enum) pattern for Python 3.10 compatibility (AMD ROCm images).
    StrEnum requires Python 3.11+. When formatting, use .value explicitly:
        f"{MemoryType.IMPLEMENTATION.value}"  # "implementation"

    Collections:
        implementations: IMPLEMENTATION, ARCHITECTURE_DECISION, STORY_OUTCOME,
                        ERROR_PATTERN, DATABASE_SCHEMA, CONFIG_PATTERN,
                        INTEGRATION_EXAMPLE
        best_practices: BEST_PRACTICE
        agent-memory: SESSION_SUMMARY, CHAT_MEMORY, AGENT_DECISION
    """

    # implementations collection
    IMPLEMENTATION = "implementation"
    ARCHITECTURE_DECISION = "architecture_decision"
    STORY_OUTCOME = "story_outcome"
    ERROR_PATTERN = "error_pattern"
    DATABASE_SCHEMA = "database_schema"
    CONFIG_PATTERN = "config_pattern"
    INTEGRATION_EXAMPLE = "integration_example"

    # best_practices collection
    BEST_PRACTICE = "best_practice"

    # agent-memory collection
    SESSION_SUMMARY = "session_summary"
    CHAT_MEMORY = "chat_memory"
    AGENT_DECISION = "agent_decision"

    # Legacy compatibility
    DECISION = "decision"
    PATTERN = "pattern"


class ImportanceLevel(str, Enum):
    """Importance levels for memories."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    # Legacy compatibility
    NORMAL = "normal"


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
        importance: Importance level: critical, high, medium, low (default: "medium")
        embedding_status: Status of embedding generation
        embedding_model: Model used for embeddings (default: "nomic-embed-code")
        relationships: List of related memory IDs
        tags: List of tags for categorization
        agent: BMAD agent that created/captured this (dev, architect, pm, etc.)
        component: System component this relates to (auth, database, api, etc.)
        story_id: Story identifier for traceability (AUTH-12, DB-05, etc.)
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
    created_at: Optional[str] = None  # ISO 8601 format, auto-generated if not provided (TECH-DEBT-012)

    # Optional enrichment
    domain: str = "general"
    importance: str = "medium"  # critical, high, medium, low
    embedding_status: EmbeddingStatus = EmbeddingStatus.COMPLETE
    embedding_model: str = "nomic-embed-code"

    # Relationships and tags
    relationships: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # BMAD agent enrichment (DEC-018)
    agent: Optional[str] = None  # dev, architect, pm, tea, etc.
    component: Optional[str] = None  # auth, database, api, etc.
    story_id: Optional[str] = None  # AUTH-12, DB-05, etc.

    def to_dict(self) -> dict:
        """Convert to dictionary for Qdrant storage.

        Converts enum values to strings and returns a dict suitable for
        Qdrant payload storage. Optional fields (agent, component, story_id)
        are only included if set to avoid cluttering the payload.

        Returns:
            Dictionary with all fields in snake_case
        """
        result = {
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

        # Include BMAD enrichment fields only if set (DEC-018)
        if self.agent is not None:
            result["agent"] = self.agent
        if self.component is not None:
            result["component"] = self.component
        if self.story_id is not None:
            result["story_id"] = self.story_id

        # Include created_at if set (TECH-DEBT-012 Round 3)
        if self.created_at is not None:
            result["created_at"] = self.created_at

        return result
