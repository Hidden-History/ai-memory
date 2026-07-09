"""Unit tests for scripts/perf/embedding_capacity/load.py — async load generation.

Uses httpx.MockTransport so these run fully offline against a fake embedding
endpoint — no live service or Docker needed.
"""

import asyncio

import httpx
import pytest
from embedding_capacity import load

pytestmark = pytest.mark.asyncio


def _client_with_handler(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_run_burst_returns_one_result_per_request():
    async def handler(request):
        return httpx.Response(
            200, json={"embeddings": [[0.1]], "model": "en", "dimensions": 1}
        )

    client = _client_with_handler(handler)
    requests = [["text a"], ["text b"], ["text c"]]
    results = await load.run_burst("http://fake", requests, model="en", client=client)
    await client.aclose()

    assert len(results) == 3
    assert all(r.status_code == 200 for r in results)


async def test_run_burst_fires_all_requests_concurrently():
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def handler(request):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
        return httpx.Response(
            200, json={"embeddings": [], "model": "en", "dimensions": 1}
        )

    client = _client_with_handler(handler)
    requests = [["t"] for _ in range(5)]
    await load.run_burst("http://fake", requests, model="en", client=client)
    await client.aclose()

    # All 5 requests must be in flight simultaneously — a serialized loop would
    # peak at max_active == 1, which is exactly the under-stress trap BP-179 §4
    # warns against for the measure/ramp burst.
    assert max_active == 5


async def test_run_burst_records_error_on_transport_failure():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    client = _client_with_handler(handler)
    results = await load.run_burst("http://fake", [["t"]], model="en", client=client)
    await client.aclose()

    assert results[0].status_code == 0
    assert results[0].error is not None


async def test_run_soak_callers_each_caller_sends_multiple_requests():
    call_count = 0

    async def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200, json={"embeddings": [], "model": "en", "dimensions": 1}
        )

    stats = await load.run_soak_callers(
        "http://fake",
        n_callers=3,
        duration_seconds=0.2,
        payload_fn=lambda: ["t"],
        transport=httpx.MockTransport(handler),
        jitter_seconds=(0.01, 0.02),
    )

    assert len(stats) == 3
    assert all(s.requests_sent >= 1 for s in stats)
    assert sum(s.requests_sent for s in stats) == call_count


async def test_run_soak_callers_stops_at_duration():
    async def handler(request):
        return httpx.Response(
            200, json={"embeddings": [], "model": "en", "dimensions": 1}
        )

    start = asyncio.get_event_loop().time()
    await load.run_soak_callers(
        "http://fake",
        n_callers=2,
        duration_seconds=0.15,
        payload_fn=lambda: ["t"],
        transport=httpx.MockTransport(handler),
        jitter_seconds=(0.01, 0.02),
    )
    elapsed = asyncio.get_event_loop().time() - start

    # Loop exits once the stop deadline passes, not indefinitely.
    assert elapsed < 1.0
