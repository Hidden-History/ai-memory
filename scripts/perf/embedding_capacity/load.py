"""Async load generation against the embedding service (BP-179 §4).

Two shapes:
  - `run_burst`: N request batches fired concurrently (all submitted before any
    completes) — the measure mode's + capacity-ramp mode's input.
  - `run_soak_callers`: genuine multi-caller sustained load — independent async
    "callers" (each modelling a distinct project/client) looping bursts with
    jitter for a duration, exercising the AIMD self-throttle the way arbitrary-N
    real callers do (BP-179 §4, point 4).
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx


@dataclass
class RequestResult:
    status_code: int
    elapsed_seconds: float
    error: str | None = None


async def _post_embed(
    client: httpx.AsyncClient, base_url: str, texts: list[str], model: str
) -> RequestResult:
    start = time.monotonic()
    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/embed/dense",
            json={"texts": texts, "model": model},
        )
        return RequestResult(response.status_code, time.monotonic() - start)
    except httpx.HTTPError as e:
        return RequestResult(0, time.monotonic() - start, error=str(e))


async def run_burst(
    base_url: str,
    requests: list[list[str]],
    model: str = "en",
    timeout: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> list[RequestResult]:
    """Fire all `requests` (one text-batch each) concurrently; wait for all to finish.

    This is the N-concurrent burst BP-179 §2 requires for measuring
    per_request_burst_peak: every request is submitted before any completes.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=timeout)
    try:
        return list(
            await asyncio.gather(
                *(_post_embed(client, base_url, texts, model) for texts in requests)
            )
        )
    finally:
        if owns_client:
            await client.aclose()


@dataclass
class CallerStats:
    caller_id: int
    requests_sent: int = 0
    results: list[RequestResult] = field(default_factory=list)


async def _caller_loop(
    caller_id: int,
    base_url: str,
    payload_fn: Callable[[], list[str]],
    model: str,
    stop_at: float,
    client: httpx.AsyncClient,
    jitter_seconds: tuple[float, float],
) -> CallerStats:
    stats = CallerStats(caller_id=caller_id)
    rng = random.Random(caller_id)
    while time.monotonic() < stop_at:
        texts = payload_fn()
        result = await _post_embed(client, base_url, texts, model)
        stats.requests_sent += 1
        stats.results.append(result)
        await asyncio.sleep(rng.uniform(*jitter_seconds))
    return stats


async def run_soak_callers(
    base_url: str,
    n_callers: int,
    duration_seconds: float,
    payload_fn: Callable[[], list[str]],
    model: str = "en",
    timeout: float = 60.0,
    jitter_seconds: tuple[float, float] = (0.05, 0.5),
    transport: httpx.BaseTransport | None = None,
) -> list[CallerStats]:
    """Run `n_callers` independent async callers concurrently for `duration_seconds`.

    Each caller is its own loop with jittered inter-request timing — genuine
    multi-caller concurrency (BP-179 §4), not one serialized loop. `n_callers`
    should be set >= the envelope's concurrency ceiling plus waiters so the
    backpressure queue is genuinely exercised. `transport` lets tests inject an
    `httpx.MockTransport` so this runs fully offline.
    """
    stop_at = time.monotonic() + duration_seconds
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        return list(
            await asyncio.gather(
                *(
                    _caller_loop(
                        i, base_url, payload_fn, model, stop_at, client, jitter_seconds
                    )
                    for i in range(n_callers)
                )
            )
        )
