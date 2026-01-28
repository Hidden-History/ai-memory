#!/usr/bin/env python3
# ARCHIVED: 2026-01-17 (TECH-DEBT-012)
# Reason: Duplicates PreCompact functionality. User prefers manual /save-memory.
#
# Replacement strategy:
# - PreCompact hook: Automatic session saves before context compaction (auto/manual)
# - /save-memory skill: Manual on-demand session saves when user requests
#
# Stop hook saved sessions on every exit, creating noise and duplicate memories.
# PreCompact provides better session summaries with full transcript analysis.
# This file kept for reference only.

"""Stop Hook - Capture session summaries when Claude Code sessions terminate.

AC 2.4.1: Stop Hook Infrastructure (Synchronous Execution)
AC 2.4.2: Session Summary Building
AC 2.4.3: Sync Storage with Graceful Degradation
AC 2.4.4: Hook Input Schema Validation
AC 2.4.5: Timeout Handling (FR35)

Exit Codes:
- 0: Success (normal completion)
- 1: Non-blocking error (session terminates normally, graceful degradation)

Performance: <5s timeout (synchronous execution allowed for Stop hook)
Pattern: Direct sync storage (Stop hook runs synchronously per AC 2.4.1)

2026 Best Practices:
- Sync QdrantClient for Stop hook (sync execution per AC 2.4.1)
- Structured JSON logging with extra={} dict (never f-strings)
- Proper exception handling: ResponseHandlingException, UnexpectedResponse
- Graceful degradation: queue to file on any failure
- All Qdrant payload fields: snake_case

Sources:
- Qdrant Python client: https://python-client.qdrant.tech/
- Qdrant exception handling: https://python-client.qdrant.tech/qdrant_client.http.exceptions
- Structured logging 2026: https://www.dash0.com/guides/logging-in-python
"""

import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add src to path for imports
# Use INSTALL_DIR to find installed module (fixes path calculation bug)
INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.graceful import graceful_hook, exit_success, exit_graceful
from memory.queue import queue_operation
from memory.storage import MemoryStorage
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.project import detect_project
from memory.logging_config import StructuredFormatter
from memory.activity_log import log_session_end
from memory.embeddings import EmbeddingClient, EmbeddingError

# Configure structured logging (Story 6.2)
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from memory.metrics import hook_duration_seconds, memory_captures_total
except ImportError:
    logger.warning("metrics_module_unavailable")
    hook_duration_seconds = None
    memory_captures_total = None

# Import Qdrant-specific exceptions for proper error handling (AC 2.4.3)
try:
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
except ImportError:
    # Graceful degradation if qdrant-client not installed
    ApiException = Exception
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception

# Timeout configuration (AC 2.4.5)
STOP_HOOK_TIMEOUT = int(os.getenv("STOP_HOOK_TIMEOUT", "5"))  # Default 5s


def validate_hook_input(data: Dict[str, Any]) -> Optional[str]:
    """Validate hook input against expected schema.

    AC 2.4.4: Input schema validation
    AC 2.4.1: Validate session_id and cwd exist

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid
    """
    # AC 2.4.1: Check required fields
    if "session_id" not in data:
        return "missing_session_id"
    if "cwd" not in data:
        return "missing_cwd"

    # AC 2.4.1: transcript is optional - will be handled separately
    # Missing transcript is not a validation error, just means nothing to store

    return None


def build_session_summary(hook_input: Dict[str, Any]) -> Dict[str, Any]:
    """Build session summary with metadata extraction.

    AC 2.4.2: Extract key session information
    AC 2.4.2: Include structured metadata
    AC 2.4.2: Create concise summary (not full transcript)
    AC 2.4.2: Format summary for optimal semantic search

    Args:
        hook_input: Validated hook input with transcript and metadata

    Returns:
        Dictionary with formatted session summary and metadata
    """
    session_id = hook_input["session_id"]
    cwd = hook_input["cwd"]
    transcript = hook_input["transcript"]
    metadata = hook_input.get("metadata", {})

    # Extract project name from cwd path (FR13)
    project_name = detect_project(cwd)

    # AC 2.4.2: Extract tools used from transcript
    # Look for patterns like "[Edit tool]", "[Bash tool]", etc.
    tools_pattern = r'\[(\w+)\s+tool\]'
    tools_found = re.findall(tools_pattern, transcript, re.IGNORECASE)
    unique_tools = list(set(tools_found))

    # AC 2.4.2: Count file operations
    files_modified = metadata.get("files_modified", 0)

    # AC 2.4.2: Include truncated transcript (first 2000 chars)
    key_activities = transcript[:2000] if transcript else ""

    # AC 2.4.2: Format summary for optimal search
    # Structure with clear headers for better retrieval
    summary_parts = [
        f"Session Summary: {project_name}",
        f"Session ID: {session_id}",
        f"Working Directory: {cwd}",
        f"Duration: {metadata.get('duration_ms', 0)}ms",
        f"Tools Used: {', '.join(unique_tools) if unique_tools else 'None'}",
        f"Files Modified: {files_modified}",
        "",
        "Key Activities:",
        key_activities
    ]

    summary_content = "\n".join(summary_parts)

    # Return structured data for storage
    return {
        "content": summary_content,
        "group_id": project_name,
        "memory_type": "session_summary",  # AC 2.4.3: Distinguish from implementations
        "source_hook": "Stop",  # AC 2.4.3: Provenance tracking
        "session_id": session_id,
        "importance": "normal",  # AC 2.4.3: Can be adjusted based on session length
        "session_metadata": {
            "duration_ms": metadata.get("duration_ms", 0),
            "tools_used": unique_tools,
            "files_modified": files_modified
        }
    }


