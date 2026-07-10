"""Embedding service client for AI Memory Module.

Provides httpx-based client for Nomic Embed Code service with connection pooling,
structured logging, and graceful error handling.

Architecture Reference: architecture.md:235-287 (Service Client Architecture)
Best Practices: https://medium.com/@sparknp1/8-httpx-asyncio-patterns-for-safer-faster-clients-f27bc82e93e6
"""

import contextlib
import logging
import os
import random
import threading
import time

import httpx

from .config import MemoryConfig, get_config
from .metrics_push import push_embedding_metrics_async, push_failure_metrics_async

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import (
        embedding_duration_seconds,
        embedding_requests_total,
        failure_events_total,
    )
except ImportError:
    embedding_requests_total = None
    embedding_duration_seconds = None
    failure_events_total = None

# Langfuse GENERATION tracing for embedding API calls (PLAN-014 G-11)
# LANGFUSE: Uses Path A (trace buffer). See LANGFUSE-INTEGRATION-SPEC.md §3.1
try:
    from .trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000

# Fixed per-request httpx phases outside the read timeout: connection establishment,
# request-body write, and pool-acquisition wait. EMBEDDING_TOTAL_TIMEOUT only bounds
# the READ/inference phase (each attempt's read timeout is capped to the remaining
# budget — see _embed_once()); these three phases are NOT covered by that cap, so
# they are fixed overhead on top of EMBEDDING_TOTAL_TIMEOUT for worst-case wall-clock
# time. Used by both the per-request httpx.Timeout construction and the
# construction-time invariant check against HOOK_TIMEOUT.
CONNECT_TIMEOUT = 3.0
WRITE_TIMEOUT = 5.0
POOL_TIMEOUT = 3.0

__all__ = ["EmbeddingClient", "EmbeddingError"]

logger = logging.getLogger("ai_memory.embed")

# ARCHITECTURE NOTE: Do NOT add @observe decorator to functions in this module.
# These functions are called from hook scripts (OS subprocess boundaries) and Docker
# services. @observe creates orphaned Langfuse traces when OTel context doesn't cross
# process boundaries. Use emit_trace_event() with explicit session_id instead.
# See LANGFUSE-INTEGRATION-SPEC.md §4.3


class _SubmitRateLimiter:
    """Process-global patient rate limiter that shapes embedding submissions to the
    embedding server's sustainable compute ceiling (PLAN-030 WI-10 load-shaping).

    Why: bulk single-process consumers (github-sync, jira-sync, document_pipeline) can
    firehose the shared embedding service far past its ~9.6 txt/s compute ceiling
    (PLAN-030 X1/TD-794), driving admission waits and last-resort sheds. BP-175 §1/§4
    prescribe BACKPRESSURE (make the producer WAIT) over shedding for a must-not-drop
    system. This is the client half: pace submissions so the server is fed at a rate it
    can sustain instead of being overrun.

    Mechanism: a reservation clock (no per-call polling). Each ``acquire(cost)`` reserves
    the next ``cost / rate`` seconds of server time and blocks until that slot opens. A
    bounded burst credit (``burst`` texts) lets an idle client send a short burst without
    pacing — so an interactive single-chunk store is never delayed — after which sustained
    submission is paced to ``rate`` texts/sec. Shared process-wide so all EmbeddingClient
    instances in one process (e.g. a sync loop that rebuilds clients) share one schedule.

    ``time_source``/``sleeper`` are injectable so the pacing math is unit-testable without
    real wall-clock sleeps.
    """

    def __init__(self, rate_per_sec, burst=None, *, time_source=None, sleeper=None):
        self._rate = float(rate_per_sec)
        # Default burst = ~1 second of credit, so a brief interactive burst is unshaped.
        self._burst = float(burst) if burst is not None else max(1.0, self._rate)
        self._time = time_source or time.monotonic
        self._sleep = sleeper or time.sleep
        self._lock = threading.Lock()
        self._next_free = 0.0

    def acquire(self, cost, max_wait=None):
        """Block (patiently) until ``cost`` texts may be submitted; return seconds waited.

        Args:
            cost: Number of texts in this submission (the pacing unit).
            max_wait: If the required wait would exceed this many seconds, skip shaping
                and return immediately (0.0) WITHOUT reserving a slot. Callers pass their
                remaining deadline budget here so load-shaping can never cause a
                must-not-drop request to blow its own timeout.

        Returns:
            Seconds actually slept (0.0 when within burst credit or shaping disabled).
        """
        if self._rate <= 0 or cost <= 0:
            return 0.0
        with self._lock:
            now = self._time()
            # Credit only up to `burst` texts of idleness — bounds the burst so a long
            # idle period cannot forgive an unbounded backlog all at once.
            floor = now - (self._burst / self._rate)
            if self._next_free < floor:
                self._next_free = floor
            start = self._next_free
            wait = start - now
            if wait < 0:
                wait = 0.0
            if max_wait is not None and wait > max_wait:
                # Deadline-tight caller: let it through unshaped rather than risk a
                # missed deadline / lost memory. Do NOT advance the reservation clock.
                return 0.0
            self._next_free = start + (cost / self._rate)
        if wait > 0:
            self._sleep(wait)
        return wait


