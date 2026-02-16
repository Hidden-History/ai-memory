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

import dataclasses
import logging
import uuid
from datetime import datetime, timezone

from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from .chunking import ContentType, IntelligentChunker
from .config import MemoryConfig, get_config
from .embeddings import EmbeddingClient, EmbeddingError
from .models import EmbeddingStatus, MemoryPayload, MemoryType
from .qdrant_client import QdrantUnavailable, get_qdrant_client
from .validation import compute_content_hash, validate_payload

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import (
        collection_size,
        deduplication_events_total,
        failure_events_total,
        memory_captures_total,
    )
except ImportError:
    memory_captures_total = None
    collection_size = None
    failure_events_total = None
    deduplication_events_total = None

__all__ = ["MemoryStorage", "store_best_practice", "update_point_payload"]

logger = logging.getLogger("ai_memory.storage")


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

    def __init__(self, config: MemoryConfig | None = None) -> None:
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

        # SPEC-009: Initialize security scanner (M3 - class-level attribute)
        if self.config.security_scanning_enabled:
            try:
                from .security_scanner import SecurityScanner

                self._scanner = SecurityScanner(
                    enable_ner=self.config.security_scanning_ner_enabled
                )
            except ImportError as e:
                logger.warning(
                    f"SecurityScanner import failed: {e}. Falling back to NER-disabled mode."
                )
                from .security_scanner import SecurityScanner

                self._scanner = SecurityScanner(enable_ner=False)
        else:
            self._scanner = None

    def _get_embedding_model(self, collection: str, content_type: str | None = None) -> str:
        """Determine embedding model based on collection and content type.

        SPEC-010 Section 4.2: Routing Rules
        - code-patterns collection -> code model
        - github_code_blob type -> code model
        - Everything else -> prose (en) model

        Args:
            collection: Target collection name
            content_type: Optional content type (e.g., "github_code_blob")

        Returns:
            Model key: "code" or "en"
        """
        # Code content -> code model
        if collection == "code-patterns":
            return "code"
        if content_type and content_type in ("github_code_blob",):
            return "code"
        # Everything else -> prose model
        return "en"

    def store_memory(
        self,
        content: str,
        cwd: str,
        memory_type: MemoryType,
        source_hook: str,
        session_id: str,
        collection: str = "code-patterns",
        group_id: str | None = None,
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
            collection: Qdrant collection name (default: "code-patterns")
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

        # TECH-DEBT-012 Round 3: Handle created_at timestamp
        created_at = extra_fields.pop("created_at", None)
        if created_at is None:
            created_at = datetime.now(timezone.utc).isoformat()

        # SPEC-009: Security scanning BEFORE chunking
        if self._scanner is not None:
            from .security_scanner import ScanAction

            scan_result = self._scanner.scan(content)
            if scan_result.action == ScanAction.BLOCKED:
                logger.warning(
                    "content_blocked_secrets_detected",
                    extra={
                        "group_id": group_id,
                        "source_hook": source_hook,
                        "findings_count": len(scan_result.findings),
                    },
                )
                return {
                    "memory_id": None,
                    "status": "blocked",
                    "reason": "secrets_detected",
                    "embedding_status": "n/a",
                }
            # Use masked content for chunking/embedding
            content = scan_result.content

        # Route content based on type per Chunking-Strategy-V2.md V2.1
        # Map MemoryType to ContentType for IntelligentChunker
        content_type_map = {
            MemoryType.USER_MESSAGE: ContentType.USER_MESSAGE,
            MemoryType.AGENT_RESPONSE: ContentType.AGENT_RESPONSE,
            MemoryType.JIRA_ISSUE: ContentType.PROSE,
            MemoryType.JIRA_COMMENT: ContentType.PROSE,
        }
        chunker_content_type = content_type_map.get(memory_type)
        # Note: For USER_MESSAGE/AGENT_RESPONSE, IntelligentChunker handles
        # whole storage (under threshold) or topical chunking (over threshold).
        # For other types, content passes through unchanged (chunked by hooks).

        # Track original content size for chunking_metadata (V2.1 compliance)
        original_content_length = len(content)

        additional_chunks = []
        chunk_results = None
        if chunker_content_type is not None:
            chunker = IntelligentChunker(max_chunk_tokens=512, overlap_pct=0.15)
            chunk_results = chunker.chunk(
                content, file_path=source_hook or "", content_type=chunker_content_type
            )

            if len(chunk_results) > 1:
                # Multiple chunks — store each as separate point
                # This replaces smart_end truncation with zero-truncation chunking
                logger.info(
                    "content_chunked_for_storage",
                    extra={
                        "memory_type": memory_type.value,
                        "num_chunks": len(chunk_results),
                        "original_length": len(content),
                    },
                )
                # Store first chunk normally, additional chunks as separate points
                content = chunk_results[0].content
                # Additional chunks will be stored after the main point
                additional_chunks = chunk_results[1:]
            else:
                # Single chunk (under threshold) - use the content as-is
                content = chunk_results[0].content

        # Build payload with computed hash
        content_hash = compute_content_hash(content)

        # Remove reserved keys from extra_fields to prevent duplicate arguments
        reserved_keys = [
            "timestamp",
            "created_at",
            "content",
            "content_hash",
            "type",
            "source_hook",
            "session_id",
            "group_id",
            "collection",
        ]
        for key in reserved_keys:
            extra_fields.pop(key, None)

        # Separate MemoryPayload-known fields from extra payload fields.
        # Unknown fields (e.g., jira_project, jira_issue_key) are passed
        # directly to the Qdrant payload, bypassing MemoryPayload.
        _mp_field_names = {f.name for f in dataclasses.fields(MemoryPayload)}
        payload_kwargs = {}
        extra_payload = {}
        for k, v in extra_fields.items():
            if k in _mp_field_names:
                payload_kwargs[k] = v
            else:
                extra_payload[k] = v

        payload = MemoryPayload(
            content=content,
            content_hash=content_hash,
            group_id=group_id,
            type=memory_type,
            source_hook=source_hook,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            created_at=created_at,
            **payload_kwargs,
        )

        # Validate payload
        errors = validate_payload(payload.to_dict())
        if errors:
            logger.error(
                "validation_failed",
                extra={
                    "errors": errors,
                    "group_id": group_id,
                    "content_hash": content_hash,
                },
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
        # SPEC-010: Route to appropriate model based on collection and content type
        embedding_model = self._get_embedding_model(collection, extra_fields.get("content_type"))
        try:
            embeddings = self.embedding_client.embed([content], model=embedding_model)
            embedding = embeddings[0]
            payload.embedding_status = EmbeddingStatus.COMPLETE
            logger.debug(
                "embedding_generated",
                extra={"content_hash": content_hash, "dimensions": len(embedding), "model": embedding_model},
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
                    component="embedding",
                    error_code="EMBEDDING_TIMEOUT",
                    project=group_id,
                ).inc()

            embedding = [0.0] * 768  # DEC-010: Zero vector placeholder
            payload.embedding_status = EmbeddingStatus.PENDING

        # Build chunking_metadata (Chunking Strategy V2.1 compliance)
        original_size_tokens = original_content_length // 4

        if additional_chunks and chunk_results:
            # First chunk of multi-chunk content
            first_chunk = chunk_results[0]
            chunking_metadata = {
                "chunk_type": first_chunk.metadata.chunk_type,
                "chunk_index": first_chunk.metadata.chunk_index,
                "total_chunks": first_chunk.metadata.total_chunks,
                "chunk_size_tokens": first_chunk.metadata.chunk_size_tokens,
                "overlap_tokens": first_chunk.metadata.overlap_tokens,
                "original_size_tokens": original_size_tokens,
                "truncated": False,
            }
        else:
            # Whole content (single chunk or unchunked)
            chunking_metadata = {
                "chunk_type": "whole",
                "chunk_index": 0,
                "total_chunks": 1,
                "chunk_size_tokens": original_size_tokens,
                "overlap_tokens": 0,
                "original_size_tokens": original_size_tokens,
                "truncated": False,
            }

        # Store in Qdrant
        memory_id = str(uuid.uuid4())
        try:
            self.qdrant_client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=memory_id,
                        vector=embedding,
                        payload={
                            **payload.to_dict(),
                            **extra_payload,
                            "chunking_metadata": chunking_metadata,
                        },
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
                    project=group_id,
                    collection=collection,
                ).inc()

            # Store additional chunks if present (TECH-DEBT-151 Phase 4)
            if additional_chunks:
                additional_points = []
                for _i, chunk in enumerate(additional_chunks, start=1):
                    chunk_id = str(uuid.uuid4())
                    chunk_hash = compute_content_hash(chunk.content)

                    chunk_payload = MemoryPayload(
                        content=chunk.content,
                        content_hash=chunk_hash,
                        group_id=group_id,
                        type=memory_type,
                        source_hook=source_hook,
                        session_id=session_id,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        created_at=created_at,
                        embedding_status=payload.embedding_status,
                        **payload_kwargs,
                    )

                    try:
                        chunk_embedding = self.embedding_client.embed([chunk.content], model=embedding_model)[
                            0
                        ]
                    except EmbeddingError:
                        chunk_embedding = [0.0] * 768

                    chunk_chunking_metadata = {
                        "chunk_type": chunk.metadata.chunk_type,
                        "chunk_index": chunk.metadata.chunk_index,
                        "total_chunks": chunk.metadata.total_chunks,
                        "chunk_size_tokens": chunk.metadata.chunk_size_tokens,
                        "overlap_tokens": chunk.metadata.overlap_tokens,
                        "original_size_tokens": original_size_tokens,
                        "truncated": False,
                    }

                    additional_points.append(
                        PointStruct(
                            id=chunk_id,
                            vector=chunk_embedding,
                            payload={
                                **chunk_payload.to_dict(),
                                **extra_payload,
                                "chunking_metadata": chunk_chunking_metadata,
                            },
                        )
                    )

                # Store additional chunks in batch
                self.qdrant_client.upsert(
                    collection_name=collection,
                    points=additional_points,
                )
                logger.info(
                    "additional_chunks_stored",
                    extra={
                        "num_additional_chunks": len(additional_chunks),
                        "memory_type": memory_type.value,
                    },
                )

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
                    project=group_id,
                    collection=collection,
                ).inc()

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="qdrant",
                    error_code="QDRANT_UNAVAILABLE",
                    project=group_id,
                ).inc()

            raise QdrantUnavailable(f"Failed to store memory: {e}") from e

    def store_memories_batch(
        self,
        memories: list[dict],
        cwd: str | None = None,
        collection: str = "code-patterns",
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
            collection: Qdrant collection name (default: "code-patterns")

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
        if not memories:
            return []

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

        # SPEC-009: Security scanning (all 3 layers for batch operations)
        # Scan all memories and filter out BLOCKED ones
        if self._scanner is not None:
            from .security_scanner import ScanAction

            scanned_memories = []
            blocked_count = 0
            masked_count = 0

            for memory in memories:
                scan_result = self._scanner.scan(memory["content"], force_ner=True)

                if scan_result.action == ScanAction.BLOCKED:
                    # Skip this memory entirely
                    blocked_count += 1
                    logger.warning(
                        "batch_memory_blocked_secrets",
                        extra={
                            "group_id": memory.get("group_id"),
                            "type": memory.get("type"),
                            "findings": len(scan_result.findings),
                        },
                    )
                    # Add blocked result to results list
                    results.append({
                        "memory_id": None,
                        "status": "blocked",
                        "reason": "secrets_detected",
                        "embedding_status": "n/a",
                    })
                    continue

                elif scan_result.action == ScanAction.MASKED:
                    # Use masked content
                    memory["content"] = scan_result.content
                    masked_count += 1
                    logger.info(
                        "batch_memory_pii_masked",
                        extra={
                            "group_id": memory.get("group_id"),
                            "type": memory.get("type"),
                            "findings": len(scan_result.findings),
                        },
                    )

                # Include memory for storage (PASSED or MASKED)
                scanned_memories.append(memory)

            if blocked_count > 0:
                logger.info(
                    "batch_scan_completed",
                    extra={
                        "total": len(memories),
                        "blocked": blocked_count,
                        "masked": masked_count,
                        "stored": len(scanned_memories),
                    },
                )

            # Update memories list to only include non-blocked items
            memories = scanned_memories

            # If all memories were blocked, return early
            if not memories:
                return results

        # Generate embeddings in batch (efficient for multiple memories)
        # SPEC-010: Group memories by embedding model to ensure correct routing
        # Mixed batches (e.g., code + prose) get routed to the correct model
        memory_models = []
        for memory in memories:
            mem_content_type = memory.get("content_type")
            mem_model = self._get_embedding_model(collection, mem_content_type)
            memory_models.append(mem_model)

        # Group by model for efficient batch embedding
        from collections import defaultdict
        model_groups = defaultdict(list)  # model -> [(original_index, content)]
        for idx, (memory, model) in enumerate(zip(memories, memory_models)):
            model_groups[model].append((idx, memory["content"]))

        embeddings = [None] * len(memories)
        embedding_status = EmbeddingStatus.COMPLETE
        try:
            for model, items in model_groups.items():
                indices, contents = zip(*items)
                group_embeddings = self.embedding_client.embed(list(contents), model=model)
                for orig_idx, emb in zip(indices, group_embeddings):
                    embeddings[orig_idx] = emb
            logger.debug("batch_embeddings_generated", extra={"count": len(memories), "models": list(model_groups.keys())})

        except EmbeddingError as e:
            # Graceful degradation: Use zero vectors for all
            logger.warning(
                "batch_embedding_failed",
                extra={"error": str(e), "count": len(memories), "models": list(model_groups.keys())},
            )

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding",
                    error_code="EMBEDDING_TIMEOUT",
                    project=(
                        memories[0].get("group_id", "unknown")
                        if memories
                        else "unknown"
                    ),
                ).inc()

            embeddings = [[0.0] * 768 for _ in memories]  # DEC-010: 768d placeholder
            embedding_status = EmbeddingStatus.PENDING

        # Collect chunk data for batch embedding (avoid N+1 API calls)
        pending_chunks = []

        # Build points for batch upsert
        for memory, embedding, mem_model in zip(memories, embeddings, memory_models, strict=True):
            memory_id = str(uuid.uuid4())

            # TECH-DEBT-012 Round 3: Handle created_at timestamp
            created_at = memory.pop("created_at", None)
            if created_at is None:
                created_at = datetime.now(timezone.utc).isoformat()

            # Get content and memory_type
            content = memory["content"]
            memory_type = (
                MemoryType(memory["type"])
                if isinstance(memory["type"], str)
                else memory["type"]
            )

            # Route content based on type per Chunking-Strategy-V2.md V2.1
            # Map MemoryType to ContentType for IntelligentChunker
            content_type_map = {
                MemoryType.USER_MESSAGE: ContentType.USER_MESSAGE,
                MemoryType.AGENT_RESPONSE: ContentType.AGENT_RESPONSE,
                MemoryType.JIRA_ISSUE: ContentType.PROSE,
                MemoryType.JIRA_COMMENT: ContentType.PROSE,
            }
            chunker_content_type = content_type_map.get(memory_type)
            # Note: For USER_MESSAGE/AGENT_RESPONSE, IntelligentChunker handles
            # whole storage (under threshold) or topical chunking (over threshold).
            # For other types, content passes through unchanged (chunked by hooks).

            # Calculate original size for chunking_metadata
            original_size_tokens = len(content) // 4  # CHARS_PER_TOKEN = 4

            if chunker_content_type is not None:
                chunker = IntelligentChunker(max_chunk_tokens=512, overlap_pct=0.15)
                chunk_results = chunker.chunk(
                    content, file_path="", content_type=chunker_content_type
                )

                if len(chunk_results) > 1:
                    # Multiple chunks — expand batch with all chunks
                    logger.info(
                        "batch_content_chunked_for_storage",
                        extra={
                            "memory_type": memory_type.value,
                            "num_chunks": len(chunk_results),
                            "original_length": len(content),
                        },
                    )
                    # Process all chunks from this memory
                    for _chunk_idx, chunk_result in enumerate(chunk_results):
                        chunk_memory_id = str(uuid.uuid4())
                        chunk_hash = compute_content_hash(chunk_result.content)

                        chunk_payload = MemoryPayload(
                            content=chunk_result.content,
                            content_hash=chunk_hash,
                            group_id=memory["group_id"],
                            type=memory["type"],
                            source_hook=memory["source_hook"],
                            session_id=memory["session_id"],
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            created_at=created_at,
                            embedding_status=embedding_status,
                        )

                        # Build chunking_metadata from ChunkResult.metadata
                        chunking_metadata = {
                            "chunk_type": chunk_result.metadata.chunk_type,
                            "chunk_index": chunk_result.metadata.chunk_index,
                            "total_chunks": chunk_result.metadata.total_chunks,
                            "chunk_size_tokens": chunk_result.metadata.chunk_size_tokens,
                            "overlap_tokens": chunk_result.metadata.overlap_tokens,
                            "original_size_tokens": original_size_tokens,
                            "truncated": False,  # Always False in v2.1 (zero-truncation principle)
                        }

                        # Add optional source metadata if available
                        if chunk_result.metadata.source_file:
                            chunking_metadata["source_file"] = (
                                chunk_result.metadata.source_file
                            )
                        if chunk_result.metadata.start_line is not None:
                            chunking_metadata["start_line"] = (
                                chunk_result.metadata.start_line
                            )
                        if chunk_result.metadata.end_line is not None:
                            chunking_metadata["end_line"] = (
                                chunk_result.metadata.end_line
                            )
                        if chunk_result.metadata.section_header:
                            chunking_metadata["section_header"] = (
                                chunk_result.metadata.section_header
                            )

                        # Convert payload to dict and add chunking_metadata
                        chunk_payload_dict = chunk_payload.to_dict()
                        chunk_payload_dict["chunking_metadata"] = chunking_metadata

                        # Collect for batch embedding (avoid N+1 API calls)
                        pending_chunks.append((chunk_memory_id, chunk_payload_dict, mem_model))
                        results.append(
                            {
                                "memory_id": chunk_memory_id,
                                "status": "stored",
                                "embedding_status": embedding_status.value,
                            }
                        )
                    # Skip normal processing for this memory (already handled)
                    continue
                else:
                    # Single chunk — re-embed the chunk content for correctness
                    # (pre-computed embedding was for original content before chunking)
                    chunk_result = chunk_results[0]
                    chunk_memory_id = str(uuid.uuid4())
                    chunk_hash = compute_content_hash(chunk_result.content)

                    chunk_payload = MemoryPayload(
                        content=chunk_result.content,
                        content_hash=chunk_hash,
                        group_id=memory["group_id"],
                        type=memory["type"],
                        source_hook=memory["source_hook"],
                        session_id=memory["session_id"],
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        created_at=created_at,
                        embedding_status=embedding_status,
                    )

                    chunk_payload_dict = chunk_payload.to_dict()
                    chunk_payload_dict["chunking_metadata"] = {
                        "chunk_type": "whole",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "chunk_size_tokens": original_size_tokens,
                        "overlap_tokens": 0,
                        "original_size_tokens": original_size_tokens,
                        "truncated": False,
                    }

                    pending_chunks.append((chunk_memory_id, chunk_payload_dict, mem_model))
                    results.append(
                        {
                            "memory_id": chunk_memory_id,
                            "status": "stored",
                            "embedding_status": embedding_status.value,
                        }
                    )
                    continue

            content_hash = compute_content_hash(content)

            payload = MemoryPayload(
                content=content,
                content_hash=content_hash,
                group_id=memory["group_id"],
                type=memory["type"],  # Already a string from dict
                source_hook=memory["source_hook"],
                session_id=memory["session_id"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                created_at=created_at,
                embedding_status=embedding_status,
            )

            # Add whole-content metadata for non-chunked memories
            payload_dict = payload.to_dict()
            payload_dict["chunking_metadata"] = {
                "chunk_type": "whole",
                "chunk_index": 0,
                "total_chunks": 1,
                "chunk_size_tokens": original_size_tokens,
                "overlap_tokens": 0,
                "original_size_tokens": original_size_tokens,
                "truncated": False,
            }

            points.append(
                PointStruct(id=memory_id, vector=embedding, payload=payload_dict)
            )
            results.append(
                {
                    "memory_id": memory_id,
                    "status": "stored",
                    "embedding_status": embedding_status.value,
                }
            )

        # Pass 2: Batch-embed all chunk contents, grouped by model
        # SPEC-010: Each chunk uses its parent memory's embedding model
        if pending_chunks:
            # Group chunks by model for efficient batch embedding
            chunk_model_groups = defaultdict(list)  # model -> [(index, chunk_id, payload)]
            for idx, (chunk_id, chunk_payload_dict, chunk_model) in enumerate(pending_chunks):
                chunk_model_groups[chunk_model].append((idx, chunk_id, chunk_payload_dict))

            chunk_embeddings = [None] * len(pending_chunks)
            for c_model, c_items in chunk_model_groups.items():
                c_indices, c_ids, c_payloads = zip(*c_items)
                c_contents = [p["content"] for p in c_payloads]
                try:
                    c_embs = self.embedding_client.embed(list(c_contents), model=c_model)
                except EmbeddingError:
                    c_embs = [[0.0] * 768 for _ in c_contents]
                for c_idx, c_emb in zip(c_indices, c_embs):
                    chunk_embeddings[c_idx] = c_emb

            for (chunk_id, chunk_payload_dict, _), chunk_emb in zip(
                pending_chunks, chunk_embeddings, strict=True
            ):
                points.append(
                    PointStruct(
                        id=chunk_id,
                        vector=chunk_emb,
                        payload=chunk_payload_dict,
                    )
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
                    component="qdrant",
                    error_code="QDRANT_UNAVAILABLE",
                    project=(
                        memories[0].get("group_id", "unknown")
                        if memories
                        else "unknown"
                    ),
                ).inc()

            raise QdrantUnavailable(f"Failed to batch store memories: {e}") from e

    def get_by_id(self, memory_id: str, collection: str = "discussions") -> dict | None:
        """Retrieve a memory by its Qdrant point ID.

        Args:
            memory_id: The Qdrant point ID (UUID string)
            collection: Which collection to search (default: discussions)

        Returns:
            Memory payload dict if found, None if not found

        Raises:
            QdrantUnavailable: If Qdrant connection fails (not for "not found")

        Note:
            No group_id filter needed - point IDs are unique within collection.
            Returns None only when memory genuinely doesn't exist.
            Raises exception on connection/server errors to allow caller handling.
        """
        try:
            # Use Qdrant retrieve API
            points = self.qdrant_client.retrieve(
                collection_name=collection,
                ids=[memory_id],
                with_payload=True,
                with_vectors=False,
            )

            if points:  # Simplified: truthy check is sufficient
                point = points[0]
                return {"id": str(point.id), **point.payload}
            return None

        except Exception as e:
            # Don't swallow errors - let caller decide how to handle
            logger.error(
                "get_by_id_failed",
                extra={
                    "memory_id": memory_id,
                    "collection": collection,
                    "error": str(e),
                },
            )
            raise QdrantUnavailable(
                f"Failed to retrieve memory {memory_id}: {e}"
            ) from e

    def _check_duplicate(
        self, content_hash: str, collection: str, group_id: str
    ) -> str | None:
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
            >>> storage._check_duplicate("abc123...", "code-patterns", "my-project")
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
                        action="skipped_duplicate",
                        collection=collection,
                        project=group_id,  # group_id is required param, always has value
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
    config: MemoryConfig | None = None,
    **kwargs,
) -> dict:
    """Store best practice accessible from all projects.

    Implements AC 4.3.1 (Best Practices Storage) and FR16 (Cross-Project Sharing).

    Best practices use a special 'shared' group_id marker and are stored
    in the 'conventions' collection for cross-project accessibility.

    Unlike code-patterns (Story 4.2), best practices:
    - Use group_id="shared" (not project-specific)
    - Stored in 'conventions' collection (not 'code-patterns')
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
            - collection: Always "conventions"

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
        'conventions'

    Note:
        Unlike code-patterns, best practices don't require 'cwd' parameter
        since they're intentionally shared across all projects.

    2026 Best Practice Rationale:
        Per Qdrant Multitenancy Guide (https://qdrant.tech/articles/multitenancy/),
        Qdrant is designed to excel in single collection with vast number of
        tenants. However, when data is not homogenous (different semantics,
        different retrieval patterns), separate collections are appropriate.

        - CORRECT: code-patterns (project-specific) vs conventions (shared)
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
            collection="conventions",  # CRITICAL: Separate from code-patterns
            memory_type=MemoryType.GUIDELINE,  # Differentiates from code-patterns
            session_id=session_id,
            source_hook=source_hook,
            **kwargs,
        )

        # Enhance result with explicit markers
        result["group_id"] = "shared"
        result["collection"] = "conventions"

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


def update_point_payload(
    collection: str,
    point_id: str,
    payload_updates: dict,
    config: MemoryConfig | None = None,
) -> bool:
    """Update payload fields on an existing Qdrant point.

    Used by TECH-DEBT-069 classification worker to persist classification results.

    Args:
        collection: Collection name (code-patterns, conventions, discussions)
        point_id: Point UUID to update
        payload_updates: Dictionary of payload fields to update/add
        config: Optional config (uses default if not provided)

    Returns:
        True if successful, False otherwise

    Raises:
        ValueError: If collection or point_id is invalid

    Example:
        >>> update_point_payload(
        ...     collection="code-patterns",
        ...     point_id="abc-123",
        ...     payload_updates={
        ...         "type": "error_fix",
        ...         "classification_confidence": 0.92,
        ...         "classified_at": "2026-01-24T10:00:00Z"
        ...     }
        ... )
        True
    """
    if not collection or not point_id:
        raise ValueError("collection and point_id are required")

    if config is None:
        config = get_config()

    try:
        client = get_qdrant_client(config)

        client.set_payload(
            collection_name=collection,
            payload=payload_updates,
            points=[point_id],
        )

        logger.info(
            "point_payload_updated",
            extra={
                "collection": collection,
                "point_id": point_id,
                "fields_updated": list(payload_updates.keys()),
            },
        )
        return True

    except QdrantUnavailable as e:
        logger.error(
            "qdrant_unavailable_during_update",
            extra={"collection": collection, "point_id": point_id, "error": str(e)},
        )
        return False

    except Exception as e:
        logger.error(
            "point_payload_update_failed",
            extra={
                "collection": collection,
                "point_id": point_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        return False
