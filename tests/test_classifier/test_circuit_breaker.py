"""Tests for circuit breaker pattern.

TECH-DEBT-069: Circuit breaker thread safety and state management.
"""

import threading
import time

from src.memory.classifier.circuit_breaker import (
    CircuitBreaker,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_closed(self):
        """New circuit breaker should start in CLOSED state."""
        breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)
        assert breaker.is_available("test_provider") is True

    def test_circuit_opens_after_threshold(self):
        """Circuit should open after reaching failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60)

        # Record failures
        for _ in range(3):
            breaker.record_failure("test_provider")

        # Circuit should now be open
        assert breaker.is_available("test_provider") is False

    def test_circuit_stays_open_during_timeout(self):
        """Circuit should stay open during reset timeout."""
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=10)

        # Open the circuit
        for _ in range(3):
            breaker.record_failure("test_provider")

        # Should be unavailable immediately
        assert breaker.is_available("test_provider") is False

        # Should still be unavailable after 1 second
        time.sleep(1)
        assert breaker.is_available("test_provider") is False

    def test_circuit_half_open_after_timeout(self):
        """Circuit should transition to HALF_OPEN after timeout."""
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=1)

        # Open the circuit
        for _ in range(3):
            breaker.record_failure("test_provider")

        # Wait for timeout
        time.sleep(1.1)

        # Should be available (HALF_OPEN)
        assert breaker.is_available("test_provider") is True

    def test_circuit_closes_on_success(self):
        """Circuit should close on successful request."""
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60)

        # Open the circuit
        for _ in range(3):
            breaker.record_failure("test_provider")

        assert breaker.is_available("test_provider") is False

        # Record success
        breaker.record_success("test_provider")

        # Circuit should be closed
        assert breaker.is_available("test_provider") is True

    def test_independent_provider_states(self):
        """Different providers should have independent circuit states."""
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60)

        # Fail provider1
        for _ in range(3):
            breaker.record_failure("provider1")

        # Provider1 should be unavailable
        assert breaker.is_available("provider1") is False

        # Provider2 should still be available
        assert breaker.is_available("provider2") is True

    def test_get_status(self):
        """Status should reflect current circuit state."""
        breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60)

        # Initial status
        status = breaker.get_status("test_provider")
        assert status["state"] == "closed"
        assert status["consecutive_failures"] == 0
        assert status["is_available"] is True

        # After failures
        for _ in range(3):
            breaker.record_failure("test_provider")

        status = breaker.get_status("test_provider")
        assert status["state"] == "open"
        assert status["consecutive_failures"] == 3
        assert status["is_available"] is False


class TestCircuitBreakerThreadSafety:
    """Test thread safety of circuit breaker."""

    def test_concurrent_state_creation(self):
        """Verify thread-safe state creation for new providers.

        This test ensures that when multiple threads simultaneously request
        state for the same new provider, only one ProviderState object is
        created and all threads get the same instance.
        """
        breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)
        results = []
        errors = []

        def get_state(provider_name: str):
            """Get state from breaker (called by multiple threads)."""
            try:
                state = breaker._get_state(provider_name)
                results.append(state)
            except Exception as e:
                errors.append(e)

        # Create 10 threads all requesting state for same new provider
        threads = [
            threading.Thread(target=get_state, args=("new_provider",))
            for _ in range(10)
        ]

        # Start all threads simultaneously
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # All should succeed without errors
        assert len(errors) == 0, f"Thread safety errors occurred: {errors}"

        # All should get results
        assert len(results) == 10

        # All should get the same state object (same identity)
        assert all(
            r is results[0] for r in results
        ), "Threads got different state objects - race condition detected!"

    def test_concurrent_failure_recording(self):
        """Verify thread-safe failure recording."""
        breaker = CircuitBreaker(failure_threshold=10, reset_timeout=60)
        errors = []

        def record_failures(provider_name: str, count: int):
            """Record multiple failures (called by multiple threads)."""
            try:
                for _ in range(count):
                    breaker.record_failure(provider_name)
            except Exception as e:
                errors.append(e)

        # Create 5 threads each recording 4 failures (20 total)
        threads = [
            threading.Thread(target=record_failures, args=("test_provider", 4))
            for _ in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0

        # Total failures should be 20
        state = breaker._get_state("test_provider")
        assert state.consecutive_failures == 20

    def test_concurrent_mixed_operations(self):
        """Verify thread safety with mixed success/failure operations."""
        breaker = CircuitBreaker(failure_threshold=50, reset_timeout=60)
        errors = []

        def mixed_operations(provider_name: str):
            """Perform mixed operations (called by multiple threads)."""
            try:
                for i in range(10):
                    if i % 2 == 0:
                        breaker.record_failure(provider_name)
                    else:
                        breaker.record_success(provider_name)
                    breaker.is_available(provider_name)
            except Exception as e:
                errors.append(e)

        # Create 10 threads performing mixed operations
        threads = [
            threading.Thread(target=mixed_operations, args=("test_provider",))
            for _ in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Thread safety errors: {errors}"

        # Circuit should still be functional
        assert breaker.is_available("test_provider") is not None
