"""Agent-friendly memory interface for AI Memory System.

Provides MemorySubagent class that wraps MemorySearch with:
- Intent detection for automatic collection routing
- Result formatting for agent consumption
- Confidence scoring for result quality assessment
- Source attribution for transparency

Enables BMAD agents to query memory mid-task without user intervention.

Example:
    >>> subagent = MemorySubagent()
    >>> result = subagent.query("How did we implement auth?")
    >>> print(result.answer)
    >>> print(result.confidence)
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from .intent import IntentType, detect_intent, get_target_collection
from .search import MemorySearch
from .storage import MemoryStorage

logger = logging.getLogger("ai_memory.subagent")

DEFAULT_LIMIT = 5


@dataclass
class QueryContext:
    """Context for memory query."""

    current_file: str | None = None
    current_task: str | None = None
    session_id: str | None = None
    project_id: str | None = None


@dataclass
class MemorySource:
    """Source attribution for a memory result."""

    collection: str
    memory_type: str
    file_path: str | None = None
    line_number: int | None = None
    score: float = 0.0


@dataclass
class MemoryResult:
    """Result from memory query."""

    answer: str  # Formatted answer text
    sources: list[MemorySource] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 to 1.0
    intent_detected: str | None = None
    collection_searched: str | None = None
    raw_results: list[dict[str, Any]] = field(default_factory=list)


class MemorySubagent:
    """Agent-friendly memory interface.

    Enables BMAD agents to query memory mid-task without user intervention.
    Wraps MemorySearch with intent detection, result formatting, and
    confidence scoring.

    Example:
        >>> subagent = MemorySubagent()
        >>> result = subagent.query("How did we implement auth?")
        >>> print(result.answer)
        >>> print(result.confidence)
    """

    def __init__(self, search_client: MemorySearch | None = None):
        """Initialize subagent.

        Args:
            search_client: Optional MemorySearch instance (creates new if None)
        """
        self.search = search_client or MemorySearch()
        logger.info("subagent_initialized")

    async def query(
        self,
        question: str,
        context: QueryContext | None = None,
        collection: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> MemoryResult:
        """Query memory with natural language question.

        Args:
            question: Natural language question
            context: Optional context (current file, task, etc.)
            collection: Override auto-detection (code-patterns, conventions, discussions)
            limit: Max results to return

        Returns:
            MemoryResult with:
            - answer: Formatted answer text
            - sources: List of MemorySource attributions
            - confidence: Score 0.0-1.0
            - intent_detected: Detected intent type
            - collection_searched: Collection that was queried
            - raw_results: Full search results for debugging/analysis
        """
        # Detect target collection and intent
        target_collection, intent = self._detect_target(question, collection)

        # Extract group_id from context if available
        group_id = context.project_id if context else None

        # Search memory
        try:
            results = self.search.search(
                query=question,
                collection=target_collection,
                group_id=group_id,
                limit=limit,
            )

            # Format answer from results
            answer = self._format_answer(results, intent)

            # Score confidence
            confidence = self._score_confidence(results)

            # Build source attribution
            sources = self._build_sources(results, target_collection)

            logger.info(
                "subagent_query_completed",
                extra={
                    "intent": intent.value,
                    "collection": target_collection,
                    "results_count": len(results),
                    "confidence": confidence,
                },
            )

            return MemoryResult(
                answer=answer,
                sources=sources,
                confidence=confidence,
                intent_detected=intent.value,
                collection_searched=target_collection,
                raw_results=results,
            )

        except Exception as e:
            logger.error(
                "subagent_query_failed",
                extra={
                    "question": question[:50],
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            # Return empty result on failure (graceful degradation)
            return MemoryResult(
                answer="No relevant memories found.",
                sources=[],
                confidence=0.0,
                intent_detected=intent.value if "intent" in locals() else None,
                collection_searched=(
                    target_collection if "target_collection" in locals() else None
                ),
                raw_results=[],
            )

    async def store(
        self,
        content: str,
        memory_type: str,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> str:
        """Store memory from agent context.

        Args:
            content: Content to store
            memory_type: Type (implementation, decision, etc.)
            tags: Optional tags
            source: Source attribution (e.g., "agent:dev")

        Returns:
            Memory ID if stored successfully, empty string on error
        """
        try:
            from .models import MemoryType

            # Validate memory_type before enum construction
            try:
                validated_type = MemoryType(memory_type)
            except ValueError:
                valid_types = [t.value for t in MemoryType]
                logger.warning(
                    "invalid_memory_type",
                    extra={
                        "provided": memory_type,
                        "valid_types": valid_types,
                    },
                )
                return ""  # Graceful degradation

            storage = MemoryStorage()

            # Use sentinel path for agent storage (no real filesystem context)
            result = storage.store_memory(
                content=content,
                cwd="/__agent__",  # Sentinel for agent-originated memories
                memory_type=validated_type,
                source_hook=source or "agent:subagent",
                session_id="agent-session",  # Placeholder
                tags=tags or [],
            )

            memory_id = result.get("memory_id", "")

            logger.info(
                "subagent_store_completed",
                extra={
                    "memory_id": memory_id,
                    "memory_type": memory_type,
                    "status": result.get("status"),
                },
            )

            return memory_id

        except Exception as e:
            logger.error(
                "subagent_store_failed",
                extra={
                    "memory_type": memory_type,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ""

    def _detect_target(
        self, question: str, collection: str | None
    ) -> tuple[str, IntentType]:
        """Detect target collection and intent."""
        # If collection explicitly provided, use it with UNKNOWN intent
        if collection is not None:
            logger.debug(
                "collection_override",
                extra={"collection": collection, "question": question[:50]},
            )
            return collection, IntentType.UNKNOWN

        # Otherwise, detect intent and map to collection
        intent = detect_intent(question)
        target_collection = get_target_collection(intent)

        logger.debug(
            "intent_detected",
            extra={
                "intent": intent.value,
                "collection": target_collection,
                "question": question[:50],
            },
        )

        return target_collection, intent

    def _format_answer(self, results: list[dict], intent: IntentType) -> str:
        """Format search results into agent-friendly answer."""
        if not results:
            return "No relevant memories found."

        # Build formatted answer with content from top results
        lines = []
        for i, result in enumerate(results[:3], 1):  # Top 3 results
            content = result.get("content", "")
            memory_type = result.get("type", "unknown")
            score = result.get("score", 0.0)

            lines.append(f"{i}. [{memory_type}] ({score:.0%})")
            lines.append(content)
            lines.append("")  # Blank line between results

        return "\n".join(lines)

    def _score_confidence(self, results: list[dict]) -> float:
        """Calculate confidence score based on result quality.

        Confidence factors:
        - Average similarity score (70% weight)
        - Number of results returned (30% weight, max boost at 3 results)

        Returns:
            Confidence score 0.0 to 1.0
        """
        if not results:
            return 0.0

        scores = [r.get("score", 0.0) for r in results]
        avg_score = sum(scores) / len(scores)

        # Boost for multiple results (max boost at 3 results)
        result_factor = min(len(results) / 3, 1.0)

        # Combine factors
        confidence = avg_score * 0.7 + result_factor * 0.3
        return min(confidence, 1.0)

    def _build_sources(
        self, results: list[dict], collection: str
    ) -> list[MemorySource]:
        """Build source attribution list from search results."""
        sources = []
        for result in results:
            source = MemorySource(
                collection=collection,
                memory_type=result.get("type", "unknown"),
                file_path=result.get("file_path"),
                line_number=result.get("line_number"),
                score=result.get("score", 0.0),
            )
            sources.append(source)

        return sources
