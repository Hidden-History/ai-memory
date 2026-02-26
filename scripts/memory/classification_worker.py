#!/usr/bin/env python3
"""Classification worker - processes classification queue.

RESOURCE LIMITS:
- Max 4 concurrent classification tasks
- Poll interval: 5 seconds
- Batch size: 10 items
- Graceful shutdown on SIGTERM/SIGINT
"""

import argparse
import asyncio
import logging
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.classifier import classify
from memory.classifier.config import CLASSIFIER_ENABLED
from memory.classifier.queue import ClassificationTask, dequeue_batch, get_queue_size
from memory.storage import update_point_payload

# SPEC-021: Trace buffer for 9_classify span emission
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 2000  # Max chars for Langfuse input/output fields (Wave 1H)

# Phase 2: Initialize Langfuse instrumentation for classifier LLM calls
try:
    from memory.langfuse_config import is_langfuse_enabled

    if is_langfuse_enabled():
        # Pre-warm Langfuse client singleton (side effect: initializes connection)
        from memory.langfuse_config import get_langfuse_client

        if get_langfuse_client():
            logging.getLogger("ai_memory.classifier.worker").info(
                "langfuse_classifier_tracing_enabled"
            )
except ImportError:
    pass

logger = logging.getLogger("ai_memory.classifier.worker")

# Resource limits
POLL_INTERVAL = 5  # seconds
BATCH_SIZE = 10
MAX_RETRIES = 3
MAX_CONCURRENT_TASKS = 4  # Limit concurrent classifications
WORKER_THREAD_POOL_SIZE = 4  # Limit thread pool

# Thread-safe shutdown event (MED-1)
_shutdown_event = threading.Event()


def setup_signal_handlers() -> None:
    """Setup graceful shutdown handlers."""

    def handle_shutdown(signum, frame):
        logger.info("shutdown_signal_received", extra={"signal": signum})
        _shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)


async def process_task(task: ClassificationTask, executor: ThreadPoolExecutor) -> bool:
    """Process single classification task. Returns True if successful."""
    try:
        loop = asyncio.get_event_loop()

        # Wave 1H: Capture real start/end times for latency measurement in Langfuse GENERATION
        classify_start = datetime.now(tz=timezone.utc)

        # Run classification in thread pool (not unbounded)
        result = await loop.run_in_executor(
            executor,
            lambda: classify(
                content=task.content,
                current_type=task.current_type,
                collection=task.collection,
            ),
        )

        # Wave 1H: Capture real end time after LLM call completes
        classify_end = datetime.now(tz=timezone.utc)

        # Wave 1H: Helper to emit 9_classify as GENERATION with actual content + timing
        def _emit_classify_trace(output_text: str, metadata: dict) -> None:
            if not emit_trace_event:
                return
            try:
                # input: actual content being classified (truncated to 2000 chars)
                # output: classification result with reasoning
                # as_type="generation": creates Langfuse GENERATION (not SPAN)
                # model: specific model name (e.g., "llama3.2:3b", "claude-3-5-haiku-20241022")
                # usage: token counts propagated from ProviderResponse via ClassificationResult
                model_name = getattr(result, "model_name", "") or "unknown" if result else "unknown"
                data_payload = {
                    "input": task.content[:TRACE_CONTENT_MAX],
                    "output": output_text[:TRACE_CONTENT_MAX],
                    "model": model_name,
                    "usage": {
                        "input": getattr(result, "input_tokens", None) or 0,
                        "output": getattr(result, "output_tokens", None) or 0,
                    },
                    "metadata": {
                        **metadata,
                        "point_id": task.point_id,
                        "collection": task.collection,
                        "source_hook": task.source_hook,
                    },
                }
                emit_trace_event(
                    event_type="9_classify",
                    data=data_payload,
                    trace_id=task.trace_id,
                    session_id=task.session_id,  # Wave 1H: Link to Claude session
                    project_id=task.group_id,
                    start_time=classify_start,
                    end_time=classify_end,
                    as_type="generation",  # Wave 1H: GENERATION not SPAN
                )
            except Exception as e:
                logger.debug("emit_classify_trace_failed: %s", e)

        if result and result.confidence >= 0.7:
            # Update Qdrant with new type (TECH-DEBT-069 Phase 5)
            success = await loop.run_in_executor(
                executor,
                lambda: update_point_payload(
                    collection=task.collection,
                    point_id=task.point_id,
                    payload_updates={
                        "type": result.classified_type,
                        "classification_confidence": result.confidence,
                        "classification_provider": result.provider_used,
                        "classification_reasoning": result.reasoning,
                        "classified_at": datetime.now(timezone.utc).isoformat(),
                        "is_classified": True,
                    },
                ),
            )

            if success:
                logger.info(
                    "classification_complete",
                    extra={
                        "point_id": task.point_id,
                        "old_type": task.current_type,
                        "new_type": result.classified_type,
                        "confidence": result.confidence,
                        "provider": result.provider_used,
                    },
                )
                _emit_classify_trace(
                    output_text=(
                        f"Classified as '{result.classified_type}' "
                        f"(confidence: {result.confidence:.2f}, "
                        f"provider: {result.provider_used}, "
                        f"reclassified: {result.was_reclassified}). "
                        f"Reasoning: {result.reasoning}"
                    ),
                    metadata={
                        "classified_type": result.classified_type,
                        "confidence": result.confidence,
                        "was_reclassified": result.was_reclassified,
                        "provider": result.provider_used,
                        "status": "success",
                    },
                )
                return True
            else:
                logger.error(
                    "classification_update_failed",
                    extra={
                        "point_id": task.point_id,
                        "collection": task.collection,
                        "classified_type": result.classified_type,
                    },
                )
                _emit_classify_trace(
                    output_text=(
                        f"Classification succeeded ('{result.classified_type}', "
                        f"confidence: {result.confidence:.2f}) but Qdrant update failed."
                    ),
                    metadata={
                        "classified_type": result.classified_type,
                        "confidence": result.confidence,
                        "was_reclassified": result.was_reclassified,
                        "provider": result.provider_used,
                        "status": "qdrant_update_failed",
                    },
                )
                return False
        else:
            logger.debug(
                "classification_unchanged",
                extra={
                    "point_id": task.point_id,
                    "reason": "low_confidence" if result else "no_result",
                },
            )
            _emit_classify_trace(
                output_text=(
                    f"Classification unchanged: kept '{result.classified_type if result else task.current_type}' "
                    f"(confidence: {result.confidence:.2f if result else 0.0}, "
                    f"provider: {result.provider_used if result else 'none'}, "
                    f"below threshold or no result)"
                ),
                metadata={
                    "classified_type": result.classified_type if result else None,
                    "confidence": result.confidence if result else None,
                    "was_reclassified": result.was_reclassified if result else None,
                    "provider": result.provider_used if result else None,
                    "status": "low_confidence",
                },
            )
            return True  # Still counts as processed

    except Exception as e:
        logger.error(
            "classification_failed",
            extra={
                "point_id": task.point_id,
                "error": str(e),
                "retry_count": task.retry_count,
            },
        )
        return False