# Client-side submit-rate ceiling (texts/sec). Default = the ~9.6 txt/s server compute
# ceiling measured at INFERENCE_THREADS=4 (PLAN-030 X1/TD-794). <= 0 disables shaping.
EMBEDDING_CLIENT_MAX_TXT_PER_SEC = float(
    os.getenv("EMBEDDING_CLIENT_MAX_TXT_PER_SEC", "9.6")
)

# Process-global limiter singleton (lazy). Shared across all EmbeddingClient instances
# in a process so a bulk sync loop that rebuilds clients is still paced as one stream.
_submit_rate_limiter: _SubmitRateLimiter | None = None
_submit_rate_limiter_lock = threading.Lock()


def _get_submit_rate_limiter() -> _SubmitRateLimiter:
    """Return the process-global submit-rate limiter, creating it on first use.

    The rate is read from the environment at first construction (falling back to the
    default ceiling) so a deployment — or the test suite — can tune or disable shaping
    without editing code. Set ``_submit_rate_limiter = None`` to force a rebuild.
    """
    global _submit_rate_limiter
    if _submit_rate_limiter is None:
        with _submit_rate_limiter_lock:
            if _submit_rate_limiter is None:
                rate = float(
                    os.getenv(
                        "EMBEDDING_CLIENT_MAX_TXT_PER_SEC",
                        str(EMBEDDING_CLIENT_MAX_TXT_PER_SEC),
                    )
                )
                _submit_rate_limiter = _SubmitRateLimiter(rate)
    return _submit_rate_limiter


