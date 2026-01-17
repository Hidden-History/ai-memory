#!/usr/bin/env python3
"""PreCompact Hook - Capture session summaries BEFORE compaction.

This hook fires BEFORE Claude Code runs compaction (manual /compact or auto-compact).
It has access to the FULL transcript via transcript_path, making it the ideal place
to save session summaries for the "aha moment" in future sessions.

Hook Events:
- PreCompact (manual): Triggered by /compact command
- PreCompact (auto): Triggered when context window is full

Exit Codes:
- 0: Success (allow compaction to proceed)
- 1: Non-blocking error (allow compaction to proceed with warning)

Performance: <10s timeout (blocking before compaction is acceptable)
Pattern: Sync storage with zero vector, background embedding generation

2026 Best Practices:
- Sync QdrantClient for PreCompact (blocking allowed)
- Structured JSON logging with extra={} dict (never f-strings)
- Proper exception handling: ResponseHandlingException, UnexpectedResponse
- Graceful degradation: queue to file on any failure
- All Qdrant payload fields: snake_case
- Store to agent-memory collection for session continuity

Sources:
- Qdrant Python client: https://python-client.qdrant.tech/
- Claude Hooks reference: oversight/research/Claude_Hooks_reference.md
- Architecture: docs/memory settings/BMAD_MEMORY_ARCHITECTURE.md
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
from typing import Any, Dict, List, Optional

# Add src to path for imports
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.graceful import graceful_hook
from memory.queue import queue_operation
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.project import detect_project
from memory.logging_config import StructuredFormatter
from memory.activity_log import log_session_end, log_precompact
from memory.embeddings import EmbeddingClient, EmbeddingError
from memory.validation import compute_content_hash

# Configure structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import hook_duration_seconds, memory_captures_total
except ImportError:
    logger.warning("metrics_module_unavailable")
    hook_duration_seconds = None
    memory_captures_total = None

# Import Qdrant-specific exceptions for proper error handling
try:
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
    from qdrant_client.models import Filter, FieldCondition, MatchValue
except ImportError:
    # Graceful degradation if qdrant-client not installed
    ApiException = Exception
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception
    Filter = None
    FieldCondition = None
    MatchValue = None

# Timeout configuration
PRECOMPACT_HOOK_TIMEOUT = int(os.getenv("PRECOMPACT_HOOK_TIMEOUT", "10"))  # Default 10s


def validate_hook_input(data: Dict[str, Any]) -> Optional[str]:
    """Validate PreCompact hook input against expected schema.

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid
    """
    # Check required fields
    if "session_id" not in data:
        return "missing_session_id"
    if "cwd" not in data:
        return "missing_cwd"
    if "transcript_path" not in data:
        return "missing_transcript_path"
    if "hook_event_name" not in data:
        return "missing_hook_event_name"
    if data.get("hook_event_name") != "PreCompact":
        return f"wrong_hook_event: {data.get('hook_event_name')}"
    if "trigger" not in data:
        return "missing_trigger"
    if data["trigger"] not in ["manual", "auto"]:
        return f"invalid_trigger: {data['trigger']}"

    return None


def read_transcript(transcript_path: str) -> List[Dict[str, Any]]:
    """Read JSONL transcript file from Claude Code.

    Args:
        transcript_path: Path to .jsonl transcript file

    Returns:
        List of transcript entries (dicts)
    """
    transcript_entries = []

    # Expand ~ in path
    expanded_path = os.path.expanduser(transcript_path)

    if not os.path.exists(expanded_path):
        logger.warning(
            "transcript_not_found",
            extra={"path": transcript_path, "expanded": expanded_path}
        )
        return []

    try:
        with open(expanded_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        transcript_entries.append(entry)
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
    except Exception as e:
        logger.warning(
            "transcript_read_error",
            extra={"error": str(e), "path": expanded_path}
        )
        return []

    return transcript_entries


def analyze_transcript(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze transcript to extract key activities.

    Args:
        entries: List of transcript entries

    Returns:
        Dict with analysis results (tools, files, key moments)
    """
    tools_used = set()
    files_modified = set()
    user_prompts = []
    assistant_responses = []

    for entry in entries:
        # Extract role-based content
        role = entry.get("role", "")
        content = entry.get("content", [])

        if role == "user":
            # Extract text from user prompts
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if text and len(text) > 20:  # Skip very short prompts
                        user_prompts.append(text[:500])  # Truncate long prompts

        elif role == "assistant":
            # Extract tool uses and text responses
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "")

                    if item_type == "tool_use":
                        tool_name = item.get("name", "")
                        if tool_name:
                            tools_used.add(tool_name)

                        # Extract file paths from Write/Edit tools
                        tool_input = item.get("input", {})
                        if tool_name in ["Write", "Edit", "NotebookEdit"]:
                            file_path = tool_input.get("file_path", "")
                            if file_path:
                                files_modified.add(file_path)

                    elif item_type == "text":
                        text = item.get("text", "")
                        if text and len(text) > 20:
                            assistant_responses.append(text[:500])

    # Build summary of key moments
    key_moments = []
    if user_prompts:
        key_moments.append(f"User goals: {user_prompts[0]}")  # First prompt often sets context
    if user_prompts and len(user_prompts) > 1:
        key_moments.append(f"Follow-up work: {user_prompts[-1]}")  # Last prompt shows final direction

    return {
        "tools_used": sorted(list(tools_used)),
        "files_modified": sorted(list(files_modified)),
        "user_prompts_count": len(user_prompts),
        "key_moments": key_moments,
        "total_entries": len(entries)
    }