def store_session_summary(summary_data: Dict[str, Any]) -> bool:
    """Store session summary using sync QdrantClient.

    AC 2.4.1: Synchronous execution (Stop hook allows this)
    AC 2.4.3: Proper exception handling with specific Qdrant exceptions
    AC 2.4.3: Queue to file on Qdrant failure
    AC 2.4.3: Store with embedding_status: pending if embedding service fails
    AC 2.4.3: Structured logging for all events
    AC 2.4.3: NEVER blocks Claude Code session termination

    Args:
        summary_data: Session summary data to store

    Returns:
        bool: True if stored successfully, False if queued (still success)

    Raises:
        No exceptions - all errors handled gracefully
    """
    try:
        # AC 2.4.1: Store directly WITHOUT embedding generation for <5s completion
        # Architecture pattern: Store with pending status, background process generates embeddings
        from qdrant_client.models import PointStruct
        from memory.models import EmbeddingStatus
        from memory.validation import compute_content_hash
        import uuid

        # Build payload
        content_hash = compute_content_hash(summary_data["content"])
        memory_id = str(uuid.uuid4())

        # Generate embedding
        embedding_status = EmbeddingStatus.PENDING.value
        vector = [0.0] * 768  # Default placeholder

        try:
            embed_client = EmbeddingClient()
            embeddings = embed_client.embed([summary_data["content"]])
            vector = embeddings[0]
            embedding_status = EmbeddingStatus.COMPLETE.value
            logger.info(
                "embedding_generated",
                extra={"memory_id": memory_id, "dimensions": len(vector)}
            )
        except EmbeddingError as e:
            logger.warning(
                "embedding_failed_using_placeholder",
                extra={"error": str(e), "memory_id": memory_id}
            )
            # Continue with zero vector - will be backfilled later

        payload = {
            "content": summary_data["content"],
            "content_hash": content_hash,
            "group_id": summary_data["group_id"],
            "type": summary_data["memory_type"],
            "source_hook": summary_data["source_hook"],
            "session_id": summary_data["session_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "embedding_status": embedding_status,
            "embedding_model": "nomic-embed-code",
            "importance": summary_data.get("importance", "normal"),
            "session_metadata": summary_data.get("session_metadata", {})
        }

        # Store to agent-memory collection for session summaries
        client = get_qdrant_client()
        client.upsert(
            collection_name="agent-memory",
            points=[
                PointStruct(
                    id=memory_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )

        # AC 2.4.3: Structured logging
        logger.info(
            "session_summary_stored",
            extra={
                "memory_id": memory_id,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
                "embedding_status": "pending"
            }
        )

        # Metrics: Increment capture counter on success (Story 6.1)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="success",
                project=summary_data["group_id"] or "unknown"
            ).inc()

        return True

    except ResponseHandlingException as e:
        # AC 2.4.3: Handle request/response errors (includes 429 rate limiting)
        logger.warning(
            "qdrant_response_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"]
            }
        )
        queue_operation(summary_data)
        # Metrics: Increment capture counter for queued (Story 6.1)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False

    except UnexpectedResponse as e:
        # AC 2.4.3: Handle HTTP errors from Qdrant
        logger.warning(
            "qdrant_unexpected_response",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"]
            }
        )
        queue_operation(summary_data)
        # Metrics: Increment capture counter for queued (Story 6.1)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False

    except QdrantUnavailable as e:
        # AC 2.4.3: Queue to file on Qdrant failure (graceful degradation)
        logger.warning(
            "qdrant_unavailable_queuing",
            extra={
                "error": str(e),
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"]
            }
        )

        # AC 2.4.3: NEVER retry - queue for background processing
        queue_success = queue_operation(summary_data)
        if queue_success:
            logger.info(
                "session_summary_queued",
                extra={
                    "session_id": summary_data["session_id"],
                    "group_id": summary_data["group_id"]
                }
            )
            # Metrics: Increment capture counter for queued (Story 6.1)
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="Stop",
                    status="queued",
                    project=summary_data["group_id"] or "unknown"
                ).inc()
        else:
            logger.error(
                "queue_failed",
                extra={
                    "session_id": summary_data["session_id"],
                    "group_id": summary_data["group_id"]
                }
            )
            # Metrics: Increment capture counter for failed (Story 6.1)
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="Stop",
                    status="failed",
                    project=summary_data["group_id"] or "unknown"
                ).inc()

        return False  # Queued, not stored directly

    except ApiException as e:
        # AC 2.4.3: Handle general Qdrant API errors (base class)
        logger.warning(
            "qdrant_api_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"]
            }
        )
        queue_operation(summary_data)
        # Metrics: Increment capture counter for queued (Story 6.1)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False

    except Exception as e:
        # AC 2.4.3: Handle all other exceptions gracefully
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"]
            }
        )

        # AC 2.4.3: Queue on any failure
        queue_operation(summary_data)
        # Metrics: Increment capture counter for queued (Story 6.1)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False


