"""Strongly-typed hook event classes per BP-040 Section 1.

TECH-DEBT-111: Provides type-safe event structures for memory operations.
These classes ensure consistent payload structure across all hooks.

Usage:
    from memory.events import CaptureEvent, RetrievalEvent

    # For capture hooks (store to database)
    event = CaptureEvent(
        collection="discussions",
        type="agent_response",
        content="Claude's response text",
        group_id="project-name",
        session_id="sess-123"
    )

    # For retrieval hooks (query database)
    event = RetrievalEvent(
        query="search query",
        collection="discussions",
        group_id="project-name"
    )
"""

from dataclasses import dataclass, field


@dataclass
class CaptureEvent:
    """Event for CAPTURE hooks (store to database).

    Used by hooks that store memories: Stop, UserPromptSubmit, PostToolUse.

    All capture operations MUST include:
    - collection: Target Qdrant collection
    - type: Memory type for filtering (e.g., "agent_response", "user_message")
    - content: The actual content to store
    - group_id: Project identifier for multi-project isolation

    Attributes:
        collection: Target collection ("discussions", "conventions", "code-patterns")
        type: Memory type for categorization and filtering
        content: The content to store (10-100,000 chars recommended)
        group_id: Project identifier - MUST be included per architecture Section 7.3
        session_id: Optional current session ID for conversation tracking
        tags: Optional list of tags for filtering and discovery
        metadata: Optional additional metadata (source_hook, turn_number, etc.)
    """

    collection: str
    type: str
    content: str
    group_id: str
    session_id: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = field(default_factory=dict)

    def __post_init__(self):
        """Validate required fields."""
        if not self.collection:
            raise ValueError("collection is required")
        if not self.type:
            raise ValueError("type is required")
        if not self.content:
            raise ValueError("content is required")
        if not self.group_id:
            raise ValueError("group_id is required per architecture Section 7.3")

    def to_payload(self) -> dict:
        """Convert to Qdrant payload format."""
        payload = {
            "content": self.content,
            "type": self.type,
            "group_id": self.group_id,
        }
        if self.session_id:
            payload["session_id"] = self.session_id
        if self.tags:
            payload["tags"] = self.tags
        if self.metadata:
            payload.update(self.metadata)
        return payload


@dataclass
class RetrievalEvent:
    """Event for RETRIEVAL hooks (query database).

    Used by hooks that retrieve memories: SessionStart, best_practices_retrieval.

    All retrieval operations MUST include:
    - query: Semantic search query
    - collection: Target collection to search
    - group_id: Project filter (architecture Section 7.3 requirement)

    Attributes:
        query: Semantic search query string
        collection: Target collection to search
        type_filter: Optional filter by memory type
        group_id: Project filter - MUST be included per architecture Section 7.3
        limit: Maximum results to return (default 10)
    """

    query: str
    collection: str
    type_filter: str | None = None
    group_id: str = ""
    limit: int = 10

    def __post_init__(self):
        """Validate required fields."""
        if not self.query:
            raise ValueError("query is required")
        if not self.collection:
            raise ValueError("collection is required")
        # Note: group_id can be empty for shared collections like "conventions"

    def to_filter_dict(self) -> dict:
        """Convert to filter dictionary for search operations."""
        filters = {}
        if self.group_id:
            filters["group_id"] = self.group_id
        if self.type_filter:
            filters["type"] = self.type_filter
        return filters
