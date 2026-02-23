"""Langfuse client configuration for AI Memory Module.

Provides a thread-safe Langfuse client factory with kill-switch support.
Phase 1+2 implementation — client factory with kill-switch helpers.

PLAN-008 / SPEC-019 / SPEC-022
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

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
            from langfuse import Langfuse
            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=os.environ.get("LANGFUSE_BASE_URL", "http://localhost:23100"),
            )
            logger.info("Langfuse client initialized (host=%s)",
                        os.environ.get("LANGFUSE_BASE_URL", "http://localhost:23100"))
            _client = client
            _initialized = True
            return client
        except ImportError:
            logger.warning("langfuse package not installed — pip install langfuse")
            return None
        except Exception as e:
            logger.error("Failed to initialize Langfuse client: %s", e)
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