def build_session_summary(hook_input: Dict[str, Any], transcript_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Build session summary from transcript analysis.

    Args:
        hook_input: Validated hook input with metadata
        transcript_analysis: Analysis results from analyze_transcript()

    Returns:
        Dictionary with formatted session summary and metadata
    """
    session_id = hook_input["session_id"]
    cwd = hook_input["cwd"]
    trigger = hook_input["trigger"]
    custom_instructions = hook_input.get("custom_instructions", "")

    # Extract project name from cwd path
    project_name = detect_project(cwd)

    # Build summary content optimized for semantic search
    summary_parts = [
        f"Session Summary: {project_name}",
        f"Session ID: {session_id}",
        f"Compaction Trigger: {trigger}",
    ]

    if custom_instructions:
        summary_parts.append(f"User Instructions: {custom_instructions}")

    summary_parts.extend([
        "",
        f"Tools Used: {', '.join(transcript_analysis['tools_used']) if transcript_analysis['tools_used'] else 'None'}",
        f"Files Modified ({len(transcript_analysis['files_modified'])}): {', '.join(transcript_analysis['files_modified'][:10])}",  # First 10 files
        f"User Interactions: {transcript_analysis['user_prompts_count']} prompts",
        "",
        "Key Activities:"
    ])

    # Add key moments from transcript
    for moment in transcript_analysis["key_moments"]:
        summary_parts.append(f"- {moment}")

    summary_content = "\n".join(summary_parts)

    # Return structured data for storage
    return {
        "content": summary_content,
        "group_id": project_name,
        "memory_type": "session_summary",
        "source_hook": "PreCompact",
        "session_id": session_id,
        "importance": "high" if trigger == "auto" else "normal",  # Auto-compact = long session = high importance
        "session_metadata": {
            "trigger": trigger,
            "tools_used": transcript_analysis["tools_used"],
            "files_modified": len(transcript_analysis["files_modified"]),
            "user_interactions": transcript_analysis["user_prompts_count"],
            "transcript_entries": transcript_analysis["total_entries"]
        }
    }


def store_session_summary(summary_data: Dict[str, Any]) -> bool:
    """Store session summary to agent-memory collection.

    Args:
        summary_data: Session summary data to store

    Returns:
        bool: True if stored successfully, False if queued (still success)

    Raises:
        No exceptions - all errors handled gracefully
    """
    try:
        # Store WITHOUT embedding generation for <10s completion
        # Pattern: Store with pending status, background process generates embeddings
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

        # Store to agent-memory collection
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

        # Structured logging
        logger.info(
            "session_summary_stored",
            extra={
                "memory_id": memory_id,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
                "source_hook": "PreCompact",
                "embedding_status": "pending"
            }
        )

        # Metrics: Increment capture counter on success
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="success",
                project=summary_data["group_id"] or "unknown"
            ).inc()

        return True

    except ResponseHandlingException as e:
        # Handle request/response errors (includes 429 rate limiting)
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
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False

    except UnexpectedResponse as e:
        # Handle HTTP errors from Qdrant
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
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False

    except QdrantUnavailable as e:
        # Queue to file on Qdrant failure (graceful degradation)
        logger.warning(
            "qdrant_unavailable_queuing",
            extra={
                "error": str(e),
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"]
            }
        )

        queue_success = queue_operation(summary_data)
        if queue_success:
            logger.info(
                "session_summary_queued",
                extra={
                    "session_id": summary_data["session_id"],
                    "group_id": summary_data["group_id"]
                }
            )
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="PreCompact",
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
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="PreCompact",
                    status="failed",
                    project=summary_data["group_id"] or "unknown"
                ).inc()

        return False

    except ApiException as e:
        # Handle general Qdrant API errors
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
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False

    except Exception as e:
        # Handle all other exceptions gracefully
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"]
            }
        )

        queue_operation(summary_data)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown"
            ).inc()
        return False


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutError("Storage timeout exceeded")


def _log_to_activity(message: str) -> None:
    """Log message to activity log for user visibility.

    Activity log provides user-visible feedback about memory operations.
    Located at $BMAD_INSTALL_DIR/logs/activity.log
    """
    from datetime import datetime
    log_dir = Path(INSTALL_DIR) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "activity.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Escape newlines for single-line output (Streamlit parses line-by-line)
    safe_message = message.replace('\n', '\\n')
    line = f"[{timestamp}] {safe_message}\n"
    try:
        with open(log_file, "a") as f:
            f.write(line)
    except Exception:
        # Never fail - this is just for user visibility
        pass


def should_store_summary(summary_data: Dict[str, Any]) -> bool:
    """Validate if summary has meaningful content worth storing.

    Args:
        summary_data: Session summary data with session_metadata field

    Returns:
        False if summary has no meaningful content, True otherwise
    """
    metadata = summary_data.get("session_metadata", {})

    # Extract structured data from session_metadata
    tools_used = metadata.get("tools_used", [])
    files_modified = metadata.get("files_modified", 0)
    user_interactions = metadata.get("user_interactions", 0)

    # Skip if no tools used AND no files modified AND 0 user prompts
    has_no_activity = (
        len(tools_used) == 0 and
        files_modified == 0 and
        user_interactions == 0
    )

    if has_no_activity:
        return False

    return True


def check_duplicate_hash(content_hash: str, group_id: str, client) -> Optional[str]:
    """Check if content hash already exists in recent memories.

    Args:
        content_hash: SHA256 hash of content
        group_id: Project identifier
        client: QdrantClient instance

    Returns:
        Existing memory ID if duplicate found, None otherwise
    """
    # Check if Qdrant models are available
    if Filter is None or FieldCondition is None or MatchValue is None:
        logger.warning(
            "qdrant_models_unavailable",
            extra={"group_id": group_id}
        )
        return None  # Fail open - allow storage

    try:
        # Only check recent memories (limit 100) to avoid slow queries
        results, _ = client.scroll(
            collection_name="agent-memory",
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id", match=MatchValue(value=group_id)
                    ),
                    FieldCondition(
                        key="content_hash", match=MatchValue(value=content_hash)
                    ),
                ]
            ),
            limit=100,
        )

        if results:
            return str(results[0].id)

        return None

    except Exception as e:
        # Fail open on error - allow storage
        logger.warning(
            "duplicate_check_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "group_id": group_id
            }
        )
        return None


@graceful_hook
def main() -> int:
    """PreCompact hook entry point.

    Reads hook input from stdin, validates it, reads transcript,
    analyzes transcript, builds session summary, and stores it.

    Returns:
        Exit code: 0 (success - allow compaction) or 1 (non-blocking error)
    """
    start_time = time.perf_counter()
    summary_data = None

    try:
        # Read hook input from stdin (Claude Code convention)
        raw_input = sys.stdin.read()

        # Handle malformed JSON
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
            return 0  # Allow compaction to proceed

        # Validate schema
        validation_error = validate_hook_input(hook_input)
        if validation_error:
            logger.info(
                "validation_failed",
                extra={
                    "reason": validation_error,
                    "session_id": hook_input.get("session_id")
                }
            )
            return 0  # Allow compaction to proceed

        # Read transcript from file
        transcript_path = hook_input["transcript_path"]
        transcript_entries = read_transcript(transcript_path)

        if not transcript_entries:
            logger.info(
                "no_transcript_skipping",
                extra={
                    "session_id": hook_input.get("session_id"),
                    "transcript_path": transcript_path
                }
            )
            # User notification - no transcript to save
            print("📤 BMAD Memory: No session transcript to save (empty transcript)", file=sys.stderr)
            return 0  # Allow compaction to proceed

        # Analyze transcript
        transcript_analysis = analyze_transcript(transcript_entries)

        # Build session summary
        summary_data = build_session_summary(hook_input, transcript_analysis)

        # Extract project name once for validation checks
        project = summary_data.get("group_id", "unknown")

        # Validation 1: Check if summary has meaningful content
        if not should_store_summary(summary_data):
            _log_to_activity("⏭️  PreCompact skipped: Empty session (no activity)")
            logger.info(
                "summary_skipped_empty",
                extra={
                    "session_id": summary_data["session_id"],
                    "group_id": project,
                    "reason": "no_activity"
                }
            )
            print(f"📤 BMAD Memory: Skipping empty session summary for {project}", file=sys.stderr)
            return 0  # Allow compaction to proceed

        # Validation 2: Check for duplicate content hash
        content_hash = compute_content_hash(summary_data["content"])

        try:
            client = get_qdrant_client()
            duplicate_id = check_duplicate_hash(content_hash, project, client)

            if duplicate_id:
                _log_to_activity(f"⏭️  PreCompact skipped: Duplicate content (hash: {content_hash[:16]})")
                logger.info(
                    "summary_skipped_duplicate",
                    extra={
                        "session_id": summary_data["session_id"],
                        "group_id": project,
                        "content_hash": content_hash,
                        "duplicate_id": duplicate_id,
                        "reason": "duplicate_hash"
                    }
                )
                print(f"📤 BMAD Memory: Skipping duplicate session summary for {project}", file=sys.stderr)
                return 0  # Allow compaction to proceed
        except Exception as e:
            # Fail open on duplicate check error - allow storage
            logger.warning(
                "duplicate_check_error",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "group_id": project
                }
            )

        # Set up timeout using signal (Unix only)
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(PRECOMPACT_HOOK_TIMEOUT)
        except (AttributeError, ValueError):
            # SIGALRM not available (Windows) - proceed without timeout
            pass

        try:
            # Store session summary synchronously
            store_session_summary(summary_data)
        except TimeoutError:
            # Queue to file on timeout
            logger.warning(
                "storage_timeout",
                extra={
                    "session_id": summary_data["session_id"],
                    "timeout": PRECOMPACT_HOOK_TIMEOUT
                }
            )
            queue_operation(summary_data)
        finally:
            # Cancel alarm
            try:
                signal.alarm(0)
            except (AttributeError, ValueError):
                pass

        # Metrics: Record hook duration
        duration_ms = (time.perf_counter() - start_time) * 1000
        if hook_duration_seconds:
            hook_duration_seconds.labels(hook_type="PreCompact").observe(duration_ms / 1000)

        # User notification via stderr (visible to user, not Claude)
        project = summary_data.get("group_id", "unknown")
        trigger = hook_input["trigger"]
        print(f"📤 BMAD Memory: Session summary saved for {project} (trigger: {trigger}) [{duration_ms:.0f}ms]", file=sys.stderr)

        # Activity log with full content
        tools_list = ", ".join(transcript_analysis["tools_used"]) if transcript_analysis["tools_used"] else "None"
        files_count = len(transcript_analysis["files_modified"])
        prompts_count = transcript_analysis["user_prompts_count"]

        # Log summary header
        session_id = summary_data.get('session_id', 'unknown')
        session_short = session_id[:8] if len(session_id) >= 8 else session_id

        # TECH-DEBT-014: Comprehensive logging with full session content
        metadata = {
            'tools_used': transcript_analysis["tools_used"],
            'files_modified': len(transcript_analysis["files_modified"]),
            'prompts_count': transcript_analysis["user_prompts_count"],
            'content_hash': content_hash
        }
        log_precompact(project, session_short, summary_data["content"], metadata, duration_ms)

        # ALWAYS exit 0 to allow compaction to proceed
        return 0

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "hook_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )

        # Metrics: Record hook duration even on error
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(hook_type="PreCompact").observe(duration_seconds)

        # Non-blocking error - allow compaction to proceed
        return 0


if __name__ == "__main__":
    sys.exit(main())
