#!/usr/bin/env python3
"""Background storage script for UserPromptSubmit hook.

Stores user messages to discussions collection with proper deduplication.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx  # For specific exception types

# BUG-010: Tenacity for transient failure retry
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# CR-1.7: Setup path inline (must happen BEFORE any memory.* imports)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# CR-1.2: Use consolidated logging and activity log
from memory.hooks_common import log_to_activity, setup_hook_logging

logger = setup_hook_logging()

# TECH-DEBT-151 Phase 3: Topical chunking for oversized user prompts (V2.1 zero-truncation)
try:
    import tiktoken
    from memory.chunking.prose_chunker import ProseChunker, ProseChunkerConfig
    from memory.validation import compute_content_hash as _compute_chunk_hash

    CHUNKING_AVAILABLE = True
except ImportError:
    CHUNKING_AVAILABLE = False
    logger.warning(
        "chunking_module_unavailable", extra={"module": "memory.chunking.prose_chunker"}
    )

from memory.config import (
    COLLECTION_DISCUSSIONS,
    EMBEDDING_MODEL,
    TYPE_USER_MESSAGE,
    get_config,
)
from memory.project import detect_project
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.queue import queue_operation
from memory.validation import compute_content_hash

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total
except ImportError:
    memory_captures_total = None

# Import Qdrant models
try:
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
    from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
except ImportError:
    PointStruct = None
    Filter = None
    FieldCondition = None
    MatchValue = None
    ApiException = Exception
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception

# CR-1.2: _log_to_activity removed - using consolidated function from hooks_common


def store_user_message(hook_input: dict[str, Any]) -> bool:
    """Store user message to discussions collection.

    Args:
        hook_input: Hook input with session_id, prompt, turn_number

    Returns:
        True if stored successfully, False if queued
    """
    try:
        session_id = hook_input["session_id"]
        prompt = hook_input["prompt"]
        turn_number = hook_input.get("turn_number", 0)
        cwd = os.getcwd()  # Detect project from current directory

        # Detect project name
        group_id = detect_project(cwd)

        # Compute content hash
        content_hash = compute_content_hash(prompt)

        # Build payload (Issue #6: single timestamp for consistency)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "content": prompt,
            "content_hash": content_hash,
            "group_id": group_id,
            "type": TYPE_USER_MESSAGE,
            "source_hook": "UserPromptSubmit",
            "session_id": session_id,
            "timestamp": now,
            "turn_number": turn_number,
            "created_at": now,
            "stored_at": now,
            "embedding_status": "pending",
            "embedding_model": EMBEDDING_MODEL,
            # v2.0.6: Semantic Decay fields
            "decay_score": 1.0,
            "freshness_status": "unverified",
            "source_authority": 0.4,
            "is_current": True,
            "version": 1,
        }

        # Check for duplicate message before storing (CRITICAL FIX: deduplication)
        client = get_qdrant_client()

        existing = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="session_id", match=MatchValue(value=session_id)
                    ),
                    FieldCondition(
                        key="content_hash", match=MatchValue(value=content_hash)
                    ),
                    FieldCondition(
                        key="type", match=MatchValue(value=TYPE_USER_MESSAGE)
                    ),
                ]
            ),
            limit=1,
            with_payload=False,
        )

        if existing[0]:  # Duplicate found
            # CR-1.2: Use consolidated log function
            # BUG-036: Include project name for multi-project visibility
            log_to_activity(
                f"⏭️  UserPrompt skipped: Duplicate [{group_id}]", INSTALL_DIR
            )
            logger.info(
                "duplicate_user_message_skipped",
                extra={
                    "content_hash": content_hash,
                    "session_id": session_id,
                    "turn_number": turn_number,
                },
            )
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="UserPromptSubmit",
                    status="duplicate",
                    project=group_id or "unknown",
                    collection="discussions",
                ).inc()
            return True

        # Generate deterministic UUID scoped to session (Fix #2: makes upsert idempotent)
        # Session-scoped: same session + same content = same ID (prevents TOCTOU race)
        # Different sessions with same content get different IDs (prevents cross-session overwrite)
        memory_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{session_id}:{content_hash}"))

        # CR-1.5: Use config constant instead of magic number
        config = get_config()

        # Issue #3: Early return for empty content - no point embedding whitespace
        if not prompt or not prompt.strip():
            logger.info("empty_content_skipped", extra={"session_id": session_id})
            return True

        # SPEC-009: Security scanning (Layers 1+2 only for hooks, ~10ms overhead)
        if config.security_scanning_enabled:
            try:
                from memory.security_scanner import SecurityScanner, ScanAction

                scanner = SecurityScanner(enable_ner=False)
                scan_result = scanner.scan(prompt, source_type="user_session")

                if scan_result.action == ScanAction.BLOCKED:
                    # Secrets detected - block storage entirely
                    log_to_activity(
                        f"🚫 UserPrompt blocked: Secrets detected [{group_id}]",
                        INSTALL_DIR,
                    )
                    logger.warning(
                        "user_prompt_blocked_secrets",
                        extra={
                            "session_id": session_id,
                            "findings": len(scan_result.findings),
                            "scan_duration_ms": scan_result.scan_duration_ms,
                        },
                    )
                    if memory_captures_total:
                        memory_captures_total.labels(
                            hook_type="UserPromptSubmit",
                            status="blocked",
                            project=group_id or "unknown",
                            collection="discussions",
                        ).inc()
                    return True  # Exit early, do not store

                elif scan_result.action == ScanAction.MASKED:
                    # PII detected and masked
                    prompt = scan_result.content
                    logger.info(
                        "user_prompt_pii_masked",
                        extra={
                            "session_id": session_id,
                            "findings": len(scan_result.findings),
                            "scan_duration_ms": scan_result.scan_duration_ms,
                        },
                    )

                # PASSED: No sensitive data, continue with original content

            except ImportError:
                logger.warning(
                    "security_scanner_unavailable", extra={"hook": "UserPromptSubmit"}
                )
            except Exception as e:
                logger.error(
                    "security_scan_failed",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "hook": "UserPromptSubmit",
                    },
                )
                # Continue with original content if scanner fails

        # TECH-DEBT-151 Phase 3: Zero-truncation — chunk if over 2000 tokens
        # Per Chunking-Strategy-V2.md V2.1 Section 2.4
        chunks_to_store = []  # List of (content, chunking_metadata) tuples
        original_token_count = 0

        if CHUNKING_AVAILABLE:
            try:
                enc = tiktoken.get_encoding("cl100k_base")
                original_token_count = len(enc.encode(prompt))

                if original_token_count > 2000:
                    # Topical chunking: 512 tokens, 15% overlap
                    chunker_config = ProseChunkerConfig(
                        max_chunk_size=512, overlap_ratio=0.15
                    )
                    prose_chunker = ProseChunker(chunker_config)
                    chunk_results = prose_chunker.chunk(prompt, source="user_prompt")

                    if chunk_results:
                        for i, cr in enumerate(chunk_results):
                            chunk_tokens = len(enc.encode(cr.content))
                            chunks_to_store.append(
                                (
                                    cr.content,
                                    {
                                        "chunk_type": "topical",
                                        "chunk_index": i,
                                        "total_chunks": len(chunk_results),
                                        "chunk_size_tokens": chunk_tokens,
                                        "overlap_tokens": cr.metadata.overlap_tokens,
                                        "original_size_tokens": original_token_count,
                                    },
                                )
                            )
                        logger.info(
                            "user_prompt_chunked",
                            extra={
                                "original_tokens": original_token_count,
                                "num_chunks": len(chunk_results),
                                "session_id": session_id,
                            },
                        )
                    else:
                        # ProseChunker returned empty — store whole as fallback
                        chunks_to_store.append(
                            (
                                prompt,
                                {
                                    "chunk_type": "whole",
                                    "chunk_index": 0,
                                    "total_chunks": 1,
                                    "chunk_size_tokens": original_token_count,
                                    "overlap_tokens": 0,
                                    "original_size_tokens": original_token_count,
                                },
                            )
                        )
                else:
                    # Under threshold — store whole
                    chunks_to_store.append(
                        (
                            prompt,
                            {
                                "chunk_type": "whole",
                                "chunk_index": 0,
                                "total_chunks": 1,
                                "chunk_size_tokens": original_token_count,
                                "overlap_tokens": 0,
                                "original_size_tokens": original_token_count,
                            },
                        )
                    )
            except Exception as e:
                logger.warning("chunking_failed_storing_whole", extra={"error": str(e)})
                chunks_to_store.append(
                    (
                        prompt,
                        {
                            "chunk_type": "whole",
                            "chunk_index": 0,
                            "total_chunks": 1,
                            "chunk_size_tokens": (len(prompt) + 2) // 3,
                            "overlap_tokens": 0,
                            "original_size_tokens": (len(prompt) + 2) // 3,
                        },
                    )
                )
        else:
            # Chunking not available — store whole
            est_tokens = (len(prompt) + 2) // 3
            chunks_to_store.append(
                (
                    prompt,
                    {
                        "chunk_type": "whole",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "chunk_size_tokens": est_tokens,
                        "overlap_tokens": 0,
                        "original_size_tokens": est_tokens,
                    },
                )
            )

        # Embed and store all chunks
        from memory.embeddings import EmbeddingClient

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.ConnectError, ConnectionError)
            ),
            reraise=True,
        )
        def _embed_batch_with_retry(contents: list[str]) -> list[list]:
            with EmbeddingClient(config) as embed_client:
                return embed_client.embed(contents)

        chunk_contents = [c for c, _ in chunks_to_store]
        try:
            vectors = _embed_batch_with_retry(chunk_contents)
            embedding_status = "complete"
        except Exception as e:
            logger.warning(
                "embedding_failed_using_zero_vectors", extra={"error": str(e)}
            )
            vectors = [[0.0] * config.embedding_dimension for _ in chunks_to_store]
            embedding_status = "pending"

        # Build points for all chunks
        points = []
        for i, ((chunk_content, chunk_meta), vector) in enumerate(
            zip(chunks_to_store, vectors)
        ):
            chunk_id = (
                str(
                    uuid.uuid5(
                        uuid.NAMESPACE_DNS, f"{session_id}:{content_hash}:chunk:{i}"
                    )
                )
                if len(chunks_to_store) > 1
                else memory_id
            )
            chunk_payload = {
                **payload,
                "content": chunk_content,
                "content_hash": (
                    _compute_chunk_hash(chunk_content)
                    if len(chunks_to_store) > 1
                    else content_hash
                ),
                "parent_content_hash": (
                    content_hash if len(chunks_to_store) > 1 else None
                ),
                "embedding_status": embedding_status,
                "chunking_metadata": chunk_meta,
            }
            points.append(
                PointStruct(id=chunk_id, vector=vector, payload=chunk_payload)
            )

        # Store all chunks to Qdrant
        client.upsert(collection_name=COLLECTION_DISCUSSIONS, points=points)

        # BUG-036: Include project name for multi-project visibility
        log_to_activity(
            f"✅ UserPrompt stored: Turn {turn_number} [{group_id}] ({len(points)} chunks)",
            INSTALL_DIR,
        )
        logger.info(
            "user_message_stored",
            extra={
                "memory_id": memory_id,
                "session_id": session_id,
                "group_id": group_id,
                "turn_number": turn_number,
                "content_length": len(prompt),
            },
        )

        # BUG-024: Enqueue for LLM classification (first chunk only)
        try:
            from memory.classifier.config import CLASSIFIER_ENABLED
            from memory.classifier.queue import (
                ClassificationTask,
                enqueue_for_classification,
            )

            if CLASSIFIER_ENABLED:
                task = ClassificationTask(
                    point_id=points[0].id if points else memory_id,
                    collection=COLLECTION_DISCUSSIONS,
                    content=prompt[:2000],  # Classifier input limit
                    current_type="user_message",
                    group_id=group_id,
                    source_hook="UserPromptSubmit",
                    created_at=now,  # Matches stored memory timestamp for traceability
                )
                enqueue_for_classification(task)
                logger.debug(
                    "classification_enqueued",
                    extra={
                        "point_id": points[0].id if points else memory_id,
                        "collection": COLLECTION_DISCUSSIONS,
                        "current_type": "user_message",
                    },
                )
        except ImportError:
            pass  # Classifier not installed
        except Exception as e:
            logger.warning(
                "classification_enqueue_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "point_id": memory_id,
                },
            )

        # Metrics
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="UserPromptSubmit",
                status="success",
                project=group_id or "unknown",
                collection="discussions",
            ).inc()

        # BUG-037: Push capture metrics to Pushgateway for Grafana visibility
        # TECH-DEBT-071: Push token count for stored user prompt
        # HIGH-3: Token estimation ~25-50% error margin (4 chars/token approximation)
        try:
            from memory.metrics_push import (
                push_capture_metrics_async,
                push_token_metrics_async,
            )

            # BUG-037: Push capture count for Grafana project visibility
            push_capture_metrics_async(
                hook_type="UserPromptSubmit",
                status="success",
                project=group_id or "unknown",
                collection=COLLECTION_DISCUSSIONS,
                count=1,
            )

            token_count = (
                len(prompt) + 2
            ) // 3  # Fast estimation, consider tiktoken if accuracy critical
            if token_count > 0:
                push_token_metrics_async(
                    operation="capture",
                    direction="stored",
                    project=group_id or "unknown",
                    token_count=token_count,
                )
        except ImportError:
            pass  # Graceful degradation if metrics_push not available

        return True

    except (
        ResponseHandlingException,
        UnexpectedResponse,
        ApiException,
        QdrantUnavailable,
    ) as e:
        # BUG-036: Include project name for multi-project visibility
        project_name = detect_project(os.getcwd())
        log_to_activity(
            f"📥 UserPrompt queued: Qdrant unavailable [{project_name}]", INSTALL_DIR
        )
        logger.warning(
            "qdrant_error_queuing",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": hook_input.get("session_id"),
            },
        )
        # Queue for retry
        queue_data = {
            "content": hook_input["prompt"],
            "group_id": detect_project(os.getcwd()),
            "memory_type": TYPE_USER_MESSAGE,
            "source_hook": "UserPromptSubmit",
            "session_id": hook_input["session_id"],
            "turn_number": hook_input.get("turn_number", 0),
        }
        queue_operation(queue_data)

        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="UserPromptSubmit",
                status="queued",
                project=queue_data["group_id"] or "unknown",
                collection="discussions",
            ).inc()

        return False

    except Exception as e:
        # BUG-036: Include project name for multi-project visibility
        project_name = (
            detect_project(os.getcwd()) if "group_id" not in dir() else group_id
        )
        log_to_activity(
            f"❌ UserPrompt failed: {type(e).__name__} [{project_name}]", INSTALL_DIR
        )
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": hook_input.get("session_id"),
            },
        )

        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="UserPromptSubmit",
                status="failed",
                project="unknown",
                collection="discussions",
            ).inc()

        return False


def main() -> int:
    """Background storage entry point."""
    try:
        # Read hook input from stdin
        raw_input = sys.stdin.read()
        hook_input = json.loads(raw_input)

        # Store user message
        store_user_message(hook_input)

        return 0

    except Exception as e:
        logger.error(
            "async_storage_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
