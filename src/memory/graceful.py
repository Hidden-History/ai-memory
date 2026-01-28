"""Graceful degradation utilities for Claude Code hooks.

This module provides exit code constants, decorators, and helper functions
for implementing graceful degradation in Claude Code hooks. All hooks should
use the @graceful_hook decorator to ensure Claude never crashes from memory
system failures.

Exit Code Policy (per project-context.md):
    - 0 (EXIT_SUCCESS): Normal completion
    - 1 (EXIT_NON_BLOCKING): Error but Claude continues (graceful degradation)
    - 2 (EXIT_BLOCKING): Block Claude action (rarely used, intentional only)

Best Practices (2025):
    - Use @graceful_hook decorator for all hook entry points
    - Catch specific exceptions internally, let decorator catch unexpected ones
    - Log errors with structured extras dict (never f-strings)
    - Always exit 0 or 1 from hooks (never 2 unless intentionally blocking)

References:
    - https://medium.com/@RampantLions/robust-error-handling-in-python-...
    - https://rinaarts.com/declutter-python-code-with-error-handling-decorators/
"""

import sys
import logging
from typing import Callable, Any, Optional
from functools import wraps

# Configure logger for hook operations
logger = logging.getLogger("ai_memory.hooks")

# Exit codes per project-context.md and Claude Code hook specification
EXIT_SUCCESS = 0       # Normal completion
EXIT_NON_BLOCKING = 1  # Error but Claude continues (graceful degradation)
EXIT_BLOCKING = 2      # Block Claude action (rarely used, intentional only)


def graceful_hook(func: Callable) -> Callable:
    """Decorator for hook functions with graceful degradation.

    Wraps hook functions to catch all exceptions and exit with non-blocking
    error code (1) instead of crashing. Ensures Claude Code never crashes
    from memory system failures.

    Uses functools.wraps to preserve function metadata (__name__, __doc__).
    Logs errors with structured extras dict for debugging.

    Args:
        func: Hook function to wrap with graceful degradation

    Returns:
        Wrapped function that catches exceptions and exits gracefully

    Example:
        @graceful_hook
        def session_start_hook():
            # Load memories from Qdrant
            memories = search_memories(...)
            # Inject context
            print(format_context(memories))

        # If search_memories() fails, hook logs error and exits 1
        # Claude session starts successfully without context

    Best Practices:
        - Use for ALL hook entry points (SessionStart, PostToolUse, Stop)
        - Catch specific exceptions internally, let decorator catch unexpected
        - Never intentionally raise from hook after wrapping with decorator
        - Log business logic errors before decorator catches them
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log with structured extras (no f-strings per project-context.md)
            logger.error("hook_failed", extra={
                "hook": func.__name__,
                "error": str(e),
                "error_type": type(e).__name__
            })
            # Always exit 1 (non-blocking) on unexpected error
            # Claude continues, memory system gracefully degrades
            sys.exit(EXIT_NON_BLOCKING)

    return wrapper


def exit_success() -> None:
    """Exit hook successfully with code 0.

    Use when hook completes normally without errors.

    Example:
        @graceful_hook
        def my_hook():
            store_memory(...)
            exit_success()  # Explicit success exit
    """
    sys.exit(EXIT_SUCCESS)


def exit_graceful(message: Optional[str] = None) -> None:
    """Exit hook with non-blocking error code 1.

    Use when hook encounters expected error but should allow Claude to continue.
    Logs warning with optional message.

    Args:
        message: Optional context about why graceful exit was triggered

    Example:
        @graceful_hook
        def my_hook():
            if not check_qdrant_health():
                exit_graceful("Qdrant unavailable - queued to file")
            store_memory(...)
    """
    if message:
        # Log with structured extras (no f-strings)
        # Use "reason" instead of "message" (logging module reserves "message")
        logger.warning("graceful_exit", extra={"reason": message})
    sys.exit(EXIT_NON_BLOCKING)


# Export public API
__all__ = [
    "EXIT_SUCCESS",
    "EXIT_NON_BLOCKING",
    "EXIT_BLOCKING",
    "graceful_hook",
    "exit_success",
    "exit_graceful",
]
