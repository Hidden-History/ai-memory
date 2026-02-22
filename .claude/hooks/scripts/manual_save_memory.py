#!/usr/bin/env python3
"""Manual Save Memory - User-triggered session summary storage.

This script is invoked by the /save-memory slash command to allow users
to manually save a session summary at any time, not just at compaction.

Usage:
  /save-memory [optional description]
  /save-memory "description" --type agent_memory
  /save-memory "description" --type agent_insight

Exit Codes:
- 0: Success
- 1: Error (prints message to stderr)

2026 Best Practices:
- Sync QdrantClient (user triggered, acceptable wait)
- Structured JSON logging with extra={} dict
- Graceful degradation: queue to file on failure
- Store to discussions collection
"""

import os
import sys
from datetime import datetime, timezone

# BUG-044: Add memory module to path before imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
src_path = os.path.join(INSTALL_DIR, "src")

# Validate path exists for graceful degradation
if not os.path.exists(src_path):
    print(f"⚠️  Warning: Memory module not found at {src_path}", file=sys.stderr)
    print(
        "⚠️  /save-memory will not function without proper installation",
        file=sys.stderr,
    )
    sys.exit(1)  # Non-blocking error - graceful degradation

sys.path.insert(0, src_path)

from memory.activity_log import log_manual_save
from memory.config import (
    COLLECTION_DISCUSSIONS,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from memory.embeddings import EmbeddingClient, EmbeddingError

# Now memory module imports will work
from memory.hooks_common import setup_hook_logging
from memory.project import detect_project
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.queue import queue_operation

# Configure structured logging using shared utility (CR-4 Wave 2)
logger = setup_hook_logging("ai_memory.manual")

# Log successful path setup (F7: telemetry)
logger.debug(
    "python_path_configured", extra={"install_dir": INSTALL_DIR, "src_path": src_path}
)

# Import Qdrant-specific exceptions
try:
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
except ImportError:
    ApiException = Exception
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception


def store_manual_summary(project_name: str, description: str, session_id: str) -> bool:
    """Store manually created session summary.

    Args:
        project_name: Project identifier
        description: User-provided description
        session_id: Current session ID (from environment)

    Returns:
        bool: True if stored successfully, False if queued
    """
    try:
        import uuid

        from qdrant_client.models import PointStruct

        from memory.models import EmbeddingStatus
        from memory.validation import compute_content_hash

        # Build summary content
        timestamp = datetime.now(timezone.utc).isoformat()
        summary_content = f"""Manual Session Save: {project_name}
Session ID: {session_id}
Timestamp: {timestamp}
User Note: {description if description else "No description provided"}

This session summary was manually saved by the user using /save-memory command.
"""

        content_hash = compute_content_hash(summary_content)
        memory_id = str(uuid.uuid4())

        # Generate embedding
        embedding_status = EmbeddingStatus.PENDING.value
        vector = [0.0] * EMBEDDING_DIMENSIONS  # Default placeholder (CR-4.6)

        try:
            embed_client = EmbeddingClient()
            embeddings = embed_client.embed([summary_content])
            vector = embeddings[0]
            embedding_status = EmbeddingStatus.COMPLETE.value
            logger.info(
                "embedding_generated",
                extra={"memory_id": memory_id, "dimensions": len(vector)},
            )
        except EmbeddingError as e:
            # CR-4.4: Explicitly set FAILED status when embedding generation fails
            embedding_status = EmbeddingStatus.FAILED.value
            logger.warning(
                "embedding_failed_using_placeholder",
                extra={
                    "error": str(e),
                    "memory_id": memory_id,
                    "embedding_status": "failed",
                },
            )
            # Continue with zero vector - will be backfilled later

        payload = {
            "content": summary_content,
            "content_hash": content_hash,
            "group_id": project_name,
            "type": "session",
            "source_hook": "ManualSave",
            "session_id": session_id,
            "timestamp": timestamp,
            "embedding_status": embedding_status,
            "embedding_model": EMBEDDING_MODEL,  # CR-4.8
            "importance": "normal",
            "manual_save": True,
            "user_description": description,
        }

        # Store to discussions collection
        client = get_qdrant_client()
        client.upsert(
            collection_name=COLLECTION_DISCUSSIONS,
            points=[PointStruct(id=memory_id, vector=vector, payload=payload)],
        )

        logger.info(
            "manual_save_stored",
            extra={
                "memory_id": memory_id,
                "session_id": session_id,
                "group_id": project_name,
            },
        )

        return True

    except (
        ResponseHandlingException,
        UnexpectedResponse,
        ApiException,
        QdrantUnavailable,
    ) as e:
        logger.warning(
            "storage_failed_queuing",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "project": project_name,
            },
        )
        # Queue for background processing
        queue_data = {
            "content": summary_content,
            "group_id": project_name,
            "memory_type": "session",
            "source_hook": "ManualSave",
            "session_id": session_id,
            "importance": "normal",
        }
        queue_operation(queue_data)
        return False

    except Exception as e:
        logger.error(
            "unexpected_error", extra={"error": str(e), "error_type": type(e).__name__}
        )
        return False


