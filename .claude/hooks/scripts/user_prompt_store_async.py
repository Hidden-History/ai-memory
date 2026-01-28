#!/usr/bin/env python3
"""Background storage script for UserPromptSubmit hook.

Stores user messages to discussions collection with proper deduplication.
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# BUG-010: Tenacity for transient failure retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx  # For specific exception types

# CR-1.7: Setup path inline (must happen BEFORE any memory.* imports)
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# CR-1.2: Use consolidated logging and activity log
from memory.hooks_common import setup_hook_logging, log_to_activity
logger = setup_hook_logging()

from memory.config import get_config, COLLECTION_DISCUSSIONS, TYPE_USER_MESSAGE, EMBEDDING_MODEL
from memory.qdrant_client import get_qdrant_client, QdrantUnavailable
from memory.project import detect_project
from memory.validation import compute_content_hash
from memory.queue import queue_operation

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total
except ImportError:
    memory_captures_total = None

# Import Qdrant models
try:
    from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
except ImportError:
    PointStruct = None
    Filter = None
    FieldCondition = None
    MatchValue = None
    ApiException = Exception
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception

# CR-1.2: _log_to_activity removed - using consolidated function from hooks_common


def store_user_message(hook_input: Dict[str, Any]) -> bool:
    """Store user message to discussions collection.

    Args:
        hook_input: Hook input with session_id, prompt, turn_number

    Returns:
        True if stored successfully, False if queued
    """
    try:
        session_id = hook_input["session_id"]
        prompt = hook_input["prompt"]
        turn_number = hook_input.get("turn_number", 0)
        cwd = os.getcwd()  # Detect project from current directory

        # Detect project name
        group_id = detect_project(cwd)

        # Compute content hash
        content_hash = compute_content_hash(prompt)

        # Build payload (Issue #6: single timestamp for consistency)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "content": prompt,
            "content_hash": content_hash,
            "group_id": group_id,
            "type": TYPE_USER_MESSAGE,
            "source_hook": "UserPromptSubmit",
            "session_id": session_id,
            "timestamp": now,
            "turn_number": turn_number,
            "created_at": now,
            "embedding_status": "pending",
            "embedding_model": EMBEDDING_MODEL
        }

        # Check for duplicate message before storing (CRITICAL FIX: deduplication)
        client = get_qdrant_client()

        existing = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=Filter(must=[
                FieldCondition(key="session_id", match=MatchValue(value=session_id)),
                FieldCondition(key="content_hash", match=MatchValue(value=content_hash)),
                FieldCondition(key="type", match=MatchValue(value=TYPE_USER_MESSAGE))
            ]),
            limit=1,
            with_payload=False
        )

        if existing[0]:  # Duplicate found
            # CR-1.2: Use consolidated log function
            # BUG-036: Include project name for multi-project visibility
            log_to_activity(f"⏭️  UserPrompt skipped: Duplicate [{group_id}]", INSTALL_DIR)
            logger.info(
                "duplicate_user_message_skipped",
                extra={
                    "content_hash": content_hash,
                    "session_id": session_id,
                    "turn_number": turn_number
                }
            )
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="UserPromptSubmit",
                    status="duplicate",
                    project=group_id or "unknown"
                ).inc()
            return True

        # Generate deterministic UUID from content_hash (Fix #2: makes upsert idempotent)
        # Using uuid5 prevents TOCTOU race - same hash = same ID = no duplicate
        memory_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))

        # CR-1.5: Use config constant instead of magic number
        config = get_config()

        # Issue #3: Early return for empty content - no point embedding whitespace
        if not prompt or not prompt.strip():
            logger.info("empty_content_skipped", extra={"session_id": session_id})
            return True

        # BUG-010 Fix: Generate embedding with retry for transient failures.
        # Per BP-023: retry → fallback → degradation. 2-3 retries before zero vector.
        # embedding_status="pending" allows backfill worker to retry later (TECH-DEBT-059).
        try:
            from memory.embeddings import EmbeddingClient

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
                retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, ConnectionError)),
                reraise=True
            )
            def _embed_with_retry(content: str) -> list:
                with EmbeddingClient(config) as embed_client:
                    return embed_client.embed([content])[0]

            vector = _embed_with_retry(prompt)
            payload["embedding_status"] = "complete"
            logger.info("embedding_generated", extra={"dimensions": len(vector)})
        except Exception as e:
            # Graceful degradation: Use zero vector if all retries fail
            logger.warning(
                "embedding_failed_using_zero_vector",
                extra={"error": str(e), "error_type": type(e).__name__}
            )
            vector = [0.0] * config.embedding_dimension
            payload["embedding_status"] = "pending"

        # Store to Qdrant
        client.upsert(
            collection_name=COLLECTION_DISCUSSIONS,
            points=[
                PointStruct(
                    id=memory_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )

        # BUG-036: Include project name for multi-project visibility
        log_to_activity(f"✅ UserPrompt stored: Turn {turn_number} [{group_id}]", INSTALL_DIR)
        logger.info(
            "user_message_stored",
            extra={
                "memory_id": memory_id,
                "session_id": session_id,
                "group_id": group_id,
                "turn_number": turn_number,
                "content_length": len(prompt)
            }
        )

        # BUG-024: Enqueue for LLM classification
        try:
            from memory.classifier.queue import enqueue_for_classification, ClassificationTask
            from memory.classifier.config import CLASSIFIER_ENABLED

            if CLASSIFIER_ENABLED:
                task = ClassificationTask(
                    point_id=memory_id,
                    collection=COLLECTION_DISCUSSIONS,
                    content=prompt[:2000],  # Truncate for classifier
                    current_type="user_message",
                    group_id=group_id,
                    source_hook="UserPromptSubmit",
                    created_at=now  # Matches stored memory timestamp for traceability
                )
                enqueue_for_classification(task)
                logger.debug("classification_enqueued", extra={
                    "point_id": memory_id,
                    "collection": COLLECTION_DISCUSSIONS,
                    "current_type": "user_message"
                })
        except ImportError:
            pass  # Classifier not installed
        except Exception as e:
            logger.warning("classification_enqueue_failed", extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "point_id": memory_id
            })

        # Metrics
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="UserPromptSubmit",
                status="success",
                project=group_id or "unknown"
            ).inc()

        # BUG-037: Push capture metrics to Pushgateway for Grafana visibility
        # TECH-DEBT-071: Push token count for stored user prompt
        # HIGH-3: Token estimation ~25-50% error margin (4 chars/token approximation)
        try:
            from memory.metrics_push import push_capture_metrics_async, push_token_metrics_async

            # BUG-037: Push capture count for Grafana project visibility
            push_capture_metrics_async(
                hook_type="UserPromptSubmit",
                status="success",
                project=group_id or "unknown",
                collection=COLLECTION_DISCUSSIONS,
                count=1
            )

            token_count = len(prompt) // 4  # Fast estimation, consider tiktoken if accuracy critical
            if token_count > 0:
                push_token_metrics_async(
                    operation="capture",
                    direction="stored",
                    project=group_id or "unknown",
                    token_count=token_count
                )
        except ImportError:
            pass  # Graceful degradation if metrics_push not available

        return True

    except (ResponseHandlingException, UnexpectedResponse, ApiException, QdrantUnavailable) as e:
        # BUG-036: Include project name for multi-project visibility
        project_name = detect_project(os.getcwd())
        log_to_activity(f"📥 UserPrompt queued: Qdrant unavailable [{project_name}]", INSTALL_DIR)
        logger.warning(
            "qdrant_error_queuing",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": hook_input.get("session_id")
            }
        )
        # Queue for retry
        queue_data = {
            "content": hook_input["prompt"],
            "group_id": detect_project(os.getcwd()),
            "memory_type": TYPE_USER_MESSAGE,
            "source_hook": "UserPromptSubmit",
            "session_id": hook_input["session_id"],
            "turn_number": hook_input.get("turn_number", 0)
        }
        queue_operation(queue_data)

        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="UserPromptSubmit",
                status="queued",
                project=queue_data["group_id"] or "unknown"
            ).inc()

        return False

    except Exception as e:
        # BUG-036: Include project name for multi-project visibility
        project_name = detect_project(os.getcwd()) if 'group_id' not in dir() else group_id
        log_to_activity(f"❌ UserPrompt failed: {type(e).__name__} [{project_name}]", INSTALL_DIR)
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": hook_input.get("session_id")
            }
        )

        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="UserPromptSubmit",
                status="failed",
                project="unknown"
            ).inc()

        return False


def main() -> int:
    """Background storage entry point."""
    try:
        # Read hook input from stdin
        raw_input = sys.stdin.read()
        hook_input = json.loads(raw_input)

        # Store user message
        store_user_message(hook_input)

        return 0

    except Exception as e:
        logger.error(
            "async_storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
