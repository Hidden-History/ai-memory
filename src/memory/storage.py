"""Memory storage module with validation and graceful degradation.

Handles memory persistence with:
- Payload validation before storage
- Embedding generation with error handling
- Content-hash based deduplication
- Graceful degradation on service failures
- Batch operations for efficiency

Implements Story 1.5 (Storage Module).
Architecture Reference: architecture.md:516-690 (Storage & Graceful Degradation)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from .config import MemoryConfig, get_config
from .embeddings import EmbeddingClient, EmbeddingError
from .models import MemoryPayload, MemoryType, EmbeddingStatus
from .qdrant_client import get_qdrant_client, QdrantUnavailable
from .validation import validate_payload, compute_content_hash

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import memory_captures_total, collection_size, failure_events_total, deduplication_events_total
except ImportError:
    memory_captures_total = None
    collection_size = None
    failure_events_total = None
    deduplication_events_total = None

__all__ = ["MemoryStorage", "store_best_practice"]

logger = logging.getLogger("bmad.memory.storage")


class MemoryStorage:
    """Handles memory storage operations with validation and graceful degradation.

    Provides store_memory() and store_memories_batch() methods that:
    - Validate payloads before storage
    - Generate embeddings with error handling
    - Check for duplicates using content_hash
    - Store memories in Qdrant with proper schema
    - Handle failures gracefully (embedding down = pending status, Qdrant down = exception)

    Example:
        >>> storage = MemoryStorage()
        >>> result = storage.store_memory(
        ...     content="def hello(): return 'world'",
        ...     cwd="/path/to/project",  # Auto-detects group_id
        ...     memory_type=MemoryType.IMPLEMENTATION,
        ...     source_hook="PostToolUse",
        ...     session_id="sess-123"
        ... )
        >>> result["status"]
        'stored'
        >>> result["embedding_status"]
        'complete'
    """

    def __init__(self, config: Optional[MemoryConfig] = None) -> None:
        """Initialize storage with configured clients.

        Args:
            config: Optional MemoryConfig instance. Uses get_config() if not provided.

        Note:
            Creates embedding and Qdrant clients. For production, consider
            connection pooling and singleton patterns for FastAPI applications.
        """
        self.config = config or get_config()
        self.embedding_client = EmbeddingClient(self.config)
        self.qdrant_client = get_qdrant_client(self.config)

    def store_memory(
        self,
        content: str,
        cwd: str,
        memory_type: MemoryType,
        source_hook: str,
        session_id: str,
        collection: str = "implementations",
        group_id: Optional[str] = None,
        **extra_fields,
    ) -> dict:
        """Store a memory with automatic project detection and validation.

        Implements AC 1.5.1 (Storage Module Implementation) and AC 4.2.1 (Project-Scoped Storage).

        BREAKING CHANGE (Story 4.2): cwd is now required for automatic project detection.
        group_id is now optional and auto-detected from cwd via detect_project().

        Process:
        1. Validate cwd parameter
        2. Auto-detect group_id from cwd using detect_project() (Story 4.1)
        3. Build payload with content_hash
        4. Validate payload
        5. Check for duplicates
        6. Generate embedding (graceful degradation on failure)
        7. Store in Qdrant

        Args:
            content: Memory content (10-100,000 chars)
            cwd: Current working directory for project detection (REQUIRED)
            memory_type: Type of memory (MemoryType enum)
            source_hook: Hook that captured this (PostToolUse, Stop, SessionStart)
            session_id: Claude session identifier
            collection: Qdrant collection name (default: "implementations")
            group_id: Optional explicit project identifier (overrides auto-detection)
            **extra_fields: Additional payload fields (domain, importance, tags, etc.)

        Returns:
            Dictionary with:
                - memory_id: UUID string if stored, None if duplicate
                - status: "stored" or "duplicate"
                - embedding_status: "complete", "pending", or "failed"

        Raises:
            ValueError: If cwd is None or payload validation fails
            QdrantUnavailable: If Qdrant is unreachable (caller should queue)

        Example:
            >>> storage = MemoryStorage()
            >>> result = storage.store_memory(
            ...     content="Implementation code here",
            ...     cwd="/path/to/project",  # REQUIRED for project detection
            ...     memory_type=MemoryType.IMPLEMENTATION,
            ...     source_hook="PostToolUse",
            ...     session_id="sess-456"
            ... )
            >>> result["status"]
            'stored'
        """
        # Validate cwd parameter (AC 4.2.1)
        if cwd is None:
            raise ValueError("cwd parameter is required for project-scoped storage")

        # Auto-detect group_id from cwd if not explicitly provided (AC 4.2.1)
        if group_id is None:
            try:
                from .project import detect_project

                group_id = detect_project(cwd)
                logger.debug(
                    "project_detected",
                    extra={"cwd": cwd, "group_id": group_id},
                )
            except Exception as e:
                # Graceful degradation: Use fallback with warning
                logger.warning(
                    "project_detection_failed",
                    extra={
                        "cwd": cwd,
                        "error": str(e),
                        "fallback": "unknown-project",
                    },
                )
                group_id = "unknown-project"
        # Build payload with computed hash
        content_hash = compute_content_hash(content)
        payload = MemoryPayload(
            content=content,
            content_hash=content_hash,
            group_id=group_id,
            type=memory_type,
            source_hook=source_hook,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            **extra_fields,
        )

        # Validate payload
        errors = validate_payload(payload.to_dict())
        if errors:
            logger.error(
                "validation_failed",
                extra={"errors": errors, "group_id": group_id, "content_hash": content_hash},
            )
            raise ValueError(f"Validation failed: {errors}")

        # Check for duplicates within same project (AC 1.5.3)
        # Note: group_id required to respect multi-tenancy isolation (fix per code review)
        existing_id = self._check_duplicate(content_hash, collection, group_id)
        if existing_id:
            logger.info(
                "duplicate_memory_skipped",
                extra={
                    "content_hash": content_hash,
                    "group_id": group_id,
                    "existing_id": existing_id,
                },
            )
            return {
                "memory_id": existing_id,
                "status": "duplicate",
                "embedding_status": "n/a",
            }

        # Generate embedding with graceful degradation (AC 1.5.4)
        try:
            embeddings = self.embedding_client.embed([content])
            embedding = embeddings[0]
            payload.embedding_status = EmbeddingStatus.COMPLETE
            logger.debug(
                "embedding_generated",
                extra={"content_hash": content_hash, "dimensions": len(embedding)},
            )

        except EmbeddingError as e:
            # Graceful degradation: Store with pending status and zero vector
            logger.warning(
                "embedding_failed_storing_pending",
                extra={
                    "error": str(e),
                    "content_hash": content_hash,
                    "group_id": group_id,
                },
            )

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding", error_code="EMBEDDING_TIMEOUT"
                ).inc()

            embedding = [0.0] * 768  # DEC-010: Zero vector placeholder
            payload.embedding_status = EmbeddingStatus.PENDING

        # Store in Qdrant
        memory_id = str(uuid.uuid4())
        try:
            self.qdrant_client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=memory_id, vector=embedding, payload=payload.to_dict()
                    )
                ],
            )

            logger.info(
                "memory_stored",
                extra={
                    "memory_id": memory_id,
                    "type": memory_type.value,
                    "group_id": group_id,
                    "embedding_status": payload.embedding_status.value,
                    "collection": collection,
                },
            )

            # Metrics: Memory capture success (Story 6.1, AC 6.1.3)
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type=source_hook,
                    status="success",
                    project=group_id
                ).inc()

            return {
                "memory_id": memory_id,
                "status": "stored",
                "embedding_status": payload.embedding_status.value,
            }

        except Exception as e:
            # Qdrant failure: Propagate exception for caller to handle
            logger.error(
                "qdrant_store_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "content_hash": content_hash,
                    "group_id": group_id,
                },
            )

            # Metrics: Memory capture failed (Story 6.1, AC 6.1.3)
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type=source_hook,
                    status="failed",
                    project=group_id
                ).inc()

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="qdrant", error_code="QDRANT_UNAVAILABLE"
                ).inc()

            raise QdrantUnavailable(f"Failed to store memory: {e}") from e

    def store_memories_batch(
        self,
        memories: list[dict],
        cwd: Optional[str] = None,
        collection: str = "implementations",
    ) -> list[dict]:
        """Store multiple memories in batch for efficiency.

        Implements AC 1.5.2 (Batch Storage Support) and AC 4.2.1 (Project-Scoped Storage).

        Batch operations:
        - Auto-detect group_id from cwd if not provided in individual memories
        - Validate all payloads upfront
        - Generate embeddings in single batch request (2025/2026 best practice)
        - Store all memories in single Qdrant upsert

        Note:
            Batch storage does NOT check for duplicates. Use store_memory() for
            deduplication support, or ensure content uniqueness before batch calls.

        Args:
            memories: List of memory dictionaries, each with keys:
                - content: str
                - group_id: str (optional if cwd provided)
                - type: str (MemoryType value)
                - source_hook: str
                - session_id: str
            cwd: Optional working directory for auto project detection.
                 Used when individual memory lacks group_id.
            collection: Qdrant collection name (default: "implementations")

        Returns:
            List of result dictionaries, one per input memory, with:
                - memory_id: UUID string
                - status: "stored"
                - embedding_status: "complete" or "pending"

        Raises:
            ValueError: If any payload validation fails
            QdrantUnavailable: If Qdrant is unreachable

        Note:
            If a memory has explicit group_id, it takes precedence over cwd.
            If neither group_id nor cwd provided, falls back to "unknown-project".

        Example:
            >>> storage = MemoryStorage()
            >>> memories = [
            ...     {"content": "Code 1", "type": "implementation",
            ...      "source_hook": "PostToolUse", "session_id": "sess"},
            ...     {"content": "Code 2", "type": "implementation",
            ...      "source_hook": "PostToolUse", "session_id": "sess"},
            ... ]
            >>> results = storage.store_memories_batch(memories, cwd="/path/to/project")
            >>> len(results)
            2
        """
        points = []
        results = []

        # Auto-detect project from cwd if provided (AC 4.2.1)
        default_group_id = None
        if cwd:
            try:
                from .project import detect_project

                default_group_id = detect_project(cwd)
                logger.debug(
                    "batch_project_detected",
                    extra={"cwd": cwd, "group_id": default_group_id},
                )
            except Exception as e:
                logger.warning(
                    "batch_project_detection_failed",
                    extra={"cwd": cwd, "error": str(e), "fallback": "unknown-project"},
                )
                default_group_id = "unknown-project"

        # Apply default group_id to memories missing it
        for memory in memories:
            if "group_id" not in memory or memory.get("group_id") is None:
                memory["group_id"] = default_group_id or "unknown-project"

        # Validate all first (fail fast)
        for memory in memories:
            errors = validate_payload(memory)
            if errors:
                logger.error(
                    "batch_validation_failed",
                    extra={"errors": errors, "group_id": memory.get("group_id")},
                )
                raise ValueError(f"Batch validation failed: {errors}")

        # Generate embeddings in batch (efficient for multiple memories)
        contents = [m["content"] for m in memories]
        try:
            embeddings = self.embedding_client.embed(contents)
            embedding_status = EmbeddingStatus.COMPLETE
            logger.debug(
                "batch_embeddings_generated", extra={"count": len(contents)}
            )

        except EmbeddingError as e:
            # Graceful degradation: Use zero vectors for all
            logger.warning(
                "batch_embedding_failed",
                extra={"error": str(e), "count": len(contents)},
            )

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding", error_code="EMBEDDING_TIMEOUT"
                ).inc()

            embeddings = [[0.0] * 768 for _ in contents]  # DEC-010: 768d placeholder
            embedding_status = EmbeddingStatus.PENDING

        # Build points for batch upsert
        for memory, embedding in zip(memories, embeddings):
            memory_id = str(uuid.uuid4())
            content_hash = compute_content_hash(memory["content"])

            payload = MemoryPayload(
                content=memory["content"],
                content_hash=content_hash,
                group_id=memory["group_id"],
                type=memory["type"],  # Already a string from dict
                source_hook=memory["source_hook"],
                session_id=memory["session_id"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                embedding_status=embedding_status,
            )

            points.append(
                PointStruct(
                    id=memory_id, vector=embedding, payload=payload.to_dict()
                )
            )
            results.append(
                {
                    "memory_id": memory_id,
                    "status": "stored",
                    "embedding_status": embedding_status.value,
                }
            )

        # Store all in single upsert
        try:
            self.qdrant_client.upsert(collection_name=collection, points=points)

            logger.info(
                "batch_stored",
                extra={
                    "count": len(points),
                    "collection": collection,
                    "embedding_status": embedding_status.value,
                },
            )

            return results

        except Exception as e:
            logger.error(
                "batch_qdrant_store_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "count": len(points),
                },
            )

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="qdrant", error_code="QDRANT_UNAVAILABLE"
                ).inc()

            raise QdrantUnavailable(f"Failed to batch store memories: {e}") from e

    def _check_duplicate(
        self, content_hash: str, collection: str, group_id: str
    ) -> Optional[str]:
        """Check if content_hash already exists in collection for the same project.

        Implements AC 1.5.3 (Deduplication Integration).

        Uses Qdrant scroll with Filter on content_hash AND group_id fields.
        Both filters required to respect multi-tenancy - same content in different
        projects is NOT a duplicate (fix per code review).

        Fails open: Returns None if check itself fails (better to allow duplicate
        than lose memory).

        Args:
            content_hash: SHA256 hash to check
            collection: Qdrant collection name
            group_id: Project identifier for multi-tenancy filtering

        Returns:
            Existing memory_id (str) if hash exists (duplicate), None otherwise

        Example:
            >>> storage = MemoryStorage()
            >>> storage._check_duplicate("abc123...", "implementations", "my-project")
            None
        """
        try:
            results = self.qdrant_client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="content_hash",
                            match=MatchValue(value=content_hash),
                        ),
                        FieldCondition(
                            key="group_id",
                            match=MatchValue(value=group_id),
                        ),
                    ]
                ),
                limit=1,
            )
            if results[0]:
                existing_id = str(results[0][0].id)
                logger.debug(
                    "duplicate_check",
                    extra={
                        "content_hash": content_hash,
                        "found": True,
                        "existing_id": existing_id,
                        "collection": collection,
                    },
                )

                # Metrics: Increment deduplication counter (Story 6.1, AC 6.1.3)
                if deduplication_events_total:
                    deduplication_events_total.labels(
                        project=group_id or "unknown"
                    ).inc()

                return existing_id

            logger.debug(
                "duplicate_check",
                extra={
                    "content_hash": content_hash,
                    "found": False,
                    "collection": collection,
                },
            )
            return None

        except Exception as e:
            # Fail open: Allow storage if check fails
            logger.warning(
                "duplicate_check_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "content_hash": content_hash,
                },
            )
            return None


def store_best_practice(
    content: str,
    session_id: str,
    source_hook: str = "manual",
    config: Optional[MemoryConfig] = None,
    **kwargs,
) -> dict:
    """Store best practice accessible from all projects.

    Implements AC 4.3.1 (Best Practices Storage) and FR16 (Cross-Project Sharing).

    Best practices use a special 'shared' group_id marker and are stored
    in the 'best_practices' collection for cross-project accessibility.

    Unlike implementations (Story 4.2), best practices:
    - Use group_id="shared" (not project-specific)
    - Stored in 'best_practices' collection (not 'implementations')
    - NO cwd parameter required (intentionally global)
    - Accessible from ALL projects without filtering

    Args:
        content: Best practice text content (10-100,000 chars)
        session_id: Current Claude session ID
        source_hook: Hook that captured this best practice (default: "manual")
                     "manual" is used for skill-based or API-driven storage
                     Added in Story 4.3 for explicit best practice capture
        config: Optional MemoryConfig instance. Uses get_config() if not provided.
        **kwargs: Additional metadata fields (e.g., domain, tags)

    Returns:
        dict: Storage result with:
            - memory_id: UUID string if stored, None if duplicate
            - status: "stored" or "duplicate"
            - embedding_status: "complete", "pending", or "failed"
            - group_id: Always "shared"
            - collection: Always "best_practices"

    Raises:
        ValueError: If content validation fails
        QdrantUnavailable: If Qdrant is unreachable (caller should queue)

    Example:
        >>> result = store_best_practice(
        ...     content="Always use type hints in Python 3.10+ for better IDE support",
        ...     session_id="sess-123",
        ...     source_hook="PostToolUse",
        ...     domain="python"
        ... )
        >>> result["status"]
        'stored'
        >>> result["group_id"]
        'shared'
        >>> result["collection"]
        'best_practices'

    Note:
        Unlike implementations, best practices don't require 'cwd' parameter
        since they're intentionally shared across all projects.

    2026 Best Practice Rationale:
        Per Qdrant Multitenancy Guide (https://qdrant.tech/articles/multitenancy/),
        Qdrant is designed to excel in single collection with vast number of
        tenants. However, when data is not homogenous (different semantics,
        different retrieval patterns), separate collections are appropriate.

        - CORRECT: implementations (project-specific) vs best_practices (shared)
          = different semantics → separate collections
        - WRONG: Multiple collections per project (homogenous data)
          = resource waste

        Why group_id="shared" instead of group_id=None?
        1. Explicit intent: "shared" clearly signals cross-project semantics
        2. Query consistency: Payload always has group_id field (no None handling)
        3. Future extensibility: Can add group_id="org-level" for hierarchies
        4. Index compatibility: Works with is_tenant=True index (Story 4.2)
    """
    try:
        storage = MemoryStorage(config=config)

        # Best practices use shared group_id marker (FR16)
        # TECH DEBT: cwd parameter required by Story 4.2 breaking change
        # Using sentinel path "/__best_practices__" as workaround
        # Proper fix (making cwd optional) deferred to avoid mid-sprint API changes
        # See TECH-DEBT-001 for future refactor
        result = storage.store_memory(
            content=content,
            cwd="/__best_practices__",  # Sentinel path for best practices (no real filesystem path)
            group_id="shared",  # CRITICAL: Special marker for cross-project access
            collection="best_practices",  # CRITICAL: Separate from implementations
            memory_type=MemoryType.PATTERN,  # Differentiates from implementations
            session_id=session_id,
            source_hook=source_hook,
            **kwargs,
        )

        # Enhance result with explicit markers
        result["group_id"] = "shared"
        result["collection"] = "best_practices"

        logger.info(
            "best_practice_stored",
            extra={
                "memory_id": result.get("memory_id"),
                "session_id": session_id,
                "source_hook": source_hook,
                "embedding_status": result.get("embedding_status"),
                "status": result.get("status"),
            },
        )

        return result

    except Exception as e:
        logger.error(
            "best_practice_storage_failed",
            extra={
                "session_id": session_id,
                "source_hook": source_hook,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        # Re-raise for caller to handle (explicit error per user requirements)
        raise
