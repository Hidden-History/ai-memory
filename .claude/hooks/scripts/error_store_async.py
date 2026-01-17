#!/usr/bin/env python3
"""Async storage script for error pattern capture background processing.

This script runs in a detached background process, storing captured
error patterns to Qdrant with type="error_pattern".

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

# Add src/memory to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total
except ImportError:
    memory_captures_total = None


def get_timeout() -> int:
    """Get timeout value from env var.

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


def queue_to_file(error_context: Dict[str, Any], reason: str) -> None:
    """Queue failed error capture to file for retry.

    Args:
        error_context: Error context data
        reason: Reason for queuing
    """
    try:
        # Queue directory
        queue_dir = Path(os.getenv("MEMORY_QUEUE_DIR", "./.memory_queue"))
        queue_dir.mkdir(parents=True, exist_ok=True)

        # Generate queue file name
        session_id = error_context.get("session_id", "unknown")
        timestamp = time.time()
        queue_file = queue_dir / f"error_{session_id}_{int(timestamp)}.json"

        # Write to queue
        queue_data = {
            "error_context": error_context,
            "reason": reason,
            "timestamp": timestamp
        }
        queue_file.write_text(json.dumps(queue_data, indent=2))

        logger.info(
            "error_pattern_queued",
            extra={
                "reason": reason,
                "queue_file": str(queue_file),
                "session_id": session_id
            }
        )

    except Exception as e:
        logger.error(
            "queue_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )


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
        # Get Qdrant configuration
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "26350"))
        collection_name = os.getenv("QDRANT_COLLECTION", "implementations")

        # Initialize AsyncQdrantClient
        if AsyncQdrantClient is None:
            raise ImportError("qdrant-client not installed")

        client = AsyncQdrantClient(host=qdrant_host, port=qdrant_port)

        # Format content for embedding
        content = format_error_content(error_context)

        # Compute content hash
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
            "type": "error_pattern",
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

        # Generate unique ID
        import uuid
        memory_id = str(uuid.uuid4())

        # Get vector dimension
        vector_size = int(os.getenv("EMBEDDING_DIMENSION", "768"))

        # Generate embedding synchronously
        try:
            from memory.embeddings import EmbeddingClient
            from memory.config import get_config

            def _generate_embedding():
                config = get_config()
                with EmbeddingClient(config) as embed_client:
                    return embed_client.embed([content])[0]

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

        # Store to Qdrant
        await client.upsert(
            collection_name=collection_name,
            points=[{
                "id": memory_id,
                "payload": payload,
                "vector": vector
            }]
        )

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
        logger.error(
            "qdrant_response_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        queue_to_file(error_context, "response_error")

    except UnexpectedResponse as e:
        logger.error(
            "qdrant_unexpected_response",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        queue_to_file(error_context, "unexpected_response")

    except ConnectionRefusedError as e:
        logger.error(
            "qdrant_unavailable",
            extra={"error": str(e)}
        )
        queue_to_file(error_context, "qdrant_unavailable")

    except RuntimeError as e:
        if "closed" in str(e).lower():
            logger.error(
                "qdrant_client_closed",
                extra={"error": str(e)}
            )
            queue_to_file(error_context, "client_closed")
        else:
            raise

    except Exception as e:
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

        queue_to_file(error_context, "unexpected_error")

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

        # Apply timeout
        timeout = get_timeout()

        # Run storage with timeout
        await asyncio.wait_for(
            store_error_pattern_async(error_context),
            timeout=timeout
        )

        return 0

    except asyncio.TimeoutError:
        logger.error(
            "storage_timeout",
            extra={"timeout_seconds": get_timeout()}
        )
        try:
            queue_to_file(error_context, "timeout")
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
