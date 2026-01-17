#!/usr/bin/env python3
"""Manual Save Memory - User-triggered session summary storage.

This script is invoked by the /save-memory slash command to allow users
to manually save a session summary at any time, not just at compaction.

Usage:
  /save-memory [optional description]

Exit Codes:
- 0: Success
- 1: Error (prints message to stderr)

2026 Best Practices:
- Sync QdrantClient (user triggered, acceptable wait)
- Structured JSON logging with extra={} dict
- Graceful degradation: queue to file on failure
- Store to agent-memory collection
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add src to path for imports
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.queue import queue_operation
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.project import detect_project
from memory.logging_config import StructuredFormatter
from memory.embeddings import EmbeddingClient, EmbeddingError
from memory.activity_log import log_manual_save

# Configure structured logging
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.manual")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

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
        from qdrant_client.models import PointStruct
        from memory.models import EmbeddingStatus
        from memory.validation import compute_content_hash
        import uuid

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
        vector = [0.0] * 768  # Default placeholder

        try:
            embed_client = EmbeddingClient()
            embeddings = embed_client.embed([summary_content])
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
            "content": summary_content,
            "content_hash": content_hash,
            "group_id": project_name,
            "type": "session_summary",
            "source_hook": "ManualSave",
            "session_id": session_id,
            "timestamp": timestamp,
            "embedding_status": embedding_status,
            "embedding_model": "nomic-embed-code",
            "importance": "normal",
            "manual_save": True,
            "user_description": description
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

        logger.info(
            "manual_save_stored",
            extra={
                "memory_id": memory_id,
                "session_id": session_id,
                "group_id": project_name
            }
        )

        return True

    except (ResponseHandlingException, UnexpectedResponse, ApiException, QdrantUnavailable) as e:
        logger.warning(
            "storage_failed_queuing",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "project": project_name
            }
        )
        # Queue for background processing
        queue_data = {
            "content": summary_content,
            "group_id": project_name,
            "memory_type": "session_summary",
            "source_hook": "ManualSave",
            "session_id": session_id,
            "importance": "normal"
        }
        queue_operation(queue_data)
        return False

    except Exception as e:
        logger.error(
            "unexpected_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return False


def main() -> int:
    """Manual save entry point.

    Returns:
        Exit code: 0 (success) or 1 (error)
    """
    # Get user description from args
    description = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""

    # Get current working directory
    cwd = os.getcwd()
    project_name = detect_project(cwd)

    # Get session ID from environment (set by Claude Code)
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # Store summary
    success = store_manual_summary(project_name, description, session_id)

    # TECH-DEBT-014: Comprehensive activity logging
    log_manual_save(project_name, description, success)

    if success:
        print(f"✅ Session summary saved to memory for {project_name}")
        if description:
            print(f"   Note: {description}")
        return 0
    else:
        print(f"⚠️  Session summary queued for background storage (Qdrant unavailable)")
        return 0  # Still return 0 - queuing is acceptable


if __name__ == "__main__":
    sys.exit(main())
