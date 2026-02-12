"""Data models for memory payloads in Qdrant.

Defines the payload schema for memories stored in Qdrant collections.
Implements Story 1.3 AC 1.3.2 with BMAD agent enrichment.
"""

from dataclasses import dataclass, field
from enum import Enum

# Import VALID_AGENTS from config to avoid duplication (CR-4.27)
from .config import VALID_AGENTS

__all__ = [
    "VALID_AGENTS",
    "EmbeddingStatus",
    "ImportanceLevel",
    "MemoryPayload",
    "MemoryType",
]


class MemoryType(str, Enum):
    """Types of memories that can be stored (Memory System v2.0).

    Total: 17 types (4 code-patterns + 5 conventions + 6 discussions + 2 jira-data)
    Spec: oversight/specs/MEMORY-SYSTEM-REDESIGN-v2.md Section 5

    Note: Uses (str, Enum) pattern for Python 3.10 compatibility (AMD ROCm images).
    StrEnum requires Python 3.11+. When formatting, use .value explicitly:
        f"{MemoryType.IMPLEMENTATION.value}"  # "implementation"

    Collections (v2.0):
        code-patterns: IMPLEMENTATION, ERROR_FIX, REFACTOR, FILE_PATTERN
        conventions: RULE, GUIDELINE, PORT, NAMING, STRUCTURE
        discussions: DECISION, SESSION, BLOCKER, PREFERENCE, USER_MESSAGE, AGENT_RESPONSE
        jira-data: JIRA_ISSUE, JIRA_COMMENT
    """

    # === code-patterns collection (HOW things are built) ===
    IMPLEMENTATION = "implementation"  # How a feature/component was built
    ERROR_FIX = "error_fix"  # Error encountered + what fixed it
    REFACTOR = "refactor"  # Code refactoring patterns applied
    FILE_PATTERN = "file_pattern"  # Patterns specific to a file or module

    # === conventions collection (WHAT rules to follow) ===
    RULE = "rule"  # Hard rules that MUST be followed
    GUIDELINE = "guideline"  # Soft guidelines that SHOULD be followed
    PORT = "port"  # Port configuration rules
    NAMING = "naming"  # Naming conventions for files, functions, etc.
    STRUCTURE = "structure"  # File and folder structure conventions

    # === discussions collection (WHY things were decided) ===
    DECISION = "decision"  # Architectural/design decisions (DEC-xxx)
    SESSION = "session"  # Session summaries
    BLOCKER = "blocker"  # Blockers and their resolutions (BLK-xxx)
    PREFERENCE = "preference"  # User preferences and working style
    USER_MESSAGE = "user_message"  # User messages from conversation
    AGENT_RESPONSE = "agent_response"  # Agent responses from conversation

    # === jira-data collection (External work items from Jira Cloud) ===
    JIRA_ISSUE = "jira_issue"  # Jira issue with metadata
    JIRA_COMMENT = "jira_comment"  # Jira issue comment


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
        type: Type of memory (implementation, session, decision, etc.)
        source_hook: Which Claude Code hook captured this (PostToolUse, Stop, SessionStart)
        session_id: Claude session identifier
        timestamp: ISO 8601 timestamp of capture
        domain: Optional domain classification (default: "general")
        importance: Importance level: critical, high, medium, low (default: "medium")
        embedding_status: Status of embedding generation
        embedding_model: Model used for embeddings (default: "jina-embeddings-v2-base-en")
        relationships: List of related memory IDs
        tags: List of tags for categorization
        agent: BMAD agent that created/captured this (dev, architect, pm, etc.)
        component: System component this relates to (auth, database, api, etc.)
        story_id: Story identifier for traceability (AUTH-12, DB-05, etc.)
        source: URL or reference for researched content (BUG-006)
        source_date: ISO 8601 date of source publication (BUG-006)
        auto_seeded: True if auto-captured by research agent, False if template-seeded (BUG-006)
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
    created_at: str | None = (
        None  # ISO 8601 format, auto-generated if not provided (TECH-DEBT-012)
    )

    # Optional enrichment
    domain: str = "general"
    importance: str = "medium"  # critical, high, medium, low
    embedding_status: EmbeddingStatus = EmbeddingStatus.COMPLETE
    embedding_model: str = "jina-embeddings-v2-base-en"

    # Relationships and tags
    relationships: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # BMAD agent enrichment (DEC-018)
    agent: str | None = None  # dev, architect, pm, tea, etc.
    component: str | None = None  # auth, database, api, etc.
    story_id: str | None = None  # AUTH-12, DB-05, etc.

    # Research provenance fields (BUG-006)
    # WHY: Enables best-practices-researcher agent to store web-sourced guidelines
    # with full attribution (source URL, publication date, capture method).
    # WHEN TO USE: Set these when storing researched best practices from external sources.
    # Template-seeded practices (from templates/conventions/) should omit or use defaults.
    source: str | None = (
        None  # URL or reference (web link, DOI, book citation, file path)
    )
    source_date: str | None = None  # ISO 8601 date when source was published/updated
    auto_seeded: bool = False  # True = auto-captured by agent, False = manually seeded

    def to_dict(self) -> dict:
        """Convert to dictionary for Qdrant storage.

        Converts enum values to strings and returns a dict suitable for
        Qdrant payload storage. Optional fields (agent, component, story_id,
        source, source_date) are only included if set to avoid cluttering
        the payload. The auto_seeded field is always included (defaults to False).

        Returns:
            Dictionary with all fields in snake_case
        """
        result = {
            "content": self.content,
            "content_hash": self.content_hash,
            "group_id": self.group_id,
            "type": (
                self.type.value if isinstance(self.type, MemoryType) else self.type
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

        # Include research provenance fields (BUG-006)
        if self.source is not None:
            result["source"] = self.source
        if self.source_date is not None:
            result["source_date"] = self.source_date
        result["auto_seeded"] = self.auto_seeded  # Always include (bool has default)

        # Include created_at if set (TECH-DEBT-012 Round 3)
        if self.created_at is not None:
            result["created_at"] = self.created_at

        return result