class EmbeddingError(Exception):
    """Raised when embedding generation fails.

    This exception wraps httpx errors and timeouts for consistent error handling.

    Attributes:
        retryable: True when the failure is transient and the caller should retry
            (e.g. server backpressure 503/429). Timeout errors are also retried via the
            message-based check for backward compatibility.
        retry_after: Server-advised wait in seconds (from a ``Retry-After`` header), or
            None. The retry layer honors this when present.
    """

    def __init__(self, message, *, retryable=False, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


def _parse_retry_after(value):
    """Parse a ``Retry-After`` header (delta-seconds) into float seconds.

    Returns None when the header is absent or not delta-seconds. The embedding service
    emits integer delta-seconds; the HTTP-date form is unsupported (and unnecessary).
    """
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


class EmbeddingClient:
    """Client for the embedding service.

    Uses long-lived httpx.Client with connection pooling for optimal performance.
    Implements 2025 best practices: granular timeouts, connection pooling, structured logging.

    Attributes:
        config: MemoryConfig instance with service endpoints
        base_url: Full URL to embedding service
        client: Shared httpx.Client instance with connection pooling

    Example:
        >>> client = EmbeddingClient()
        >>> embeddings = client.embed(["def hello(): return 'world'"])
        >>> len(embeddings[0])
        768  # DEC-010: Jina Embeddings v2 Base Code dimensions
    """

    def __init__(self, config: MemoryConfig | None = None):
        """Initialize embedding client with configuration.

        Args:
            config: Optional MemoryConfig instance. Uses get_config() if not provided.

        Note:
            Creates a long-lived httpx.Client with connection pooling. Reuse this
            client instance across requests for optimal performance (60%+ latency reduction).
        """
        self.config = config or get_config()
        self.base_url = (
            f"http://{self.config.embedding_host}:{self.config.embedding_port}"
        )

        # TD-782/788 TIMEOUT COHERENCE: the client read timeout must out-wait the
        # server's worst-case response time, or the client abandons a request the
        # server is still legitimately servicing (premature EMBEDDING_TIMEOUT → retry
        # storm → server-side admission shed). The server response spans TWO phases the
        # client holds the connection open for: the admission wait (block-not-drop up to
        # EMBEDDING_ACQUIRE_TIMEOUT for an inference slot — docker/embedding/main.py) and
        # then the inference itself (a single large-text embed measured at ~19-28s,
        # PLAN-030 X1). So the coherent floor for any read timeout is
        # acquire_timeout + inference_timeout. Below that floor is the inversion bug.
        self._acquire_timeout = max(
            0.0, float(os.getenv("EMBEDDING_ACQUIRE_TIMEOUT", "30.0"))
        )
        # Realistic worst-case single-request inference time (covers the observed
        # 19-28s large-text range with margin). Separate knob so ops can tune the
        # inference term without touching the server's admission timeout.
        self._inference_timeout = max(
            0.0, float(os.getenv("EMBEDDING_INFERENCE_TIMEOUT", "30.0"))
        )
        coherent_read_floor = self._acquire_timeout + self._inference_timeout

        # EMBEDDING_READ_TIMEOUT / _CODE remain configurable, but are floored UP to the
        # coherent value so a stale/short setting can never reintroduce the inversion.
        # A larger configured value (slow hardware) is preserved.
        # BUG-329 fix round (F1): stored on self so _embed_once() can cap it to the
        # remaining EMBEDDING_TOTAL_TIMEOUT budget on each attempt.
        self._read_timeout = max(
            float(os.getenv("EMBEDDING_READ_TIMEOUT", "15.0")), coherent_read_floor
        )
        # BUG-288: Code model is slower than en model under CPU load.
        # Per-request override applied in _embed_once() when model="code".
        self._read_timeout_code = max(
            float(os.getenv("EMBEDDING_READ_TIMEOUT_CODE", "30.0")), coherent_read_floor
        )
        timeout_config = httpx.Timeout(
            connect=CONNECT_TIMEOUT,  # Connection establishment timeout
            read=self._read_timeout,  # Coherent read floor (>= acquire + inference)
            write=WRITE_TIMEOUT,  # Write timeout for request body
            pool=POOL_TIMEOUT,  # Pool acquisition timeout
        )

        # Connection pooling with 2025 recommended defaults
        # Source: https://www.python-httpx.org/advanced/resource-limits/
        limits = httpx.Limits(
            max_keepalive_connections=20,  # Keep-alive pool size
            max_connections=100,  # Total connection limit
            keepalive_expiry=10.0,  # Idle timeout - reduced from 30s to avoid stale connections
        )

        self.client = httpx.Client(timeout=timeout_config, limits=limits)

        # BUG-113: Retry configuration for transient timeout failures
        self._max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "2"))
        self._backoff_base = float(os.getenv("EMBEDDING_BACKOFF_BASE", "1.0"))
        self._backoff_cap = float(os.getenv("EMBEDDING_BACKOFF_CAP", "15.0"))

        # BUG-329/TD-710: Overall wall-clock deadline for embed()'s retry loop.
        # Per-chunk retries with no cumulative bound can exceed the store hooks'
        # HOOK_TIMEOUT (coherent default 90s), which cancels the whole store coroutine
        # mid-embed instead of letting the pending-status fallback handle it.
        # Must stay below HOOK_TIMEOUT so embed() raises EMBEDDING_TIMEOUT while
        # the caller still has budget left to upsert with embedding_status=pending.
        # F1/F1-guard: each attempt's HTTP read timeout is capped to the remaining
        # portion of this budget (see _embed_once()), which makes the READ phase a
        # hard ceiling rather than just a between-attempts check. Fixed httpx
        # connect/write/pool overhead runs on top of this budget (see the
        # construction-time invariant check below).
        # TD-782/788: made inference-time-aware. The default AND the lower floor are the
        # coherent single-attempt budget (acquire + inference) so the deadline can never
        # be smaller than one full legitimate attempt — otherwise the deadline itself
        # would clip a request the server is still servicing (the inversion, one layer
        # up). Per-attempt HTTP read timeout is still capped to the remaining portion of
        # this budget (see _embed_once()).
        default_total = coherent_read_floor if coherent_read_floor > 0 else 45.0
        self._total_timeout = float(
            os.getenv("EMBEDDING_TOTAL_TIMEOUT", str(default_total))
        )
        if coherent_read_floor > 0 and self._total_timeout < coherent_read_floor:
            # A configured deadline below one coherent attempt reintroduces premature
            # timeout. Floor it up and log so the misconfiguration is visible.
            logger.warning(
                "embedding_total_timeout_below_coherent_floor",
                extra={
                    "configured_value": self._total_timeout,
                    "coherent_read_floor": coherent_read_floor,
                    "acquire_timeout": self._acquire_timeout,
                    "inference_timeout": self._inference_timeout,
                },
            )
            self._total_timeout = coherent_read_floor
        if self._total_timeout <= 0:
            # A non-positive budget would make embed() raise EMBEDDING_TIMEOUT on
            # every call before a first attempt is ever made, silently disabling
            # embedding generation. Floor it and log so misconfiguration is visible.
            logger.warning(
                "embedding_total_timeout_invalid_using_floor",
                extra={
                    "configured_value": self._total_timeout,
                    "floor_seconds": 1.0,
                },
            )
            self._total_timeout = 1.0

        # F1 construction-time invariant: F1 caps each attempt's READ timeout to the
        # remaining EMBEDDING_TOTAL_TIMEOUT budget (see _embed_once()), so the read
        # phase can never itself exceed that budget. What EMBEDDING_TOTAL_TIMEOUT does
        # NOT cover is the fixed httpx connect/write/pool overhead outside the read
        # phase (CONNECT_TIMEOUT + WRITE_TIMEOUT + POOL_TIMEOUT, ~11s) — that overhead
        # runs on top of the deadline on every attempt. So the real worst-case
        # wall-clock is total_timeout + that fixed overhead, and THAT must stay below
        # the store hooks' own HOOK_TIMEOUT, or the hook's outer timeout can still
        # fire before embed() gets a chance to raise EMBEDDING_TIMEOUT and let the
        # caller's pending-status fallback run. Read HOOK_TIMEOUT the same way the
        # hooks do (hooks_common.get_hook_timeout()).
        try:
            hook_timeout = int(os.getenv("HOOK_TIMEOUT", "90"))
        except ValueError:
            hook_timeout = 90
        fixed_overhead = CONNECT_TIMEOUT + WRITE_TIMEOUT + POOL_TIMEOUT
        if self._total_timeout + fixed_overhead > hook_timeout:
            logger.warning(
                "embedding_total_timeout_invariant_violated",
                extra={
                    "total_timeout": self._total_timeout,
                    "fixed_overhead_seconds": fixed_overhead,
                    "hook_timeout": hook_timeout,
                },
            )

    def embed(
        self, texts: list[str], model: str = "en", project: str = "unknown"
    ) -> list[list[float]]:
        """Generate embeddings with retry on transient failures.

        Wraps _embed_once() with exponential backoff + full jitter (AWS formula,
        BP-091). Retries on timeout AND on server backpressure (HTTP 503/429) — the
        latter honoring the ``Retry-After`` header so the client stays in lockstep with
        the service's bounded-queue admission (BP-175 §8): a backpressure signal makes
        the caller wait and re-submit rather than dropping the memory. Non-retryable
        errors (e.g. 413 oversized, 4xx) raise immediately.

        BUG-329/TD-710 (fix round F1/F4) + TD-782/788: The whole retry loop is bounded
        by an overall wall-clock deadline (``EMBEDDING_TOTAL_TIMEOUT``, coherent default
        = acquire + inference, 60s). F1 caps each attempt's HTTP read/inference timeout
        to ``min(configured_read_timeout, remaining_budget)`` (see _embed_once()), so the
        READ phase of no single attempt can run long enough on its own to blow past the
        deadline. Without this cap, per-chunk retries could cumulatively exceed the store
        hooks' HOOK_TIMEOUT (coherent default 90s) even though the deadline was "checked"
        between attempts, because a
        single slow attempt could still run for the full configured read timeout
        regardless of how little budget remained — aborting the entire store coroutine
        mid-embed instead of letting the caller's pending-status fallback run. This is
        NOT an exact ceiling on total wall-clock time: the fixed httpx connect/write/pool
        overhead (``CONNECT_TIMEOUT + WRITE_TIMEOUT + POOL_TIMEOUT``, ~11s) on each
        attempt runs on top of the deadline and is not itself budget-capped, so
        worst-case wall-clock per call is approximately ``EMBEDDING_TOTAL_TIMEOUT +
        11s``. That combined figure must stay at or below ``HOOK_TIMEOUT``; the
        client's construction-time invariant check warns (`embedding_total_timeout_invariant_violated`)
        when it doesn't. F4: if the backoff sleep itself would consume more than the
        remaining budget, embed() raises EMBEDDING_TIMEOUT immediately rather than
        sleeping out the remainder and then raising anyway — preserving budget for the
        caller's fallback path.

        Args:
            texts: List of text strings to embed.
            model: "en" for prose, "code" for code content.
            project: Project identifier for metrics.

        Returns:
            List of embedding vectors (768 dimensions each).

        Raises:
            EmbeddingError: If all retries exhausted, the overall deadline is
                exceeded, or a non-retryable error occurs.
        """
        last_error: EmbeddingError | None = None
        deadline = time.monotonic() + self._total_timeout
        for attempt in range(1 + self._max_retries):
            # Load-shaping (BP-175/BP-180, PLAN-030 WI-10): pace submissions to the
            # server's sustainable compute ceiling so bulk consumers apply patient
            # backpressure instead of firehosing. Done BEFORE computing `remaining` so
            # the pacing wait is charged against the deadline (the per-attempt read
            # timeout below shrinks accordingly); max_wait caps it to the remaining
            # budget so shaping can never make a must-not-drop request miss its deadline.
            budget = deadline - time.monotonic()
            _get_submit_rate_limiter().acquire(len(texts), max_wait=max(0.0, budget))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._log_total_timeout_exceeded(attempt, texts, model)
                raise EmbeddingError("EMBEDDING_TIMEOUT") from last_error
            try:
                return self._embed_once(
                    texts, model=model, project=project, remaining_budget=remaining
                )
            except EmbeddingError as e:
                retryable = (
                    getattr(e, "retryable", False) or "timeout" in str(e).lower()
                )
                if not retryable:
                    raise  # Non-retryable errors: surface immediately
                last_error = e
                if attempt < self._max_retries:
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after is not None:
                        # Honor the server's Retry-After, capped so a stuck server can't
                        # block the caller indefinitely.
                        sleep_time = min(self._backoff_cap, retry_after)
                    else:
                        sleep_time = random.uniform(
                            0, min(self._backoff_cap, self._backoff_base * (2**attempt))
                        )
                    remaining = deadline - time.monotonic()
                    # F4: a sleep that would consume the rest of the budget buys
                    # nothing — the next attempt will just find the deadline already
                    # passed. Raise now instead of burning that time doing nothing.
                    if remaining <= 0 or sleep_time >= remaining:
                        self._log_total_timeout_exceeded(attempt, texts, model)
                        raise EmbeddingError("EMBEDDING_TIMEOUT") from e
                    logger.warning(
                        "embedding_retry",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self._max_retries,
                            "sleep_seconds": round(sleep_time, 2),
                            "retry_after": retry_after,
                            "texts_count": len(texts),
                            "model": model,
                        },
                    )
                    time.sleep(sleep_time)
        raise last_error  # type: ignore[misc]

    def _log_total_timeout_exceeded(
        self, attempt: int, texts: list[str], model: str
    ) -> None:
        """Emit the shared warning for an EMBEDDING_TOTAL_TIMEOUT deadline hit.

        BUG-329/TD-710 fix round: extracted so embed()'s two deadline-hit sites
        (before an attempt, before a backoff sleep) log identically.
        """
        logger.warning(
            "embedding_total_timeout_exceeded",
            extra={
                "attempt": attempt + 1,
                "total_timeout": self._total_timeout,
                "texts_count": len(texts),
                "model": model,
            },
        )

    def _embed_once(
        self,
        texts: list[str],
        model: str = "en",
        project: str = "unknown",
        remaining_budget: float | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for texts using specified model.

        Sends batch request to embedding service and returns vector embeddings.
        Uses connection pooling for optimal performance.

        Args:
            texts: List of text strings to embed (supports batch operations).
            model: "en" for prose, "code" for code content. Default: "en".
            remaining_budget: Seconds left in the caller's EMBEDDING_TOTAL_TIMEOUT
                deadline, if called from embed()'s retry loop. When provided
                (BUG-329 fix round F1), the request's read timeout is capped to
                ``min(configured_read_timeout, remaining_budget)`` so this attempt
                cannot alone run long enough to blow past the deadline.

        Returns:
            List of embedding vectors, one per input text. Each vector has
            768 dimensions (SPEC-010: Jina Embeddings v2 dual model support).

        Raises:
            EmbeddingError: If request times out or HTTP error occurs.

        Example:
            >>> client = EmbeddingClient()
            >>> embeddings = client.embed(["text1", "text2"], model="en")
            >>> len(embeddings)
            2
            >>> len(embeddings[0])
            768
        """
        start_time = time.perf_counter()

        # BUG-288: Code model embeddings take longer under CPU load, so it gets its
        # own (longer) configured read timeout than the "en" model.
        # BUG-329 fix round (F1): always send a per-request override, capped to the
        # caller's remaining deadline budget when known. This is what makes
        # EMBEDDING_TOTAL_TIMEOUT a hard ceiling — previously only the code-model
        # timeout was overridden per-request, and neither was ever bounded by how
        # much of the deadline was left, so a single slow attempt could run the full
        # configured read timeout even with almost no budget remaining.
        base_read_timeout = (
            self._read_timeout_code if model == "code" else self._read_timeout
        )
        read_timeout = (
            min(base_read_timeout, remaining_budget)
            if remaining_budget is not None
            else base_read_timeout
        )
        _request_timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT,
            read=read_timeout,
            write=WRITE_TIMEOUT,
            pool=POOL_TIMEOUT,
        )

        try:
            response = self.client.post(
                f"{self.base_url}/embed/dense",
                json={"texts": texts, "model": model},
                timeout=_request_timeout,
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]

            # TD-354: Validate non-zero embeddings
            for i, vec in enumerate(embeddings):
                if not vec or all(v == 0.0 for v in vec):
                    raise EmbeddingError(
                        f"degenerate_zero_vector at index {i} for text length {len(texts[i])}"
                    )

            # Metrics: Embedding request success (Story 6.1, AC 6.1.3)
            # TECH-DEBT-067: Add embedding_type and context labels
            duration_seconds = time.perf_counter() - start_time
            if embedding_requests_total:
                embedding_requests_total.labels(
                    status="success",
                    embedding_type="dense",
                    context="realtime",
                    project=project,
                    model=model,
                ).inc()
            if embedding_duration_seconds:
                embedding_duration_seconds.labels(
                    embedding_type="dense", model=model
                ).observe(duration_seconds)

            # Push to Pushgateway for hook subprocess visibility
            push_embedding_metrics_async(
                status="success",
                embedding_type="dense",
                duration_seconds=duration_seconds,
                context="realtime",
                model=model,
            )

            # PLAN-014 G-11: GENERATION trace for dense embedding API call
            if emit_trace_event:
                with contextlib.suppress(Exception):
                    emit_trace_event(
                        event_type="embedding_generation",
                        data={
                            "input": f"Embed {len(texts)} texts (model={model})"[
                                :TRACE_CONTENT_MAX
                            ],
                            "output": f"{len(embeddings)} embeddings generated"[
                                :TRACE_CONTENT_MAX
                            ],
                            "model": "jina-embeddings-v2-base-en",
                            "usage": {"input": len(texts), "output": 0},
                            "metadata": {
                                "text_count": len(texts),
                                "model": model,
                                "endpoint": "dense",
                            },
                        },
                        session_id=os.environ.get("CLAUDE_SESSION_ID"),
                        as_type="generation",
                        tags=["search", "embedding"],
                    )

            return embeddings

        except httpx.TimeoutException as e:
            logger.error(
                "embedding_timeout",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "model": model,
                    "error": str(e),
                },
            )

            # Metrics: Embedding request timeout (Story 6.1, AC 6.1.3)
            # TECH-DEBT-067: Add embedding_type and context labels
            duration_seconds = time.perf_counter() - start_time
            if embedding_requests_total:
                embedding_requests_total.labels(
                    status="timeout",
                    embedding_type="dense",
                    context="realtime",
                    project=project,
                    model=model,
                ).inc()
            if embedding_duration_seconds:
                embedding_duration_seconds.labels(
                    embedding_type="dense", model=model
                ).observe(duration_seconds)

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding",
                    error_code="EMBEDDING_TIMEOUT",
                    project=project,
                ).inc()

            # Push to Pushgateway for hook subprocess visibility
            push_embedding_metrics_async(
                status="timeout",
                embedding_type="dense",
                duration_seconds=duration_seconds,
                context="realtime",
                model=model,
            )
            push_failure_metrics_async(
                component="embedding",
                error_code="EMBEDDING_TIMEOUT",
                project=project,
            )

            raise EmbeddingError("EMBEDDING_TIMEOUT") from e

        except httpx.HTTPError as e:
            # BP-175 §8: a 503/429 is server backpressure (bounded-queue admission), not
            # a hard failure — mark it retryable and carry Retry-After so embed()
            # re-submits in lockstep rather than dropping the memory. Other HTTP errors
            # (e.g. 413 oversized, 4xx) are terminal and must not loop.
            backpressure = isinstance(
                e, httpx.HTTPStatusError
            ) and e.response.status_code in (503, 429)
            retry_after = (
                _parse_retry_after(e.response.headers.get("Retry-After"))
                if backpressure
                else None
            )
            logger.error(
                "embedding_error",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "model": model,
                    "error": str(e),
                    "backpressure": backpressure,
                    "retry_after": retry_after,
                },
            )

            # Metrics: Embedding request failed (Story 6.1, AC 6.1.3)
            # TECH-DEBT-067: Add embedding_type and context labels
            duration_seconds = time.perf_counter() - start_time
            if embedding_requests_total:
                embedding_requests_total.labels(
                    status="failed",
                    embedding_type="dense",
                    context="realtime",
                    project=project,
                    model=model,
                ).inc()
            if embedding_duration_seconds:
                embedding_duration_seconds.labels(
                    embedding_type="dense", model=model
                ).observe(duration_seconds)

            # Metrics: Failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="embedding",
                    error_code="EMBEDDING_ERROR",
                    project=project,
                ).inc()

            # Push to Pushgateway for hook subprocess visibility
            push_embedding_metrics_async(
                status="failed",
                embedding_type="dense",
                duration_seconds=duration_seconds,
                context="realtime",
                model=model,
            )
            push_failure_metrics_async(
                component="embedding",
                error_code="EMBEDDING_ERROR",
                project=project,
            )

            if backpressure:
                raise EmbeddingError(
                    f"EMBEDDING_BACKPRESSURE: HTTP {e.response.status_code}",
                    retryable=True,
                    retry_after=retry_after,
                ) from e
            raise EmbeddingError(f"EMBEDDING_ERROR: {e}") from e

    def embed_sparse(self, texts: list[str]) -> list[dict]:
        """Generate BM25 sparse embeddings via embedding service.

        Args:
            texts: List of text strings to generate sparse embeddings for.

        Returns:
            List of dicts with 'indices' and 'values' keys for each input text.

        Raises:
            EmbeddingError: If request fails or service returns an error.
        """
        try:
            response = self.client.post(
                f"{self.base_url}/embed/sparse",
                json={"texts": texts},
                timeout=30.0,
            )
            response.raise_for_status()
            sparse_embeddings = response.json()["embeddings"]

            # PLAN-014 G-11: GENERATION trace for sparse embedding API call
            if emit_trace_event:
                with contextlib.suppress(Exception):
                    emit_trace_event(
                        event_type="embedding_generation",
                        data={
                            "input": f"Embed {len(texts)} texts (sparse BM25)"[
                                :TRACE_CONTENT_MAX
                            ],
                            "output": f"{len(sparse_embeddings)} sparse embeddings generated"[
                                :TRACE_CONTENT_MAX
                            ],
                            "model": "Qdrant/bm25",
                            "usage": {"input": len(texts), "output": 0},
                            "metadata": {
                                "text_count": len(texts),
                                "endpoint": "sparse",
                            },
                        },
                        session_id=os.environ.get("CLAUDE_SESSION_ID"),
                        as_type="generation",
                        tags=["search", "embedding"],
                    )

            return sparse_embeddings
        except httpx.TimeoutException as e:
            logger.error(
                "sparse_embedding_timeout",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "error": str(e),
                },
            )
            raise EmbeddingError("SPARSE_EMBEDDING_TIMEOUT") from e
        except httpx.HTTPError as e:
            logger.error(
                "sparse_embedding_error",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "error": str(e),
                },
            )
            raise EmbeddingError(f"SPARSE_EMBEDDING_ERROR: {e}") from e

    def embed_late(self, texts: list[str]) -> list[list[list[float]]]:
        """Generate ColBERT late interaction embeddings via embedding service.

        Returns multi-vector embeddings for ColBERT reranking. Each text produces
        a list of token-level vectors (list[list[float]]).

        Args:
            texts: List of text strings to generate late interaction embeddings for.

        Returns:
            List of multi-vector embeddings. Each element is a list of token vectors
            (list[list[float]]) suitable for Qdrant's multi-vector 'colbert' named vector.

        Raises:
            EmbeddingError: If request fails or service returns an error.
        """
        try:
            response = self.client.post(
                f"{self.base_url}/embed/late",
                json={"texts": texts},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()["embeddings"]
            # Service returns [{embeddings: [[float]]}] — extract inner embeddings
            late_embeddings = [item["embeddings"] for item in data]

            # PLAN-014 G-11: GENERATION trace for late interaction (ColBERT) embedding API call
            if emit_trace_event:
                with contextlib.suppress(Exception):
                    emit_trace_event(
                        event_type="embedding_generation",
                        data={
                            "input": f"Embed {len(texts)} texts (ColBERT late interaction)"[
                                :TRACE_CONTENT_MAX
                            ],
                            "output": f"{len(late_embeddings)} late interaction embeddings generated"[
                                :TRACE_CONTENT_MAX
                            ],
                            "model": "colbert-ir/colbertv2.0",
                            "usage": {"input": len(texts), "output": 0},
                            "metadata": {"text_count": len(texts), "endpoint": "late"},
                        },
                        session_id=os.environ.get("CLAUDE_SESSION_ID"),
                        as_type="generation",
                        tags=["search", "embedding"],
                    )

            return late_embeddings
        except httpx.TimeoutException as e:
            logger.error(
                "late_embedding_timeout",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "error": str(e),
                },
            )
            raise EmbeddingError("LATE_EMBEDDING_TIMEOUT") from e
        except httpx.HTTPError as e:
            logger.error(
                "late_embedding_error",
                extra={
                    "texts_count": len(texts),
                    "base_url": self.base_url,
                    "error": str(e),
                },
            )
            raise EmbeddingError(f"LATE_EMBEDDING_ERROR: {e}") from e

    def embed_with_late_chunking(
        self,
        document: str,
        chunk_offsets: list[tuple[int, int]],
        project: str = "unknown",
    ) -> list[list[float]]:
        """Generate embeddings using chunked embedding (BP-028).

        Sends each chunk as an independent text segment and returns per-chunk
        embeddings. Note: Despite the method name, the current implementation uses
        independent chunk embedding, not true late chunking. True late chunking
        (single transformer pass with per-chunk mean pooling) deferred to v2.3.0.
        See TD-274.

        Only valid for documents <= 8192 tokens (Jina context limit).
        For documents > 8192 tokens, use regular embed() per chunk instead.

        Args:
            document: Full document text (must be <= 8192 tokens).
            chunk_offsets: List of (start_char, end_char) character offsets
                defining each chunk's boundary within the document.
            project: Project name for logging/metrics.

        Returns:
            List of 768-dim float vectors, one per chunk offset.
            Returns empty list if the embedding service is unavailable or errors.

        Raises:
            EmbeddingError: If the service returns an error response.
        """
        try:
            response = self.client.post(
                f"{self.base_url}/embed/chunked",
                json={
                    "texts": [document],
                    "late_chunking": True,
                    "chunk_offsets": [[start, end] for start, end in chunk_offsets],
                },
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
            embeddings = result.get("embeddings", [])
            if not embeddings:
                raise EmbeddingError(
                    "LATE_CHUNKING_EMPTY_RESPONSE: service returned no embeddings"
                )
            # Chunked embedding returns list of per-chunk embeddings (not wrapped in outer list)
            # Shape: [[chunk0_vector], [chunk1_vector], ...] OR [chunk0_vector, chunk1_vector, ...]
            # Normalize to flat list of vectors
            if (
                embeddings
                and isinstance(embeddings[0], list)
                and isinstance(embeddings[0][0], list)
            ):
                # Wrapped format: [[vec1], [vec2]] -> [vec1, vec2]
                return [e[0] for e in embeddings]
            return embeddings
        except EmbeddingError:
            raise
        except Exception as e:
            logger.error(
                "late_chunking_embedding_error",
                extra={
                    "document_length": len(document),
                    "chunk_count": len(chunk_offsets),
                    "project": project,
                    "error": str(e),
                },
            )
            raise EmbeddingError(f"LATE_CHUNKING_ERROR: {e}") from e

    def health_check(self) -> bool:
        """Check if embedding service is healthy.

        Sends GET request to /health endpoint with timeout handling.

        Returns:
            True if service responds with 200, False otherwise.

        Example:
            >>> client = EmbeddingClient()
            >>> if client.health_check():
            ...     embeddings = client.embed(["test"])
        """
        try:
            response = self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(
                "embedding_health_check_failed",
                extra={"base_url": self.base_url, "error": str(e)},
            )
            return False

    def close(self) -> None:
        """Close httpx client and release resources.

        Call this method when done with the client, or use context manager.

        Example:
            >>> client = EmbeddingClient()
            >>> try:
            ...     embeddings = client.embed(["test"])
            ... finally:
            ...     client.close()
        """
        if hasattr(self, "client") and self.client is not None:
            self.client.close()

    def __enter__(self) -> "EmbeddingClient":
        """Enter context manager.

        Returns:
            Self for use in with statement.

        Example:
            >>> with EmbeddingClient() as client:
            ...     embeddings = client.embed(["test"])
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close client.

        Args:
            exc_type: Exception type if raised, None otherwise.
            exc_val: Exception value if raised, None otherwise.
            exc_tb: Exception traceback if raised, None otherwise.
        """
        self.close()

    def __del__(self) -> None:
        """Close httpx client on garbage collection.

        Note:
            Uses contextlib.suppress to handle interpreter shutdown safely.
            Prefer using context manager or explicit close() instead.
        """
        # Silently ignore errors during interpreter shutdown
        # when httpx module may already be unloaded
        with contextlib.suppress(Exception):
            self.close()
