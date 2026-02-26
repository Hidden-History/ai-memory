#!/usr/bin/env python3
"""Async storage script for error pattern capture background processing.

This script runs in a detached background process, storing captured
error patterns to Qdrant with type="error_fix" (v2.0).

Performance: Runs independently of hook (no <500ms constraint)
Timeout: Configurable via HOOK_TIMEOUT env var (default: 60s)
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# CR-1.7: Setup path inline (must happen BEFORE any memory.* imports)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import COLLECTION_CODE_PATTERNS, get_config

# Import project detection
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
    from memory.validation import compute_content_hash
except ImportError:
    # Fallback if validation module not available
    import hashlib

    def compute_content_hash(content: str) -> str:
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"


# Configure structured logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total
except ImportError:
    memory_captures_total = None

# TECH-DEBT-075: Import push metrics for Pushgateway
try:
    from memory.metrics_push import push_capture_metrics_async
except ImportError:
    push_capture_metrics_async = None

# CR-1.2, CR-1.3, CR-1.4: Use consolidated utility functions
from memory.hooks_common import get_hook_timeout, log_to_activity
from memory.queue import queue_operation

# SPEC-021: Trace buffer for pipeline instrumentation
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 2000  # Max chars for Langfuse input/output fields

# TECH-DEBT-151: Structured truncation for error output (max 800 tokens)
try:
    import tiktoken

    from memory.chunking.truncation import structured_truncate

    TRUNCATION_AVAILABLE = True
except ImportError:
    TRUNCATION_AVAILABLE = False


def format_error_content(error_context: dict[str, Any]) -> str:
    """Format error context into searchable content string.

    Args:
        error_context: Error context dict

    Returns:
        Formatted content string for embedding
    """
    parts = []

    # Error type header
    parts.append("[error_pattern]")

    # Command that failed
    if error_context.get("command"):
        parts.append(f"Command: {error_context['command']}")

    # Error message
    if error_context.get("error_message"):
        parts.append(f"Error: {error_context['error_message']}")

    # Exit code
    if error_context.get("exit_code") is not None:
        parts.append(f"Exit Code: {error_context['exit_code']}")

    # File references
    file_refs = error_context.get("file_references", [])
    if file_refs:
        parts.append("\nFile References:")
        for ref in file_refs:
            if "column" in ref:
                parts.append(f"  {ref['file']}:{ref['line']}:{ref['column']}")
            else:
                parts.append(f"  {ref['file']}:{ref['line']}")

    # Stack trace (if present)
    if error_context.get("stack_trace"):
        parts.append("\nStack Trace:")
        parts.append(error_context["stack_trace"])

    # Output (smart truncation)
    # TECH-DEBT-151: Use structured truncation instead of hard [:500] truncation
    if error_context.get("output"):
        parts.append("\nCommand Output:")
        if TRUNCATION_AVAILABLE:
            try:
                # Structured truncation preserves command + error + output structure
                sections = {
                    "command": error_context.get("command", ""),
                    "error": error_context.get("error_message", ""),
                    "output": error_context.get("output", ""),
                }
                truncated_output = structured_truncate(
                    error_context["output"], max_tokens=800, sections=sections
                )
                parts.append(truncated_output)
            except Exception:
                # Fallback to original content if truncation fails
                parts.append(error_context["output"])
        else:
            # Truncation not available - store full output (V2.1 zero-truncation principle)
            logger.warning(
                "storing_full_output_no_truncation",
                extra={"output_length": len(error_context["output"])},
            )
            parts.append(error_context["output"])

    return "\n".join(parts)


async def store_error_pattern_async(error_context: dict[str, Any]) -> None:
    """Store error pattern to Qdrant.

    Args:
        error_context: Error context from hook
    """
    client = None

    try:
        # SPEC-021: Read trace_id from capture hook env propagation
        trace_id = os.environ.get("LANGFUSE_TRACE_ID")
        session_id = error_context.get("session_id", "")

        # Get Qdrant configuration (BP-040)
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "26350"))
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        qdrant_use_https = os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true"
        collection_name = os.getenv("QDRANT_COLLECTION", COLLECTION_CODE_PATTERNS)

        # FIX #3: Dedup check in background (not hot path)
        # Check if this exact error has already been stored
        content_hash = error_context.get("content_hash")
        if content_hash:
            from memory.filters import ImplementationFilter

            impl_filter = ImplementationFilter()
            if impl_filter.is_duplicate(content_hash, collection_name):
                logger.info(
                    "error_duplicate_skipped_background",
                    extra={
                        "content_hash": content_hash,
                        "error": error_context.get("error_message", "")[:50],
                    },
                )
                return  # Skip storage, already captured

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

        # Format content for embedding
        content = format_error_content(error_context)

        # Group ID from cwd (moved up for trace spans)
        cwd = error_context.get("cwd", "")
        group_id = detect_project(cwd)

        # SPEC-021: 2_log span — content captured for processing
        if emit_trace_event:
            try:
                log_path = str(Path(INSTALL_DIR) / "logs" / "activity.log")
                emit_trace_event(
                    event_type="2_log",
                    data={
                        "input": content[:TRACE_CONTENT_MAX],
                        "output": f"Logged to {log_path}",
                        "metadata": {"content_length": len(content), "log_path": log_path},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # SPEC-021: 3_detect span — content type is predetermined
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="3_detect",
                    data={
                        "input": content[:300],
                        "output": "Detected type: error_fix (confidence: 1.0)",
                        "metadata": {"detected_type": "error_fix", "confidence": 1.0},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # SPEC-009: Security scanning (Layers 1+2 only for hooks, ~10ms overhead)
        scan_action = "skipped"  # Default if scanning disabled/unavailable
        scan_findings = []
        scan_actually_ran = False
        scan_input_length = len(content)  # Capture BEFORE potential masking
        config = get_config()
        if config.security_scanning_enabled:
            try:
                from memory.security_scanner import ScanAction, SecurityScanner

                scanner = SecurityScanner(enable_ner=False)
                scan_result = scanner.scan(content, source_type="user_session")
                scan_actually_ran = True
                scan_action = scan_result.action.value if hasattr(scan_result.action, 'value') else str(scan_result.action)
                scan_findings = scan_result.findings

                if scan_result.action == ScanAction.BLOCKED:
                    # Secrets detected - block storage entirely
                    log_to_activity(
                        "🚫 ErrorPattern blocked: Secrets detected", INSTALL_DIR
                    )
                    logger.warning(
                        "error_pattern_blocked_secrets",
                        extra={
                            "session_id": error_context.get("session_id", ""),
                            "findings": len(scan_result.findings),
                            "scan_duration_ms": scan_result.scan_duration_ms,
                        },
                    )
                    # SPEC-021: 4_scan (BLOCKED) + pipeline_terminated
                    if emit_trace_event:
                        try:
                            emit_trace_event(
                                event_type="4_scan",
                                data={
                                    "input": content[:300],
                                    "output": f"Scan result: blocked (findings: {len(scan_result.findings)})",
                                    "metadata": {"scan_result": "blocked", "pii_found": False, "secrets_found": True},
                                },
                                trace_id=trace_id, session_id=session_id, project_id=group_id,
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
                                trace_id=trace_id, session_id=session_id, project_id=group_id,
                            )
                        except Exception:
                            pass
                    return  # Exit early, do not store

                elif scan_result.action == ScanAction.MASKED:
                    # PII detected and masked
                    content = scan_result.content
                    logger.info(
                        "error_pattern_pii_masked",
                        extra={
                            "session_id": error_context.get("session_id", ""),
                            "findings": len(scan_result.findings),
                            "scan_duration_ms": scan_result.scan_duration_ms,
                        },
                    )

                # PASSED: No sensitive data, continue with original content

            except ImportError:
                logger.warning(
                    "security_scanner_unavailable", extra={"hook": "PostToolUse_Error"}
                )
            except Exception as e:
                logger.error(
                    "security_scan_failed",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "hook": "PostToolUse_Error",
                    },
                )
                # Continue with original content if scanner fails

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
                        "input": content[:300],
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

        # Use pre-computed content hash if available, otherwise compute it
        content_hash = error_context.get("content_hash")
        if not content_hash:
            content_hash = compute_content_hash(content)

        # Extract primary file reference if available
        file_refs = error_context.get("file_references", [])
        primary_file = file_refs[0]["file"] if file_refs else "unknown"

        # Calculate token count for metadata
        if TRUNCATION_AVAILABLE:
            try:
                enc = tiktoken.get_encoding("cl100k_base")
                content_tokens = len(enc.encode(content))
            except Exception:
                content_tokens = len(content) // 4
        else:
            content_tokens = len(content) // 4

        # Build Qdrant payload
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "content": content,
            "content_hash": content_hash,
            "group_id": group_id,
            "type": "error_fix",
            "source_hook": "PostToolUse_ErrorCapture",
            "session_id": error_context.get("session_id", ""),
            "timestamp": now,
            "created_at": now,
            "stored_at": now,
            "embedding_status": "pending",
            "command": error_context.get("command", ""),
            "error_message": error_context.get("error_message", ""),
            "exit_code": error_context.get("exit_code"),
            "file_path": primary_file,
            "file_references": file_refs,
            "has_stack_trace": bool(error_context.get("stack_trace")),
            "tags": ["error", "bash_failure"],
            # TECH-DEBT-151: Add chunking metadata per Chunking-Strategy-V2.md Section 5
            "chunking_metadata": {
                "chunk_type": "structured_smart_truncate",
                "chunk_index": 0,
                "total_chunks": 1,
                "chunk_size_tokens": content_tokens,
                "overlap_tokens": 0,
            },
            # v2.0.6: Semantic Decay fields
            "decay_score": 1.0,
            "freshness_status": "unverified",
            "source_authority": 0.4,
            "is_current": True,
            "version": 1,
        }

        # SPEC-021: 5_chunk span — error patterns use structured truncation (single chunk)
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="5_chunk",
                    data={
                        "input": content[:TRACE_CONTENT_MAX],
                        "output": "Produced 1 chunk",
                        "metadata": {"num_chunks": 1, "chunk_type": "structured_smart_truncate", "content_length": len(content)},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        logger.info(
            "storing_error_pattern",
            extra={
                "session_id": error_context.get("session_id", ""),
                "command": error_context.get("command", "")[:50],
                "collection": collection_name,
            },
        )

        # Generate deterministic UUID from content_hash (Fix: makes upsert idempotent)
        # Using uuid5 prevents TOCTOU race - same hash = same ID = no duplicate
        import uuid

        memory_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))

        # Generate embedding synchronously
        try:
            from memory.embeddings import EmbeddingClient

            def _generate_embedding():
                config = get_config()
                with EmbeddingClient(config) as embed_client:
                    # SPEC-010: Use code model for code-patterns collection
                    return embed_client.embed([content], model="code")[0]

            vector = await asyncio.to_thread(_generate_embedding)
            payload["embedding_status"] = "complete"
            logger.info("embedding_generated_sync", extra={"dimensions": len(vector)})
        except Exception as e:
            # Graceful degradation: Use zero vector if embedding fails
            # CR-1.5: Use config constant instead of magic number
            config = get_config()
            logger.warning(
                "embedding_failed_using_zero_vector",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            vector = [0.0] * config.embedding_dimension
            payload["embedding_status"] = "pending"

        # SPEC-021: 6_embed span — embedding generation
        if emit_trace_event:
            try:
                dim = len(vector)
                emit_trace_event(
                    event_type="6_embed",
                    data={
                        "input": "Embedding 1 chunk",
                        "output": f"Generated 1 vector ({dim}-dim)",
                        "metadata": {"embedding_status": payload["embedding_status"], "num_vectors": 1, "dimensions": dim},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # Store to Qdrant
        await client.upsert(
            collection_name=collection_name,
            points=[{"id": memory_id, "payload": payload, "vector": vector}],
        )

        # SPEC-021: 7_store span — data persisted to Qdrant
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="7_store",
                    data={
                        "input": f"Storing 1 point to {collection_name}",
                        "output": f"Stored 1 point (ID: {memory_id})",
                        "metadata": {"collection": collection_name, "points_stored": 1},
                    },
                    trace_id=trace_id,
                    session_id=session_id,
                    project_id=group_id,
                )
            except Exception:
                pass

        # SPEC-021: 8_enqueue span — error patterns do not use classifier
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="8_enqueue",
                    data={
                        "input": f"Enqueuing point {memory_id} for classification",
                        "output": f"Enqueued: False (collection: {collection_name})",
                        "metadata": {"collection": collection_name, "current_type": "error_fix", "reason": "classifier_not_integrated"},
                    },
                    trace_id=trace_id, session_id=session_id, project_id=group_id,
                )
            except Exception:
                pass

        # CR-1.2: Use consolidated log function
        log_to_activity(
            f"✅ ErrorPattern stored: {error_context.get('command', 'Unknown')[:30]}",
            INSTALL_DIR,
        )
        logger.info(
            "error_pattern_stored",
            extra={
                "memory_id": memory_id,
                "session_id": error_context.get("session_id", ""),
                "collection": collection_name,
                "embedding_status": payload["embedding_status"],
            },
        )

        # Metrics: Increment capture counter (local)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PostToolUse_Error",
                status="success",
                project=group_id or "unknown",
                collection="code-patterns",
            ).inc()

        # TECH-DEBT-075: Push metrics to Pushgateway
        if push_capture_metrics_async:
            push_capture_metrics_async(
                hook_type="PostToolUse_Error",
                status="success",
                project=group_id or "unknown",
                collection="code-patterns",
                count=1,
            )

    except ResponseHandlingException as e:
        # CR-1.2, CR-1.3: Use consolidated functions
        log_to_activity("📥 ErrorPattern queued: Qdrant unavailable", INSTALL_DIR)
        logger.error(
            "qdrant_response_error",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        queue_operation(error_context, "response_error")

    except UnexpectedResponse as e:
        log_to_activity("📥 ErrorPattern queued: Qdrant unavailable", INSTALL_DIR)
        logger.error(
            "qdrant_unexpected_response",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        queue_operation(error_context, "unexpected_response")

    except ConnectionRefusedError as e:
        log_to_activity("📥 ErrorPattern queued: Qdrant unavailable", INSTALL_DIR)
        logger.error("qdrant_unavailable", extra={"error": str(e)})
        queue_operation(error_context, "qdrant_unavailable")

    except RuntimeError as e:
        if "closed" in str(e).lower():
            logger.error("qdrant_client_closed", extra={"error": str(e)})
            queue_operation(error_context, "client_closed")
        else:
            raise

    except Exception as e:
        log_to_activity(f"❌ ErrorPattern failed: {type(e).__name__}", INSTALL_DIR)
        logger.error(
            "storage_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )

        # Metrics: Increment capture counter for failures (local)
        try:
            project = error_context.get("cwd", "unknown")
            if project != "unknown":
                project = detect_project(project)
        except Exception:
            project = "unknown"

        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PostToolUse_Error",
                status="failed",
                project=project,
                collection="code-patterns",
            ).inc()

        # TECH-DEBT-075: Push metrics to Pushgateway
        if push_capture_metrics_async:
            push_capture_metrics_async(
                hook_type="PostToolUse_Error",
                status="failed",
                project=project,
                collection="code-patterns",
                count=1,
            )

        queue_operation(error_context, "unexpected_error")

    finally:
        # Clean up client connection
        if client is not None:
            try:
                await client.close()
            except Exception as e:
                logger.error("client_close_failed", extra={"error": str(e)})


async def main_async() -> int:
    """Async entry point with timeout handling.

    Returns:
        Exit code: 0 (success) or 1 (error)
    """
    try:
        # Read error context from stdin
        raw_input = sys.stdin.read()
        error_context = json.loads(raw_input)

        # CR-1.4: Use consolidated timeout function
        timeout = get_hook_timeout()

        # Run storage with timeout
        await asyncio.wait_for(
            store_error_pattern_async(error_context), timeout=timeout
        )

        return 0

    except asyncio.TimeoutError:
        logger.error("storage_timeout", extra={"timeout_seconds": get_hook_timeout()})
        try:
            queue_operation(error_context, "timeout")
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
