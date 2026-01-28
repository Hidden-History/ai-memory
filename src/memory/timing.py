"""Timing utilities for structured logging.

Implements AC 6.2.3: Timing Context Manager with timed_operation.

Uses time.perf_counter() for sub-millisecond precision timing per 2026 best practices.

Research sources:
- time.perf_counter() vs time.time(): https://superfastpython.com/time-time-vs-time-perf_counter/
- Python perf_counter best practices: https://docs.python.org/3/library/time.html
"""

import logging
import time
from contextlib import contextmanager
from typing import Optional


@contextmanager
def timed_operation(
    operation: str,
    logger: logging.Logger,
    level: int = logging.INFO,
    extra: Optional[dict] = None,
):
    """Context manager for timing operations with structured logging.

    Implements AC 6.2.3:
    - Captures start time on entry using time.perf_counter()
    - Logs duration on exit (success or failure)
    - Re-raises exceptions after logging

    Args:
        operation: Operation name (used in log message as {operation}_completed)
        logger: Logger instance to use for logging
        level: Log level for success case (default: INFO)
        extra: Optional dict of extra context to include in log

    Yields:
        None

    Example:
        >>> logger = logging.getLogger("ai_memory.storage")
        >>> with timed_operation("store_memory", logger, extra={"id": "abc"}):
        ...     # operation code here
        ...     pass

    Logs on success:
        {"timestamp": "...", "level": "INFO", "message": "store_memory_completed",
         "context": {"id": "abc", "duration_ms": 145.23, "status": "success"}}

    Logs on failure:
        {"timestamp": "...", "level": "ERROR", "message": "store_memory_failed",
         "context": {"id": "abc", "duration_ms": 89.01, "status": "failed",
                     "error": "...", "error_type": "ValueError"}}
    """
    start = time.perf_counter()
    _extra = extra or {}

    try:
        yield

        # Success case: log with duration
        duration_ms = (time.perf_counter() - start) * 1000
        logger.log(
            level,
            f"{operation}_completed",
            extra={
                **_extra,
                "duration_ms": round(duration_ms, 2),
                "status": "success",
            },
        )

    except Exception as e:
        # Failure case: log error with duration, then re-raise
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(
            f"{operation}_failed",
            extra={
                **_extra,
                "duration_ms": round(duration_ms, 2),
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
