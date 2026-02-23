#!/usr/bin/env python3
"""Classification queue processor daemon.

BUG-024 Fix: Processes classification queue using asyncio daemon pattern.

Architecture:
- Asyncio daemon with graceful shutdown per BP-039
- Batch processing: dequeue_batch(batch_size=10)
- Concurrent classification: asyncio.gather() with return_exceptions=True
- Updates Qdrant payload on reclassification
- Prometheus Pushgateway metrics (port 29091)
- Structured logging with setup_hook_logging()

Usage:
    # Run standalone
    python3 scripts/memory/process_classification_queue.py

    # Run as Docker service (future)
    docker compose -f docker/docker-compose.yml up -d classifier-worker

Reference:
- BP-039: Async Background Task Processing for Python (2025)
- BUG-024: LLM Classifier works but no daemon processes the queue
"""

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

# Setup Python path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

import json
from dataclasses import asdict

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    pushadd_to_gateway,
)

from memory.classifier.llm_classifier import classify
from memory.classifier.queue import (
    MAX_BATCH_SIZE,
    QUEUE_DIR,
    ClassificationTask,
    dequeue_batch,
    get_queue_size,
)
from memory.hooks_common import setup_hook_logging
from memory.storage import update_point_payload

# =============================================================================
# CONFIGURATION
# =============================================================================

BATCH_SIZE = 10  # Max items per batch
POLL_INTERVAL = 5.0  # Seconds between queue checks when empty
MAX_BACKOFF = 60.0  # Max backoff seconds on repeated errors
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "localhost:29091")
PUSHGATEWAY_ENABLED = os.getenv("PUSHGATEWAY_ENABLED", "true").lower() == "true"
JOB_NAME = "ai_memory_classifier"
DLQ_FILE = QUEUE_DIR / "classification_queue_dlq.jsonl"  # Dead letter queue

# Setup logging
logger = setup_hook_logging("ai_memory.classifier.processor")

# SPEC-020 §6: Enable Langfuse auto-instrumentation for Anthropic calls
try:
    from memory.langfuse_config import is_langfuse_enabled
    if is_langfuse_enabled():
        try:
            from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
            AnthropicInstrumentor().instrument()
            logger.info("langfuse_anthropic_instrumentor_enabled")
        except ImportError:
            logger.warning("opentelemetry-instrumentation-anthropic not installed — Anthropic SDK calls will not be traced")
except ImportError:
    pass  # memory.langfuse_config not available

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

# Per-worker registry (not global) - BP-039 best practice
registry = CollectorRegistry()

# Queue processing metrics
classifier_queue_processed_total = Counter(
    "ai_memory_classifier_queue_processed_total",
    "Total tasks processed from queue",
    ["status"],  # success, failed, skipped
    registry=registry,
)

classifier_last_success_timestamp = Gauge(
    "ai_memory_classifier_last_success_timestamp",
    "Last successful batch timestamp",
    registry=registry,
)

classifier_batch_duration_seconds = Histogram(
    "ai_memory_classifier_batch_duration_seconds",
    "Time to process batch",
    registry=registry,
    # Buckets for LLM classification latency: 500ms - 60s
    # Covers fast classifications (<2s) and slow ones (>10s for long content)
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
)

classifier_queue_size_gauge = Gauge(
    "ai_memory_classifier_queue_size", "Current queue size", registry=registry
)

# LOW #9: Queue throughput metrics for trend analysis
classifier_queue_dequeued_total = Counter(
    "ai_memory_classifier_queue_dequeued_total",
    "Total tasks dequeued from queue",
    registry=registry,
)


