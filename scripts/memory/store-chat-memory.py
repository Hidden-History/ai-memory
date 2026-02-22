#!/usr/bin/env python3
"""Store chat memory to discussions collection for BMAD workflows.

Usage:
    python3 store-chat-memory.py --session-id <id> --agent <agent> --content <text>

Arguments:
    --session-id: Claude session ID
    --agent: BMAD agent name (dev, architect, pm, tea, analyst, etc.)
    --content: Conversation context to store

Stores to discussions collection with:
- type="chat_memory"
- timestamp (ISO 8601)
- agent field (BMAD context)
- session_id for traceability
- Embedding generation with graceful degradation

Exit Codes:
- 0: Success (stored or gracefully degraded)

Called by BMAD workflows during long sessions to persist conversation context.

2026 Best Practices:
- Structured JSON logging with extra={} dict (never f-strings)
- Graceful degradation: log warning and exit 0 on any error
- All Qdrant payload fields: snake_case
- Uses EmbeddingClient from src/memory/embeddings.py
- Follows MemoryPayload structure from src/memory/models.py
"""

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
# Use project root during development, installed location in production
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)

# Prefer local src if running from project, fallback to installed
if (PROJECT_ROOT / "src" / "memory").exists():
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
else:
    sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from qdrant_client.models import PointStruct

from memory.embeddings import EmbeddingClient, EmbeddingError
from memory.logging_config import StructuredFormatter
from memory.models import VALID_AGENTS, EmbeddingStatus, MemoryType
from memory.project import detect_project
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.validation import compute_content_hash

# Configure structured logging (Story 6.2)
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.scripts")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False


def store_chat_memory(
    session_id: str, agent: str, content: str, cwd: str = None
) -> bool:
    """Store chat memory to discussions collection.

    Args:
        session_id: Claude session identifier
        agent: BMAD agent name (dev, architect, pm, etc.)
        content: Conversation context to store
        cwd: Optional working directory for project detection

    Returns:
        bool: True if stored successfully, False if gracefully degraded

    Raises:
        No exceptions - all errors handled gracefully with exit 0
    """
    try:
        # Validate agent name
        if agent not in VALID_AGENTS:
            logger.warning(
                "invalid_agent_name",
                extra={
                    "agent": agent,
                    "valid_agents": VALID_AGENTS,
                    "session_id": session_id,
                },
            )
            # Continue with invalid agent for graceful degradation

        # Detect project from cwd if provided
        group_id = "unknown-project"
        if cwd:
            try:
                group_id = detect_project(cwd)
                logger.debug(
                    "project_detected", extra={"cwd": cwd, "group_id": group_id}
                )
            except Exception as e:
                logger.warning(
                    "project_detection_failed",
                    extra={"cwd": cwd, "error": str(e), "fallback": "unknown-project"},
                )

        # Generate embedding with graceful degradation
        embedding_status = EmbeddingStatus.PENDING.value
        vector = [0.0] * 768  # Default placeholder

        try:
            embed_client = EmbeddingClient()
            embeddings = embed_client.embed([content])
            vector = embeddings[0]
            embedding_status = EmbeddingStatus.COMPLETE.value
            logger.debug(
                "embedding_generated",
                extra={"session_id": session_id, "dimensions": len(vector)},
            )
        except EmbeddingError as e:
            logger.warning(
                "embedding_failed_using_placeholder",
                extra={"error": str(e), "session_id": session_id, "agent": agent},
            )
            # Continue with zero vector - graceful degradation

        # Build payload
        content_hash = compute_content_hash(content)
        memory_id = str(uuid.uuid4())

        payload = {
            "content": content,
            "content_hash": content_hash,
            "group_id": group_id,
            "type": MemoryType.CHAT_MEMORY.value,
            "source_hook": "bmad_workflow",  # Indicates BMAD workflow origin
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "embedding_status": embedding_status,
            "embedding_model": "jina-embeddings-v2-base-en",
            "agent": agent,  # BMAD agent context
            "importance": "medium",
        }

        # Store to discussions collection
        client = get_qdrant_client()
        client.upsert(
            collection_name="discussions",
            points=[PointStruct(id=memory_id, vector=vector, payload=payload)],
        )

        logger.info(
            "chat_memory_stored",
            extra={
                "memory_id": memory_id,
                "session_id": session_id,
                "agent": agent,
                "group_id": group_id,
                "embedding_status": embedding_status,
                "content_length": len(content),
            },
        )

        return True

    except QdrantUnavailable as e:
        logger.warning(
            "qdrant_unavailable",
            extra={"error": str(e), "session_id": session_id, "agent": agent},
        )
        return False

    except Exception as e:
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": session_id,
                "agent": agent,
            },
        )
        return False


def main() -> int:
    """Entry point with argument parsing.

    Returns:
        Exit code: Always 0 (graceful degradation)
    """
    parser = argparse.ArgumentParser(
        description="Store chat memory to discussions collection"
    )
    parser.add_argument("--session-id", required=True, help="Claude session ID")
    parser.add_argument(
        "--agent", required=True, help=f"BMAD agent name ({', '.join(VALID_AGENTS)})"
    )
    parser.add_argument(
        "--content", required=True, help="Conversation context to store"
    )
    parser.add_argument(
        "--cwd", required=False, help="Optional working directory for project detection"
    )

    try:
        args = parser.parse_args()

        # Validate content length (10-100,000 chars per MemoryPayload schema)
        content_len = len(args.content)
        if content_len < 10:
            logger.warning(
                "content_too_short",
                extra={
                    "content_length": content_len,
                    "minimum": 10,
                    "session_id": args.session_id,
                },
            )
            print(
                f"⚠️  AI Memory: Content too short ({content_len} chars, minimum 10)",
                file=sys.stderr,
            )
            return 0  # Graceful exit

        if content_len > 100000:
            logger.warning(
                "content_too_long_truncating",
                extra={
                    "content_length": content_len,
                    "maximum": 100000,
                    "session_id": args.session_id,
                },
            )
            args.content = args.content[:100000]  # Truncate to max

        # Store chat memory
        success = store_chat_memory(
            session_id=args.session_id,
            agent=args.agent,
            content=args.content,
            cwd=args.cwd,
        )

        if success:
            print(
                f"💬 AI Memory: Chat memory stored for {args.agent} "
                f"({len(args.content)} chars)",
                file=sys.stderr,
            )
        else:
            print(
                "⚠️  AI Memory: Chat memory storage failed (graceful degradation)",
                file=sys.stderr,
            )

        # Always exit 0 for graceful degradation
        return 0

    except Exception as e:
        logger.error(
            "script_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )
        print("⚠️  AI Memory: Script error (graceful degradation)", file=sys.stderr)
        return 0  # Always exit 0


if __name__ == "__main__":
    sys.exit(main())