async def process_batch(executor: ThreadPoolExecutor) -> int:
    """Process one batch of classification tasks. Returns items processed."""
    tasks = dequeue_batch(BATCH_SIZE)

    if not tasks:
        return 0

    # Use semaphore to limit concurrent tasks
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

    async def limited_process(task):
        async with semaphore:
            return await process_task(task, executor)

    # Process with concurrency limit
    results = await asyncio.gather(
        *[limited_process(task) for task in tasks], return_exceptions=True
    )

    # MED-4: Log exceptions explicitly
    success_count = 0
    for r in results:
        if isinstance(r, Exception):
            logger.error(
                "task_exception", extra={"error": str(r), "type": type(r).__name__}
            )
        elif r is True:
            success_count += 1
    logger.info(
        "batch_processed",
        extra={
            "total": len(tasks),
            "success": success_count,
            "failed": len(tasks) - success_count,
        },
    )

    return len(tasks)


async def run_worker() -> None:
    """Main worker loop with resource limits."""
    logger.info(
        "worker_started",
        extra={
            "poll_interval": POLL_INTERVAL,
            "batch_size": BATCH_SIZE,
            "max_concurrent": MAX_CONCURRENT_TASKS,
        },
    )

    # Create bounded thread pool
    executor = ThreadPoolExecutor(max_workers=WORKER_THREAD_POOL_SIZE)

    try:
        while not _shutdown_event.is_set():
            if not CLASSIFIER_ENABLED:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            queue_size = get_queue_size()
            if queue_size > 0:
                logger.debug("queue_poll", extra={"queue_size": queue_size})
                await process_batch(executor)

            await asyncio.sleep(POLL_INTERVAL)
    finally:
        executor.shutdown(wait=True)
        logger.info("worker_stopped")


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Classification worker")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument(
        "--once", action="store_true", help="Process one batch and exit"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    setup_signal_handlers()

    if args.once:
        executor = ThreadPoolExecutor(max_workers=WORKER_THREAD_POOL_SIZE)
        try:
            count = asyncio.run(process_batch(executor))
            print(f"Processed {count} items")
        finally:
            executor.shutdown(wait=True)
        return 0

    asyncio.run(run_worker())
    return 0


if __name__ == "__main__":
    sys.exit(main())
