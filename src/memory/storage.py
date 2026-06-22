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
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    SparseVector,
)

from .chunking import ContentType, IntelligentChunker
from .config import (
    COLLECTION_DISCUSSIONS,
    COLLECTION_JIRA_DATA,
    COLLECTION_NAMES,
    MemoryConfig,
    get_config,
)
from .embeddings import EmbeddingClient, EmbeddingError
from .models import EmbeddingStatus, MemoryPayload, MemoryType
from .qdrant_client import QdrantUnavailable, get_qdrant_client
from .stats import get_last_updated as _get_last_updated
from .stats import get_unique_field_values as _get_unique_field_values
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

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4, §7.7
# SDK VERSION: V4. Path A files use emit_trace_event() only — no direct langfuse import.
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)
try:
    from .trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000

__all__ = ["MemoryStorage", "store_best_practice", "update_point_payload"]

logger = logging.getLogger("ai_memory.storage")


def _embedding_inflight_envelope() -> int:
    """The embedding service's memory-safety ceiling on concurrent in-flight texts.

    Mirrors ``EMBEDDING_SAFE_INFLIGHT_TEXTS`` in ``docker/embedding/main.py`` (default
    48). The service bounds the SUM of batch sizes of all requests concurrently holding
    an inference slot to this value, and (BUG-327) permanently 413s a lone request whose
    own batch exceeds it. Floored at 1.
    """
    return max(1, int(os.getenv("EMBEDDING_SAFE_INFLIGHT_TEXTS", "48")))


def _client_embed_batch_ceiling() -> int:
    """Max texts the client may send in one embed/embed_sparse request.

    BUG-327: every client embed call sub-batches to <= the embedding service's in-flight
    work envelope so a lone batch can never breach the container memory cap (and never
    earns the service's permanent 413). The ceiling is the tightest of three knobs:

      - ``EMBEDDING_SAFE_INFLIGHT_TEXTS`` — memory-safety ceiling (default 48). GOVERNS.
      - ``EMBEDDING_CLIENT_SUBBATCH``     — throughput knob (default 128).
      - ``EMBEDDING_MAX_BATCH_TEXTS``     — server hard per-request upper bound (default 256).

    Relationship: SAFE_INFLIGHT (memory safety) <= CLIENT_SUBBATCH (throughput) <=
    MAX_BATCH_TEXTS (hard upper bound). The 128 -> 48 throughput reduction is the accepted
    cost of memory safety: a lone 128-text batch alone (~6.4 GiB) breaches the 6 GiB cap,
    so TD-689's 128 ceiling was never memory-safe — the memory envelope governs. Floored
    at 1 so a misconfiguration can never produce a zero-size batch.
    """
    return max(
        1,
        min(
            int(os.getenv("EMBEDDING_CLIENT_SUBBATCH", "128")),
            _embedding_inflight_envelope(),
            int(os.getenv("EMBEDDING_MAX_BATCH_TEXTS", "256")),
        ),
    )