def parse_args(argv: list[str]) -> tuple[str, str | None]:
    """Parse command line arguments.

    Args:
        argv: Arguments (sys.argv[1:])

    Returns:
        Tuple of (description, type_override)

    Raises:
        ValueError: If --type is provided without a value
    """
    description_parts = []
    type_override = None

    i = 0
    while i < len(argv):
        if argv[i] == "--type":
            if i + 1 < len(argv):
                type_override = argv[i + 1]
                i += 2
            else:
                raise ValueError(
                    "--type requires a value (agent_memory or agent_insight)"
                )
        else:
            description_parts.append(argv[i])
            i += 1

    return " ".join(description_parts), type_override


def main() -> int:
    """Manual save entry point.

    Returns:
        Exit code: 0 (success) or 1 (error)
    """
    # Parse arguments: support --type agent_memory|agent_insight
    try:
        description, type_override = parse_args(sys.argv[1:])
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    # Get current working directory
    cwd = os.getcwd()
    project_name = detect_project(cwd)

    # Get session ID from environment (set by Claude Code)
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # Agent memory storage path (SPEC-017 S4)
    if type_override in ("agent_memory", "agent_insight"):
        # Check if parzival is enabled
        try:
            from memory.config import get_config

            config = get_config()
            if not config.parzival_enabled:
                print(
                    "Error: Agent memory types require Parzival to be enabled (parzival_enabled=true)",
                    file=sys.stderr,
                )
                return 1
        except Exception:
            print(
                "Error: Could not load config to check parzival_enabled",
                file=sys.stderr,
            )
            return 1

        # Use store_agent_memory() from SPEC-015
        try:
            from memory.storage import MemoryStorage

            storage = MemoryStorage()
            result = storage.store_agent_memory(
                content=description or "Manual save",
                memory_type=type_override,
                agent_id="parzival",
                group_id=project_name,
                cwd=cwd,
            )

            if result["status"] == "stored":
                print(
                    f"✅ Saved {type_override} to Parzival namespace for {project_name}"
                )
                if description:
                    print(f"   Note: {description}")
                log_manual_save(project_name, description, True)
                return 0
            elif result["status"] == "blocked":
                print(
                    "Content blocked by security scanner (secrets detected)",
                    file=sys.stderr,
                )
                log_manual_save(project_name, description, False)
                return 1
            elif result["status"] == "duplicate":
                print("Content already exists (duplicate)")
                log_manual_save(project_name, description, True)
                return 0
            else:
                print(f"Unexpected storage result: {result['status']}", file=sys.stderr)
                log_manual_save(project_name, description, False)
                return 1
        except Exception as e:
            logger.error("agent_memory_save_failed", extra={"error": str(e)})
            print(f"Error saving agent memory: {e}", file=sys.stderr)
            log_manual_save(project_name, description, False)
            return 1
    elif type_override is not None:
        print(
            f"Error: Invalid type '{type_override}'. Must be 'agent_memory' or 'agent_insight'",
            file=sys.stderr,
        )
        return 1

    # Default path: store session summary (existing behavior unchanged)
    success = store_manual_summary(project_name, description, session_id)

    # TECH-DEBT-014: Comprehensive activity logging
    log_manual_save(project_name, description, success)

    if success:
        print(f"✅ Session summary saved to memory for {project_name}")
        if description:
            print(f"   Note: {description}")
        return 0
    else:
        print("⚠️  Session summary queued for background storage (Qdrant unavailable)")
        return 0  # Still return 0 - queuing is acceptable


if __name__ == "__main__":
    sys.exit(main())
