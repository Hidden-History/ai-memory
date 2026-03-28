"""Langfuse client configuration for AI Memory Module.

Provides a thread-safe Langfuse client factory with kill-switch support.

SPEC: LANGFUSE-INTEGRATION-SPEC.md Section 7.2
"""

# LANGFUSE: Client factory (Path B infrastructure). See LANGFUSE-INTEGRATION-SPEC.md §7.2
# SDK VERSION: V3 ONLY. Uses get_client() singleton — Do NOT use Langfuse() constructor.

import logging
import os
import threading

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on transient errors; do not retry if langfuse package is missing."""
    return not isinstance(exc, ImportError)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def _create_langfuse_client_with_retry():
    """Create Langfuse V3 client with exponential backoff retry (TD-206).

    5 attempts, backoff 1s-16s. ImportError is not retried (langfuse not installed).
    NOTE: Local import so tests can patch sys.modules["langfuse"] at runtime.
    """
    from langfuse import get_client as _get_client

    return _get_client()


_client = None
_client_lock = threading.Lock()
_initialized = False


def get_langfuse_client():
    """Get or create a Langfuse client singleton.

    Returns None if Langfuse is disabled or not configured.
    Thread-safe via threading.Lock.

    Does NOT cache None returns — if called before env vars are set,
    a later call (after env vars are configured) will succeed.
    This is important for long-lived processes (Phase 2, SPEC-020).

    Returns:
        Langfuse client instance, or None if disabled/unavailable.
    """
    global _client, _initialized

    if _initialized:
        return _client

    with _client_lock:
        # Double-check under lock
        if _initialized:
            return _client

        enabled = os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"
        # Bridge our kill-switch to the real Langfuse SDK env var so the SDK respects it
        os.environ["LANGFUSE_TRACING_ENABLED"] = "true" if enabled else "false"
        if not enabled:
            logger.debug("Langfuse disabled (LANGFUSE_ENABLED != true)")
            return None

        # Note: reads directly from env (not config.py) since this runs in hook subprocesses
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

        if not public_key or not secret_key:
            logger.warning("Langfuse enabled but API keys not configured — skipping")
            return None

        try:
            # V3 SDK: get_client() is a singleton that reads env vars automatically.
            # We set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL
            # in the environment above, so get_client() picks them up.
            # TD-206: wrapped in _create_langfuse_client_with_retry for exponential backoff.
            client = _create_langfuse_client_with_retry()
            logger.info(
                "Langfuse client initialized via V3 get_client() (host=%s)",
                os.environ.get("LANGFUSE_BASE_URL", "http://localhost:23100"),
            )
            _client = client
            _initialized = True
            return client
        except ImportError:
            logger.warning("langfuse package not installed — pip install langfuse")
            return None
        except Exception as e:
            logger.error("Failed to initialize Langfuse client after retries: %s", e)
            return None


def reset_langfuse_client():
    """Reset client singleton for testing."""
    global _client, _initialized
    with _client_lock:
        _client = None
        _initialized = False


def is_langfuse_enabled() -> bool:
    """Check if Langfuse is enabled without creating client."""
    return os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"


def is_hook_tracing_enabled() -> bool:
    """Check if Tier 2 hook tracing is enabled."""
    return (
        is_langfuse_enabled()
        and os.environ.get("LANGFUSE_TRACE_HOOKS", "true").lower() == "true"
    )
