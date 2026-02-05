#!/usr/bin/env python3
"""Background storage script for Stop hook.

Stores agent responses to discussions collection with proper deduplication.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx  # For specific exception types

# BUG-010: Tenacity for transient failure retry
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# CR-1.7: Setup path inline (must happen BEFORE any memory.* imports)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# CR-1.2: Use consolidated logging and activity log
from memory.hooks_common import log_to_activity, setup_hook_logging

logger = setup_hook_logging()

from memory.config import (
    COLLECTION_DISCUSSIONS,
    EMBEDDING_MODEL,
    TYPE_AGENT_RESPONSE,
    get_config,
)
from memory.project import detect_project
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.queue import queue_operation
from memory.validation import compute_content_hash

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total
except ImportError:
    memory_captures_total = None

# Import Qdrant models
try:
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
    from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
except ImportError:
    PointStruct = None
    Filter = None
    FieldCondition = None
    MatchValue = None
    ApiException = Exception
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception

# CR-1.2: _log_to_activity removed - using consolidated function from hooks_common


def store_agent_response(store_data: dict[str, Any]) -> bool:
    """Store agent response to discussions collection.

    Args:
        store_data: Data with session_id, response_text, turn_number

    Returns:
        True if stored successfully, False if queued
    """
    try:
        session_id = store_data["session_id"]
        response_text = store_data["response_text"]
        turn_number = store_data.get("turn_number", 0)

        cwd = os.getcwd()  # Detect project from current directory

        # Detect project name
        group_id = detect_project(cwd)

        # Compute content hash
        content_hash = compute_content_hash(response_text)

        # Build payload (Issue #6: single timestamp for consistency)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "content": response_text,
            "content_hash": content_hash,
            "group_id": group_id,
            "type": TYPE_AGENT_RESPONSE,
            "source_hook": "Stop",
            "session_id": session_id,
            "timestamp": now,
            "turn_number": turn_number,
            "created_at": now,
            "embedding_status": "pending",
            "embedding_model": EMBEDDING_MODEL,
        }

        # Check for duplicate response before storing (CRITICAL FIX: deduplication)
        client = get_qdrant_client()

        existing = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="session_id", match=MatchValue(value=session_id)
                    ),
                    FieldCondition(
                        key="content_hash", match=MatchValue(value=content_hash)
                    ),
                    FieldCondition(
                        key="type", match=MatchValue(value=TYPE_AGENT_RESPONSE)
                    ),
                ]
            ),
            limit=1,
            with_payload=False,
        )

        if existing[0]:  # Duplicate found
            # CR-1.2: Use consolidated log function
            # BUG-036: Include project name for multi-project visibility
            log_to_activity(
                f"⏭️  AgentResponse skipped: Duplicate [{group_id}]", INSTALL_DIR
            )
            logger.info(
                "duplicate_agent_response_skipped",
                extra={
                    "content_hash": content_hash,
                    "session_id": session_id,
                    "turn_number": turn_number,
                },
            )
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="Stop",
                    status="duplicate",
                    project=group_id or "unknown",
                    collection="discussions",
                ).inc()
            return True

        # Generate deterministic UUID from content_hash (Fix #2: makes upsert idempotent)
        # Using uuid5 prevents TOCTOU race - same hash = same ID = no duplicate
        memory_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))

        # CR-1.5: Use config constant instead of magic number
        config = get_config()

        # Issue #3: Early return for empty content - no point embedding whitespace
        if not response_text or not response_text.strip():
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
                retry=retry_if_exception_type(
                    (httpx.TimeoutException, httpx.ConnectError, ConnectionError)
                ),
                reraise=True,
            )
            def _embed_with_retry(content: str) -> list:
                with EmbeddingClient(config) as embed_client:
                    return embed_client.embed([content])[0]

            vector = _embed_with_retry(response_text)
            payload["embedding_status"] = "complete"
            logger.info("embedding_generated", extra={"dimensions": len(vector)})
        except Exception as e:
            # Graceful degradation: Use zero vector if all retries fail
            logger.warning(
                "embedding_failed_using_zero_vector",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            vector = [0.0] * config.embedding_dimension
            payload["embedding_status"] = "pending"

        # Store to Qdrant
        client.upsert(
            collection_name=COLLECTION_DISCUSSIONS,
            points=[PointStruct(id=memory_id, vector=vector, payload=payload)],
        )

        # BUG-036: Include project name for multi-project visibility
        log_to_activity(
            f"✅ AgentResponse stored: Turn {turn_number} [{group_id}]", INSTALL_DIR
        )
        logger.info(
            "agent_response_stored",
            extra={
                "memory_id": memory_id,
                "session_id": session_id,
                "group_id": group_id,
                "turn_number": turn_number,
                "content_length": len(response_text),
            },
        )

        # BUG-024: Enqueue for LLM classification
        try:
            from memory.classifier.config import CLASSIFIER_ENABLED
            from memory.classifier.queue import (
                ClassificationTask,
                enqueue_for_classification,
            )

            if CLASSIFIER_ENABLED:
                task = ClassificationTask(
                    point_id=memory_id,
                    collection=COLLECTION_DISCUSSIONS,
                    content=response_text[:2000],  # Truncate for classifier
                    current_type="agent_response",
                    group_id=group_id,
                    source_hook="Stop",
                    created_at=now,  # Matches stored memory timestamp for traceability
                )
                enqueue_for_classification(task)
                logger.debug(
                    "classification_enqueued",
                    extra={
                        "point_id": memory_id,
                        "collection": COLLECTION_DISCUSSIONS,
                        "current_type": "agent_response",
                    },
                )
        except ImportError:
            pass  # Classifier not installed
        except Exception as e:
            logger.warning(
                "classification_enqueue_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "point_id": memory_id,
                },
            )

        # Metrics
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="success",
                project=group_id or "unknown",
                collection="discussions",
            ).inc()

        # BUG-037: Push capture metrics to Pushgateway for Grafana visibility
        # TECH-DEBT-071: Push token count for stored agent response
        # HIGH-3: Token estimation ~25-50% error margin (4 chars/token approximation)
        try:
            from memory.metrics_push import (
                push_capture_metrics_async,
                push_token_metrics_async,
            )

            # BUG-037: Push capture count for Grafana project visibility
            push_capture_metrics_async(
                hook_type="Stop",
                status="success",
                project=group_id or "unknown",
                collection=COLLECTION_DISCUSSIONS,
                count=1,
            )

            token_count = (
                len(response_text) // 4
            )  # Fast estimation, consider tiktoken if accuracy critical
            if token_count > 0:
                push_token_metrics_async(
                    operation="capture",
                    direction="stored",
                    project=group_id or "unknown",
                    token_count=token_count,
                )
        except ImportError:
            pass  # Graceful degradation if metrics_push not available

        return True

    except (
        ResponseHandlingException,
        UnexpectedResponse,
        ApiException,
        QdrantUnavailable,
    ) as e:
        # BUG-036: Include project name for multi-project visibility
        project_name = detect_project(os.getcwd())
        log_to_activity(
            f"📥 AgentResponse queued: Qdrant unavailable [{project_name}]", INSTALL_DIR
        )
        logger.warning(
            "qdrant_error_queuing",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": store_data.get("session_id"),
            },
        )
        # Queue for retry
        queue_data = {
            "content": store_data["response_text"],
            "group_id": detect_project(os.getcwd()),
            "memory_type": TYPE_AGENT_RESPONSE,
            "source_hook": "Stop",
            "session_id": store_data["session_id"],
            "turn_number": store_data.get("turn_number", 0),
        }
        queue_operation(queue_data)

        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="queued",
                project=queue_data["group_id"] or "unknown",
                collection="discussions",
            ).inc()

        return False

    except Exception as e:
        # BUG-036: Include project name for multi-project visibility
        project_name = (
            detect_project(os.getcwd()) if "group_id" not in dir() else group_id
        )
        log_to_activity(
            f"❌ AgentResponse failed: {type(e).__name__} [{project_name}]", INSTALL_DIR
        )
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": store_data.get("session_id"),
            },
        )

        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="Stop",
                status="failed",
                project="unknown",
                collection="discussions",
            ).inc()

        return False


def main() -> int:
    """Background storage entry point."""
    try:
        # Read store data from stdin
        raw_input = sys.stdin.read()
        store_data = json.loads(raw_input)

        # Store agent response
        store_agent_response(store_data)
        return 0

    except Exception as e:
        logger.error(
            "async_storage_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