def _embed_sparse_subbatched(client: "EmbeddingClient", texts: list) -> list:
    """``embed_sparse`` the texts in envelope-sized sub-batches, preserving order.

    BUG-327: BM25 sparse vectors are per-text independent, so chunking the call and
    concatenating the results is identical to one call — but keeps every request <= the
    in-flight-work envelope. Returns one result per input text, in input order.
    """
    ceiling = _client_embed_batch_ceiling()
    out: list = []
    for start in range(0, len(texts), ceiling):
        out.extend(client.embed_sparse(texts[start : start + ceiling]))
    return out


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

    def _get_embedding_model(
        self, collection: str, content_type: str | None = None
    ) -> str:
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
        *,
        group_id: str,
        collection: str = "code-patterns",
        source_type: str | None = None,
        **extra_fields,
    ) -> dict:
        """Store a memory with explicit project scope and validation.

        Implements AC 1.5.1 (Storage Module Implementation), AC 4.2.1 (Project-Scoped
        Storage), and PLAN-028 P1B / W-09 (required-explicit project scope per
        DEC-PM302-D1 / DEC-PM302-D2).

        Project scope is REQUIRED-EXPLICIT (DEC-PM298-D4 / DEC-PM302-D1 / W-09): the
        caller MUST pass a non-empty ``group_id``. There is no working-directory
        fallback — silent project inference is the cross-project contamination
        vector PLAN-028 P1B exists to close.

        Process:
        1. Validate cwd parameter (non-None)
        2. Validate group_id parameter (non-empty after strip)
        3. Build payload with content_hash
        4. Validate payload
        5. Check for duplicates
        6. Generate embedding (graceful degradation on embedding failure only)
        7. Store in Qdrant

        Args:
            content: Memory content (10-100,000 chars)
            cwd: Current working directory (REQUIRED — used for logging/audit;
                project_id is NOT inferred from cwd)
            memory_type: Type of memory (MemoryType enum)
            source_hook: Hook that captured this (PostToolUse, Stop, SessionStart)
            session_id: Claude session identifier
            group_id: REQUIRED explicit project identifier (keyword-only). Must be a
                non-empty string; there is no auto-detection fallback.
            collection: Qdrant collection name (default: "code-patterns")
            **extra_fields: Additional payload fields (domain, importance, tags, etc.)

        Returns:
            dict with keys:
                - memory_id (str): UUID of stored/matched memory, or None if blocked
                - status (str): One of:
                    - "stored": Successfully stored (content may have been masked for PII)
                    - "blocked": Content blocked due to secrets detection, not stored
                    - "duplicate": Content hash matches existing memory, not re-stored
                - embedding_status (str): "complete" (success), "pending" (embedding
                    service down), or "n/a" (blocked/duplicate)
                - reason (str): Human-readable explanation (present on "blocked" status)

        Raises:
            ValueError: If cwd is None, group_id is missing/empty, or payload
                validation fails.
            QdrantUnavailable: If Qdrant storage backend fails

        Example:
            >>> storage = MemoryStorage()
            >>> result = storage.store_memory(
            ...     content="Implementation code here",
            ...     cwd="/path/to/project",
            ...     memory_type=MemoryType.IMPLEMENTATION,
            ...     source_hook="PostToolUse",
            ...     session_id="sess-456",
            ...     group_id="my-project",
            ... )
            >>> result["status"]
            'stored'
        """
        _store_start = datetime.now(timezone.utc)

        # Validate cwd parameter (AC 4.2.1)
        if cwd is None:
            raise ValueError("cwd parameter is required for project-scoped storage")

        # PLAN-028 P1B (DEC-PM302-D1 / W-09): project scope is required-explicit.
        # Fail loud rather than guess — see the function docstring for rationale.
        if not group_id or not group_id.strip():
            raise ValueError(
                "store_memory requires an explicit project scope (group_id); "
                "refusing to guess. An implicit working-directory fallback risks "
                "cross-project contamination."
            )

        # TECH-DEBT-012 Round 3: Handle created_at timestamp
        created_at = extra_fields.pop("created_at", None)
        if created_at is None:
            created_at = datetime.now(timezone.utc).isoformat()

        # SPEC-009: Security scanning BEFORE chunking
        if self._scanner is not None:
            from .security_scanner import ScanAction

            scan_result = self._scanner.scan(
                content,
                source_type=source_type or "user_session",
                # F1: SOT registry owner/added_by are intentional ownership handles
                # (e.g. @hidden-history). Exempt ONLY the HANDLE pattern for SOT_ENTRY
                # so the derived 5b cache stays byte-faithful; secret-blocking +
                # EMAIL/IP/CC/SSN masking remain active. All other memory types
                # unchanged.
                exempt_handle_pii=(memory_type == MemoryType.SOT_ENTRY),
            )
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
            # v2.0.6 Agent Memory Types (SPEC-015) — enables chunking for oversized agent content
            MemoryType.AGENT_HANDOFF: ContentType.AGENT_RESPONSE,
            MemoryType.AGENT_MEMORY: ContentType.PROSE,
            MemoryType.AGENT_TASK: ContentType.PROSE,
            MemoryType.AGENT_INSIGHT: ContentType.PROSE,
        }
        chunker_content_type = content_type_map.get(memory_type)
        # Note: For USER_MESSAGE/AGENT_RESPONSE, IntelligentChunker handles
        # whole storage (under threshold) or topical chunking (over threshold).
        # For other types, content passes through unchanged (chunked by hooks).

        additional_chunks = []
        chunk_results = None
        if chunker_content_type is not None:
            chunker = IntelligentChunker(
                max_chunk_tokens=512, overlap_pct=0.15, min_chunk_tokens=0
            )
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
            if emit_trace_event:
                _dedup_end = datetime.now(timezone.utc)
                emit_trace_event(
                    event_type="7_store_skip",
                    data={
                        "input": str(content_hash)[:TRACE_CONTENT_MAX],
                        "output": str(existing_id)[:TRACE_CONTENT_MAX],
                        "metadata": {
                            "collection": str(collection),
                            "group_id": str(group_id),
                            "status": "duplicate",
                            "reason": "duplicate",
                        },
                    },
                    session_id=session_id,
                    project_id=group_id,
                    tags=["store", "memory"],
                    start_time=_store_start,
                    end_time=_dedup_end,
                )
            return {
                "memory_id": existing_id,
                "status": "duplicate",
                "embedding_status": "n/a",
            }

        # TD-060: Cross-collection duplicate check
        if self.config.cross_dedup_enabled:
            from .deduplication import cross_collection_duplicate_check

            cross_result = cross_collection_duplicate_check(
                content_hash, group_id, collection, client=self.qdrant_client
            )
            if cross_result.is_duplicate:
                logger.info(
                    "cross_collection_duplicate_skipped",
                    extra={
                        "content_hash": content_hash,
                        "group_id": group_id,
                        "found_collection": cross_result.found_collection,
                        "existing_id": cross_result.existing_id,
                    },
                )
                if emit_trace_event:
                    _cross_dedup_end = datetime.now(timezone.utc)
                    emit_trace_event(
                        event_type="7_store_skip",
                        data={
                            "input": str(content_hash)[:TRACE_CONTENT_MAX],
                            "output": str(cross_result.existing_id)[:TRACE_CONTENT_MAX],
                            "metadata": {
                                "collection": str(collection),
                                "group_id": str(group_id),
                                "status": "duplicate",
                                "reason": "duplicate",
                                "found_collection": str(cross_result.found_collection),
                            },
                        },
                        session_id=session_id,
                        project_id=group_id,
                        tags=["store", "memory"],
                        start_time=_store_start,
                        end_time=_cross_dedup_end,
                    )
                return {
                    "memory_id": cross_result.existing_id,
                    "status": "duplicate",
                    "embedding_status": "n/a",
                }

        # Generate embedding with graceful degradation (AC 1.5.4)
        # SPEC-010: Route to appropriate model based on collection and content type
        embedding_model = self._get_embedding_model(
            collection, extra_fields.get("content_type")
        )
        try:
            embeddings = self.embedding_client.embed([content], model=embedding_model)
            embedding = embeddings[0]
            payload.embedding_status = EmbeddingStatus.COMPLETE
            logger.debug(
                "embedding_generated",
                extra={
                    "content_hash": content_hash,
                    "dimensions": len(embedding),
                    "model": embedding_model,
                },
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
        original_size_tokens = len(content.split())

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

        # Generate sparse vector for hybrid search (T-022)
        if self.config.hybrid_search_enabled:
            try:
                sparse_results = self.embedding_client.embed_sparse([content])
                if isinstance(sparse_results, list) and sparse_results:
                    sr = sparse_results[0]
                    point_vector = {
                        "": embedding,  # Default dense vector
                        "bm25": SparseVector(
                            indices=sr["indices"], values=sr["values"]
                        ),
                    }
                else:
                    point_vector = embedding
            except Exception as e:
                logger.warning(
                    "sparse_embedding_failed",
                    extra={"error": str(e)},
                )
                point_vector = embedding  # Fallback: dense only
        else:
            point_vector = embedding

        try:
            self.qdrant_client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=memory_id,
                        vector=point_vector,
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
                        chunk_embedding = self.embedding_client.embed(
                            [chunk.content], model=embedding_model
                        )[0]
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

                    # Generate sparse vector for chunk (T-022)
                    if self.config.hybrid_search_enabled:
                        try:
                            chunk_sparse = self.embedding_client.embed_sparse(
                                [chunk.content]
                            )
                            if isinstance(chunk_sparse, list) and chunk_sparse:
                                csr = chunk_sparse[0]
                                chunk_point_vector = {
                                    "": chunk_embedding,
                                    "bm25": SparseVector(
                                        indices=csr["indices"],
                                        values=csr["values"],
                                    ),
                                }
                            else:
                                chunk_point_vector = chunk_embedding
                        except Exception as e:
                            logger.warning(
                                "chunk_sparse_embedding_failed",
                                extra={"error": str(e)},
                            )
                            chunk_point_vector = chunk_embedding
                    else:
                        chunk_point_vector = chunk_embedding

                    additional_points.append(
                        PointStruct(
                            id=chunk_id,
                            vector=chunk_point_vector,
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

            # TD-317: Trace event for store operation (after all chunks stored)
            _store_end = datetime.now(timezone.utc)
            if emit_trace_event:
                emit_trace_event(
                    event_type="7_store",
                    data={
                        "input": str(content_hash)[:TRACE_CONTENT_MAX],
                        "output": str(memory_id)[:TRACE_CONTENT_MAX],
                        "metadata": {
                            "collection": str(collection),
                            "group_id": str(group_id),
                            "status": "stored",
                            "content_length": str(len(content)),
                        },
                    },
                    session_id=session_id,
                    project_id=group_id,
                    tags=["store", "memory"],
                    start_time=_store_start,
                    end_time=_store_end,
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
        *,
        group_id: str,
        collection: str = "code-patterns",
        source_type: str | None = None,
    ) -> list[dict]:
        """Store multiple memories in batch for efficiency.

        Implements AC 1.5.2 (Batch Storage Support), AC 4.2.1 (Project-Scoped
        Storage), and PLAN-028 P1B / W-09 (required-explicit project scope per
        DEC-PM302-D1 / DEC-PM302-D2).

        Project scope is REQUIRED-EXPLICIT (DEC-PM298-D4 / DEC-PM302-D1 / W-09):
        the caller MUST pass a non-empty ``group_id``. There is no
        working-directory fallback. Per-item ``group_id`` keys are honored if
        present (and validated non-empty); the batch-level ``group_id`` is the
        default for items that omit it.

        Batch operations:
        - Validate caller-supplied default group_id (non-empty)
        - Apply default group_id to memories missing it; validate each item's
          group_id is non-empty after the merge
        - Validate all payloads upfront
        - Generate embeddings in single batch request (2025/2026 best practice)
        - Store all memories in single Qdrant upsert

        Note:
            Batch storage does NOT check for duplicates. Use store_memory() for
            deduplication support, or ensure content uniqueness before batch calls.

        Args:
            memories: List of memory dictionaries, each with keys:
                - content: str
                - group_id: str (optional — defaults to batch-level group_id)
                - type: str (MemoryType value)
                - source_hook: str
                - session_id: str
            group_id: REQUIRED explicit project identifier (keyword-only).
                Applied to any memory dict lacking its own group_id.
            collection: Qdrant collection name (default: "code-patterns")
            source_type: Origin of content. Defaults to "user_session" (highest scrutiny).
                         Use "github_*" for GitHub-sourced content (relaxed mode skips L2).

        Returns:
            List of result dictionaries, one per input memory, with:
                - memory_id: UUID string
                - status: "stored"
                - embedding_status: "complete" or "pending"

        Raises:
            ValueError: If group_id is missing/empty, any per-item group_id is
                empty, or any payload validation fails.
            QdrantUnavailable: If Qdrant is unreachable

        Example:
            >>> storage = MemoryStorage()
            >>> memories = [
            ...     {"content": "Code 1", "type": "implementation",
            ...      "source_hook": "PostToolUse", "session_id": "sess"},
            ...     {"content": "Code 2", "type": "implementation",
            ...      "source_hook": "PostToolUse", "session_id": "sess"},
            ... ]
            >>> results = storage.store_memories_batch(memories, group_id="my-project")
            >>> len(results)
            2
        """
        _batch_store_start = datetime.now(timezone.utc)

        if not memories:
            return []

        # PLAN-028 P1B (DEC-PM302-D1 / W-09): project scope is required-explicit.
        if not group_id or not group_id.strip():
            raise ValueError(
                "store_memories_batch requires an explicit project scope "
                "(group_id); refusing to guess. An implicit working-directory "
                "fallback risks cross-project contamination."
            )

        # Shallow copy to avoid mutating caller's dicts (F-15)
        memories = [dict(m) for m in memories]

        points = []
        results = []

        # Apply default group_id to memories missing it; validate every item's
        # final group_id is non-empty (per-item override is allowed but must be
        # a valid project id, never "" or None).
        for memory in memories:
            if "group_id" not in memory or memory.get("group_id") is None:
                memory["group_id"] = group_id
            item_gid = memory.get("group_id")
            if not isinstance(item_gid, str) or not item_gid.strip():
                raise ValueError(
                    "store_memories_batch: per-item group_id must be a non-empty "
                    "string; refusing to guess project scope. Offending memory: "
                    f"content_hash={memory.get('content_hash', '<unhashed>')}"
                )

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
                # Intentionally omits exempt_handle_pii: SOT uses per-row store_memory; batching SOT rows would silently re-redact owner handles.
                scan_result = self._scanner.scan(
                    memory["content"],
                    force_ner=True,
                    source_type=source_type or "user_session",
                )

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
                    results.append(
                        {
                            "memory_id": None,
                            "status": "blocked",
                            "reason": "secrets_detected",
                            "embedding_status": "n/a",
                        }
                    )
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
        for idx, (memory, model) in enumerate(
            zip(memories, memory_models, strict=True)
        ):
            model_groups[model].append((idx, memory["content"]))

        embeddings = [None] * len(memories)
        embedding_status = EmbeddingStatus.COMPLETE
        # TD-689 / BUG-327: sub-batch each model group client-side so a large batch never
        # exceeds the embedding service's in-flight-work envelope. The ceiling is the
        # tightest of EMBEDDING_CLIENT_SUBBATCH (throughput), EMBEDDING_SAFE_INFLIGHT_TEXTS
        # (memory-safety, governs at 48), and EMBEDDING_MAX_BATCH_TEXTS (server hard upper
        # bound) — see _client_embed_batch_ceiling. Emitting batches <= the envelope is the
        # contract the server's lone-request ADMIT (and its over-envelope 413) is built on.
        embed_ceiling = _client_embed_batch_ceiling()
        try:
            for model, items in model_groups.items():
                indices, contents = zip(*items, strict=True)
                contents = list(contents)
                group_embeddings = []
                for start in range(0, len(contents), embed_ceiling):
                    group_embeddings.extend(
                        self.embedding_client.embed(
                            contents[start : start + embed_ceiling], model=model
                        )
                    )
                for orig_idx, emb in zip(indices, group_embeddings, strict=True):
                    embeddings[orig_idx] = emb

            logger.debug(
                "batch_embeddings_generated",
                extra={"count": len(memories), "models": list(model_groups.keys())},
            )

        except EmbeddingError as e:
            # Graceful degradation: Use zero vectors for all
            logger.warning(
                "batch_embedding_failed",
                extra={
                    "error": str(e),
                    "count": len(memories),
                    "models": list(model_groups.keys()),
                },
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

        # NI-V3-004: Validate non-zero embeddings AFTER error recovery
        # (moved outside try/except so it validates final embeddings, not pre-recovery)
        for i, vec in enumerate(embeddings):
            if vec is not None and (not vec or all(v == 0.0 for v in vec)):
                logger.warning(
                    "degenerate_zero_vector_in_batch",
                    extra={
                        "index": i,
                        "text_length": len(memories[i].get("content", "")),
                    },
                )
                embedding_status = EmbeddingStatus.PENDING

        # F-14: Guard against None embeddings from partial service responses
        for idx, emb in enumerate(embeddings):
            if emb is None:
                logger.warning(
                    "embedding_missing_in_batch",
                    extra={
                        "context": {
                            "index": idx,
                            "memory_type": memories[idx].get("type", "unknown"),
                        }
                    },
                )
                embeddings[idx] = [0.0] * 768
                embedding_status = EmbeddingStatus.PENDING

        # Collect chunk data for batch embedding (avoid N+1 API calls)
        pending_chunks = []
        # Collect non-chunked points for batch sparse embedding (avoid N+1 API calls)
        pending_main_points = []

        # Build points for batch upsert
        for memory, embedding, mem_model in zip(
            memories, embeddings, memory_models, strict=True
        ):
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
                # v2.0.6 Agent Memory Types (SPEC-015)
                MemoryType.AGENT_HANDOFF: ContentType.AGENT_RESPONSE,
                MemoryType.AGENT_MEMORY: ContentType.PROSE,
                MemoryType.AGENT_TASK: ContentType.PROSE,
                MemoryType.AGENT_INSIGHT: ContentType.PROSE,
            }
            chunker_content_type = content_type_map.get(memory_type)
            # Note: For USER_MESSAGE/AGENT_RESPONSE, IntelligentChunker handles
            # whole storage (under threshold) or topical chunking (over threshold).
            # For other types, content passes through unchanged (chunked by hooks).

            # Calculate original size for chunking_metadata
            original_size_tokens = len(content.split())

            if chunker_content_type is not None:
                chunker = IntelligentChunker(
                    max_chunk_tokens=512, overlap_pct=0.15, min_chunk_tokens=0
                )
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
                        pending_chunks.append(
                            (chunk_memory_id, chunk_payload_dict, mem_model)
                        )
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

                    pending_chunks.append(
                        (chunk_memory_id, chunk_payload_dict, mem_model)
                    )
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

            # Stage point for sparse embedding (deferred to batch call below)
            pending_main_points.append((memory_id, embedding, payload_dict, content))
            results.append(
                {
                    "memory_id": memory_id,
                    "status": "stored",
                    "embedding_status": embedding_status.value,
                }
            )

        # Batch sparse embeddings for non-chunked main points (T-022, avoid N+1 calls)
        if pending_main_points and self.config.hybrid_search_enabled:
            main_contents = [c for _, _, _, c in pending_main_points]
            try:
                # BUG-327: sub-batch to <= the in-flight-work envelope (was unbounded).
                main_sparse_results = _embed_sparse_subbatched(
                    self.embedding_client, main_contents
                )
            except Exception as e:
                logger.warning(
                    "batch_sparse_embedding_failed",
                    extra={"error": str(e), "count": len(main_contents)},
                )
                main_sparse_results = None

            for i, (mid, emb, pdict, _content) in enumerate(pending_main_points):
                if (
                    isinstance(main_sparse_results, list)
                    and i < len(main_sparse_results)
                    and main_sparse_results[i]
                ):
                    bsr = main_sparse_results[i]
                    point_vector = {
                        "": emb,
                        "bm25": SparseVector(
                            indices=bsr["indices"], values=bsr["values"]
                        ),
                    }
                else:
                    point_vector = emb
                points.append(PointStruct(id=mid, vector=point_vector, payload=pdict))
        else:
            for mid, emb, pdict, _content in pending_main_points:
                points.append(PointStruct(id=mid, vector=emb, payload=pdict))

        # Pass 2: Batch-embed all chunk contents, grouped by model
        # SPEC-010: Each chunk uses its parent memory's embedding model
        if pending_chunks:
            # Group chunks by model for efficient batch embedding
            chunk_model_groups = defaultdict(
                list
            )  # model -> [(index, chunk_id, payload)]
            for idx, (chunk_id, chunk_payload_dict, chunk_model) in enumerate(
                pending_chunks
            ):
                chunk_model_groups[chunk_model].append(
                    (idx, chunk_id, chunk_payload_dict)
                )

            chunk_embeddings = [None] * len(pending_chunks)
            for c_model, c_items in chunk_model_groups.items():
                c_indices, _c_ids, c_payloads = zip(*c_items, strict=True)
                c_contents = [p["content"] for p in c_payloads]
                try:
                    # BUG-327: sub-batch to <= the in-flight-work envelope (was unbounded).
                    c_embs = []
                    for start in range(0, len(c_contents), embed_ceiling):
                        c_embs.extend(
                            self.embedding_client.embed(
                                c_contents[start : start + embed_ceiling], model=c_model
                            )
                        )
                except EmbeddingError:
                    c_embs = [[0.0] * 768 for _ in c_contents]
                for c_idx, c_emb in zip(c_indices, c_embs, strict=True):
                    chunk_embeddings[c_idx] = c_emb

            # Batch sparse embeddings for all chunks (T-022, avoid N+1 calls)
            chunk_sparse_results = None
            if self.config.hybrid_search_enabled:
                all_chunk_contents = [pd["content"] for _, pd, _ in pending_chunks]
                try:
                    # BUG-327: sub-batch to <= the in-flight-work envelope (was unbounded).
                    chunk_sparse_results = _embed_sparse_subbatched(
                        self.embedding_client, all_chunk_contents
                    )
                except Exception as e:
                    logger.warning(
                        "batch_chunk_sparse_embedding_failed",
                        extra={"error": str(e), "count": len(all_chunk_contents)},
                    )

            for ci, ((chunk_id, chunk_payload_dict, _), chunk_emb) in enumerate(
                zip(pending_chunks, chunk_embeddings, strict=True)
            ):
                if (
                    isinstance(chunk_sparse_results, list)
                    and ci < len(chunk_sparse_results)
                    and chunk_sparse_results[ci]
                ):
                    bcsr = chunk_sparse_results[ci]
                    bc_point_vector = {
                        "": chunk_emb,
                        "bm25": SparseVector(
                            indices=bcsr["indices"],
                            values=bcsr["values"],
                        ),
                    }
                else:
                    bc_point_vector = chunk_emb

                points.append(
                    PointStruct(
                        id=chunk_id,
                        vector=bc_point_vector,
                        payload=chunk_payload_dict,
                    )
                )

        # Store in sub-batches to avoid Qdrant gRPC 64MB limit (F-13)
        _UPSERT_BATCH_SIZE = 64
        try:
            for i in range(0, len(points), _UPSERT_BATCH_SIZE):
                sub_batch = points[i : i + _UPSERT_BATCH_SIZE]
                self.qdrant_client.upsert(collection_name=collection, points=sub_batch)

            logger.info(
                "batch_stored",
                extra={
                    "count": len(points),
                    "collection": collection,
                    "embedding_status": embedding_status.value,
                },
            )

            # TD-317: Trace event for batch store operation
            _batch_store_end = datetime.now(timezone.utc)
            if emit_trace_event:
                emit_trace_event(
                    event_type="7_store",
                    data={
                        "input": f"batch({len(points)} points)"[:TRACE_CONTENT_MAX],
                        "output": f"stored {len(points)} points"[:TRACE_CONTENT_MAX],
                        "metadata": {
                            "collection": str(collection),
                            "group_id": str(group_id),
                            "status": "stored",
                            "point_count": str(len(points)),
                        },
                    },
                    session_id=os.environ.get("CLAUDE_SESSION_ID"),
                    project_id=group_id,
                    tags=["store", "memory"],
                    start_time=_batch_store_start,
                    end_time=_batch_store_end,
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

    def store_github_code_blob_chunks_batch(
        self,
        chunk_items: list[dict[str, Any]],
        *,
        cwd: str,
        collection: str,
        group_id: str,
        memory_type: MemoryType,
        source_hook: str,
        session_id: str,
        chunk_batch_size: int = 8,
    ) -> list[dict]:
        """Store pre-chunked GitHub code blobs with batched embeddings and upserts.

        Skips IntelligentChunker and duplicate checks (callers already chunked;
        code_sync performs security scan). Sub-batches embedding so one slow
        batch degrades to pending vectors without failing prior sub-batches.

        Args:
            chunk_items: One dict per chunk; must include ``content`` and GitHub
                payload fields (``file_path``, ``blob_hash``, ``chunk_index``, etc.).
            cwd: Working directory (REQUIRED — used for logging/audit; project
                scope is NOT inferred from cwd).
            collection: Qdrant collection (typically ``github``).
            group_id: REQUIRED non-empty repository / project id (keyword-only).
                Applied to all points unless overridden per item; per-item values
                must also be non-empty.
            memory_type: ``MemoryType.GITHUB_CODE_BLOB``.
            source_hook: e.g. ``github_code_sync``.
            session_id: Sync batch / session id.
            chunk_batch_size: Max chunks per embed + upsert sub-batch.

        Returns:
            One result dict per input chunk (``memory_id``, ``status``, ``embedding_status``).

        Raises:
            ValueError: If ``cwd`` is None or ``group_id`` is missing/empty
                (PLAN-028 P1B / W-09 — DEC-PM302-D1).
        """
        _blob_store_start = datetime.now(timezone.utc)

        if not chunk_items:
            return []

        if cwd is None:
            raise ValueError("cwd parameter is required for project-scoped storage")

        # PLAN-028 P1B (DEC-PM302-D1 / W-09): project scope is required-explicit.
        if not group_id or not group_id.strip():
            raise ValueError(
                "store_github_code_blob_chunks_batch requires an explicit project "
                "scope (group_id); refusing to guess. An implicit "
                "working-directory fallback risks cross-project contamination."
            )

        default_group_id = group_id

        memory_type_enum = (
            memory_type
            if isinstance(memory_type, MemoryType)
            else MemoryType(memory_type)
        )

        all_out: list[dict] = []
        stored_point_ids: list[str] = []
        # BUG-327: clamp the configured github code-blob batch to the client embed ceiling
        # (the tightest of EMBEDDING_SAFE_INFLIGHT_TEXTS, EMBEDDING_CLIENT_SUBBATCH, and
        # EMBEDDING_MAX_BATCH_TEXTS — see _client_embed_batch_ceiling) so an operator-set
        # github_code_blob_chunk_batch_size (le=128) can never emit an embed/sparse batch
        # the service would 413, INCLUDING the case where a low EMBEDDING_MAX_BATCH_TEXTS
        # (not the envelope) is the binding cap. Matches every other call site's ceiling.
        # The embed + embed_sparse calls below iterate sub_batch_size, so this bounds them
        # to <= the ceiling.
        sub_batch_size = min(max(1, chunk_batch_size), _client_embed_batch_ceiling())
        payload_field_names = {
            field.name for field in dataclasses.fields(MemoryPayload)
        }
        reserved_keys = {
            "timestamp",
            "created_at",
            "content",
            "content_hash",
            "type",
            "source_hook",
            "session_id",
            "group_id",
            "collection",
        }

        def _split_row_fields(
            row: dict[str, Any],
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            payload_kwargs: dict[str, Any] = {}
            extra_payload: dict[str, Any] = {}
            for key, value in row.items():
                if key in reserved_keys:
                    continue
                target = payload_kwargs if key in payload_field_names else extra_payload
                target[key] = value
            return payload_kwargs, extra_payload

        def _build_chunking_metadata(
            content: str, row: dict[str, Any]
        ) -> dict[str, Any]:
            token_count = len(content.split())
            return {
                "chunk_type": "whole",
                "chunk_index": row.get("chunk_index", 0),
                "total_chunks": row.get("total_chunks", 1),
                "chunk_size_tokens": token_count,
                "overlap_tokens": 0,
                "original_size_tokens": token_count,
                "truncated": False,
            }

        def _build_point_vector(
            embedding: list[float], sparse_results: list | None, index: int
        ) -> list[float] | dict[str, Any]:
            if not (
                isinstance(sparse_results, list)
                and index < len(sparse_results)
                and sparse_results[index]
            ):
                return embedding

            sparse_row = sparse_results[index]
            return {
                "": embedding,
                "bm25": SparseVector(
                    indices=sparse_row["indices"], values=sparse_row["values"]
                ),
            }

        try:
            for start in range(0, len(chunk_items), sub_batch_size):
                sub_batch = chunk_items[start : start + sub_batch_size]
                prepared_rows: list[dict[str, Any]] = []

                for raw in sub_batch:
                    row = dict(raw)
                    if row.get("group_id") is None:
                        row["group_id"] = default_group_id
                    # PLAN-028 P1B (DEC-PM302-D1 / W-09): per-item group_id must
                    # be non-empty; never silently coerce to a sentinel.
                    item_gid = row.get("group_id")
                    if not isinstance(item_gid, str) or not item_gid.strip():
                        raise ValueError(
                            "store_github_code_blob_chunks_batch: per-item "
                            "group_id must be a non-empty string; refusing to "
                            "guess project scope. Offending chunk: "
                            f"file_path={row.get('file_path', '<unknown>')} "
                            f"blob_hash={row.get('blob_hash', '<unknown>')}"
                        )
                    row["type"] = memory_type_enum.value
                    row["source_hook"] = source_hook
                    row["session_id"] = session_id
                    row.setdefault("content_type", "github_code_blob")
                    if not row.get("content_hash"):
                        row["content_hash"] = compute_content_hash(row["content"])

                    errs = validate_payload(row)
                    if errs:
                        logger.error(
                            "github_code_blob_batch_validation_failed",
                            extra={"errors": errs, "group_id": row.get("group_id")},
                        )
                        raise ValueError(
                            f"GitHub code blob batch validation failed: {errs}"
                        )
                    prepared_rows.append(row)

                contents = [r["content"] for r in prepared_rows]
                batch_embedding_status = EmbeddingStatus.COMPLETE
                try:
                    embeddings = self.embedding_client.embed(contents, model="code")
                    if len(embeddings) != len(prepared_rows):
                        raise EmbeddingError(
                            "Embedding count mismatch for GitHub code blob batch"
                        )
                except Exception as e:
                    logger.warning(
                        "github_code_blob_batch_embedding_failed",
                        extra={
                            "error": str(e),
                            "count": len(contents),
                            "group_id": default_group_id,
                        },
                    )
                    if failure_events_total:
                        failure_events_total.labels(
                            component="embedding",
                            error_code="EMBEDDING_TIMEOUT",
                            project=default_group_id,
                        ).inc()
                    embeddings = [[0.0] * 768 for _ in contents]
                    batch_embedding_status = EmbeddingStatus.PENDING

                sparse_for_sub: list | None = None
                if self.config.hybrid_search_enabled:
                    try:
                        sparse_for_sub = self.embedding_client.embed_sparse(contents)
                    except Exception as e:
                        logger.warning(
                            "github_code_blob_batch_sparse_failed",
                            extra={"error": str(e), "count": len(contents)},
                        )
                        sparse_for_sub = None

                points: list[PointStruct] = []
                batch_out: list[dict] = []
                for i, row in enumerate(prepared_rows):
                    content = row["content"]
                    created_at = (
                        row.get("created_at") or datetime.now(timezone.utc).isoformat()
                    )
                    gid = row["group_id"]
                    content_hash = row["content_hash"]
                    payload_kwargs, extra_payload = _split_row_fields(row)

                    payload = MemoryPayload(
                        content=content,
                        content_hash=content_hash,
                        group_id=gid,
                        type=memory_type_enum,
                        source_hook=source_hook,
                        session_id=session_id,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        created_at=created_at,
                        embedding_status=batch_embedding_status,
                        **payload_kwargs,
                    )

                    payload_dict = {
                        **payload.to_dict(),
                        **extra_payload,
                        "chunking_metadata": _build_chunking_metadata(content, row),
                    }

                    memory_key = (
                        f"{gid}:{row.get('file_path', '')}:{row.get('blob_hash', '')}:"
                        f"{content_hash}:{row.get('chunk_index', 0)}"
                    )
                    memory_id = str(uuid.uuid5(uuid.NAMESPACE_URL, memory_key))
                    points.append(
                        PointStruct(
                            id=memory_id,
                            vector=_build_point_vector(
                                embeddings[i], sparse_for_sub, i
                            ),
                            payload=payload_dict,
                        )
                    )
                    batch_out.append(
                        {
                            "memory_id": memory_id,
                            "status": "pending",
                            "embedding_status": batch_embedding_status.value,
                        }
                    )

                try:
                    self.qdrant_client.upsert(collection_name=collection, points=points)
                    stored_point_ids.extend(str(point.id) for point in points)
                    for item in batch_out:
                        item["status"] = "stored"
                    logger.info(
                        "github_code_blob_batch_stored",
                        extra={
                            "count": len(points),
                            "collection": collection,
                            "embedding_status": batch_embedding_status.value,
                        },
                    )
                    all_out.extend(batch_out)
                    if memory_captures_total:
                        for _ in points:
                            memory_captures_total.labels(
                                hook_type=source_hook,
                                status="success",
                                project=default_group_id,
                                collection=collection,
                            ).inc()
                except Exception as e:
                    logger.error(
                        "github_code_blob_batch_qdrant_failed",
                        extra={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "count": len(points),
                        },
                    )
                    if failure_events_total:
                        failure_events_total.labels(
                            component="qdrant",
                            error_code="QDRANT_UNAVAILABLE",
                            project=default_group_id,
                        ).inc()
                    if memory_captures_total:
                        for _ in points:
                            memory_captures_total.labels(
                                hook_type=source_hook,
                                status="failed",
                                project=default_group_id,
                                collection=collection,
                            ).inc()
                    raise QdrantUnavailable(
                        f"Failed to batch store GitHub code blobs: {e}"
                    ) from e
        except Exception:
            if stored_point_ids:
                try:
                    self.qdrant_client.delete(
                        collection_name=collection,
                        points_selector=PointIdsList(
                            points=stored_point_ids,
                        ),
                    )
                    logger.warning(
                        "github_code_blob_batch_rolled_back",
                        extra={
                            "context": {
                                "count": len(stored_point_ids),
                                "collection": collection,
                            }
                        },
                    )
                except Exception as rollback_err:
                    logger.error(
                        "github_code_blob_batch_rollback_failed",
                        extra={
                            "context": {
                                "error": str(rollback_err),
                                "point_ids_count": len(stored_point_ids),
                                "collection": collection,
                            }
                        },
                    )
            raise

        # TD-317: Trace event for github code blob batch store
        _blob_store_end = datetime.now(timezone.utc)
        if emit_trace_event:
            emit_trace_event(
                event_type="7_store",
                data={
                    "input": f"github_blob_batch({len(chunk_items)} chunks)"[
                        :TRACE_CONTENT_MAX
                    ],
                    "output": f"stored {len(all_out)} chunks"[:TRACE_CONTENT_MAX],
                    "metadata": {
                        "collection": str(collection),
                        "group_id": str(default_group_id or "unknown"),
                        "status": "stored",
                        "chunk_count": str(len(chunk_items)),
                    },
                },
                session_id=session_id,
                project_id=default_group_id or "unknown",
                tags=["store", "memory"],
                start_time=_blob_store_start,
                end_time=_blob_store_end,
            )

        return all_out

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

    def store_agent_memory(
        self,
        content: str,
        memory_type: str,
        *,
        group_id: str,
        agent_id: str = "parzival",
        session_id: str | None = None,
        cwd: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Store an agent memory to the discussions collection.

        Convenience method that wraps store_memory() with agent-specific
        defaults. Validates memory_type against allowed agent types, sets
        agent_id payload field, and routes to discussions collection.

        Implements PLAN-028 P1B / W-09 (required-explicit project scope per
        DEC-PM302-D1): the caller MUST pass a non-empty ``group_id``. There
        is no cwd-based auto-detection.

        Passes through the full security scanning pipeline (AD-4).
        Chunks if content > 3K tokens (per Chunking-Strategy-V2).

        Args:
            content: Memory content text.
            memory_type: One of: agent_handoff, agent_memory, agent_task,
                agent_insight, decision.
            group_id: REQUIRED explicit project identifier (keyword-only).
            agent_id: Agent identifier (default "parzival").
            session_id: Optional session identifier. Defaults to f"agent_{agent_id}".
            cwd: Working directory (optional — used for logging/audit; project
                scope is NOT inferred from cwd).
            metadata: Additional payload fields to include.

        Returns:
            store_memory() result dict with status, memory_id, embedding_status.

        Raises:
            ValueError: If memory_type is not a valid agent type.
            ValueError: If group_id is missing or empty.
        """
        # TD-519 / D-2-A: "decision" added as first-class allowed type so the
        # /parzival-save-decision skill can emit DEC entries to Qdrant for L2
        # retrieval. Decisions store WHOLE (1 vector, no chunking) per
        # Chunking-Strategy-V2 §3.3 + §7 — guaranteed by content_type_map
        # NOT mapping MemoryType.DECISION (unmapped types skip the chunker).
        VALID_AGENT_TYPES = {
            "agent_handoff",
            "agent_memory",
            "agent_task",
            "agent_insight",
            "decision",
        }
        if memory_type not in VALID_AGENT_TYPES:
            raise ValueError(
                f"Invalid agent memory type: '{memory_type}'. "
                f"Must be one of: {sorted(VALID_AGENT_TYPES)}"
            )

        # PLAN-028 P1B (DEC-PM302-D1 / W-09): project scope is required-explicit.
        if not group_id or not group_id.strip():
            raise ValueError(
                "store_agent_memory requires an explicit project scope "
                "(group_id); refusing to guess."
            )

        extra_fields = {
            "agent_id": agent_id,
        }
        if metadata:
            extra_fields.update(metadata)

        effective_session_id = session_id or f"agent_{agent_id}"

        return self.store_memory(
            content=content,
            cwd=cwd or ".",
            memory_type=MemoryType(memory_type),
            source_hook="parzival_agent",
            session_id=effective_session_id,
            collection=COLLECTION_DISCUSSIONS,
            group_id=group_id,
            **extra_fields,
        )

    def supersede_prior_agent_memories(
        self,
        *,
        group_id: str,
        agent_id: str,
        memory_type: str,
        exclude_memory_id: str | None = None,
        collection: str = COLLECTION_DISCUSSIONS,
    ) -> int:
        """Mark prior agent memories of one type as superseded (is_current=False).

        D4 F-2 (DEC-PM338-D4.2): write-time supersession. The handoff save path
        calls this after storing a new handoff to auto-demote the previous
        handoff(s) for the same agent_id + group_id. Points are flagged in place
        (set_payload), NEVER deleted — the D6 read filter excludes only
        explicitly-superseded points, and deletion would destroy history.

        Only currently-live points are demoted (must_not is_current==False), so
        re-running is idempotent. The just-stored point is left untouched via
        exclude_memory_id.

        Args:
            group_id: Project scope (multi-tenancy isolation).
            agent_id: Agent whose prior memories are superseded.
            memory_type: Memory type to supersede (e.g. "agent_handoff").
            exclude_memory_id: Point id to leave untouched (the new memory).
            collection: Qdrant collection (default discussions).

        Returns:
            Count of points demoted to is_current=False (0 on failure).

        Raises:
            ValueError: if group_id is empty (tenant-isolation guard — an
                unscoped supersede could demote another project's memories).
        """
        if not group_id:
            raise ValueError(
                "supersede_prior_agent_memories requires explicit project scope "
                "(group_id); refusing to run unscoped across all tenants"
            )
        scroll_filter = Filter(
            must=[
                FieldCondition(key="group_id", match=MatchValue(value=group_id)),
                FieldCondition(key="agent_id", match=MatchValue(value=agent_id)),
                FieldCondition(key="type", match=MatchValue(value=memory_type)),
            ],
            must_not=[
                FieldCondition(key="is_current", match=MatchValue(value=False)),
            ],
        )
        ids_to_demote: list = []
        next_offset = None
        try:
            while True:
                points, next_offset = self.qdrant_client.scroll(
                    collection_name=collection,
                    scroll_filter=scroll_filter,
                    limit=128,
                    offset=next_offset,
                    with_payload=False,
                    with_vectors=False,
                )
                ids_to_demote.extend(
                    p.id for p in points if str(p.id) != str(exclude_memory_id)
                )
                if next_offset is None:
                    break
            if ids_to_demote:
                self.qdrant_client.set_payload(
                    collection_name=collection,
                    payload={"is_current": False},
                    points=ids_to_demote,
                )
                logger.info(
                    "agent_memories_superseded",
                    extra={
                        "group_id": group_id,
                        "agent_id": agent_id,
                        "memory_type": memory_type,
                        "count": len(ids_to_demote),
                    },
                )
        except Exception as e:
            logger.warning(
                "supersede_prior_agent_memories_failed",
                extra={
                    "error": str(e),
                    "group_id": group_id,
                    "agent_id": agent_id,
                    "memory_type": memory_type,
                },
            )
            return 0
        return len(ids_to_demote)

    def supersede_memory_by_id(
        self,
        memory_id: str,
        *,
        group_id: str,
        collection: str = COLLECTION_DISCUSSIONS,
    ) -> bool:
        """Mark a single memory point superseded (is_current=False) by id.

        D4 F-2 (DEC-PM338-D4.2): opt-in supersession for the insight save path
        (``--supersedes <id>``). Flags in place (set_payload), never deletes.

        Tenant-safety (RSK-021 / W-02): the shared Qdrant hosts other projects
        (e.g. DocIntel group_id="document-pipeline"). A mistyped/copy-pasted id
        must never demote another project's point. The target is retrieved and
        its ``group_id`` verified against the active project BEFORE demotion;
        a missing point or a cross-project point is a no-op that returns False.

        Args:
            memory_id: Point id to supersede.
            group_id: Active project scope; the point is demoted only if its
                own group_id matches this value.
            collection: Qdrant collection (default discussions).

        Returns:
            True if an in-project point was demoted; False if the point is
            missing, belongs to another project, or the operation failed.

        Raises:
            ValueError: if group_id is empty (tenant-isolation guard).
        """
        if not group_id:
            raise ValueError(
                "supersede_memory_by_id requires explicit project scope "
                "(group_id); refusing to demote a point unscoped"
            )
        try:
            records = self.qdrant_client.retrieve(
                collection_name=collection,
                ids=[memory_id],
                with_payload=True,
                with_vectors=False,
            )
            if not records:
                logger.warning(
                    "supersede_memory_by_id_not_found",
                    extra={"memory_id": memory_id, "group_id": group_id},
                )
                return False
            point_group_id = (records[0].payload or {}).get("group_id")
            if point_group_id != group_id:
                logger.warning(
                    "supersede_memory_by_id_cross_project_blocked",
                    extra={
                        "memory_id": memory_id,
                        "group_id": group_id,
                        "point_group_id": point_group_id,
                    },
                )
                return False
            self.qdrant_client.set_payload(
                collection_name=collection,
                payload={"is_current": False},
                points=[memory_id],
            )
            return True
        except Exception as e:
            logger.warning(
                "supersede_memory_by_id_failed",
                extra={
                    "error": str(e),
                    "memory_id": memory_id,
                    "group_id": group_id,
                },
            )
            return False

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

    def get_collection_stats(self) -> dict:
        """Return point counts and status for all available collections.

        Returns:
            Dict mapping collection name to stats dict with keys:
                - points_count (int)
                - segments_count (int)
                - status (str)

        Example:
            >>> storage = MemoryStorage()
            >>> stats = storage.get_collection_stats()
            >>> stats["code-patterns"]["points_count"]
            150
        """
        stats = {}
        collections_to_check = list(COLLECTION_NAMES)
        # Include jira-data if it exists (conditional collection)
        try:
            self.qdrant_client.get_collection(COLLECTION_JIRA_DATA)
            collections_to_check.append(COLLECTION_JIRA_DATA)
        except Exception:
            pass
        for collection in collections_to_check:
            try:
                info = self.qdrant_client.get_collection(collection)
                stats[collection] = {
                    "points_count": info.points_count,
                    "segments_count": info.segments_count,
                    "status": str(info.status.value) if info.status else "unknown",
                }
            except Exception as e:
                logger.warning(
                    "Failed to get stats for collection %s: %s", collection, e
                )
                stats[collection] = {
                    "points_count": 0,
                    "segments_count": 0,
                    "status": "error",
                }
        return stats

    def get_unique_field_values(
        self, collection: str, field: str, limit: int = 100
    ) -> list[str]:
        """Return unique values for a payload field in a collection.

        Args:
            collection: Qdrant collection name
            field: Payload field name to extract unique values from
            limit: Maximum number of unique values to return (default: 100)

        Returns:
            Sorted list of unique string values for the field

        Example:
            >>> storage = MemoryStorage()
            >>> projects = storage.get_unique_field_values("code-patterns", "group_id")
            >>> print(projects)
            ['proj-a', 'proj-b']
        """
        try:
            return _get_unique_field_values(self.qdrant_client, collection, field)[
                :limit
            ]
        except Exception:
            logger.warning(
                "Failed to get unique field values for %s.%s", collection, field
            )
            return []

    def get_last_updated(self, collection: str) -> str | None:
        """Return the most recent timestamp in a collection.

        Args:
            collection: Qdrant collection name

        Returns:
            ISO 8601 timestamp string of most recent point, or None if empty

        Example:
            >>> storage = MemoryStorage()
            >>> ts = storage.get_last_updated("code-patterns")
            >>> print(ts or "N/A")
            2026-02-24T10:00:00Z
        """
        return _get_last_updated(self.qdrant_client, collection)


# Sentinel passed as `cwd` when group_id is supplied explicitly and store_memory()
# therefore never calls detect_project(). A descriptive string (rather than "")
# keeps logs self-explanatory instead of showing a blank {"cwd": ""}.
_CWD_UNUSED_GROUP_ID_EXPLICIT = "<cwd-unused: group_id supplied explicitly>"


def store_best_practice(
    content: str,
    session_id: str,
    source_hook: str = "manual",
    config: MemoryConfig | None = None,
    group_id: str | None = None,
    **kwargs,
) -> dict:
    """Store a best practice under an explicitly-provided project (project-scoped).

    Implements AC 4.3.1 (Best Practices Storage) and FR16 (Project-Scoped per W-01).

    Best practices are stored in the 'conventions' collection under the caller's
    project group_id, identical to how code-patterns and other collections work.
    The former cross-project "shared" tier was removed in PLAN-028 P1 (W-01).

    Project scope is REQUIRED-EXPLICIT (DEC-PM298-D4 / DEC-PM302-D1 / W-09): the
    caller MUST pass a non-empty group_id. There is no working-directory
    fallback — any implicit cwd/os.getcwd() fallback would silently re-create
    the cross-project contamination PLAN-028 P1 / P1B exist to eliminate. Per
    PLAN-028 P1B (DEC-PM302-D1), detect_project() now itself raises ValueError
    on detection failure (rather than returning a "unknown-project" sentinel),
    making implicit fallbacks impossible at the call-site level too. When
    group_id is absent or empty this function fails loudly with a ValueError.

    Args:
        content: Best practice text content (10-100,000 chars)
        session_id: Current Claude session ID
        source_hook: Hook that captured this best practice (default: "manual")
                     "manual" is used for skill-based or API-driven storage
                     Added in Story 4.3 for explicit best practice capture
        config: Optional MemoryConfig instance. Uses get_config() if not provided.
        group_id: REQUIRED explicit project identifier. Must be a non-empty string;
                  there is no auto-detection fallback (DEC-PM298-D4).
        **kwargs: Additional metadata fields (e.g., domain, tags)

    Returns:
        dict: Storage result with:
            - memory_id: UUID string if stored, None if duplicate
            - status: "stored" or "duplicate"
            - embedding_status: "complete", "pending", or "failed"
            - group_id: The explicitly provided project identifier
            - collection: Always "conventions"

    Raises:
        ValueError: If group_id is missing/empty, or if content validation fails
        QdrantUnavailable: If Qdrant is unreachable (caller should queue)

    Example:
        >>> result = store_best_practice(
        ...     content="Always use type hints in Python 3.10+ for better IDE support",
        ...     session_id="sess-123",
        ...     group_id="my-project",
        ...     source_hook="PostToolUse",
        ...     domain="python"
        ... )
        >>> result["status"]
        'stored'
        >>> result["collection"]
        'conventions'
    """
    # PLAN-028 P1 (DEC-PM298-D4 / W-09): project scope is required-explicit.
    # Fail loud rather than guess — see the function docstring for rationale.
    if not group_id or not group_id.strip():
        raise ValueError(
            "store_best_practice requires an explicit project scope (group_id); "
            "refusing to guess. An implicit working-directory fallback risks "
            "cross-project contamination of the 'conventions' collection."
        )

    try:
        storage = MemoryStorage(config=config)

        # cwd is unused for scoping here: group_id is supplied explicitly, so
        # store_memory() never invokes detect_project(). The named sentinel
        # satisfies store_memory()'s non-None cwd requirement and keeps logs
        # self-explanatory (no blank {"cwd": ""}).
        result = storage.store_memory(
            content=content,
            cwd=_CWD_UNUSED_GROUP_ID_EXPLICIT,
            group_id=group_id,
            collection="conventions",
            memory_type=MemoryType.GUIDELINE,  # Differentiates from code-patterns
            session_id=session_id,
            source_hook=source_hook,
            **kwargs,
        )

        result["collection"] = "conventions"
        result["group_id"] = group_id

        logger.info(
            "best_practice_stored",
            extra={
                "memory_id": result.get("memory_id"),
                "group_id": result.get("group_id"),
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
        ...         "type": "error_pattern",
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
