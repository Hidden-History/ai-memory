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
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Add src/memory to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Import pattern extraction (Story 2.3)
from memory.extraction import extract_patterns
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
    from memory.deduplication import is_duplicate
except ImportError:
    # Fallback if validation module not available
    import hashlib
    def compute_content_hash(content: str) -> str:
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"

    # Mock is_duplicate if not available
    async def is_duplicate(content, group_id, collection="memories"):
        return type('Result', (), {'is_duplicate': False, 'reason': 'module_unavailable'})()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import metrics for Prometheus instrumentation (Story 6.1)
try:
    from memory.metrics import memory_captures_total, deduplication_events_total
except ImportError:
    memory_captures_total = None
    deduplication_events_total = None


def get_timeout() -> int:
    """Get timeout value from env var (AC 2.1.5).

    Returns:
        Timeout in seconds (default: 60)
    """
    try:
        timeout_str = os.getenv("HOOK_TIMEOUT", "60")
        return int(timeout_str)
    except ValueError:
        logger.warning(
            "invalid_timeout_env",
            extra={"value": timeout_str, "using_default": 60}
        )
        return 60


def queue_to_file(hook_input: Dict[str, Any], reason: str) -> None:
    """Queue failed memory capture to file for retry (AC 2.1.2).

    Graceful degradation: When Qdrant unavailable, queue to file.

    Args:
        hook_input: Original hook input data
        reason: Reason for queuing (e.g., 'qdrant_unavailable')
    """
    try:
        # Queue directory (from config or default)
        queue_dir = Path(os.getenv("MEMORY_QUEUE_DIR", "./.memory_queue"))
        queue_dir.mkdir(parents=True, exist_ok=True)

        # Generate queue file name
        session_id = hook_input.get("session_id", "unknown")
        timestamp = time.time()
        queue_file = queue_dir / f"{session_id}_{int(timestamp)}.json"

        # Write to queue
        queue_data = {
            "hook_input": hook_input,
            "reason": reason,
            "timestamp": timestamp
        }
        queue_file.write_text(json.dumps(queue_data, indent=2))

        logger.info(
            "memory_queued",
            extra={
                "reason": reason,
                "queue_file": str(queue_file),
                "session_id": session_id
            }
        )

        # Metrics: Increment capture counter for queued (Story 6.1)
        if memory_captures_total:
            # Extract project from hook_input if available
            try:
                from memory.project import detect_project
                cwd = hook_input.get("cwd", "")
                project = detect_project(cwd) if cwd else "unknown"
            except Exception:
                project = "unknown"

            memory_captures_total.labels(
                hook_type="PostToolUse",
                status="queued",
                project=project
            ).inc()

    except Exception as e:
        logger.error(
            "queue_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )


async def store_memory_async(hook_input: Dict[str, Any]) -> None:
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
        # Get Qdrant configuration
        # Use host/port parameters instead of url to avoid conflicts with QDRANT_URL env var
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "26350"))
        collection_name = os.getenv("QDRANT_COLLECTION", "implementations")

        # Initialize AsyncQdrantClient
        if AsyncQdrantClient is None:
            raise ImportError("qdrant-client not installed")

        # Use host/port parameters instead of url to avoid QDRANT_URL env var interference
        client = AsyncQdrantClient(host=qdrant_host, port=qdrant_port)

        # Extract tool information
        tool_name = hook_input["tool_name"]
        tool_input = hook_input["tool_input"]
        session_id = hook_input["session_id"]
        cwd = hook_input["cwd"]

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

        # Story 2.2: Check for duplicates before storing
        try:
            dedup_result = await is_duplicate(
                content=code_content,
                group_id=group_id,
                collection=collection_name
            )

            if dedup_result.is_duplicate:
                logger.info(
                    "duplicate_skipped",
                    extra={
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "reason": dedup_result.reason,
                        "existing_id": dedup_result.existing_id,
                        "similarity_score": getattr(dedup_result, 'similarity_score', None)
                    }
                )
                # Metrics: Increment deduplication counter (Story 6.1)
                if deduplication_events_total:
                    deduplication_events_total.labels(project=group_id or "unknown").inc()
                # Skip storage - duplicate detected
                return
        except Exception as e:
            # Fail open: If deduplication check fails, allow storage
            logger.warning(
                "deduplication_check_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "session_id": session_id
                }
            )

        # Story 2.3: Extract patterns from the content
        file_path = tool_input.get("file_path", "unknown")

        # Extract patterns using Story 2.3 module (code_content already extracted above)
        patterns = extract_patterns(code_content, file_path)

        if not patterns:
            # Skip storage if no patterns extracted (invalid content)
            logger.info(
                "no_patterns_extracted",
                extra={
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "file_path": file_path
                }
            )
            return

        # Build Qdrant payload using extracted patterns (AC 2.1.2: ALL fields snake_case)
        payload = {
            "content": patterns["content"],  # Enriched content with [lang/framework] header
            "content_hash": content_hash,
            "group_id": group_id,
            "type": "implementation",
            "source_hook": "PostToolUse",
            "session_id": session_id,
            "embedding_status": "pending",  # Will be updated when embedding completes
            "tool_name": tool_name,
            "file_path": patterns["file_path"],
            "language": patterns["language"],
            "framework": patterns["framework"],
            "importance": patterns["importance"],
            "tags": patterns["tags"],
            "domain": patterns["domain"]
        }

        # Pattern extraction integrated (Story 2.3 - complete)
        # Deduplication module integrated (Story 2.2 - completed)

        # Store to Qdrant (using points API directly for MVP)
        # Note: Embedding will be added later via separate process
        logger.info(
            "storing_memory",
            extra={
                "session_id": session_id,
                "tool_name": tool_name,
                "collection": collection_name
            }
        )

        # Store to Qdrant using points API (Story 1.5: MemoryStorage integration)
        logger.info(
            "memory_payload_ready",
            extra={
                "payload_fields": list(payload.keys()),
                "content_length": len(code_content)
            }
        )

        # Generate unique ID for this memory
        import uuid
        memory_id = str(uuid.uuid4())

        # Get vector dimension from config (default: 768 for Jina Embeddings v2 Base Code per DEC-010)
        vector_size = int(os.getenv("EMBEDDING_DIMENSION", "768"))

        # Generate embedding synchronously for immediate searchability (fix per code review)
        # Note: This changes from async background processing to sync for test compatibility
        try:
            from memory.embeddings import EmbeddingClient
            from memory.config import get_config

            def _generate_embedding():
                config = get_config()
                with EmbeddingClient(config) as embed_client:
                    return embed_client.embed([patterns["content"]])[0]

            vector = await asyncio.to_thread(_generate_embedding)
            payload["embedding_status"] = "complete"
            logger.info("embedding_generated_sync", extra={"dimensions": len(vector)})
        except Exception as e:
            # Graceful degradation: Use zero vector if embedding fails
            logger.warning(
                "embedding_failed_using_zero_vector",
                extra={"error": str(e), "error_type": type(e).__name__}
            )
            vector = [0.0] * vector_size
            payload["embedding_status"] = "pending"

        # Store to Qdrant with real embedding (or zero vector fallback)
        await client.upsert(
            collection_name=collection_name,
            points=[{
                "id": memory_id,
                "payload": payload,
                "vector": vector
            }]
        )

        logger.info(
            "memory_stored",
            extra={
                "memory_id": memory_id,
                "session_id": session_id,
                "collection": collection_name,
                "embedding_status": payload["embedding_status"]
            }
        )

        # Metrics: Increment capture counter on success (Story 6.1)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PostToolUse",
                status="success",
                project=group_id or "unknown"
            ).inc()

    except ResponseHandlingException as e:
        # AC 2.1.2: Handle request/response errors (includes 429 rate limiting)
        logger.error(
            "qdrant_response_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        # AC 2.1.2: Queue on response handling failure
        queue_to_file(hook_input, "response_error")

    except UnexpectedResponse as e:
        # AC 2.1.2: Handle HTTP errors
        logger.error(
            "qdrant_unexpected_response",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        # AC 2.1.2: Queue on unexpected response
        queue_to_file(hook_input, "unexpected_response")

    except ConnectionRefusedError as e:
        # Qdrant service unavailable
        logger.error(
            "qdrant_unavailable",
            extra={"error": str(e)}
        )
        # AC 2.1.2: Queue on connection failure
        queue_to_file(hook_input, "qdrant_unavailable")

    except RuntimeError as e:
        # AC 2.1.2: Handle closed client instances
        if "closed" in str(e).lower():
            logger.error(
                "qdrant_client_closed",
                extra={"error": str(e)}
            )
            queue_to_file(hook_input, "client_closed")
        else:
            raise  # Re-raise if not client-related

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
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
                project=project
            ).inc()

        # AC 2.1.2: Queue on any failure
        queue_to_file(hook_input, "unexpected_error")

    finally:
        # Clean up client connection
        if client is not None:
            try:
                await client.close()
            except Exception as e:
                logger.error(
                    "client_close_failed",
                    extra={"error": str(e)}
                )


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
        timeout = get_timeout()

        # Run storage with timeout
        await asyncio.wait_for(
            store_memory_async(hook_input),
            timeout=timeout
        )

        return 0

    except asyncio.TimeoutError:
        # AC 2.1.5: Handle timeout
        logger.error(
            "storage_timeout",
            extra={"timeout_seconds": get_timeout()}
        )
        # Queue for retry
        try:
            queue_to_file(hook_input, "timeout")
        except Exception:
            pass
        return 1

    except Exception as e:
        logger.error(
            "async_main_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return 1


def main() -> int:
    """Synchronous entry point."""
    try:
        return asyncio.run(main_async())
    except Exception as e:
        logger.error(
            "asyncio_run_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
