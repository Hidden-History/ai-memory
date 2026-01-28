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
import time
from pathlib import Path
from typing import Any, Dict

# CR-1.7: Setup path inline (must happen BEFORE any memory.* imports)
INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Import project detection
from memory.project import detect_project
from memory.config import COLLECTION_CODE_PATTERNS, get_config

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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total
except ImportError:
    memory_captures_total = None

# CR-1.2, CR-1.3, CR-1.4: Use consolidated utility functions
from memory.hooks_common import log_to_activity, get_hook_timeout
from memory.queue import queue_operation


def format_error_content(error_context: Dict[str, Any]) -> str:
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
            if 'column' in ref:
                parts.append(f"  {ref['file']}:{ref['line']}:{ref['column']}")
            else:
                parts.append(f"  {ref['file']}:{ref['line']}")

    # Stack trace (if present)
    if error_context.get("stack_trace"):
        parts.append("\nStack Trace:")
        parts.append(error_context['stack_trace'])

    # Output (truncated)
    if error_context.get("output"):
        parts.append("\nCommand Output:")
        parts.append(error_context['output'][:500])  # Limit to 500 chars

    return "\n".join(parts)


async def store_error_pattern_async(error_context: Dict[str, Any]) -> None:
    """Store error pattern to Qdrant.

    Args:
        error_context: Error context from hook
    """
    client = None

    try:
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
                logger.info("error_duplicate_skipped_background", extra={
                    "content_hash": content_hash,
                    "error": error_context.get("error_message", "")[:50]
                })
                return  # Skip storage, already captured

        # Initialize AsyncQdrantClient
        if AsyncQdrantClient is None:
            raise ImportError("qdrant-client not installed")

        # BP-040: API key + HTTPS configurable via environment variables
        client = AsyncQdrantClient(
            host=qdrant_host, port=qdrant_port, api_key=qdrant_api_key, https=qdrant_use_https
        )

        # Format content for embedding
        content = format_error_content(error_context)

        # Use pre-computed content hash if available, otherwise compute it
        content_hash = error_context.get("content_hash")
        if not content_hash:
            content_hash = compute_content_hash(content)

        # Group ID from cwd
        cwd = error_context.get("cwd", "")
        group_id = detect_project(cwd)

        # Extract primary file reference if available
        file_refs = error_context.get("file_references", [])
        primary_file = file_refs[0]["file"] if file_refs else "unknown"

        # Build Qdrant payload
        payload = {
            "content": content,
            "content_hash": content_hash,
            "group_id": group_id,
            "type": "error_fix",
            "source_hook": "PostToolUse_ErrorCapture",
            "session_id": error_context.get("session_id", ""),
            "embedding_status": "pending",
            "command": error_context.get("command", ""),
            "error_message": error_context.get("error_message", ""),
            "exit_code": error_context.get("exit_code"),
            "file_path": primary_file,
            "file_references": file_refs,
            "has_stack_trace": bool(error_context.get("stack_trace")),
            "tags": ["error", "bash_failure"]
        }

        logger.info(
            "storing_error_pattern",
            extra={
                "session_id": error_context.get("session_id", ""),
                "command": error_context.get("command", "")[:50],
                "collection": collection_name
            }
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
                    return embed_client.embed([content])[0]

            vector = await asyncio.to_thread(_generate_embedding)
            payload["embedding_status"] = "complete"
            logger.info("embedding_generated_sync", extra={"dimensions": len(vector)})
        except Exception as e:
            # Graceful degradation: Use zero vector if embedding fails
            # CR-1.5: Use config constant instead of magic number
            config = get_config()
            logger.warning(
                "embedding_failed_using_zero_vector",
                extra={"error": str(e), "error_type": type(e).__name__}
            )
            vector = [0.0] * config.embedding_dimension
            payload["embedding_status"] = "pending"

        # Store to Qdrant
        await client.upsert(
            collection_name=collection_name,
            points=[{
                "id": memory_id,
                "payload": payload,
                "vector": vector
            }]
        )

        # CR-1.2: Use consolidated log function
        log_to_activity(f"✅ ErrorPattern stored: {error_context.get('command', 'Unknown')[:30]}", INSTALL_DIR)
        logger.info(
            "error_pattern_stored",
            extra={
                "memory_id": memory_id,
                "session_id": error_context.get("session_id", ""),
                "collection": collection_name,
                "embedding_status": payload["embedding_status"]
            }
        )

        # Metrics: Increment capture counter
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PostToolUse_Error",
                status="success",
                project=group_id or "unknown"
            ).inc()

    except ResponseHandlingException as e:
        # CR-1.2, CR-1.3: Use consolidated functions
        log_to_activity("📥 ErrorPattern queued: Qdrant unavailable", INSTALL_DIR)
        logger.error(
            "qdrant_response_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        queue_operation(error_context, "response_error")

    except UnexpectedResponse as e:
        log_to_activity("📥 ErrorPattern queued: Qdrant unavailable", INSTALL_DIR)
        logger.error(
            "qdrant_unexpected_response",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        queue_operation(error_context, "unexpected_response")

    except ConnectionRefusedError as e:
        log_to_activity("📥 ErrorPattern queued: Qdrant unavailable", INSTALL_DIR)
        logger.error(
            "qdrant_unavailable",
            extra={"error": str(e)}
        )
        queue_operation(error_context, "qdrant_unavailable")

    except RuntimeError as e:
        if "closed" in str(e).lower():
            logger.error(
                "qdrant_client_closed",
                extra={"error": str(e)}
            )
            queue_operation(error_context, "client_closed")
        else:
            raise

    except Exception as e:
        log_to_activity(f"❌ ErrorPattern failed: {type(e).__name__}", INSTALL_DIR)
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )

        # Metrics: Increment capture counter for failures
        if memory_captures_total:
            try:
                project = error_context.get("cwd", "unknown")
                if project != "unknown":
                    project = detect_project(project)
            except Exception:
                project = "unknown"

            memory_captures_total.labels(
                hook_type="PostToolUse_Error",
                status="failed",
                project=project
            ).inc()

        queue_operation(error_context, "unexpected_error")

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
            store_error_pattern_async(error_context),
            timeout=timeout
        )

        return 0

    except asyncio.TimeoutError:
        logger.error(
            "storage_timeout",
            extra={"timeout_seconds": get_hook_timeout()}
        )
        try:
            queue_operation(error_context, "timeout")
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