def push_metrics() -> None:
    """Push metrics to Pushgateway (non-blocking, graceful degradation).

    Pushes TWO registries:
    1. Worker's custom registry (queue_processed_total, batch_duration, etc.)
    2. Global REGISTRY (classifier metrics from src/memory/classifier/metrics.py)

    BUG-021: Classifier metrics (requests_total, tokens_total, fallbacks_total)
    were defined in global REGISTRY but never pushed. This fix ensures both
    worker AND classifier metrics reach Prometheus.
    """
    if not PUSHGATEWAY_ENABLED:
        return

    try:
        # Update queue size gauge before push
        current_queue_size = get_queue_size()
        classifier_queue_size_gauge.set(current_queue_size)

        # Push worker's custom registry (queue metrics)
        # MEDIUM #5: Increased timeout from 0.5s to 2.0s for CPU bursts
        pushadd_to_gateway(
            PUSHGATEWAY_URL, job=JOB_NAME, registry=registry, timeout=2.0
        )

        # BUG-021 FIX: Also push global REGISTRY (classifier LLM metrics)
        # Classifier metrics are incremented in src/memory/classifier/metrics.py
        # via record_classification(), record_fallback(), etc.
        pushadd_to_gateway(
            PUSHGATEWAY_URL,
            job=JOB_NAME,
            registry=REGISTRY,  # Global registry with classifier metrics
            timeout=2.0,
        )
    except Exception as e:
        logger.warning(
            "pushgateway_push_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )


def _touch_health_file() -> None:
    """Create health check marker for Docker (non-blocking, graceful degradation)."""
    try:
        Path("/tmp/worker.health").touch()
        logger.debug("health_file_updated", extra={"path": "/tmp/worker.health"})
    except Exception as e:
        # F3: Log failure for debugging (non-blocking, graceful degradation)
        logger.warning(
            "health_file_update_failed",
            extra={
                "path": "/tmp/worker.health",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )


def _move_to_dlq(task: ClassificationTask, error: str) -> None:
    """Move failed task to dead letter queue for manual review.

    Args:
        task: Failed ClassificationTask
        error: Error message describing failure
    """
    try:
        # Ensure DLQ directory exists
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        # Add error info to task
        task_dict = asdict(task)
        task_dict["last_error"] = error
        task_dict["retry_count"] = task.retry_count + 1
        task_dict["dlq_timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Append to DLQ file
        with open(DLQ_FILE, "a") as f:
            f.write(json.dumps(task_dict) + "\n")

        logger.info(
            "task_moved_to_dlq",
            extra={
                "point_id": task.point_id,
                "collection": task.collection,
                "error": error[:100],  # Truncate for logs
                "dlq_file": str(DLQ_FILE),
            },
        )
    except Exception as dlq_error:
        # DLQ failure is logged but doesn't propagate
        logger.warning(
            "dlq_write_failed",
            extra={
                "point_id": task.point_id,
                "error": str(dlq_error),
                "error_type": type(dlq_error).__name__,
            },
        )


# =============================================================================
# CLASSIFICATION WORKER
# =============================================================================


class ClassificationWorker:
    """Asyncio daemon for processing classification queue.

    Implements BP-039 async background worker pattern:
    - Graceful shutdown with signal handlers
    - Batch processing with concurrent execution
    - Exponential backoff when idle
    - Prometheus metrics push
    """

    def __init__(
        self, batch_size: int = BATCH_SIZE, poll_interval: float = POLL_INTERVAL
    ):
        """Initialize worker.

        Args:
            batch_size: Max tasks per batch (default: 10)
            poll_interval: Seconds between checks when queue empty (default: 5.0)
        """
        self.batch_size = min(batch_size, MAX_BATCH_SIZE)  # Cap at queue limit
        self.poll_interval = poll_interval
        self.shutdown_event = asyncio.Event()

        # MEDIUM #2: Exponential backoff on repeated errors
        self.consecutive_failures = 0
        self.max_backoff = MAX_BACKOFF

        # MEDIUM #4: Track in-flight batch for graceful shutdown
        self.current_batch_task: asyncio.Task | None = None

    async def process_queue(self):
        """Main processing loop with graceful shutdown."""
        logger.info(
            "classifier_worker_started",
            extra={"batch_size": self.batch_size, "poll_interval": self.poll_interval},
        )

        while not self.shutdown_event.is_set():
            try:
                # Dequeue batch (file-based, thread-safe)
                tasks = dequeue_batch(self.batch_size)

                if tasks:
                    logger.info(
                        "batch_dequeued",
                        extra={"count": len(tasks), "remaining": get_queue_size()},
                    )

                    # LOW #9: Track dequeue rate for metrics
                    classifier_queue_dequeued_total.inc(len(tasks))

                    # MEDIUM #4: Track in-flight batch for graceful shutdown
                    self.current_batch_task = asyncio.create_task(
                        self.process_batch(tasks)
                    )
                    await self.current_batch_task
                    self.current_batch_task = None

                    # MEDIUM #2: Reset failure counter on successful batch
                    self.consecutive_failures = 0
                else:
                    # Exponential backoff when idle (BP-039)
                    logger.debug("queue_empty", extra={"sleeping": self.poll_interval})
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                # MEDIUM #2: Exponential backoff on repeated errors
                self.consecutive_failures += 1
                backoff = min(
                    self.poll_interval * (2**self.consecutive_failures),
                    self.max_backoff,
                )
                logger.error(
                    "processing_error",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "consecutive_failures": self.consecutive_failures,
                        "backoff_seconds": backoff,
                    },
                )
                # Continue processing after error (don't crash daemon)
                await asyncio.sleep(backoff)

    async def process_batch(self, tasks: list[ClassificationTask]):
        """Process batch concurrently with error handling.

        Args:
            tasks: List of ClassificationTask from queue
        """
        start_time = time.time()

        # Process all tasks concurrently - BP-039 pattern
        results = await asyncio.gather(
            *[self.process_task(task) for task in tasks],
            return_exceptions=True,  # Prevent one failure from killing batch
        )

        # Track results
        success_count = 0
        failed_count = 0
        skipped_count = 0

        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(
                    "task_failed",
                    extra={
                        "point_id": task.point_id,
                        "collection": task.collection,
                        "error": str(result),
                        "error_type": type(result).__name__,
                    },
                )
                classifier_queue_processed_total.labels(status="failed").inc()
                failed_count += 1

                # MEDIUM #6: Move failed task to dead letter queue
                _move_to_dlq(task, str(result))
            elif result is None:
                # Task skipped (no reclassification needed)
                skipped_count += 1
            else:
                # Task succeeded
                success_count += 1

        # Record batch metrics
        batch_duration = time.time() - start_time
        classifier_batch_duration_seconds.observe(batch_duration)

        # BUG-048: Update timestamp when ANY task is processed (success OR skipped)
        # Skipped tasks (no reclassification needed) are still successful processing
        if success_count > 0 or skipped_count > 0:
            classifier_last_success_timestamp.set_to_current_time()

        logger.info(
            "batch_processed",
            extra={
                "total": len(tasks),
                "success": success_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "duration_seconds": batch_duration,
            },
        )

        # Push metrics to Pushgateway (non-blocking)
        push_metrics()

        # MEDIUM #1: Update health check file (Docker healthcheck)
        _touch_health_file()

    async def process_task(self, task: ClassificationTask) -> bool | None:
        """Classify content and update Qdrant payload.

        Args:
            task: ClassificationTask from queue

        Returns:
            True if payload updated, None if skipped, raises on error

        Raises:
            ValueError: On classification failure
            Exception: On Qdrant update failure
        """
        logger.debug(
            "processing_task",
            extra={
                "point_id": task.point_id,
                "collection": task.collection,
                "current_type": task.current_type,
            },
        )

        # MEDIUM #3: Run classification in executor to avoid blocking event loop
        # classify() is synchronous and takes 1-2s (Ollama HTTP API call)
        # Using ThreadPoolExecutor since it's I/O-bound (HTTP), not pure CPU
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,  # Use default ThreadPoolExecutor
            classify,
            task.content,
            task.collection,
            task.current_type,
            None,  # file_path - no file context in queue
        )

        # Check if reclassification occurred
        if not result.was_reclassified:
            logger.info(
                "no_reclassification_needed",
                extra={
                    "point_id": task.point_id,
                    "type": result.classified_type,
                    "confidence": result.confidence,
                    "provider": result.provider_used,
                },
            )
            classifier_queue_processed_total.labels(status="skipped").inc()
            return None  # Signal task was skipped

        # Update Qdrant payload with new classification
        payload_updates = {
            "type": result.classified_type,
            "classification_confidence": result.confidence,
            "classification_reasoning": result.reasoning,
            "classification_provider": result.provider_used,
            "classified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Add tags if provided
        if result.tags:
            payload_updates["tags"] = result.tags

        success = update_point_payload(
            collection=task.collection,
            point_id=task.point_id,
            payload_updates=payload_updates,
        )

        if not success:
            logger.error(
                "qdrant_update_failed",
                extra={
                    "point_id": task.point_id,
                    "collection": task.collection,
                    "classified_type": result.classified_type,
                },
            )
            raise ValueError(f"Failed to update payload for point {task.point_id}")

        logger.info(
            "reclassification_complete",
            extra={
                "point_id": task.point_id,
                "original_type": task.current_type,
                "classified_type": result.classified_type,
                "confidence": result.confidence,
                "provider": result.provider_used,
            },
        )

        classifier_queue_processed_total.labels(status="success").inc()
        return True

    def _handle_shutdown(self) -> None:
        """Set shutdown event (called by signal handler)."""
        logger.info("shutdown_signal_received")
        self.shutdown_event.set()

    async def run(self):
        """Main entry point with signal handling.

        Sets up signal handlers for graceful shutdown per BP-039.
        CRITICAL: Uses loop.add_signal_handler() for Docker compatibility.
        """
        # Register signal handlers - CRITICAL for Docker (BP-039)
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, self._handle_shutdown)
        loop.add_signal_handler(signal.SIGINT, self._handle_shutdown)

        logger.info(
            "worker_started",
            extra={
                "batch_size": self.batch_size,
                "poll_interval": self.poll_interval,
                "pushgateway": PUSHGATEWAY_URL,
                "pushgateway_enabled": PUSHGATEWAY_ENABLED,
            },
        )

        # BUG-045: Create health file at startup (not just after first batch)
        # Root cause: Health file only created after batch processing completed.
        # If queue is empty at startup, no batches run, so health check never passes.
        _touch_health_file()

        try:
            await self.process_queue()
        finally:
            # MEDIUM #4 & LOW #10: Wait for in-flight batch before logging shutdown
            if self.current_batch_task and not self.current_batch_task.done():
                logger.info("waiting_for_in_flight_batch")
                try:
                    await self.current_batch_task
                except Exception as e:
                    logger.warning(
                        "in_flight_batch_error_during_shutdown",
                        extra={"error": str(e), "error_type": type(e).__name__},
                    )
            logger.info("worker_shutdown_complete")


# =============================================================================
# ENTRY POINT
# =============================================================================


def main() -> None:
    """Entry point - uses low-level API for graceful shutdown.

    CRITICAL: Don't use asyncio.run() - it cancels all tasks on KeyboardInterrupt.
    Per BP-039, use manual event loop control for graceful shutdown.
    """
    worker = ClassificationWorker()

    # Use low-level API for better shutdown control (BP-039)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(worker.run())
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        loop.close()
        logger.info("event_loop_closed")


if __name__ == "__main__":
    main()
