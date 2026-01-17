#!/usr/bin/env python3
"""
Async Storage Script for Post-Work Memory Storage

Runs in detached background process to store implementation memories
without blocking the calling BMAD workflow.

Features:
- Async storage with timeout handling
- Graceful degradation (queue on failure)
- Prometheus metrics integration
- Structured logging
- No retry loops (fail fast, queue for later)

Exit Codes:
- 0: Success
- 1: Storage failed (queued for retry)

Created: 2026-01-17
Pattern follows .claude/hooks/scripts/store_async.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Add src to path for imports
# Try dev repo FIRST, then fall back to installed location
dev_src = Path(__file__).parent.parent.parent / "src"
if dev_src.exists():
    sys.path.insert(0, str(dev_src))
else:
    INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
    sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.storage import MemoryStorage
from memory.qdrant_client import QdrantUnavailable
from memory.logging_config import StructuredFormatter
from memory.models import MemoryType

# Configure structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.post_work_store_async")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total, deduplication_events_total
except ImportError:
    memory_captures_total = None
    deduplication_events_total = None


def get_timeout() -> int:
    """
    Get timeout value from env var.

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


def queue_to_file(payload: Dict[str, Any], reason: str) -> None:
    """
    Queue failed memory capture to file for retry.

    Graceful degradation: When Qdrant unavailable, queue to file.

    Args:
        payload: Original payload data (content + metadata)
        reason: Reason for queuing (e.g., 'qdrant_unavailable')
    """
    try:
        # Queue directory (from config or default)
        queue_dir = Path(os.getenv("MEMORY_QUEUE_DIR", "./.memory_queue"))
        queue_dir.mkdir(parents=True, exist_ok=True)

        # Generate queue file name
        metadata = payload.get("metadata", {})
        group_id = metadata.get("group_id", "unknown")
        timestamp = time.time()
        queue_file = queue_dir / f"{group_id}_{int(timestamp)}.json"

        # Write to queue
        queue_data = {
            "payload": payload,
            "reason": reason,
            "timestamp": timestamp
        }
        queue_file.write_text(json.dumps(queue_data, indent=2))

        logger.info(
            "memory_queued",
            extra={
                "reason": reason,
                "queue_file": str(queue_file),
                "group_id": group_id,
                "story_id": metadata.get("story_id"),
            }
        )

        # Metrics: Increment capture counter for queued
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type=metadata.get("source_hook", "manual"),
                status="queued",
                project=group_id
            ).inc()

    except Exception as e:
        logger.error(
            "queue_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )


async def store_memory_async(payload: Dict[str, Any]) -> None:
    """
    Store memory to Qdrant using MemoryStorage class.

    Args:
        payload: Dictionary with:
            - content: Memory content string
            - metadata: Metadata dictionary with type, group_id, etc.

    Implementation notes:
    - Uses MemoryStorage for consistent storage patterns
    - Handles Qdrant exceptions with graceful degradation
    - No retry loops (queue on failure)
    """
    try:
        from memory.models import MemoryType

        # Extract payload components
        content = payload["content"]
        metadata = payload["metadata"]

        # Get required fields from metadata
        memory_type_str = metadata.get("type")
        group_id = metadata.get("group_id")
        session_id = metadata.get("session_id", "workflow")
        source_hook = metadata.get("source_hook", "manual")  # "manual" for workflow-driven storage

        # Convert string type to MemoryType enum
        memory_type = MemoryType(memory_type_str)

        # Determine collection based on type
        if memory_type_str == "best_practice":
            collection = "best_practices"
        elif memory_type_str in ["session_summary", "chat_memory", "agent_decision"]:
            collection = "agent-memory"
        else:
            collection = "implementations"

        # Get cwd for project detection (fallback to root if not provided)
        cwd = metadata.get("cwd", "/")

        # Create storage instance
        storage = MemoryStorage()

        # Store memory using MemoryStorage class
        # Run in thread pool to avoid blocking event loop
        def _store_sync():
            return storage.store_memory(
                content=content,
                cwd=cwd,
                group_id=group_id,
                memory_type=memory_type,
                source_hook=source_hook,
                session_id=session_id,
                collection=collection,
                # Pass additional metadata fields
                agent=metadata.get("agent"),
                component=metadata.get("component"),
                story_id=metadata.get("story_id"),
                importance=metadata.get("importance"),
            )

        result = await asyncio.to_thread(_store_sync)

        # Log result
        logger.info(
            "memory_stored",
            extra={
                "memory_id": result.get("memory_id"),
                "status": result.get("status"),
                "embedding_status": result.get("embedding_status"),
                "type": memory_type_str,
                "group_id": group_id,
                "story_id": metadata.get("story_id"),
                "collection": collection,
            }
        )

        # Metrics: Increment capture counter on success
        if memory_captures_total:
            status = "success" if result["status"] == "stored" else "duplicate"
            memory_captures_total.labels(
                hook_type=source_hook,
                status=status,
                project=group_id or "unknown"
            ).inc()

        # Metrics: Increment deduplication counter if duplicate
        if result["status"] == "duplicate" and deduplication_events_total:
            deduplication_events_total.labels(
                project=group_id or "unknown"
            ).inc()

    except QdrantUnavailable as e:
        # Qdrant service unavailable
        logger.error(
            "qdrant_unavailable",
            extra={"error": str(e)}
        )
        # Queue on connection failure
        queue_to_file(payload, "qdrant_unavailable")

        # Metrics: Increment capture counter for failures
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type=metadata.get("source_hook", "workflow_post_work"),
                status="failed",
                project=metadata.get("group_id", "unknown")
            ).inc()

    except ValueError as e:
        # Validation failed (including invalid MemoryType enum value)
        logger.error(
            "validation_failed",
            extra={
                "error": str(e),
                "type": payload.get("metadata", {}).get("type"),
                "group_id": payload.get("metadata", {}).get("group_id"),
            }
        )
        # Don't queue validation errors - they need to be fixed at the source

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "type": payload.get("metadata", {}).get("type"),
                "group_id": payload.get("metadata", {}).get("group_id"),
            }
        )

        # Metrics: Increment capture counter for failures
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type=metadata.get("source_hook", "workflow_post_work"),
                status="failed",
                project=metadata.get("group_id", "unknown")
            ).inc()

        # Queue on unexpected error
        queue_to_file(payload, "unexpected_error")


async def main_async() -> int:
    """
    Async entry point with timeout handling.

    Returns:
        Exit code: 0 (success) or 1 (error)
    """
    payload = None  # Define outside try block for error handling

    try:
        # Read payload from stdin
        raw_input = sys.stdin.read()

        try:
            payload = json.loads(raw_input)
        except json.JSONDecodeError as e:
            logger.error(
                "malformed_json",
                extra={
                    "error": str(e),
                    "input_preview": raw_input[:100]
                }
            )
            return 1

        # Validate payload structure
        if "content" not in payload:
            logger.error("payload_missing_content")
            return 1
        if "metadata" not in payload:
            logger.error("payload_missing_metadata")
            return 1

        # Apply timeout
        timeout = get_timeout()

        # Run storage with timeout
        await asyncio.wait_for(
            store_memory_async(payload),
            timeout=timeout
        )

        return 0

    except asyncio.TimeoutError:
        # Handle timeout
        logger.error(
            "storage_timeout",
            extra={"timeout_seconds": get_timeout()}
        )
        # Queue for retry
        if payload:
            queue_to_file(payload, "timeout")
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
