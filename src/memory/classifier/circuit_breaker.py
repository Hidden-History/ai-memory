"""Circuit breaker for LLM provider resilience.

FIX-10: Prevents hammering unavailable providers with exponential backoff.

Pattern based on:
- Netflix Hystrix: https://github.com/Netflix/Hystrix/wiki
- AWS Well-Architected Framework (2026): Implement circuit breakers for dependent services
- Martin Fowler: https://martinfowler.com/bliki/CircuitBreaker.html

TECH-DEBT-069: LLM classification resilience.
"""

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ai_memory.classifier.circuit_breaker")

__all__ = ["CircuitBreaker", "CircuitState", "circuit_breaker"]


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class ProviderState:
    """State tracking for a single provider."""

    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    state: CircuitState = CircuitState.CLOSED
    half_open_attempts: int = 0


class CircuitBreaker:
    """Circuit breaker with configurable thresholds.

    Three states:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: After timeout, allow limited test requests

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)
        >>> if breaker.is_available("ollama"):
        ...     result = call_provider("ollama")
        ...     breaker.record_success("ollama")
        ... else:
        ...     # Circuit open, skip provider
        ...     pass
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        half_open_max_attempts: int = 3,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening circuit
            reset_timeout: Seconds before transitioning to HALF_OPEN
            half_open_max_attempts: Max test requests in HALF_OPEN state
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_attempts = half_open_max_attempts
        self._states: dict[str, ProviderState] = {}
        self._lock = threading.Lock()  # Thread-safe state creation

        logger.info(
            "circuit_breaker_initialized",
            extra={
                "failure_threshold": failure_threshold,
                "reset_timeout_seconds": reset_timeout,
                "half_open_attempts": half_open_max_attempts,
            },
        )

    def _get_state(self, provider: str) -> ProviderState:
        """Get or create state for provider.

        Thread-safe: Uses double-checked locking to prevent race conditions
        when multiple threads create state for same provider simultaneously.

        Args:
            provider: Provider name

        Returns:
            ProviderState instance
        """
        # Fast path: state already exists (no lock needed for read)
        if provider in self._states:
            return self._states[provider]

        # Slow path: need to create state (lock required)
        with self._lock:
            # Double-check after acquiring lock (another thread may have created it)
            if provider not in self._states:
                self._states[provider] = ProviderState()
            return self._states[provider]

    def is_available(self, provider: str) -> bool:
        """Check if provider is available (circuit not open).

        Args:
            provider: Provider name

        Returns:
            True if requests should be allowed, False if circuit is open
        """
        state = self._get_state(provider)

        # CLOSED state: always available
        if state.state == CircuitState.CLOSED:
            return True

        # OPEN state: check if timeout has passed
        if state.state == CircuitState.OPEN:
            elapsed = time.time() - state.last_failure_time

            if elapsed > self.reset_timeout:
                # Transition to HALF_OPEN
                state.state = CircuitState.HALF_OPEN
                state.half_open_attempts = 0

                logger.info(
                    "circuit_half_open",
                    extra={
                        "provider": provider,
                        "timeout_seconds": self.reset_timeout,
                        "elapsed_seconds": elapsed,
                    },
                )
                return True
            else:
                # Still open, reject request
                logger.debug(
                    "circuit_open_request_rejected",
                    extra={
                        "provider": provider,
                        "time_until_reset": self.reset_timeout - elapsed,
                    },
                )
                return False

        # HALF_OPEN state: allow limited test requests
        if state.state == CircuitState.HALF_OPEN:
            if state.half_open_attempts < self.half_open_max_attempts:
                state.half_open_attempts += 1
                logger.debug(
                    "circuit_half_open_test",
                    extra={
                        "provider": provider,
                        "attempt": state.half_open_attempts,
                        "max_attempts": self.half_open_max_attempts,
                    },
                )
                return True
            else:
                # Max attempts reached in HALF_OPEN, still failing
                logger.warning(
                    "circuit_half_open_max_attempts", extra={"provider": provider}
                )
                return False

        return False

    def record_success(self, provider: str):
        """Record successful request, potentially close circuit.

        Args:
            provider: Provider name
        """
        state = self._get_state(provider)
        prev_state = state.state

        # Reset failure counter and close circuit
        state.consecutive_failures = 0
        state.last_success_time = time.time()
        state.state = CircuitState.CLOSED
        state.half_open_attempts = 0

        if prev_state != CircuitState.CLOSED:
            logger.info(
                "circuit_closed",
                extra={
                    "provider": provider,
                    "previous_state": prev_state.value,
                },
            )

    def record_failure(self, provider: str, error_type: str = "unknown"):
        """Record failed request, potentially open circuit.

        Args:
            provider: Provider name
            error_type: Type of error (timeout, connection, parse, etc.)
        """
        state = self._get_state(provider)
        state.consecutive_failures += 1
        state.last_failure_time = time.time()

        logger.debug(
            "circuit_failure_recorded",
            extra={
                "provider": provider,
                "consecutive_failures": state.consecutive_failures,
                "error_type": error_type,
            },
        )

        # Check if we should open the circuit
        if (
            state.consecutive_failures >= self.failure_threshold
            and state.state != CircuitState.OPEN
        ):
            state.state = CircuitState.OPEN
            logger.warning(
                "circuit_opened",
                extra={
                    "provider": provider,
                    "failures": state.consecutive_failures,
                    "threshold": self.failure_threshold,
                    "timeout_seconds": self.reset_timeout,
                },
            )

    def get_status(self, provider: str) -> dict:
        """Get current circuit status for provider.

        Args:
            provider: Provider name

        Returns:
            Dict with status information
        """
        state = self._get_state(provider)

        return {
            "provider": provider,
            "state": state.state.value,
            "consecutive_failures": state.consecutive_failures,
            "last_failure": state.last_failure_time,
            "last_success": state.last_success_time,
            "is_available": self.is_available(provider),
        }


# Global circuit breaker instance
# Shared across all classification requests in the process
circuit_breaker = CircuitBreaker(
    failure_threshold=5,  # 5 consecutive failures opens circuit
    reset_timeout=60,  # 60 seconds before trying again
    half_open_max_attempts=3,  # 3 test requests in half-open state
)