def timeout_handler(signum, frame):
    """Signal handler for timeout (AC 2.4.5)."""
    raise TimeoutError("Storage timeout exceeded")


@graceful_hook
def main() -> int:
    """Stop hook entry point.

    AC 2.4.1: Synchronous execution (Stop hook allows this)
    AC 2.4.1: <5s timeout
    AC 2.4.1: Exit 0 (success) or 1 (non-blocking error)
    AC 2.4.3: NEVER blocks Claude Code session termination

    Reads hook input from stdin, validates it, builds session summary,
    and stores it synchronously.

    Returns:
        Exit code: 0 (success) or 1 (non-blocking error)
    """
    start_time = time.perf_counter()
    summary_data = None  # For timeout handler access

    try:
        # Read hook input from stdin (Claude Code convention)
        raw_input = sys.stdin.read()

        # AC 2.4.4: Handle malformed JSON (FR34)
        try:
            hook_input = json.loads(raw_input)
        except json.JSONDecodeError as e:
            logger.error(
                "malformed_json",
                extra={
                    "error": str(e),
                    "input_preview": raw_input[:100]
                }
            )
            return 0  # AC 2.4.4: Exit 0 for invalid input (graceful)

        # AC 2.4.4: Validate schema
        validation_error = validate_hook_input(hook_input)
        if validation_error:
            logger.info(
                "validation_failed",
                extra={
                    "reason": validation_error,
                    "session_id": hook_input.get("session_id")
                }
            )
            return 0  # AC 2.4.4: Exit 0 for invalid input (graceful)

        # AC 2.4.1: Handle missing/empty transcript gracefully
        transcript = hook_input.get("transcript", "")
        if not transcript:
            logger.info(
                "no_transcript_skipping",
                extra={
                    "session_id": hook_input.get("session_id")
                }
            )
            # User notification via JSON systemMessage (visible in Claude Code UI per issue #4084)
            print(json.dumps({"systemMessage": "📤 AI Memory: No session transcript to save"}))
            sys.stdout.flush()  # Ensure output is flushed before exit
            return 0  # AC 2.4.1: Exit 0 immediately if no transcript

        # AC 2.4.2: Build session summary
        summary_data = build_session_summary(hook_input)

        # AC 2.4.5: Set up timeout using signal (Unix only)
        # Windows compatibility: signal.SIGALRM not available, skip timeout
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(STOP_HOOK_TIMEOUT)
        except (AttributeError, ValueError):
            # SIGALRM not available (Windows) - proceed without timeout
            pass

        try:
            # AC 2.4.3: Store session summary synchronously
            store_session_summary(summary_data)
        except TimeoutError:
            # AC 2.4.5: Queue to file on timeout
            logger.warning(
                "storage_timeout",
                extra={
                    "session_id": summary_data["session_id"],
                    "timeout": STOP_HOOK_TIMEOUT
                }
            )
            queue_operation(summary_data)
        finally:
            # Cancel alarm
            try:
                signal.alarm(0)
            except (AttributeError, ValueError):
                pass

        # Metrics: Record hook duration (Story 6.1, AC 6.1.3)
        duration_ms = (time.perf_counter() - start_time) * 1000
        if hook_duration_seconds:
            hook_duration_seconds.labels(hook_type="Stop").observe(duration_ms / 1000)

        # User notification via JSON systemMessage (visible in Claude Code UI per issue #4084)
        # Icon: 📤 for session summary (matches 🧠 retrieval, 📥 capture)
        project = summary_data.get("group_id", "unknown")
        message = f"📤 AI Memory: Session summary saved for {project} [{duration_ms:.0f}ms]"
        print(json.dumps({"systemMessage": message}))
        sys.stdout.flush()  # Ensure output is flushed before exit

        # Activity log (reliable visibility via tail -f ~/.ai-memory/logs/activity.log)
        log_session_end(project, duration_ms, stored=True)

        # AC 2.4.1: Exit 0 after storage (success)
        # AC 2.4.3: NEVER blocks session termination
        return 0

    except Exception as e:
        # Catch-all for unexpected errors (should be rare due to @graceful_hook)
        logger.error(
            "hook_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )

        # Metrics: Record hook duration even on error (Story 6.1, AC 6.1.3)
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(hook_type="Stop").observe(duration_seconds)

        return 1  # Non-blocking error


if __name__ == "__main__":
    sys.exit(main())
