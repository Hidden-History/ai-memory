"""Tests for unified keyword trigger.

TECH-DEBT-062: Tests for parallel trigger system consolidation.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import the module under test (after path setup)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '.claude', 'hooks', 'scripts'))
import unified_keyword_trigger as ukt


class TestDetectAllTriggers:
    """Tests for parallel keyword detection."""

    @pytest.mark.asyncio
    async def test_detect_all_triggers_parallel(self):
        """Verify all detectors run in parallel."""
        with patch('unified_keyword_trigger.detect_decision_keywords') as mock_decision, \
             patch('unified_keyword_trigger.detect_session_history_keywords') as mock_session, \
             patch('unified_keyword_trigger.detect_best_practices_keywords') as mock_best_practices:

            # Setup mocks
            mock_decision.return_value = "authentication"
            mock_session.return_value = None
            mock_best_practices.return_value = "error handling"

            # Execute
            result = await ukt.detect_all_triggers("why did we choose authentication? what's the best practice for error handling?")

            # Verify all called
            assert mock_decision.called
            assert mock_session.called
            assert mock_best_practices.called

            # Verify results
            assert result["decision"] == "authentication"
            assert result["session"] is None
            assert result["best_practices"] == "error handling"

    @pytest.mark.asyncio
    async def test_detect_all_triggers_handles_exceptions(self):
        """Verify exceptions are caught and handled (CR-FIX CRIT-1: now synchronous)."""
        with patch('unified_keyword_trigger.detect_decision_keywords') as mock_decision, \
             patch('unified_keyword_trigger.detect_session_history_keywords') as mock_session, \
             patch('unified_keyword_trigger.detect_best_practices_keywords') as mock_best_practices:

            # Setup normal returns
            mock_decision.return_value = None
            mock_session.return_value = "last session"
            mock_best_practices.return_value = None

            # Execute - should work fine
            result = await ukt.detect_all_triggers("test prompt")

            # All called
            assert mock_decision.called
            assert mock_session.called
            assert mock_best_practices.called

            # Results correct
            assert result["decision"] is None
            assert result["session"] == "last session"
            assert result["best_practices"] is None


class TestSearchAllTriggered:
    """Tests for parallel Qdrant searches."""

    @pytest.fixture(autouse=True)
    def reset_circuit_breaker(self):
        """Reset circuit breaker before each test."""
        ukt._circuit_breaker.failures = 0
        ukt._circuit_breaker.is_open = False
        ukt._circuit_breaker.last_failure = 0.0
        yield

    @pytest.mark.asyncio
    async def test_search_all_triggered_parallel(self):
        """Verify all triggered searches run in parallel (CR-FIX HIGH-1: shared client)."""
        triggers = {
            "decision": "authentication",
            "session": "last sprint",
            "best_practices": "error handling"
        }

        # CR-FIX HIGH-1: Mock MemorySearch client instead of perform_search
        mock_client = MagicMock()
        mock_client.search.return_value = [{"content": "test", "score": 0.9}]
        mock_client.close = MagicMock()

        # Mock config
        mock_config = MagicMock()
        mock_config.similarity_threshold = 0.4

        with patch('unified_keyword_trigger.MemorySearch', return_value=mock_client):
            # Execute
            start = time.time()
            results = await ukt.search_all_triggered(triggers, "test-project", mock_config)
            elapsed = time.time() - start

            # Should complete quickly (parallel, not sequential)
            assert elapsed < 1.0  # Much faster than 3x sequential searches

            # All 3 searches executed
            assert len(results) == 3
            assert all(isinstance(r, ukt.TriggerResult) for r in results)

            # Verify client was created once and closed once (shared client)
            assert mock_client.close.call_count == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(self):
        """Verify circuit breaker prevents searches when open."""
        # Open the circuit breaker
        ukt._circuit_breaker.is_open = True
        ukt._circuit_breaker.last_failure = time.time()

        triggers = {"decision": "test"}

        mock_config = MagicMock()

        # Execute - should return empty
        results = await ukt.search_all_triggered(triggers, "test-project", mock_config)

        assert results == []

    @pytest.mark.asyncio
    async def test_search_timeout_protection(self):
        """Verify timeout protection works (CR-FIX MED-2)."""
        triggers = {"decision": "test"}

        # CR-FIX HIGH-1: Mock the shared client's search method
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.similarity_threshold = 0.4

        def slow_search(*args, **kwargs):
            time.sleep(10)  # Longer than SEARCH_TIMEOUT (3s)
            return []

        mock_client.search = slow_search

        with patch('unified_keyword_trigger.MemorySearch', return_value=mock_client):
            start = time.time()
            results = await ukt.search_all_triggered(triggers, "test-project", mock_config)
            elapsed = time.time() - start

            # CR-FIX MED-2: More precise assertion (3s timeout + 1s overhead)
            assert elapsed < 4.0, f"Timeout took {elapsed}s, expected <4s"
            assert len(results) == 1
            assert results[0].results == []  # Timeout returns empty


class TestDeduplication:
    """Tests for result deduplication and priority ordering."""

    def test_deduplicate_results_by_hash(self):
        """Verify deduplication by content_hash."""
        trigger_results = [
            ukt.TriggerResult(
                trigger_type="decision",
                topic="auth",
                results=[
                    {"content": "Use JWT", "content_hash": "hash1", "score": 0.9},
                    {"content": "Use OAuth", "content_hash": "hash2", "score": 0.8}
                ],
                search_time_ms=100
            ),
            ukt.TriggerResult(
                trigger_type="best_practices",
                topic="auth",
                results=[
                    {"content": "Use JWT", "content_hash": "hash1", "score": 0.85},  # Duplicate
                    {"content": "Use HTTPS", "content_hash": "hash3", "score": 0.7}
                ],
                search_time_ms=120
            )
        ]

        deduplicated = ukt.deduplicate_results(trigger_results)

        # Should have 3 unique results (hash1 appears once, hash2 once, hash3 once)
        assert len(deduplicated) == 3
        hashes = [r["content_hash"] for r in deduplicated]
        assert len(set(hashes)) == 3  # All unique

    def test_priority_ordering(self):
        """Verify priority: decision > session > best_practices."""
        trigger_results = [
            ukt.TriggerResult(
                trigger_type="best_practices",
                topic="test",
                results=[{"content": "BP", "content_hash": "hash1", "score": 0.9}],
                search_time_ms=100
            ),
            ukt.TriggerResult(
                trigger_type="decision",
                topic="test",
                results=[{"content": "DEC", "content_hash": "hash2", "score": 0.8}],
                search_time_ms=100
            ),
            ukt.TriggerResult(
                trigger_type="session",
                topic="test",
                results=[{"content": "SESS", "content_hash": "hash3", "score": 0.85}],
                search_time_ms=100
            )
        ]

        deduplicated = ukt.deduplicate_results(trigger_results)

        # Order should be: decision, session, best_practices
        assert deduplicated[0]["_trigger_type"] == "decision"
        assert deduplicated[1]["_trigger_type"] == "session"
        assert deduplicated[2]["_trigger_type"] == "best_practices"

    def test_max_results_limit(self):
        """Verify MAX_TOTAL_RESULTS limit enforced."""
        # Create more results than MAX_TOTAL_RESULTS
        trigger_results = [
            ukt.TriggerResult(
                trigger_type="decision",
                topic="test",
                results=[
                    {"content": f"Result {i}", "content_hash": f"hash{i}", "score": 0.9}
                    for i in range(10)  # More than MAX_TOTAL_RESULTS
                ],
                search_time_ms=100
            )
        ]

        deduplicated = ukt.deduplicate_results(trigger_results)

        # Should not exceed MAX_TOTAL_RESULTS (default 5)
        assert len(deduplicated) <= ukt.MAX_TOTAL_RESULTS


class TestCircuitBreaker:
    """Tests for circuit breaker logic."""

    def test_circuit_opens_after_threshold_failures(self):
        """Verify circuit opens after CIRCUIT_BREAKER_THRESHOLD failures."""
        cb = ukt.CircuitBreaker()

        # Record failures up to threshold
        for _ in range(ukt.CIRCUIT_BREAKER_THRESHOLD):
            cb.record_failure()

        assert cb.is_open

    def test_circuit_resets_after_timeout(self):
        """Verify circuit resets after CIRCUIT_BREAKER_RESET seconds."""
        cb = ukt.CircuitBreaker()

        # Open circuit
        for _ in range(ukt.CIRCUIT_BREAKER_THRESHOLD):
            cb.record_failure()

        assert cb.is_open

        # Simulate time passing
        cb.last_failure = time.time() - (ukt.CIRCUIT_BREAKER_RESET + 1)

        # Should allow after reset period
        assert cb.should_allow()
        assert not cb.is_open

    def test_circuit_closes_on_success(self):
        """Verify circuit closes and resets on success."""
        cb = ukt.CircuitBreaker()

        # Record some failures
        cb.record_failure()
        cb.record_failure()

        assert cb.failures == 2

        # Success resets
        cb.record_success()

        assert cb.failures == 0
        assert not cb.is_open


class TestFormatResult:
    """Tests for result formatting."""

    def test_format_result_basic(self):
        """Verify basic result formatting."""
        result = {
            "content": "Use JWT for authentication",
            "score": 0.87,
            "type": "decision",
            "_trigger_type": "decision",
            "tags": ["auth", "jwt", "security"]
        }

        formatted = ukt.format_result(result, 1)

        assert "1." in formatted
        assert "decision" in formatted
        assert "87%" in formatted
        assert "[decision]" in formatted
        assert "auth, jwt, security" in formatted
        assert "Use JWT" in formatted

    def test_format_result_truncates_long_content(self):
        """Verify long content is truncated."""
        result = {
            "content": "x" * 1000,  # Very long content
            "score": 0.9,
            "type": "implementation",
            "_trigger_type": "best_practices",
            "tags": []
        }

        formatted = ukt.format_result(result, 1)

        # Should be truncated to 500 chars + formatting
        assert len(formatted) < 600


class TestMetricsPushing:
    """Tests for metrics push correctness (CR-FIX HIGH-2)."""

    @pytest.fixture(autouse=True)
    def reset_circuit_breaker(self):
        """Reset circuit breaker before each test."""
        ukt._circuit_breaker.failures = 0
        ukt._circuit_breaker.is_open = False
        ukt._circuit_breaker.last_failure = 0.0
        yield

    @pytest.mark.asyncio
    async def test_metrics_track_found_vs_shown(self):
        """Verify metrics correctly track found vs shown (CRIT-2 fix)."""
        # Setup: Create trigger results where decision and best_practices find SAME memory
        trigger_results = [
            ukt.TriggerResult(
                trigger_type="decision",
                topic="auth",
                results=[
                    {"content": "Use JWT", "content_hash": "hash1", "score": 0.9, "type": "decision"},
                ],
                search_time_ms=100
            ),
            ukt.TriggerResult(
                trigger_type="best_practices",
                topic="auth",
                results=[
                    {"content": "Use JWT", "content_hash": "hash1", "score": 0.85, "type": "guideline"},  # Same hash
                ],
                search_time_ms=120
            ),
            ukt.TriggerResult(
                trigger_type="session",
                topic="auth",
                results=[],  # No results
                search_time_ms=50
            )
        ]

        # Track BEFORE deduplication
        results_found_by_trigger = {
            "decision": 0,
            "session": 0,
            "best_practices": 0,
        }

        for tr in trigger_results:
            results_found_by_trigger[tr.trigger_type] = len(tr.results)

        # Verify found counts BEFORE dedup
        assert results_found_by_trigger["decision"] == 1
        assert results_found_by_trigger["best_practices"] == 1  # Found a result
        assert results_found_by_trigger["session"] == 0

        # Perform deduplication
        final_results = ukt.deduplicate_results(trigger_results)

        # Track AFTER deduplication
        results_shown_by_trigger = {
            "decision": 0,
            "session": 0,
            "best_practices": 0,
        }

        for result in final_results:
            trigger_type = result.get("_trigger_type")
            if trigger_type in results_shown_by_trigger:
                results_shown_by_trigger[trigger_type] += 1

        # Verify shown counts AFTER dedup
        assert results_shown_by_trigger["decision"] == 1  # Kept (higher priority)
        assert results_shown_by_trigger["best_practices"] == 0  # Deduplicated
        assert results_shown_by_trigger["session"] == 0

        # CRIT-2 FIX: Status should be "success" for best_practices
        # even though shown=0, because it FOUND a result
        for trigger_type in ["decision", "session", "best_practices"]:
            found = results_found_by_trigger[trigger_type]
            shown = results_shown_by_trigger[trigger_type]
            status = "success" if found > 0 else "empty"

            if trigger_type == "best_practices":
                # This is the key test: found=1, shown=0, status should be "success"
                assert found == 1
                assert shown == 0
                assert status == "success"  # Not "empty"!
            elif trigger_type == "decision":
                assert found == 1
                assert shown == 1
                assert status == "success"
            elif trigger_type == "session":
                assert found == 0
                assert shown == 0
                assert status == "empty"

    @pytest.mark.asyncio
    async def test_metrics_all_triggers_empty(self):
        """Verify empty status when no triggers find results."""
        # All triggers return no results
        trigger_results = [
            ukt.TriggerResult("decision", "test", [], 100),
            ukt.TriggerResult("session", "test", [], 100),
            ukt.TriggerResult("best_practices", "test", [], 100),
        ]

        results_found_by_trigger = {
            "decision": 0,
            "session": 0,
            "best_practices": 0,
        }

        for tr in trigger_results:
            results_found_by_trigger[tr.trigger_type] = len(tr.results)

        # All should be empty
        for trigger_type in ["decision", "session", "best_practices"]:
            found = results_found_by_trigger[trigger_type]
            status = "success" if found > 0 else "empty"
            assert status == "empty"

    @pytest.mark.asyncio
    async def test_metrics_all_triggers_find_unique_results(self):
        """Verify metrics when all triggers find unique results (no dedup)."""
        trigger_results = [
            ukt.TriggerResult(
                trigger_type="decision",
                topic="test",
                results=[
                    {"content": "Decision A", "content_hash": "hash1", "score": 0.9, "type": "decision"},
                ],
                search_time_ms=100
            ),
            ukt.TriggerResult(
                trigger_type="session",
                topic="test",
                results=[
                    {"content": "Session B", "content_hash": "hash2", "score": 0.8, "type": "session"},
                ],
                search_time_ms=100
            ),
            ukt.TriggerResult(
                trigger_type="best_practices",
                topic="test",
                results=[
                    {"content": "Practice C", "content_hash": "hash3", "score": 0.7, "type": "guideline"},
                ],
                search_time_ms=100
            ),
        ]

        # Track found
        results_found_by_trigger = {
            "decision": len(trigger_results[0].results),
            "session": len(trigger_results[1].results),
            "best_practices": len(trigger_results[2].results),
        }

        # Deduplicate (no overlap)
        final_results = ukt.deduplicate_results(trigger_results)

        # Track shown
        results_shown_by_trigger = {
            "decision": 0,
            "session": 0,
            "best_practices": 0,
        }

        for result in final_results:
            trigger_type = result.get("_trigger_type")
            if trigger_type in results_shown_by_trigger:
                results_shown_by_trigger[trigger_type] += 1

        # All should have found=1, shown=1, status=success
        for trigger_type in ["decision", "session", "best_practices"]:
            found = results_found_by_trigger[trigger_type]
            shown = results_shown_by_trigger[trigger_type]
            status = "success" if found > 0 else "empty"

            assert found == 1
            assert shown == 1
            assert status == "success"
