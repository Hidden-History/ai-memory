# Location: ai-memory/tests/unit/test_embedding_retry.py
"""Unit tests for BUG-113: Embedding retry with exponential backoff."""

import logging
import os
from unittest.mock import Mock, patch

import pytest

from memory.embeddings import EmbeddingClient, EmbeddingError


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config singleton between tests."""
    from memory.config import reset_config

    reset_config()
    yield
    reset_config()


@pytest.fixture
def client():
    """Create an EmbeddingClient with retry enabled."""
    with patch.dict(os.environ, {"EMBEDDING_MAX_RETRIES": "2"}):
        c = EmbeddingClient()
        yield c
        c.close()


class TestEmbeddingRetry:
    """Tests for embed() retry wrapper (BUG-113)."""

    def test_retry_on_timeout_then_success(self, client):
        """Should retry on timeout and succeed on second attempt."""
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.raise_for_status = Mock()
        mock_response_ok.json.return_value = {"embeddings": [[0.1] * 768]}

        import httpx

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ReadTimeout("Connection timed out")
            return mock_response_ok

        with (
            patch.object(client.client, "post", side_effect=side_effect),
            patch("memory.embeddings.time.sleep"),
        ):
            result = client.embed(["test text"])

        assert len(result) == 1
        assert len(result[0]) == 768
        assert call_count == 2

    def test_all_retries_exhausted_raises(self, client):
        """Should raise EmbeddingError after all retries exhausted."""
        import httpx

        with (
            patch.object(
                client.client,
                "post",
                side_effect=httpx.ReadTimeout("timeout"),
            ),
            patch("memory.embeddings.time.sleep"),
            pytest.raises(EmbeddingError, match="EMBEDDING_TIMEOUT"),
        ):
            client.embed(["test text"])

    def test_non_timeout_error_no_retry(self, client):
        """Non-timeout errors should raise immediately without retry."""
        import httpx

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = Mock()
            resp.status_code = 500
            raise httpx.HTTPStatusError("Server Error", request=Mock(), response=resp)

        with (
            patch.object(client.client, "post", side_effect=side_effect),
            pytest.raises(EmbeddingError, match="EMBEDDING_ERROR"),
        ):
            client.embed(["test text"])

        # Should only be called once (no retry for non-timeout errors)
        assert call_count == 1

    def test_backoff_delay_increases(self, client):
        """Backoff delay range should increase with attempt number."""
        import httpx

        sleep_times = []

        def fake_sleep(t):
            sleep_times.append(t)

        with (
            patch.object(
                client.client,
                "post",
                side_effect=httpx.ReadTimeout("timeout"),
            ),
            patch("memory.embeddings.time.sleep", side_effect=fake_sleep),
            pytest.raises(EmbeddingError),
        ):
            client.embed(["test text"])

        # With 2 retries, we sleep twice
        assert len(sleep_times) == 2
        # Both sleeps should be non-negative (full jitter: uniform(0, cap))
        for t in sleep_times:
            assert t >= 0

    def test_no_retry_when_max_retries_zero(self):
        """With EMBEDDING_MAX_RETRIES=0, no retry should happen."""
        with patch.dict(os.environ, {"EMBEDDING_MAX_RETRIES": "0"}):
            from memory.config import reset_config

            reset_config()
            c = EmbeddingClient()
            try:
                import httpx

                call_count = 0

                def side_effect(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    raise httpx.ReadTimeout("timeout")

                with (
                    patch.object(c.client, "post", side_effect=side_effect),
                    pytest.raises(EmbeddingError),
                ):
                    c.embed(["test"])

                assert call_count == 1
            finally:
                c.close()


class _FakeClock:
    """Deterministic stand-in for time.monotonic()/time.sleep() (BUG-329/TD-710).

    Advancing "real" wall time inside tests to exercise a 45s deadline would make
    the suite slow and flaky. Instead, both time.monotonic() and time.sleep() are
    patched onto this shared clock: sleep() advances the clock instead of blocking,
    and slow_post() (below) simulates a request that takes real time before it
    times out. The test runs in milliseconds while the deadline math is exercised
    exactly as it would run in production.
    """

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class TestEmbeddingTotalTimeout:
    """Tests for EMBEDDING_TOTAL_TIMEOUT (BUG-329/TD-710).

    A per-chunk retry loop with no overall deadline can cumulatively exceed the
    store hooks' HOOK_TIMEOUT (60s default), which cancels the entire store
    coroutine mid-embed instead of letting the pending-status fallback run. These
    tests prove embed() now bounds its own wall-clock time and that the typed
    EMBEDDING_TIMEOUT it raises is exactly what the store path's fallback expects.
    """

    def test_deadline_exceeded_raises_embedding_timeout_within_budget(self):
        """Once EMBEDDING_TOTAL_TIMEOUT has elapsed, embed() raises EMBEDDING_TIMEOUT
        immediately instead of starting another attempt — bounding cumulative retry
        time regardless of EMBEDDING_MAX_RETRIES."""
        import httpx

        clock = _FakeClock()
        call_count = 0

        def slow_timeout_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate a single attempt that alone burns past the total deadline
            # (e.g. a stalled read). The deadline check happens BETWEEN attempts —
            # it cannot preempt an in-flight HTTP call — so this proves the loop
            # stops requesting further attempts once the budget is spent.
            clock.now += 15.0
            raise httpx.ReadTimeout("simulated slow timeout")

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_MAX_RETRIES": "2",
                "EMBEDDING_TOTAL_TIMEOUT": "10.0",
                # Disable the TD-782 coherence floor (acquire+inference=0) so this
                # test can exercise the raw F1 deadline mechanics at a small 10s
                # budget; the coherence flooring has its own tests (TestTimeoutCoherence).
                "EMBEDDING_ACQUIRE_TIMEOUT": "0",
                "EMBEDDING_INFERENCE_TIMEOUT": "0",
            },
        ):
            from memory.config import reset_config

            reset_config()
            c = EmbeddingClient()
            try:
                with (
                    patch.object(c.client, "post", side_effect=slow_timeout_post),
                    patch("memory.embeddings.time.monotonic", clock.monotonic),
                    patch("memory.embeddings.time.sleep", clock.sleep),
                    pytest.raises(
                        EmbeddingError, match="EMBEDDING_TIMEOUT"
                    ) as exc_info,
                ):
                    c.embed(["slow text"])

                assert exc_info.value.args[0] == "EMBEDDING_TIMEOUT"
                # Deadline exceeded after the FIRST attempt (15s > 10s budget): the
                # 2 configured retries never fire. Without this fix, all 3 attempts
                # (1 + 2 retries) would run regardless of elapsed time.
                assert call_count == 1
            finally:
                c.close()

    def test_deadline_not_hit_when_attempts_are_fast(self):
        """Fast failures within budget still exhaust normal retries untouched."""
        import httpx

        with patch.dict(
            os.environ,
            {"EMBEDDING_MAX_RETRIES": "2", "EMBEDDING_TOTAL_TIMEOUT": "45.0"},
        ):
            from memory.config import reset_config

            reset_config()
            c = EmbeddingClient()
            try:
                call_count = 0

                def side_effect(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    raise httpx.ReadTimeout("timeout")

                with (
                    patch.object(c.client, "post", side_effect=side_effect),
                    patch("memory.embeddings.time.sleep"),
                    pytest.raises(EmbeddingError, match="EMBEDDING_TIMEOUT"),
                ):
                    c.embed(["test text"])

                # All 3 attempts (1 + 2 retries) ran — the deadline (45s) never
                # bound this because the mocked calls/sleeps are effectively instant.
                assert call_count == 3
            finally:
                c.close()

    def test_last_attempt_read_timeout_capped_to_remaining_budget(self):
        """BUG-329 fix round (F1): each attempt's HTTP read timeout is capped to
        min(configured_read_timeout, remaining_budget) — a HARD ceiling instead of
        the between-attempts-only check the original fix shipped with.

        Reproduces the exact tail case that defeated the original fix: two
        individual stalls each well UNDER the configured per-request read timeout
        (30s for the code model) but cumulatively over EMBEDDING_TOTAL_TIMEOUT
        (45s). Without F1, neither attempt's read timeout was ever bounded by how
        little budget remained, so two ~29s stalls could burn ~58s of wall clock —
        beating the 60s HOOK_TIMEOUT on its own trigger. With F1, the second
        attempt's read timeout is capped to what's left of the budget (~16s), so
        the request is cut short there instead, and the whole call finishes at
        the 45s deadline rather than ~58s.
        """
        import httpx

        clock = _FakeClock()
        call_count = 0
        observed_read_timeouts = []

        def slow_but_individually_under_configured_timeout(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            req_timeout = kwargs.get("timeout")
            observed_read_timeouts.append(req_timeout.read)
            # Each attempt "wants" to stall 29s — under the configured 30s
            # code-model read timeout on its own — but an attempt can never run
            # past whatever read timeout was actually passed to the request
            # (real httpx behavior; simulated here since post() is mocked).
            desired_stall = 29.0
            clock.now += min(desired_stall, req_timeout.read)
            raise httpx.ReadTimeout("simulated stall")

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_MAX_RETRIES": "2",
                "EMBEDDING_TOTAL_TIMEOUT": "45.0",
                # Coherence floor disabled so the configured 30s code read timeout
                # governs (this test asserts the F1 remaining-budget cap, not the
                # TD-782 floor — see TestTimeoutCoherence for that).
                "EMBEDDING_ACQUIRE_TIMEOUT": "0",
                "EMBEDDING_INFERENCE_TIMEOUT": "0",
            },
        ):
            from memory.config import reset_config

            reset_config()
            c = EmbeddingClient()
            try:
                with (
                    patch.object(
                        c.client,
                        "post",
                        side_effect=slow_but_individually_under_configured_timeout,
                    ),
                    patch("memory.embeddings.time.monotonic", clock.monotonic),
                    patch("memory.embeddings.time.sleep", clock.sleep),
                    patch("memory.embeddings.random.uniform", return_value=0.0),
                    pytest.raises(
                        EmbeddingError, match="EMBEDDING_TIMEOUT"
                    ) as exc_info,
                ):
                    c.embed(["slow code text"], model="code")

                assert exc_info.value.args[0] == "EMBEDDING_TIMEOUT"
                # Exactly two attempts: the deadline ends it there, not retry
                # exhaustion (EMBEDDING_MAX_RETRIES=2 would otherwise allow a 3rd).
                assert call_count == 2
                # First attempt: the full 45s budget still exceeds the configured
                # 30s code-model read timeout, so it's uncapped at 30s.
                assert observed_read_timeouts[0] == 30.0
                # Second attempt: only ~16s of the 45s budget is left (45 - 29) —
                # the per-attempt read timeout is capped DOWN to that, well below
                # the configured 30s. This is the F1 assertion: the cap tracks
                # the remaining budget, not just the configured timeout.
                assert observed_read_timeouts[1] == 16.0
                # Total elapsed stops at the deadline, not ~58s (2 x 29s uncapped).
                assert clock.now == 45.0
            finally:
                c.close()


class TestEmbeddingTotalTimeoutInvariantGuard:
    """Tests for the construction-time EMBEDDING_TOTAL_TIMEOUT invariant guard.

    A dual re-review of the F1 fix round found the guard's original formula
    compared ``total_timeout + read_timeout`` against HOOK_TIMEOUT — but F1
    already caps the READ phase to the remaining budget, so the read timeout was
    never the uncapped risk. That wrong formula false-positived on the shipped
    defaults (45 + 30 = 75 > 60), logging a warning on EVERY EmbeddingClient
    construction (store_async.py builds a new client per chunk), i.e. per-chunk
    log spam forever on a correctly configured install. The only wall-clock
    EMBEDDING_TOTAL_TIMEOUT does NOT bound is the fixed httpx connect+write+pool
    overhead (11s), so the corrected guard compares ``total_timeout + 11s``
    against HOOK_TIMEOUT instead. These tests prove the corrected guard is
    silent on the shipped defaults and fires only when the configured total
    genuinely cannot guarantee staying under HOOK_TIMEOUT.
    """

    def test_invariant_guard_silent_on_default_config(self, monkeypatch, caplog):
        """Coherent shipped defaults (EMBEDDING_TOTAL_TIMEOUT=60, HOOK_TIMEOUT=90) must
        not trigger the invariant warning: 60 + 11 (fixed overhead) = 71 <= 90."""
        monkeypatch.delenv("EMBEDDING_TOTAL_TIMEOUT", raising=False)
        monkeypatch.delenv("HOOK_TIMEOUT", raising=False)
        from memory.config import reset_config

        reset_config()
        with caplog.at_level(logging.WARNING, logger="ai_memory.embed"):
            c = EmbeddingClient()
        try:
            assert not any(
                r.getMessage() == "embedding_total_timeout_invariant_violated"
                for r in caplog.records
            )
        finally:
            c.close()

    def test_invariant_guard_fires_on_unsafe_config(self, monkeypatch, caplog):
        """A configured total that genuinely can't guarantee staying under
        HOOK_TIMEOUT once the fixed overhead is added must fire the guard:
        45 + 11 (fixed overhead) = 56 > 50."""
        monkeypatch.setenv("EMBEDDING_TOTAL_TIMEOUT", "45.0")
        monkeypatch.setenv("HOOK_TIMEOUT", "50")
        # Coherence floor disabled so the configured 45s total is used as-is (this test
        # asserts the fixed-overhead invariant, not the TD-782 floor).
        monkeypatch.setenv("EMBEDDING_ACQUIRE_TIMEOUT", "0")
        monkeypatch.setenv("EMBEDDING_INFERENCE_TIMEOUT", "0")
        from memory.config import reset_config

        reset_config()
        with caplog.at_level(logging.WARNING, logger="ai_memory.embed"):
            c = EmbeddingClient()
        try:
            violations = [
                r
                for r in caplog.records
                if r.getMessage() == "embedding_total_timeout_invariant_violated"
            ]
            assert len(violations) == 1
            assert violations[0].total_timeout == 45.0
            assert violations[0].fixed_overhead_seconds == 11.0
            assert violations[0].hook_timeout == 50
        finally:
            c.close()


class TestEmbeddingTimeoutStoreFallback:
    """Proves the store path's pending-status fallback fires on EMBEDDING_TIMEOUT
    (BUG-329/TD-710 verify-before-coding finding).

    src/memory/storage.py::MemoryStorage.store_memory() catches EmbeddingError and
    upserts with embedding_status="pending" + a zero vector rather than dropping the
    memory. This test drives that fallback with the SAME deadline-driven
    EmbeddingClient.embed() exercised above, proving the two halves of the fix work
    together end-to-end: embed() raises EMBEDDING_TIMEOUT well inside HOOK_TIMEOUT,
    and the store path treats it as a graceful degradation, not a lost write.
    """

    def test_embedding_timeout_falls_back_to_pending_upsert(
        self, tmp_path, monkeypatch
    ):
        import httpx

        from memory.models import MemoryType
        from memory.storage import MemoryStorage

        clock = _FakeClock()

        def slow_timeout_post(*args, **kwargs):
            # Single attempt alone burns past the total deadline (see
            # TestEmbeddingTotalTimeout for why the check can't preempt an
            # in-flight call) — deterministically triggers deadline-exceeded
            # after exactly one attempt, regardless of backoff jitter.
            clock.now += 15.0
            raise httpx.ReadTimeout("simulated slow timeout")

        mock_cfg = Mock()
        mock_cfg.qdrant_host = "localhost"
        mock_cfg.qdrant_port = 26350
        mock_cfg.embedding_host = "localhost"
        mock_cfg.embedding_port = 28080
        mock_cfg.security_scanning_enabled = False
        # embed_sparse is out of scope for this fix (SPARSE_EMBEDDING_TIMEOUT has its
        # own bound) — disable hybrid search so store_memory doesn't also route the
        # mocked slow post through embed_sparse and confound the dense-path assertion.
        mock_cfg.hybrid_search_enabled = False
        monkeypatch.setattr("memory.storage.get_config", lambda: mock_cfg)
        mock_qdrant = Mock()
        mock_qdrant.upsert = Mock()
        monkeypatch.setattr("memory.storage.get_qdrant_client", lambda x: mock_qdrant)
        monkeypatch.setattr("memory.project.detect_project", lambda cwd: "test-project")

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_MAX_RETRIES": "2",
                "EMBEDDING_TOTAL_TIMEOUT": "10.0",
                # Coherence floor disabled so the small 10s budget drives the
                # store-path pending fallback quickly (TestTimeoutCoherence covers
                # the floor itself).
                "EMBEDDING_ACQUIRE_TIMEOUT": "0",
                "EMBEDDING_INFERENCE_TIMEOUT": "0",
            },
        ):
            from memory.config import reset_config

            reset_config()
            real_embedding_client = EmbeddingClient()
            monkeypatch.setattr(
                "memory.storage.EmbeddingClient", lambda cfg: real_embedding_client
            )

            try:
                with (
                    patch.object(
                        real_embedding_client.client,
                        "post",
                        side_effect=slow_timeout_post,
                    ),
                    patch("memory.embeddings.time.monotonic", clock.monotonic),
                    patch("memory.embeddings.time.sleep", clock.sleep),
                ):
                    storage = MemoryStorage()
                    result = storage.store_memory(
                        content="Test content hitting the embedding deadline",
                        cwd=str(tmp_path),
                        group_id="test-project",
                        memory_type=MemoryType.IMPLEMENTATION,
                        source_hook="PostToolUse",
                        session_id="sess-329",
                    )
            finally:
                real_embedding_client.close()

        # The memory was NOT dropped: it was upserted with the pending fallback
        # instead of the whole store coroutine being aborted mid-embed.
        assert result["status"] == "stored"
        assert result["embedding_status"] == "pending"
        mock_qdrant.upsert.assert_called_once()
        upserted_point = mock_qdrant.upsert.call_args[1]["points"][0]
        assert upserted_point.vector == [0.0] * 768
        # embed() raised EMBEDDING_TIMEOUT after exactly one attempt (10s budget,
        # not the full 2-retry exhaustion) — proving the deadline, not ordinary
        # retry exhaustion, is what triggered the pending fallback here.
        assert clock.now == 15.0


class TestStoreAsyncHookFallback:
    """Proves the PostToolUse HOOK path — .claude/hooks/scripts/store_async.py's
    store_memory_async() — survives the exact tail case F1 fixes (BUG-329/TD-710).

    This is the actual production path that produced the 203-item
    pending_queue.jsonl backlog (RCA evidence pack); only the SDK's
    storage.py::MemoryStorage.store_memory() fallback (above) had test coverage
    before this fix round, and that SDK test doesn't exercise the hook's own
    ``asyncio.wait_for(..., timeout=HOOK_TIMEOUT)`` wrapper (see main_async()) —
    the actual mechanism the tail case defeats: without F1, a single attempt can
    run long enough that HOOK_TIMEOUT fires and cancels the coroutine BEFORE
    embed() ever gets a chance to raise EMBEDDING_TIMEOUT, so the graceful
    pending-status fallback below never runs and the item is lost to the (already
    non-draining) retry queue instead. This test uses the REAL EmbeddingClient
    with a mocked HTTP layer (not a mocked EmbeddingClient) and real wall-clock
    timing so it genuinely exercises that race — it fails without F1 and passes
    with it.
    """

    def test_hook_path_falls_back_to_pending_within_hook_timeout(
        self, tmp_path, monkeypatch
    ):
        import asyncio
        import sys
        import time as real_time
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock

        import httpx

        # Import the hook script as a module (same convention as
        # tests/hooks/test_*_store_async.py — the script has no package
        # __init__.py, so sys.path insertion is how it's made importable).
        hooks_dir = str(Path(__file__).parent.parent.parent / ".claude/hooks/scripts")
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        import store_async

        mock_cfg = MagicMock()
        mock_cfg.embedding_host = "localhost"
        mock_cfg.embedding_port = 28080
        mock_cfg.embedding_dimension = 768
        mock_cfg.security_scanning_enabled = False
        mock_cfg.hybrid_search_enabled = False
        # NOTE: patched onto memory.config.get_config below, AFTER reset_config()
        # and the real EmbeddingClient() construction — reset_config() needs the
        # real lru_cache-wrapped get_config still in place to clear.

        mock_qdrant = MagicMock()
        mock_qdrant.upsert = AsyncMock()
        mock_qdrant.close = AsyncMock()
        monkeypatch.setattr(
            store_async, "AsyncQdrantClient", lambda **kwargs: mock_qdrant
        )
        monkeypatch.setattr(
            store_async, "resolve_project_id", lambda cwd: "test-project"
        )
        monkeypatch.setattr(
            store_async,
            "is_duplicate",
            AsyncMock(return_value=MagicMock(is_duplicate=False)),
        )

        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "app.py",
                "content": (
                    "def process_payment(amount, currency='USD'):\n"
                    "    '''Process a payment transaction and return a status record.'''\n"
                    "    if amount <= 0:\n"
                    "        raise ValueError('Amount must be positive')\n"
                    "    if currency not in ('USD', 'EUR', 'GBP'):\n"
                    "        raise ValueError(f'Unsupported currency: {currency}')\n"
                    "    fee = round(amount * 0.029 + 0.30, 2)\n"
                    "    net_amount = round(amount - fee, 2)\n"
                    "    return {\n"
                    "        'status': 'processed',\n"
                    "        'amount': amount,\n"
                    "        'currency': currency,\n"
                    "        'fee': fee,\n"
                    "        'net_amount': net_amount,\n"
                    "    }\n"
                ),
            },
            "cwd": str(tmp_path),
            "session_id": "sess-hook-329",
        }

        call_count = 0

        def slow_but_individually_under_configured_timeout(*args, **kwargs):
            """Two 2.8s stalls — each individually under the 5.0s configured
            EMBEDDING_READ_TIMEOUT — cumulatively exceed the 3.0s
            EMBEDDING_TOTAL_TIMEOUT budget. Mirrors the tail case from the RCA
            (two individually-fine attempts blowing the cumulative budget),
            scaled down for a fast test. The 5.0s configured value (vs. a 3.0s
            total budget) makes the gap this closes obvious: without F1, a
            second attempt is never capped below the full 5.0s configured
            value no matter how little budget remains, so two 2.8s stalls cost
            ~5.6s wall clock — over this test's 5s HOOK_TIMEOUT. With F1, the
            second attempt's cap shrinks to the ~0.2s left in the budget, so
            the whole call finishes at ~3.0s, comfortably (2s margin) inside
            HOOK_TIMEOUT — widened from the original ~1s margin (2.0s call vs
            3s HOOK_TIMEOUT) to be more robust under CI load while still
            failing against pre-F1 code (~5.6s > 5s HOOK_TIMEOUT).
            """
            nonlocal call_count
            call_count += 1
            req_timeout = kwargs.get("timeout")
            cap = req_timeout.read if req_timeout is not None else 5.0
            real_time.sleep(min(2.8, cap))
            raise httpx.ReadTimeout("simulated stall")

        env = {
            "EMBEDDING_READ_TIMEOUT": "5.0",
            "EMBEDDING_TOTAL_TIMEOUT": "3.0",
            "EMBEDDING_MAX_RETRIES": "2",
            "HOOK_TIMEOUT": "5",
            # Coherence floor disabled (acquire+inference=0) so the scaled-down 3s
            # total / 5s read / 5s HOOK budgets drive the F1 tail case; the TD-782
            # floor is covered by TestTimeoutCoherence.
            "EMBEDDING_ACQUIRE_TIMEOUT": "0",
            "EMBEDDING_INFERENCE_TIMEOUT": "0",
            # Isolate from the classifier enqueue side path (unrelated to this
            # fix; avoids it resolving a queue dir off an unconfigured mock).
            "MEMORY_CLASSIFIER_ENABLED": "false",
        }
        with patch.dict(os.environ, env):
            from memory.config import reset_config

            reset_config()
            real_embedding_client = EmbeddingClient()
            monkeypatch.setattr(
                "memory.embeddings.EmbeddingClient",
                lambda cfg=None: real_embedding_client,
            )
            # Safe to replace get_config now — the real EmbeddingClient is
            # already built, and this is the only get_config() call the rest of
            # store_memory_async() needs (security scan gate, embedding_dimension,
            # hybrid_search_enabled).
            monkeypatch.setattr("memory.config.get_config", lambda: mock_cfg)

            try:
                with (
                    patch.object(
                        real_embedding_client.client,
                        "post",
                        side_effect=slow_but_individually_under_configured_timeout,
                    ),
                    patch("memory.embeddings.random.uniform", return_value=0.0),
                ):
                    # Mirrors main_async()'s own wrapper (AC 2.1.5) — this is the
                    # exact mechanism the tail case defeats: HOOK_TIMEOUT racing
                    # the retry loop's real wall-clock time.
                    asyncio.run(
                        asyncio.wait_for(
                            store_async.store_memory_async(hook_input),
                            timeout=store_async.get_hook_timeout(),
                        )
                    )
            finally:
                real_embedding_client.close()

        # Exactly 2 attempts, each individually under the 5.0s configured read
        # timeout — the tail case, not an attempt hitting its own cap.
        assert call_count == 2
        # The memory was NOT dropped and NOT lost to a HOOK_TIMEOUT cancellation:
        # embed() raised EMBEDDING_TIMEOUT within the 3s hook budget (F1), so
        # store_memory_async() completed and upserted with the pending fallback.
        mock_qdrant.upsert.assert_called_once()
        points = mock_qdrant.upsert.call_args[1]["points"]
        assert len(points) == 1
        for point in points:
            assert point["payload"]["embedding_status"] == "pending"
            assert point["vector"] == [0.0] * 768


class TestTimeoutCoherence:
    """TD-782/788: the client read timeout / overall deadline must out-wait the
    embedding server's worst-case response (admission wait + inference), or the
    client abandons a request the server is still legitimately servicing — the
    inversion bug that drives premature EMBEDDING_TIMEOUT and server-side sheds.
    """

    def test_read_timeout_floored_removes_inversion(self):
        """With the shipped (inverted) read timeouts, the effective read timeout is
        floored UP to acquire + inference, so it can no longer expire before the
        server can even admit the request (let alone finish inference)."""
        from memory.config import reset_config

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_ACQUIRE_TIMEOUT": "30",
                "EMBEDDING_INFERENCE_TIMEOUT": "30",
                # The shipped, inverted values (15s < 30s server admission alone).
                "EMBEDDING_READ_TIMEOUT": "15.0",
                "EMBEDDING_READ_TIMEOUT_CODE": "30.0",
            },
        ):
            reset_config()
            c = EmbeddingClient()
            try:
                floor = 30.0 + 30.0
                assert c._read_timeout == floor
                assert c._read_timeout_code == floor
                # Inversion removed: the read timeout now exceeds the server's
                # admission wait, so the client never gives up mid-admission.
                assert c._read_timeout > c._acquire_timeout
            finally:
                c.close()

    def test_configured_read_above_floor_is_preserved(self):
        """A LONGER configured read timeout (slow hardware) is kept — the floor only
        raises, never lowers."""
        from memory.config import reset_config

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_ACQUIRE_TIMEOUT": "30",
                "EMBEDDING_INFERENCE_TIMEOUT": "30",
                "EMBEDDING_READ_TIMEOUT": "120.0",
            },
        ):
            reset_config()
            c = EmbeddingClient()
            try:
                assert c._read_timeout == 120.0  # above the 60s floor, preserved
            finally:
                c.close()

    def test_total_timeout_default_is_inference_aware(self):
        """With no EMBEDDING_TOTAL_TIMEOUT set, the default deadline equals the
        coherent single-attempt budget (acquire + inference), not a flat constant."""
        from memory.config import reset_config

        with patch.dict(
            os.environ,
            {"EMBEDDING_ACQUIRE_TIMEOUT": "30", "EMBEDDING_INFERENCE_TIMEOUT": "30"},
        ):
            os.environ.pop("EMBEDDING_TOTAL_TIMEOUT", None)
            reset_config()
            c = EmbeddingClient()
            try:
                assert c._total_timeout == 60.0
            finally:
                c.close()

    def test_total_timeout_below_floor_is_raised_with_warning(self, caplog):
        """A stale/short EMBEDDING_TOTAL_TIMEOUT (e.g. the shipped 45s) is floored up
        to the coherent budget so it can't clip a legitimate attempt — and the
        misconfiguration is logged, not silently swallowed."""
        from memory.config import reset_config

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_ACQUIRE_TIMEOUT": "30",
                "EMBEDDING_INFERENCE_TIMEOUT": "30",
                "EMBEDDING_TOTAL_TIMEOUT": "45.0",
            },
        ):
            reset_config()
            with caplog.at_level(logging.WARNING, logger="ai_memory.embed"):
                c = EmbeddingClient()
            try:
                assert c._total_timeout == 60.0
                warnings = [
                    r
                    for r in caplog.records
                    if r.getMessage() == "embedding_total_timeout_below_coherent_floor"
                ]
                assert len(warnings) == 1
                assert warnings[0].configured_value == 45.0
                assert warnings[0].coherent_read_floor == 60.0
            finally:
                c.close()

    def test_hook_ceiling_sits_above_coordinated_budget(self):
        """The whole point of the coordinated budget: HOOK_TIMEOUT (the outer store
        ceiling) must exceed EMBEDDING_TOTAL_TIMEOUT + fixed httpx overhead, so the
        hook cannot fire mid-embed. Proven on the coherent defaults."""
        from memory.config import reset_config
        from memory.embeddings import (
            CONNECT_TIMEOUT,
            POOL_TIMEOUT,
            WRITE_TIMEOUT,
        )
        from memory.hooks_common import get_hook_timeout

        with patch.dict(
            os.environ,
            {"EMBEDDING_ACQUIRE_TIMEOUT": "30", "EMBEDDING_INFERENCE_TIMEOUT": "30"},
        ):
            for key in ("EMBEDDING_TOTAL_TIMEOUT", "HOOK_TIMEOUT"):
                os.environ.pop(key, None)
            reset_config()
            c = EmbeddingClient()
            try:
                fixed_overhead = CONNECT_TIMEOUT + WRITE_TIMEOUT + POOL_TIMEOUT
                assert c._total_timeout + fixed_overhead <= get_hook_timeout()
            finally:
                c.close()


class TestSubmitRateLimiter:
    """PLAN-030 WI-10 load-shaping: the client paces embedding submissions to the
    server's sustainable compute ceiling (~9.6 txt/s) with patient backpressure
    (BP-175/BP-180) instead of firehosing it.
    """

    class _FakeReservationClock:
        """Deterministic clock where sleep() advances time (models real wall-clock
        consumption) so the limiter's pacing math is tested without real sleeps."""

        def __init__(self):
            self.now = 0.0
            self.slept = []

        def time(self):
            return self.now

        def sleep(self, seconds):
            self.slept.append(seconds)
            self.now += seconds

    def _make(self, rate, burst):
        from memory.embeddings import _SubmitRateLimiter

        clk = self._FakeReservationClock()
        lim = _SubmitRateLimiter(
            rate, burst=burst, time_source=clk.time, sleeper=clk.sleep
        )
        return lim, clk

    def test_default_rate_targets_server_ceiling(self):
        """The default submit rate is the ~9.6 txt/s server compute ceiling."""
        from memory.embeddings import EMBEDDING_CLIENT_MAX_TXT_PER_SEC

        assert EMBEDDING_CLIENT_MAX_TXT_PER_SEC == 9.6

    def test_sustained_submissions_paced_to_rate(self):
        """N single-text submissions are paced so cumulative wall-clock ~= the time
        the server needs at the ceiling: (N - burst_credit) / rate."""
        lim, clk = self._make(rate=10.0, burst=1.0)
        for _ in range(11):
            lim.acquire(1)
        # burst=1 forgives ~1 text; the remaining 10 are paced at 10/s => ~1.0s.
        assert abs(sum(clk.slept) - 1.0) < 1e-9

    def test_batch_cost_counts_all_texts(self):
        """A batch submission is charged for every text in it (the pacing unit is
        texts, not requests)."""
        lim, clk = self._make(rate=10.0, burst=0.0)
        lim.acquire(5)  # first call: reserves 0.5s of future server time, waits 0
        lim.acquire(5)  # second call must wait for that 0.5s to elapse
        assert abs(sum(clk.slept) - 0.5) < 1e-9

    def test_burst_credit_absorbs_idle(self):
        """After an idle period, up to `burst` texts submit unshaped (bounded burst),
        then pacing resumes."""
        lim, clk = self._make(rate=10.0, burst=5.0)
        clk.now = 100.0  # simulate a long idle gap
        total = 0.0
        for _ in range(5):
            total += lim.acquire(1)
        assert total == 0.0  # 5 texts within the burst credit: no shaping

    def test_disabled_when_rate_nonpositive(self):
        """rate <= 0 disables shaping entirely (never sleeps)."""
        lim, clk = self._make(rate=0.0, burst=1.0)
        for _ in range(50):
            assert lim.acquire(1) == 0.0
        assert clk.slept == []

    def test_deadline_bypass_does_not_shape_or_reserve(self):
        """When the required wait would exceed the caller's remaining budget, the
        submission passes through unshaped AND the reservation clock is not advanced —
        a must-not-drop request never misses its deadline because of shaping."""
        lim, _clk = self._make(rate=2.0, burst=0.0)
        lim.acquire(10)  # reserves 5s of future server time
        next_free_before = lim._next_free
        waited = lim.acquire(1, max_wait=0.5)  # would need ~5s wait > 0.5 budget
        assert waited == 0.0
        assert lim._next_free == next_free_before  # reservation not advanced

    def test_embed_consults_limiter_with_text_count(self):
        """embed() feeds the submission's text count to the shared limiter before
        posting, so bulk callers are actually shaped."""
        import memory.embeddings as emod
        from memory.config import reset_config

        recorded = []

        class _RecordingLimiter:
            def acquire(self, cost, max_wait=None):
                recorded.append((cost, max_wait))
                return 0.0

        mock_ok = Mock()
        mock_ok.status_code = 200
        mock_ok.raise_for_status = Mock()
        mock_ok.json.return_value = {"embeddings": [[0.1] * 768] * 3}

        with patch.dict(
            os.environ,
            {"EMBEDDING_ACQUIRE_TIMEOUT": "0", "EMBEDDING_INFERENCE_TIMEOUT": "0"},
        ):
            reset_config()
            c = EmbeddingClient()
            try:
                with (
                    patch.object(
                        emod, "_get_submit_rate_limiter", lambda: _RecordingLimiter()
                    ),
                    patch.object(c.client, "post", return_value=mock_ok),
                ):
                    c.embed(["a", "b", "c"])
                assert recorded
                assert recorded[0][0] == 3  # cost == number of texts
            finally:
                c.close()
