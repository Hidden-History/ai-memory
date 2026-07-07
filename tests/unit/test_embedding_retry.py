# Location: ai-memory/tests/unit/test_embedding_retry.py
"""Unit tests for BUG-113: Embedding retry with exponential backoff."""

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
            {"EMBEDDING_MAX_RETRIES": "2", "EMBEDDING_TOTAL_TIMEOUT": "45.0"},
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
            {"EMBEDDING_MAX_RETRIES": "2", "EMBEDDING_TOTAL_TIMEOUT": "10.0"},
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
            """Two 1.8s stalls — each individually under the 5.0s configured
            EMBEDDING_READ_TIMEOUT — cumulatively exceed the 2.0s
            EMBEDDING_TOTAL_TIMEOUT budget. Mirrors the tail case from the RCA
            (two individually-fine attempts blowing the cumulative budget),
            scaled down for a fast test. The 5.0s configured value (vs. a 2.0s
            total budget) makes the gap this closes obvious: without F1, a
            second attempt is never capped below the full 5.0s configured
            value no matter how little budget remains, so two 1.8s stalls cost
            ~3.6s wall clock — over this test's 3s HOOK_TIMEOUT. With F1, the
            second attempt's cap shrinks to the ~0.2s left in the budget, so
            the whole call finishes at ~2.0s, comfortably inside HOOK_TIMEOUT.
            """
            nonlocal call_count
            call_count += 1
            req_timeout = kwargs.get("timeout")
            cap = req_timeout.read if req_timeout is not None else 5.0
            real_time.sleep(min(1.8, cap))
            raise httpx.ReadTimeout("simulated stall")

        env = {
            "EMBEDDING_READ_TIMEOUT": "5.0",
            "EMBEDDING_TOTAL_TIMEOUT": "2.0",
            "EMBEDDING_MAX_RETRIES": "2",
            "HOOK_TIMEOUT": "3",
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
        assert len(points) >= 1
        for point in points:
            assert point["payload"]["embedding_status"] == "pending"
            assert point["vector"] == [0.0] * 768
