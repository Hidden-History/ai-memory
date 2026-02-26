#!/usr/bin/env python3
"""Async storage script for PostToolUse hook background processing.

AC 2.1.2: Async Storage Script with Graceful Degradation
AC 2.1.5: Timeout Handling

This script runs in a detached background process, storing captured
implementation patterns to Qdrant with proper error handling.

Performance: Runs independently of hook (no <500ms constraint)
Timeout: Configurable via HOOK_TIMEOUT env var (default: 60s)

Sources:
- Qdrant AsyncQdrantClient: https://python-client.qdrant.tech/
- Exception handling: https://python-client.qdrant.tech/qdrant_client.http.exceptions
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# CR-1.7: Setup path inline (must happen BEFORE any memory.* imports)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Import pattern extraction (Story 2.3)
from datetime import datetime, timezone

from memory.chunking import IntelligentChunker
from memory.config import COLLECTION_CODE_PATTERNS
from memory.extraction import extract_patterns
from memory.filters import ImplementationFilter
from memory.project import detect_project

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http.exceptions import (
        ResponseHandlingException,
        UnexpectedResponse,
    )
except ImportError:
    # Graceful degradation if qdrant-client not installed
    AsyncQdrantClient = None
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception

try:
    from memory.deduplication import is_duplicate
    from memory.validation import compute_content_hash
except ImportError:
    # Fallback if validation module not available
    import hashlib

    def compute_content_hash(content: str) -> str:
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"

    # Mock is_duplicate if not available
    async def is_duplicate(content, group_id, collection="memories"):
        return type(
            "Result", (), {"is_duplicate": False, "reason": "module_unavailable"}
        )()


# CR-1.2: Use consolidated logging setup
from memory.hooks_common import get_hook_timeout, setup_hook_logging

logger = setup_hook_logging()

# CR-1.3: Use consolidated queue operation
from memory.queue import queue_operation

# SPEC-021: Trace buffer for pipeline instrumentation
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 2000  # Max chars for Langfuse input/output fields

# Import metrics for Prometheus instrumentation (Story 6.1)
try:
    from memory.metrics import deduplication_events_total, memory_captures_total
except ImportError:
    memory_captures_total = None
    deduplication_events_total = None

# CR-1.4: get_timeout() removed - using consolidated get_hook_timeout() from hooks_common
# CR-1.3: queue_to_file() removed - using consolidated queue_operation() from queue.py


async def store_memory_async(hook_input: dict[str, Any]) -> None:
    """Store captured pattern to Qdrant (AC 2.1.2).

    Args:
        hook_input: Validated hook input from PostToolUse

    Implementation notes:
    - Uses AsyncQdrantClient for async operations
    - Handles specific Qdrant exceptions
    - Graceful degradation: queue on failure
    - No retry loops (violates NFR-P1)
    """
    client = None

    try:
        # SPEC-021: Read trace_id from capture hook env propagation
        trace_id = os.environ.get("LANGFUSE_TRACE_ID")

        # Get Qdrant configuration (BP-040)
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "26350"))
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        qdrant_use_https = os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true"
        collection_name = os.getenv("QDRANT_COLLECTION", COLLECTION_CODE_PATTERNS)

        # Initialize AsyncQdrantClient
        if AsyncQdrantClient is None:
            raise ImportError("qdrant-client not installed")

        # BP-040: API key + HTTPS configurable via environment variables
        client = AsyncQdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            api_key=qdrant_api_key,
            https=qdrant_use_https,
        )

        # Extract tool information (TECH-DEBT-097: safe .get() access)
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})
        cwd = hook_input.get("cwd", "")

        if not tool_name or not cwd:
            logger.error(
                "missing_required_fields",
                extra={"has_tool_name": bool(tool_name), "has_cwd": bool(cwd)},
            )
            return

        # BUG-058 Fix: session_id is for audit trail, not tenant isolation (group_id handles that)
        # Use graceful fallback per BP-037 (Fallback Tenant ID Pattern)
        session_id = hook_input.get("session_id")
        if not session_id:
            session_id = "unknown"
            logger.warning(
                "session_id_missing_using_fallback",
                extra={"cwd": cwd, "tool_name": tool_name},
            )

        # Extract the actual code content for hashing and pattern extraction
        # For Edit tool, extract patterns from new_string (the actual code change)
        if tool_name == "Edit":
            code_content = tool_input.get("new_string", "")
        elif tool_name == "Write":
            code_content = tool_input.get("content", "")
        elif tool_name == "NotebookEdit":
            code_content = tool_input.get("new_source", "")
        else:
            code_content = json.dumps(tool_input)

        # Compute content hash for deduplication (Story 2.2)
        # IMPORTANT: Hash the actual code, not formatted version
        content_hash = compute_content_hash(code_content)

        # Group ID: Project name from cwd (FR13)
        group_id = detect_project(cwd)

        # SPEC-021: 2_log span
        if emit_trace_event:
            try:
                log_path = str(Path(INSTALL_DIR) / "logs" / "activity.log")
                emit_trace_event(
                    event_type="2_log",
                    data={
                        "input": code_content[:TRACE_CONTENT_MAX],
                        "output": f"Logged to {log_path}",
                        "metadata": {"content_length": len(code_content), "log_path": log_path},
                    },
                    trace_id=trace_id, session_id=session_id, project_id=group_id,
                )
            except Exception:
                pass

        # Story 2.2: Check for duplicates before storing
        try:
            dedup_result = await is_duplicate(
                content=code_content, group_id=group_id, collection=collection_name
            )

            if dedup_result.is_duplicate:
                logger.info(
                    "duplicate_skipped",
                    extra={
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "reason": dedup_result.reason,
                        "existing_id": dedup_result.existing_id,
                        "similarity_score": getattr(
                            dedup_result, "similarity_score", None
                        ),
                    },
                )
                # Metrics: Increment deduplication counter (Story 6.1)
                if deduplication_events_total:
                    deduplication_events_total.labels(
                        project=group_id or "unknown"
                    ).inc()
                # Skip storage - duplicate detected
                return
        except Exception as e:
            # Fail open: If deduplication check fails, allow storage
            logger.warning(
                "deduplication_check_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "session_id": session_id,
                },
            )

        # Story 2.3: Extract patterns from the content
        file_path = tool_input.get("file_path", "unknown")

        # BUG-013: Apply ImplementationFilter BEFORE extract_patterns()
        # Filter rejects .md, .txt, .json, insignificant changes, generated dirs
        impl_filter = ImplementationFilter()
        if not impl_filter.should_store(file_path, code_content, tool_name):
            logger.info(
                "implementation_filtered",
                extra={
                    "file_path": file_path,
                    "tool_name": tool_name,
                    "reason": "filter_rejected",
                },
            )
            return

        # Extract patterns using Story 2.3 module (code_content already extracted above)
        patterns = extract_patterns(code_content, file_path)

        # SPEC-021: 3_detect span — content type detected via extract_patterns
        if emit_trace_event:
            try:
                language = patterns.get("language", "unknown") if patterns else "unknown"
                emit_trace_event(
                    event_type="3_detect",
                    data={
                        "input": code_content[:300],
                        "output": f"Detected type: implementation (confidence: 1.0)",
                        "metadata": {"detected_type": "implementation", "confidence": 1.0, "language": language},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        if not patterns:
            # Skip storage if no patterns extracted (invalid content)
            logger.info(
                "no_patterns_extracted",
                extra={
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "file_path": file_path,
                },
            )
            if emit_trace_event:
                try:
                    emit_trace_event(
                        event_type="pipeline_terminated",
                        data={
                            "input": "no_patterns_extracted",
                            "output": "Pipeline terminated: no patterns extracted from tool output",
                            "metadata": {"reason": "no_patterns_extracted"},
                        },
                        trace_id=trace_id, session_id=session_id, project_id=group_id,
                    )
                except Exception:
                    pass
            return

        # SPEC-021: Default scan tracking vars (used by 4_scan span)
        scan_action = "skipped"  # Default if scanning disabled/unavailable
        scan_findings = []
        scan_actually_ran = False
        scan_input_length = len(patterns["content"])  # Capture BEFORE potential masking

        # SPEC-009: Security scanning before storage (match other 3 hooks)
        try:
            from memory.config import get_config as _get_sec_config

            sec_config = _get_sec_config()
            if sec_config.security_scanning_enabled:
                try:
                    from memory.security_scanner import SecurityScanner, ScanAction

                    scanner = SecurityScanner(enable_ner=False)
                    scan_result = scanner.scan(patterns["content"])
                    scan_actually_ran = True
                    # SPEC-021: Capture scan outcome for 4_scan span
                    scan_action = scan_result.action.value if hasattr(scan_result.action, 'value') else str(scan_result.action)
                    scan_findings = scan_result.findings

                    if scan_result.action == ScanAction.BLOCKED:
                        logger.warning(
                            "code_pattern_blocked_secrets",
                            extra={
                                "session_id": session_id,
                                "file_path": file_path,
                                "findings_count": len(scan_result.findings),
                            },
                        )
                        # SPEC-021: 4_scan span (BLOCKED) + pipeline_terminated
                        if emit_trace_event:
                            try:
                                emit_trace_event(
                                    event_type="4_scan",
                                    data={
                                        "input": patterns["content"][:300],
                                        "output": f"Scan result: blocked (findings: {len(scan_result.findings)})",
                                        "metadata": {"scan_result": "blocked", "pii_found": False, "secrets_found": True},
                                    },
                                    trace_id=trace_id,
                                    session_id=session_id,
                                    project_id=group_id,
                                )
                            except Exception:
                                pass
                            try:
                                emit_trace_event(
                                    event_type="pipeline_terminated",
                                    data={
                                        "input": "scan_blocked",
                                        "output": "Pipeline terminated: scan_blocked",
                                        "metadata": {"reason": "scan_blocked", "scan_blocked": True},
                                    },
                                    trace_id=trace_id,
                                    session_id=session_id,
                                    project_id=group_id,
                                )
                            except Exception:
                                pass
                        return
                    elif scan_result.action == ScanAction.MASKED:
                        patterns["content"] = scan_result.content
                except ImportError:
                    logger.warning(
                        "security_scanner_unavailable",
                        extra={"hook": "PostToolUse"},
                    )
        except Exception as e:
            logger.error(
                "security_scan_failed",
                extra={"hook": "PostToolUse", "error": str(e)},
            )

        # SPEC-021: 4_scan span (non-blocked paths) — only emit if scan actually ran
        if emit_trace_event and scan_actually_ran:
            try:
                pii_found = any(
                    hasattr(f, 'finding_type') and f.finding_type.name.startswith("PII_")
                    for f in scan_findings
                )
                secrets_found = any(
                    hasattr(f, 'finding_type') and f.finding_type.name.startswith("SECRET_")
                    for f in scan_findings
                )
                emit_trace_event(
                    event_type="4_scan",
                    data={
                        "input": patterns["content"][:300],
                        "output": f"Scan result: {scan_action} (findings: {len(scan_findings)})",
                        "metadata": {
                            "scan_result": scan_action,
                            "content_length": scan_input_length,
                            "pii_found": pii_found,
                            "secrets_found": secrets_found,
                        },
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # TECH-DEBT-051: Use IntelligentChunker for content chunking
        # MVP returns whole content as single chunk; TECH-DEBT-052 adds Tree-sitter AST chunking
        chunker = IntelligentChunker(max_chunk_tokens=512, overlap_pct=0.15)
        chunks = chunker.chunk(patterns["content"], file_path)

        if not chunks:
            logger.info(
                "no_chunks_created",
                extra={"session_id": session_id, "file_path": file_path},
            )
            return

        logger.info(
            "chunking_complete",
            extra={
                "file_path": file_path,
                "chunk_count": len(chunks),
                "total_tokens": sum(c.metadata.chunk_size_tokens for c in chunks),
            },
        )

        # SPEC-021: 5_chunk span — chunking complete
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="5_chunk",
                    data={
                        "input": patterns["content"][:TRACE_CONTENT_MAX],
                        "output": f"Produced {len(chunks)} chunks",
                        "metadata": {
                            "num_chunks": len(chunks),
                            "chunk_type": chunks[0].metadata.chunk_type if chunks else "unknown",
                            "total_tokens": sum(c.metadata.chunk_size_tokens for c in chunks),
                            "content_length": len(patterns["content"]),
                        },
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # CR-1.5: Use config constant instead of env var with magic number
        from memory.config import get_config

        config = get_config()
        vector_size = config.embedding_dimension

        # Store each chunk as a separate memory point
        import uuid

        points_to_store = []

        for chunk in chunks:
            memory_id = str(uuid.uuid4())

            # Build Qdrant payload with chunk metadata (AC 2.1.2: ALL fields snake_case)
            # FIX 1: Add created_at timestamp
            now = datetime.now(timezone.utc).isoformat()
            payload = {
                "content": chunk.content,
                "content_hash": content_hash,
                "group_id": group_id,
                "type": "implementation",
                "source_hook": "PostToolUse",
                "session_id": session_id,
                "created_at": now,
                "stored_at": now,
                "embedding_status": "pending",
                "tool_name": tool_name,
                "file_path": patterns["file_path"],
                "language": patterns["language"],
                "framework": patterns["framework"],
                "importance": patterns["importance"],
                "tags": patterns["tags"],
                "domain": patterns["domain"],
                # FIX 2: Add chunk metadata from IntelligentChunker
                "chunk_type": chunk.metadata.chunk_type,
                "chunk_index": chunk.metadata.chunk_index,
                "total_chunks": chunk.metadata.total_chunks,
                "chunk_size_tokens": chunk.metadata.chunk_size_tokens,
                # TECH-DEBT-069: Mark as not yet classified
                "is_classified": False,
                # v2.0.6: Semantic Decay fields
                "timestamp": now,
                "decay_score": 1.0,
                "freshness_status": "unverified",
                "source_authority": 0.4,
                "is_current": True,
                "version": 1,
            }

            # Generate embedding synchronously for immediate searchability
            try:
                from memory.embeddings import EmbeddingClient

                def _generate_embedding(content):
                    cfg = get_config()
                    with EmbeddingClient(cfg) as embed_client:
                        return embed_client.embed([content])[0]

                vector = await asyncio.to_thread(_generate_embedding, chunk.content)
                payload["embedding_status"] = "complete"
            except Exception as e:
                # Graceful degradation: Use zero vector if embedding fails
                logger.warning(
                    "embedding_failed_using_zero_vector",
                    extra={"error": str(e), "chunk_index": chunk.metadata.chunk_index},
                )
                vector = [0.0] * vector_size
                payload["embedding_status"] = "pending"

            points_to_store.append(
                {"id": memory_id, "payload": payload, "vector": vector}
            )

        # SPEC-021: 6_embed span — embedding generation
        if emit_trace_event:
            try:
                embed_statuses = [p["payload"]["embedding_status"] for p in points_to_store]
                dim = len(points_to_store[0]["vector"]) if points_to_store else 0
                emit_trace_event(
                    event_type="6_embed",
                    data={
                        "input": f"Embedding {len(points_to_store)} chunks",
                        "output": f"Generated {len(points_to_store)} vectors ({dim}-dim)",
                        "metadata": {"embedding_status": embed_statuses[0] if embed_statuses else "unknown", "num_vectors": len(points_to_store), "dimensions": dim},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # HIGH-4: Calculate token count BEFORE upsert for atomicity
        # (Prevents underreporting if storage succeeds but metrics fail)
        total_tokens = sum(len(p["payload"]["content"]) // 4 for p in points_to_store)

        # Store all chunks to Qdrant
        await client.upsert(collection_name=collection_name, points=points_to_store)

        # SPEC-021: 7_store span — data persisted to Qdrant
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="7_store",
                    data={
                        "input": f"Storing {len(points_to_store)} points to {collection_name}",
                        "output": f"Stored {len(points_to_store)} points (IDs: {[p['id'] for p in points_to_store][:5]})",
                        "metadata": {"collection": collection_name, "points_stored": len(points_to_store)},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        logger.info(
            "memory_stored",
            extra={
                "chunks_stored": len(points_to_store),
                "session_id": session_id,
                "collection": collection_name,
                "file_path": file_path,
            },
        )

        # TECH-DEBT-069: Enqueue for async classification
        classification_enqueued = False
        enqueue_count = 0
        try:
            from memory.classifier.config import CLASSIFIER_ENABLED
            from memory.classifier.queue import (
                ClassificationTask,
                enqueue_for_classification,
            )

            if CLASSIFIER_ENABLED:
                for point in points_to_store:
                    task = ClassificationTask(
                        point_id=point["id"],
                        collection=collection_name,
                        content=point["payload"]["content"][
                            :2000
                        ],  # Limit content size
                        current_type=point["payload"]["type"],
                        group_id=group_id,
                        source_hook="PostToolUse",
                        created_at=point["payload"]["created_at"],
                        trace_id=trace_id,
                        session_id=session_id,  # Wave 1H: Propagate session_id for 9_classify trace
                    )
                    enqueue_for_classification(task)
                    enqueue_count += 1
                classification_enqueued = True
        except ImportError:
            pass  # Classifier module not installed
        except Exception as e:
            logger.warning("classification_enqueue_failed", extra={"error": str(e)})

        # SPEC-021: 8_enqueue span — reports actual enqueue outcome
        if emit_trace_event:
            try:
                first_point_id = points_to_store[0]["id"] if points_to_store else "unknown"
                emit_trace_event(
                    event_type="8_enqueue",
                    data={
                        "input": f"Enqueuing point {first_point_id} for classification",
                        "output": f"Enqueued: {classification_enqueued} (collection: {collection_name})",
                        "metadata": {"collection": collection_name, "current_type": "implementation", "enqueue_count": enqueue_count},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # Metrics: Increment capture counter on success (Story 6.1)
        if memory_captures_total:
            # Increment by number of chunks stored
            memory_captures_total.labels(
                hook_type="PostToolUse",
                status="success",
                project=group_id or "unknown",
                collection="code-patterns",
            ).inc(len(points_to_store))

        # TECH-DEBT-070: Push metrics to Pushgateway (async to avoid latency)
        from memory.metrics_push import (
            push_capture_metrics_async,
            push_token_metrics_async,
        )

        push_capture_metrics_async(
            hook_type="PostToolUse",
            status="success",
            project=group_id or "unknown",
            collection=COLLECTION_CODE_PATTERNS,
            count=len(points_to_store),
        )

        # TECH-DEBT-071: Push token count for captured content
        # HIGH-3: Token estimation accuracy ~25-50% error margin
        # Actual: Python code ~3 chars/token, JSON ~5-6 chars/token
        # Using len(content) // 4 for performance (avoids tiktoken dependency)
        # TODO: Consider tiktoken for precise counting if accuracy becomes critical
        # HIGH-4: Use pre-calculated total_tokens (calculated before upsert)
        if total_tokens > 0:
            push_token_metrics_async(
                operation="capture",
                direction="stored",
                project=group_id or "unknown",
                token_count=total_tokens,
            )

    except ResponseHandlingException as e:
        # AC 2.1.2: Handle request/response errors (includes 429 rate limiting)
        logger.error(
            "qdrant_response_error",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        # AC 2.1.2: Queue on response handling failure
        queue_operation(hook_input, "response_error")

    except UnexpectedResponse as e:
        # AC 2.1.2: Handle HTTP errors
        logger.error(
            "qdrant_unexpected_response",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        # AC 2.1.2: Queue on unexpected response
        queue_operation(hook_input, "unexpected_response")

    except ConnectionRefusedError as e:
        # Qdrant service unavailable
        logger.error("qdrant_unavailable", extra={"error": str(e)})
        # AC 2.1.2: Queue on connection failure
        queue_operation(hook_input, "qdrant_unavailable")

    except RuntimeError as e:
        # AC 2.1.2: Handle closed client instances
        if "closed" in str(e).lower():
            logger.error("qdrant_client_closed", extra={"error": str(e)})
            queue_operation(hook_input, "client_closed")
        else:
            raise  # Re-raise if not client-related

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "storage_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )

        # Metrics: Increment capture counter for failures (Story 6.1)
        if memory_captures_total:
            try:
                project = hook_input.get("cwd", "unknown")
                if project != "unknown":
                    project = detect_project(project)
            except Exception:
                project = "unknown"

            memory_captures_total.labels(
                hook_type="PostToolUse",
                status="failed",
                project=project,
                collection="code-patterns",
            ).inc()

        # AC 2.1.2: Queue on any failure
        queue_operation(hook_input, "unexpected_error")

    finally:
        # Clean up client connection
        if client is not None:
            try:
                await client.close()
            except Exception as e:
                logger.error("client_close_failed", extra={"error": str(e)})


async def main_async() -> int:
    """Async entry point with timeout handling (AC 2.1.5).

    Returns:
        Exit code: 0 (success) or 1 (error)
    """
    try:
        # Read hook input from stdin
        raw_input = sys.stdin.read()
        hook_input = json.loads(raw_input)

        # AC 2.1.5: Apply timeout
        timeout = get_hook_timeout()

        # Run storage with timeout
        await asyncio.wait_for(store_memory_async(hook_input), timeout=timeout)

        return 0

    except asyncio.TimeoutError:
        # AC 2.1.5: Handle timeout
        logger.error("storage_timeout", extra={"timeout_seconds": get_hook_timeout()})
        # Queue for retry
        try:
            queue_operation(hook_input, "timeout")
        except Exception:
            pass
        return 1

    except Exception as e:
        logger.error(
            "async_main_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )
        return 1


def main() -> int:
    """Synchronous entry point."""
    try:
        return asyncio.run(main_async())
    except Exception as e:
        logger.error(
            "asyncio_run_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
