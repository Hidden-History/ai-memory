"""Service-side resilience tests for the embedding FastAPI app (TD-670).

Verifies the embedding service stays up and bounded under concurrent + large embed
load:

- a single faulty/oversized request is isolated to an HTTP 503 — the worker never
  dies and keeps serving other requests;
- simultaneous model inference never exceeds the configured concurrency cap (the
  peak-memory / shared-model-access guard that addresses the suspected clean-exit
  trigger).

Runs fully offline: the real fastembed/ONNX models are replaced with an in-process
stub, so there are no model downloads, no Docker, and no shared-Qdrant access.
"""

import asyncio
import importlib.util
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

import httpx
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

_MAIN_PATH = Path(__file__).resolve().parents[1] / "docker" / "embedding" / "main.py"


class _ConcurrencyTracker:
    """Records the peak number of stub inferences running simultaneously."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def reset(self):
        with self.lock:
            self.active = 0
            self.max_active = 0

    def enter(self):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)

    def exit(self):
        with self.lock:
            self.active -= 1


_tracker = _ConcurrencyTracker()


class _StubDenseModel:
    """Stand-in for fastembed.TextEmbedding with a measurable inference window."""

    def __init__(self, name="stub", delay=0.05, **kwargs):
        # **kwargs tolerates constructor args the service passes (e.g. threads=).
        self.name = name
        self.delay = delay

    def embed(self, texts):
        _tracker.enter()
        try:
            time.sleep(self.delay)  # hold the window open so overlap is observable
            return [np.full(768, 0.1, dtype=np.float32) for _ in texts]
        finally:
            _tracker.exit()


class _StubSparseModel:
    """Stand-in for fastembed.SparseTextEmbedding."""

    def __init__(self, name="stub-bm25", **kwargs):
        # **kwargs tolerates constructor args the service passes (e.g. threads=).
        self.name = name

    def embed(self, texts):
        results = []
        for _ in texts:
            result = type("SparseResult", (), {})()
            result.indices = np.array([1, 2, 3])
            result.values = np.array([0.5, 0.5, 0.5], dtype=np.float32)
            results.append(result)
        return results


class _StubLateModel:
    """Stand-in for fastembed.LateInteractionTextEmbedding.

    Late interaction (ColBERT) yields one *2D* array per text — (n_tokens, dim) token
    vectors — not a single flat vector, so the stub must mirror that shape to match
    ``EmbedLateResponse``.
    """

    def __init__(self, name="stub-colbert", n_tokens=4, **kwargs):
        # **kwargs tolerates constructor args the service passes (e.g. threads=).
        self.name = name
        self.n_tokens = n_tokens

    def embed(self, texts):
        return [np.full((self.n_tokens, 768), 0.1, dtype=np.float32) for _ in texts]


class _RaisingModel:
    """Model whose inference always fails — simulates a bad/oversized request."""

    def embed(self, texts):
        raise RuntimeError("simulated inference failure")


def _install_fake_fastembed():
    """Inject a stub ``fastembed`` so the service imports without the real models."""
    module = ModuleType("fastembed")
    module.TextEmbedding = _StubDenseModel
    module.SparseTextEmbedding = _StubSparseModel
    module.LateInteractionTextEmbedding = _StubLateModel
    sys.modules["fastembed"] = module


@pytest.fixture(autouse=True)
def _restore_global_state():
    """Keep the injected ``fastembed`` stub and EMBEDDING_* env from leaking.

    Each test installs a stub module and sets EMBEDDING_* env vars; without cleanup
    those would persist past this module and pollute unrelated tests.
    """
    module_keys = ("fastembed", "embedding_main_under_test")
    env_keys = (
        "EMBEDDING_MAX_CONCURRENCY",
        "EMBEDDING_ACQUIRE_TIMEOUT",
        "EMBEDDING_MAX_BATCH_TEXTS",
        "EMBEDDING_MAX_INPUT_CHARS",
        "EMBEDDING_MAX_TEXT_CHARS",
        "EMBEDDING_MAX_WAITERS",
        "EMBEDDING_RETRY_AFTER",
        "EMBEDDING_INFERENCE_THREADS",
        "EMBEDDING_SAFE_INFLIGHT_TEXTS",
        "EMBEDDING_SAFE_INFLIGHT_CHARS",
        "EMBEDDING_MEMORY_HIGH_RATIO",
        "EMBEDDING_MEMORY_OK_RATIO",
    )
    saved_modules = {k: sys.modules.get(k) for k in module_keys}
    saved_env = {k: os.environ.get(k) for k in env_keys}
    try:
        yield
    finally:
        for k, v in saved_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _load_service(max_concurrency, acquire_timeout=None):
    """Import a fresh copy of the embedding service with the given concurrency cap."""
    _install_fake_fastembed()
    os.environ["EMBEDDING_MAX_CONCURRENCY"] = str(max_concurrency)
    if acquire_timeout is not None:
        os.environ["EMBEDDING_ACQUIRE_TIMEOUT"] = str(acquire_timeout)
    sys.modules.pop("embedding_main_under_test", None)
    spec = importlib.util.spec_from_file_location(
        "embedding_main_under_test", _MAIN_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_shaped_batch(count=8):
    """A batch of realistic prose chunks (~2KB each), not toy strings."""
    paragraph = (
        "The embedding service must remain available while persisting memory. "
        "Each capture carries multi-paragraph prose describing a decision, a code "
        "pattern, or a convention that future sessions will need to retrieve. "
    ) * 12
    return [f"chunk {i}: {paragraph}" for i in range(count)]


def _backpressure_count(service, action):
    """Read the embedding_backpressure_total counter child for a given action.

    The metric is a process-global collector reused across module reloads, so callers
    compare *deltas* around an action rather than absolute values.
    """
    return service.embedding_backpressure_total.labels(action=action)._value.get()


def test_concurrent_inference_never_exceeds_cap():
    """Simultaneous inference must stay at or below EMBEDDING_MAX_CONCURRENCY."""
    cap = 3
    service = _load_service(cap)
    _tracker.reset()
    request_cls = service.EmbedDenseRequest
    texts = _production_shaped_batch(count=4)

    async def _drive():
        async def call():
            return await service.embed_dense(request_cls(texts=list(texts), model="en"))

        return await asyncio.gather(*[call() for _ in range(12)])

    results = asyncio.run(_drive())

    assert all(len(r.embeddings) == len(texts) for r in results)
    # Core guard: the semaphore + bounded executor never let more than `cap` run at once.
    assert _tracker.max_active <= cap
    # Sanity: genuine concurrency occurred, so the bound was actually exercised.
    assert _tracker.max_active >= 2


def test_faulty_request_returns_503_and_service_survives():
    """A failing inference is isolated to a 503; the worker keeps serving."""
    service = _load_service(4)
    client = TestClient(service.app)

    healthy = client.post("/embed", json={"texts": ["hello world"]})
    assert healthy.status_code == 200

    original = service.MODEL_REGISTRY["en"]
    service.MODEL_REGISTRY["en"] = _RaisingModel()
    try:
        bad = client.post("/embed", json={"texts": ["boom"]})
        # Clean 5xx, NOT a dropped connection / worker death.
        assert bad.status_code == 503
    finally:
        service.MODEL_REGISTRY["en"] = original

    # The service is still alive and serving after the failure.
    recovered = client.post("/embed", json={"texts": ["still alive"]})
    assert recovered.status_code == 200


def test_service_stable_under_concurrent_large_load():
    """Many concurrent large requests all receive a clean response — none dropped.

    Drives concurrency over the real HTTP path on a single event loop (httpx
    ASGITransport). The service-global asyncio.Semaphore is bound to the one uvicorn
    event loop in production; a multi-threaded TestClient would span several loops, which
    no single-worker deployment ever does.
    """
    service = _load_service(4)
    texts = _production_shaped_batch(count=8)

    async def _drive():
        transport = httpx.ASGITransport(app=service.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://embedding.test"
        ) as client:

            async def call():
                response = await client.post(
                    "/embed/dense", json={"texts": texts, "model": "en"}
                )
                return response.status_code

            return await asyncio.gather(*[call() for _ in range(32)])

    codes = asyncio.run(_drive())
    assert all(code == 200 for code in codes)


def test_oversized_batch_returns_413():
    """Too many texts in one request is rejected up front with HTTP 413."""
    service = _load_service(4)
    service.EMBEDDING_MAX_BATCH_TEXTS = 2
    client = TestClient(service.app)

    resp = client.post("/embed/dense", json={"texts": ["a", "b", "c"], "model": "en"})
    assert resp.status_code == 413


def test_oversized_input_chars_returns_413():
    """A single huge text exceeding the total-char budget is rejected with HTTP 413."""
    service = _load_service(4)
    service.EMBEDDING_MAX_INPUT_CHARS = 10
    client = TestClient(service.app)

    resp = client.post("/embed/dense", json={"texts": ["x" * 50], "model": "en"})
    assert resp.status_code == 413


def test_acquire_timeout_returns_503_when_no_slot():
    """When no inference slot frees within the timeout, the request is shed with a 503.

    Shedding is the last resort (the bounded queue cannot drain in time); it carries a
    Retry-After so the client retries rather than dropping the memory (Phase 3).
    """
    service = _load_service(1, acquire_timeout=0.2)

    async def _drive():
        # Seize the only inference slot so the next admission cannot acquire one.
        await service._inference_semaphore.acquire()
        before = _backpressure_count(service, "shed")
        try:
            with pytest.raises(HTTPException) as exc:
                await service.run_inference_async(lambda: [1])
            return exc.value, _backpressure_count(service, "shed") - before
        finally:
            service._inference_semaphore.release()

    err, shed_delta = asyncio.run(_drive())
    assert err.status_code == 503
    assert err.headers["Retry-After"] == str(service.EMBEDDING_RETRY_AFTER)
    assert shed_delta == 1


def test_late_embeddings_return_2d_shape():
    """ColBERT late interaction returns one 2D (n_tokens, dim) array per text."""
    service = _load_service(4)
    service.LATE_REGISTRY["colbert"] = _StubLateModel()
    client = TestClient(service.app)

    resp = client.post("/embed/late", json={"texts": ["token rich text"]})
    assert resp.status_code == 200
    token_vectors = resp.json()["embeddings"][0]["embeddings"]
    # 2D: a list of per-token vectors, each a 768-dim list.
    assert isinstance(token_vectors, list) and isinstance(token_vectors[0], list)
    assert len(token_vectors[0]) == 768


def test_backpressure_waits_without_shedding_under_designed_load():
    """Realistic-size multi-client load stays bounded, WAITS (not sheds), and drains.

    Phase-1 server-side resilience proof: concurrency far exceeds the slot cap but stays
    within the bounded wait-queue, so every request is admitted by *waiting*
    (backpressure) — none dropped, shed delta == 0, and inference never exceeds the cap
    (the bounded-memory proxy). The end-to-end client<->server retry proof (inject 503 ->
    client retries -> zero lost memories) lands in Phase 3.
    """
    cap = 4
    service = _load_service(cap)
    # Designed load: far more concurrent requests than slots, but within the wait-queue.
    service.EMBEDDING_MAX_WAITERS = 256
    _tracker.reset()
    request_cls = service.EmbedDenseRequest
    texts = _production_shaped_batch(count=8)
    concurrency = 40

    before_shed = _backpressure_count(service, "shed")
    before_waited = _backpressure_count(service, "waited")

    async def _drive():
        loop = asyncio.get_running_loop()
        all_slots_held = asyncio.Event()
        release_threads = threading.Event()

        def _on_all_held():
            # Barrier action: called in a thread once all cap threads arrive.
            loop.call_soon_threadsafe(all_slots_held.set)

        barrier = threading.Barrier(cap, action=_on_all_held, timeout=10)

        class _GatedModel:
            """Stub that parks all cap inference threads at a barrier before releasing.

            When all cap threads are simultaneously inside embed() the asyncio event loop
            is notified (all_slots_held). Threads then hold at release_threads until the
            asyncio side has let rest_tasks observe locked()==True. This removes the
            scheduling-dependent saturation window that caused the 3.11 failure.
            """

            name = "gated-stub"

            def embed(self, embed_texts):
                _tracker.enter()
                try:
                    barrier.wait()  # park until all cap threads arrive simultaneously
                    release_threads.wait(timeout=10)  # hold until asyncio says go
                    return [np.full(768, 0.1, dtype=np.float32) for _ in embed_texts]
                finally:
                    _tracker.exit()

        service.MODEL_REGISTRY["en"] = _GatedModel()

        async def call():
            return await service.embed_dense(request_cls(texts=list(texts), model="en"))

        # Phase 1: fill all cap slots; barrier action sets all_slots_held once all cap
        # threads are simultaneously inside embed() (semaphore fully drained).
        fill_tasks = [asyncio.create_task(call()) for _ in range(cap)]
        await all_slots_held.wait()

        # Phase 2: rest admissions all see locked()==True and increment "waited".
        rest_tasks = [asyncio.create_task(call()) for _ in range(concurrency - cap)]

        # One event-loop cycle: rest_tasks all run to their first await (past the
        # locked() check) before _drive resumes — deterministic on 3.10/3.11/3.12.
        await asyncio.sleep(0)

        # Release the threads; they return, freeing slots for rest_tasks to drain.
        release_threads.set()

        return await asyncio.gather(*fill_tasks, *rest_tasks)

    results = asyncio.run(_drive())

    # No dropped embed: every request returned a full set of vectors.
    assert len(results) == concurrency
    assert all(len(r.embeddings) == len(texts) for r in results)
    # Memory stayed bounded: inference never exceeded the slot cap (peak-memory proxy).
    assert _tracker.max_active <= cap
    # And the cap was actually exercised under real concurrency (not a vacuous bound).
    assert _tracker.max_active >= 2
    # Backpressure engaged (callers were made to wait) but NOTHING was shed.
    assert _backpressure_count(service, "shed") - before_shed == 0
    assert _backpressure_count(service, "waited") - before_waited > 0


# --- BUG-326: proactive in-flight-work admission envelope ---


def test_admission_envelope_sheds_over_envelope_concurrent_work():
    """Once work is in flight, a request that would push the concurrent in-flight work
    over EMBEDDING_SAFE_INFLIGHT_TEXTS is shed (503 + Retry-After); a request that fits is
    admitted (BUG-326). The semaphore cap is not the binding constraint here — the
    work-envelope is.
    """
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 40

    async def _drive():
        gate = threading.Event()

        def _blocking_op():
            gate.wait(timeout=10)  # hold the slot so _inflight_work stays at 30
            return ["held"]

        # Hold one in-flight request of 30 work-units; wait until it is counted.
        holder = asyncio.create_task(
            service.run_inference_async(_blocking_op, work_units=30)
        )
        while service._inflight_work < 30:
            await asyncio.sleep(0)

        # Over-envelope: 30 + 20 = 50 > 40 -> shed.
        before_shed = _backpressure_count(service, "shed")
        with pytest.raises(HTTPException) as over:
            await service.run_inference_async(lambda: ["x"], work_units=20)
        shed_delta = _backpressure_count(service, "shed") - before_shed

        # Under-envelope: 30 + 10 = 40, not over -> admitted.
        fit = await service.run_inference_async(lambda: ["y"], work_units=10)

        gate.set()
        await holder
        # BUG-327: all in-flight work unwinds to zero — neither the shed nor the
        # admitted requests leak a work-unit (the slot release is callback-driven, so
        # yield until the threadsafe release has run).
        for _ in range(1000):
            if service._inflight_work == 0:
                break
            await asyncio.sleep(0)
        assert service._inflight_work == 0
        return over.value, shed_delta, fit

    err, shed_delta, fit = asyncio.run(_drive())
    assert err.status_code == 503
    assert err.detail == "embedding_admission_over_envelope"
    assert err.headers["Retry-After"] == str(service.EMBEDDING_RETRY_AFTER)
    assert shed_delta == 1
    assert fit == ["y"]


def test_admission_envelope_admits_lone_request_within_envelope():
    """The lone-request ADMIT (deadlock prevention) is preserved for batches <= the
    envelope: an idle request whose work_units fits is admitted (BUG-326/327).
    """
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 40

    async def _drive():
        # 40 == envelope, service idle -> admitted (not shed, not 413).
        return await service.run_inference_async(lambda: ["solo"], work_units=40)

    assert asyncio.run(_drive()) == ["solo"]


def test_lone_request_over_envelope_returns_permanent_413():
    """BUG-327 root fix: a LONE request whose own batch exceeds the envelope is rejected
    with a PERMANENT 413 (not a retryable 503), even when the service is idle — the
    belt-and-suspenders behind the now-sub-batching clients. No slot/work is consumed.
    """
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 40

    async def _drive():
        before_inflight_work = service._inflight_work
        with pytest.raises(HTTPException) as exc:
            # 100 > 40 envelope, idle -> permanent 413 (the BUG-326 lone-any-size ADMIT is
            # intentionally superseded for over-envelope batches).
            await service.run_inference_async(lambda: ["x"], work_units=100)
        # No Retry-After header: it is not retryable.
        assert "Retry-After" not in (exc.value.headers or {})
        # The reject happens before slot acquisition -> no work counted, slot free.
        assert service._inflight_work == before_inflight_work == 0
        assert not service._inference_semaphore.locked()
        return exc.value

    err = asyncio.run(_drive())
    assert err.status_code == 413


def test_subbatched_legit_traffic_never_413s():
    """A stream of requests each <= the envelope (the contract clients now honor) is never
    413'd — proving the belt-and-suspenders never fires on legitimate sub-batched traffic.
    """
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 40

    async def _drive():
        results = []
        for size in (1, 40, 12, 40, 7):  # all <= envelope
            results.append(
                await service.run_inference_async(lambda: ["ok"], work_units=size)
            )
        return results

    assert asyncio.run(_drive()) == [["ok"]] * 5


def test_admission_envelope_enforced_on_http_path_with_production_batches():
    """End-to-end on the real /embed/dense path with production-shaped (~2KB/text)
    batches: while a 30-text request is in flight, a concurrent 20-text request (30 + 20
    = 50 > 40 envelope) is shed with the over-envelope 503. Proves work_units is wired
    from the actual request batch size (BUG-326).
    """
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 40

    async def _drive():
        gate = threading.Event()
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()

        class _GatedModel:
            name = "gated-stub"

            def embed(self, embed_texts):
                loop.call_soon_threadsafe(entered.set)
                gate.wait(timeout=10)  # hold the slot while the second request arrives
                return [np.full(768, 0.1, dtype=np.float32) for _ in embed_texts]

        service.MODEL_REGISTRY["en"] = _GatedModel()

        transport = httpx.ASGITransport(app=service.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://embedding.test"
        ) as client:
            held = _production_shaped_batch(count=30)  # 30 in-flight work-units
            holder = asyncio.create_task(
                client.post("/embed/dense", json={"texts": held, "model": "en"})
            )
            await entered.wait()  # the 30-text request is now in flight (counted)

            over = await client.post(
                "/embed/dense",
                json={"texts": _production_shaped_batch(count=20), "model": "en"},
            )

            gate.set()
            holder_resp = await holder
            # BUG-327: in-flight work fully unwinds after the e2e exchange.
            for _ in range(1000):
                if service._inflight_work == 0:
                    break
                await asyncio.sleep(0)
            assert service._inflight_work == 0
            return over.status_code, over.json().get("detail"), holder_resp.status_code

    status, detail, holder_status = asyncio.run(_drive())
    assert status == 503
    assert detail == "embedding_admission_over_envelope"
    assert holder_status == 200


def test_inflight_envelope_default_matches_client_default():
    """BUG-327: EMBEDDING_SAFE_INFLIGHT_TEXTS (embedding service, docker/embedding/main.py)
    and _embedding_inflight_envelope() (storage client, src/memory/storage.py) are separate
    deploy units that cannot share a runtime import, so their DEFAULTS must be kept in
    lockstep by hand. Fail loudly here if one is re-pegged without the other — otherwise the
    envelope contract breaks silently (clients would sub-batch to a different size than the
    server enforces).
    """
    os.environ.pop("EMBEDDING_SAFE_INFLIGHT_TEXTS", None)
    service = _load_service(4)
    from src.memory.storage import _embedding_inflight_envelope

    client_default = _embedding_inflight_envelope()
    assert client_default == service.EMBEDDING_SAFE_INFLIGHT_TEXTS


def test_over_envelope_batch_returns_permanent_413_on_http_path():
    """End-to-end on the real /embed/dense ASGI path: a single batch larger than the
    in-flight-work envelope earns a PERMANENT 413 (no Retry-After), proving the
    work_units=len(texts) contract and the 413 gate are wired at the endpoint — not only
    via a direct run_inference_async call. The batch (50) stays well under
    EMBEDDING_MAX_BATCH_TEXTS (256), so the envelope 413 (not the payload-limit 413) is the
    one exercised.
    """
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 40

    async def _drive():
        transport = httpx.ASGITransport(app=service.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://embedding.test"
        ) as client:
            resp = await client.post(
                "/embed/dense",
                json={"texts": _production_shaped_batch(count=50), "model": "en"},
            )
            return resp.status_code, resp.json().get("detail"), dict(resp.headers)

    status, detail, headers = asyncio.run(_drive())
    assert status == 413
    assert "memory envelope" in detail  # envelope gate, not the payload-limit guard
    assert "retry-after" not in {k.lower() for k in headers}  # permanent, not retryable


def test_over_envelope_413_is_endpoint_agnostic():
    """BUG-327: the over-envelope 413 is a server-wide gate (it lives in
    run_inference_async), so it fires identically on a NON-dense endpoint. Drives the real
    /embed/sparse ASGI path (BM25, loaded by default — no COLBERT needed) with an
    over-envelope batch and asserts the same permanent 413.
    """
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 40

    async def _drive():
        transport = httpx.ASGITransport(app=service.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://embedding.test"
        ) as client:
            resp = await client.post(
                "/embed/sparse",
                json={"texts": _production_shaped_batch(count=50)},
            )
            return resp.status_code, dict(resp.headers)

    status, headers = asyncio.run(_drive())
    assert status == 413
    assert "retry-after" not in {k.lower() for k in headers}


# --- TD-795: single-request per-text cap ---


def test_oversized_single_text_returns_413():
    """TD-795: a lone text exceeding EMBEDDING_MAX_TEXT_CHARS is rejected with 413, even
    when the batch count and total-char budgets would pass — the super-linear per-text
    memory driver is capped independently of the total-chars bound."""
    service = _load_service(4)
    service.EMBEDDING_MAX_TEXT_CHARS = 10
    service.EMBEDDING_MAX_INPUT_CHARS = (
        10_000  # total budget is NOT the binding limit here
    )
    client = TestClient(service.app)

    resp = client.post("/embed/dense", json={"texts": ["x" * 50], "model": "en"})
    assert resp.status_code == 413
    assert "per text" in resp.json()["detail"]


def test_per_text_cap_fires_before_total_char_cap():
    """A batch whose TOTAL chars fit but which contains one over-cap text is rejected on the
    per-text cap (TD-795) — the distribution matters, not just the sum."""
    service = _load_service(4)
    service.EMBEDDING_MAX_TEXT_CHARS = 10
    service.EMBEDDING_MAX_INPUT_CHARS = 10_000  # sum (2 + 50) is well under this
    client = TestClient(service.app)

    resp = client.post("/embed/dense", json={"texts": ["ok", "x" * 50], "model": "en"})
    assert resp.status_code == 413
    assert "Text 1" in resp.json()["detail"]  # the second text is the offender


# --- TD-783: byte/superlinear-aware in-flight admission envelope ---


def test_char_envelope_sheds_over_char_budget_concurrent_work():
    """TD-783: once work is in flight, a request that would push the concurrent in-flight
    CHAR total over EMBEDDING_SAFE_INFLIGHT_CHARS is shed (503 + Retry-After), while one
    that fits is admitted. The count envelope is NOT the binding constraint here (work_units
    stay tiny) — the byte budget is."""
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_CHARS = 40
    # Keep the count envelope non-binding so only the char gate can fire.
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 48

    async def _drive():
        gate = threading.Event()

        def _blocking_op():
            gate.wait(timeout=10)  # hold the slot so _inflight_chars stays at 30
            return ["held"]

        # Hold one in-flight request of 30 chars (1 text); wait until it is counted.
        holder = asyncio.create_task(
            service.run_inference_async(_blocking_op, work_units=1, work_chars=30)
        )
        while service._inflight_chars < 30:
            await asyncio.sleep(0)

        # Over-char-envelope: 30 + 20 = 50 > 40 -> shed (count is 1 + 1 = 2 << 48).
        before_shed = _backpressure_count(service, "shed")
        with pytest.raises(HTTPException) as over:
            await service.run_inference_async(
                lambda: ["x"], work_units=1, work_chars=20
            )
        shed_delta = _backpressure_count(service, "shed") - before_shed

        # Under-envelope: 30 + 10 = 40, not over -> admitted.
        fit = await service.run_inference_async(
            lambda: ["y"], work_units=1, work_chars=10
        )

        gate.set()
        await holder
        # All in-flight char/work bookkeeping unwinds to zero — no leak.
        for _ in range(1000):
            if service._inflight_chars == 0 and service._inflight_work == 0:
                break
            await asyncio.sleep(0)
        assert service._inflight_chars == 0
        assert service._inflight_work == 0
        return over.value, shed_delta, fit

    err, shed_delta, fit = asyncio.run(_drive())
    assert err.status_code == 503
    assert err.detail == "embedding_admission_over_char_envelope"
    assert err.headers["Retry-After"] == str(service.EMBEDDING_RETRY_AFTER)
    assert shed_delta == 1
    assert fit == ["y"]


def test_char_envelope_admits_lone_request_at_budget():
    """The lone-request ADMIT (deadlock prevention) holds for the char gate: an idle request
    whose chars equal the envelope is admitted, never starved (TD-783)."""
    service = _load_service(4)
    service.EMBEDDING_SAFE_INFLIGHT_CHARS = 40

    async def _drive():
        # 40 == envelope, service idle -> admitted.
        return await service.run_inference_async(
            lambda: ["solo"], work_units=1, work_chars=40
        )

    assert asyncio.run(_drive()) == ["solo"]


def test_char_envelope_enforced_on_http_path_with_large_texts():
    """End-to-end on the real /embed/dense path: while a large-text request is in flight, a
    concurrent large-text request that would breach EMBEDDING_SAFE_INFLIGHT_CHARS is shed
    with the byte-envelope 503 — proving work_chars is wired from the real request size
    (TD-783). Batches stay well under the count envelope, so the CHAR gate is the one that
    fires."""
    service = _load_service(4)
    # ~2 KB/text x 8 texts = ~16 KB in flight; set the char budget just above one such
    # request so a second concurrent one breaches it. Count stays 8 << 48.
    one_request_chars = sum(len(t) for t in _production_shaped_batch(count=8))
    service.EMBEDDING_SAFE_INFLIGHT_CHARS = one_request_chars + 100
    service.EMBEDDING_SAFE_INFLIGHT_TEXTS = 48

    async def _drive():
        gate = threading.Event()
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()

        class _GatedModel:
            name = "gated-stub"

            def embed(self, embed_texts):
                loop.call_soon_threadsafe(entered.set)
                gate.wait(timeout=10)  # hold the slot while the second request arrives
                return [np.full(768, 0.1, dtype=np.float32) for _ in embed_texts]

        service.MODEL_REGISTRY["en"] = _GatedModel()
        texts = _production_shaped_batch(count=8)

        transport = httpx.ASGITransport(app=service.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://embedding.test"
        ) as client:
            holder = asyncio.create_task(
                client.post("/embed/dense", json={"texts": texts, "model": "en"})
            )
            await entered.wait()  # first request in flight (chars counted)

            over = await client.post(
                "/embed/dense", json={"texts": texts, "model": "en"}
            )

            gate.set()
            holder_resp = await holder
            for _ in range(1000):
                if service._inflight_chars == 0:
                    break
                await asyncio.sleep(0)
            assert service._inflight_chars == 0
            return over.status_code, over.json().get("detail"), holder_resp.status_code

    status, detail, holder_status = asyncio.run(_drive())
    assert status == 503
    assert detail == "embedding_admission_over_char_envelope"
    assert holder_status == 200


# --- TD-793/794/795: config wiring (threads, memory-high ratio, byte caps) ---


def test_config_defaults_wired():
    """The Fix C defaults are wired into the module and internally consistent (TD-793/794/
    795): threads=4, the memory-high/ok hysteresis band lowered, and the byte caps sized so
    a lone request can never exceed the concurrent envelope."""
    for key in (
        "EMBEDDING_INFERENCE_THREADS",
        "EMBEDDING_MEMORY_HIGH_RATIO",
        "EMBEDDING_MEMORY_OK_RATIO",
        "EMBEDDING_MAX_INPUT_CHARS",
        "EMBEDDING_MAX_TEXT_CHARS",
        "EMBEDDING_SAFE_INFLIGHT_CHARS",
    ):
        os.environ.pop(key, None)
    service = _load_service(4)

    # TD-794: measured thread sweet-spot.
    assert service.EMBEDDING_INFERENCE_THREADS == 4
    # TD-793: lowered memory-high band, hysteresis gap preserved.
    assert service.EMBEDDING_MEMORY_HIGH_RATIO == 0.80
    assert service.EMBEDDING_MEMORY_OK_RATIO == 0.65
    assert service.EMBEDDING_MEMORY_OK_RATIO < service.EMBEDDING_MEMORY_HIGH_RATIO
    # TD-795: byte caps.
    assert service.EMBEDDING_MAX_INPUT_CHARS == 200_000
    assert service.EMBEDDING_MAX_TEXT_CHARS == 8_192
    assert service.EMBEDDING_SAFE_INFLIGHT_CHARS == 200_000
    # Sizing invariant: a lone (always-admitted) request cannot exceed the concurrent
    # char envelope.
    assert service.EMBEDDING_MAX_INPUT_CHARS <= service.EMBEDDING_SAFE_INFLIGHT_CHARS


def test_thread_config_aligned_across_compose_and_env_example():
    """TD-794: OMP_NUM_THREADS and EMBEDDING_INFERENCE_THREADS must both default to 4 and
    stay aligned in BOTH docker-compose.yml and docker/.env.example (a non-OpenMP onnxruntime
    build makes the two levers independent, so a drift between them silently mis-sizes the
    pool)."""
    repo_root = Path(__file__).resolve().parents[1]
    compose = (repo_root / "docker" / "docker-compose.yml").read_text()
    env_example = (repo_root / "docker" / ".env.example").read_text()

    # compose uses ${VAR:-default}; .env.example uses VAR=value.
    assert "OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}" in compose
    assert "EMBEDDING_INFERENCE_THREADS=${EMBEDDING_INFERENCE_THREADS:-4}" in compose
    assert re.search(r"^OMP_NUM_THREADS=4$", env_example, re.MULTILINE)
    assert re.search(r"^EMBEDDING_INFERENCE_THREADS=4$", env_example, re.MULTILINE)


def test_new_env_keys_mirrored_in_env_example_and_compose():
    """Every new EMBEDDING_* key must appear in BOTH docker-compose.yml and
    docker/.env.example (env-key parity — a compose key absent from .env.example drifts the
    operator's real .env)."""
    repo_root = Path(__file__).resolve().parents[1]
    compose = (repo_root / "docker" / "docker-compose.yml").read_text()
    env_example = (repo_root / "docker" / ".env.example").read_text()
    for key in (
        "EMBEDDING_MAX_TEXT_CHARS",
        "EMBEDDING_SAFE_INFLIGHT_CHARS",
    ):
        assert key in compose, f"{key} missing from docker-compose.yml"
        assert re.search(
            rf"^{key}=", env_example, re.MULTILINE
        ), f"{key} missing from docker/.env.example"


# --- WI-10 acceptance proofs at PRODUCTION defaults (DEC-PM390 amended DONE-WHEN) ---


def test_over_cap_request_rejected_cleanly_at_default_caps():
    """(a) At the shipped defaults (no cap overrides), an over-cap single request is
    rejected with a clean 413 — NOT a crash — and the service keeps serving. Covers both
    the per-text cap (a >8192-char text) and the total-chars cap (a ~1M-char batch, the
    old limit that could reach ~28 GiB)."""
    service = _load_service(
        4
    )  # ships EMBEDDING_MAX_TEXT_CHARS=8192, MAX_INPUT_CHARS=200000
    client = TestClient(service.app)

    # A single text over the 8 KB per-text cap -> clean 413.
    over_text = client.post("/embed/dense", json={"texts": ["x" * 8193], "model": "en"})
    assert over_text.status_code == 413
    assert "per text" in over_text.json()["detail"]

    # The old 1,000,000-char total (as in-cap 8000-char texts) -> clean 413 on the total
    # budget (125 x 8000 = 1,000,000 > 200,000; each text <= 8192 so the per-text cap passes
    # and the TOTAL cap is the one exercised).
    big_batch = ["x" * 8000] * 125
    over_total = client.post("/embed/dense", json={"texts": big_batch, "model": "en"})
    assert over_total.status_code == 413
    assert "Input too large" in over_total.json()["detail"]

    # Service survived both rejections and still serves a normal request.
    ok = client.post("/embed/dense", json={"texts": ["still alive"], "model": "en"})
    assert ok.status_code == 200


def test_kill_load_sheds_to_envelope_at_default():
    """(b) The 48x8 KB kill-load (~393,216 concurrent in-flight chars, which OOM'd the
    10 GiB cap) can no longer be admitted: at the shipped EMBEDDING_SAFE_INFLIGHT_CHARS
    default, once ~200 K chars are in flight, further work SHEDS — in-flight never reaches
    393 K. Proven at the production default (no override)."""
    service = _load_service(4)
    assert (
        service.EMBEDDING_SAFE_INFLIGHT_CHARS == 200_000
    )  # shipped default, not overridden

    async def _drive():
        gate = threading.Event()

        def _blocking_op():
            gate.wait(
                timeout=10
            )  # hold the envelope full while the next request arrives
            return ["held"]

        # Fill the char envelope exactly (200 K chars, in-cap 8000-char texts, lone-admitted).
        held_chars = service.EMBEDDING_SAFE_INFLIGHT_CHARS
        holder = asyncio.create_task(
            service.run_inference_async(
                _blocking_op, work_units=1, work_chars=held_chars
            )
        )
        while service._inflight_chars < held_chars:
            await asyncio.sleep(0)

        # Any further concurrent work would push in-flight past 200 K toward the 393 K
        # kill-load -> shed (503), so in-flight is pinned at <= the envelope.
        before_shed = _backpressure_count(service, "shed")
        with pytest.raises(HTTPException) as over:
            await service.run_inference_async(
                lambda: ["x"], work_units=1, work_chars=8192
            )
        shed_delta = _backpressure_count(service, "shed") - before_shed
        peak_inflight = service._inflight_chars

        gate.set()
        await holder
        return over.value, shed_delta, peak_inflight

    err, shed_delta, peak_inflight = asyncio.run(_drive())
    assert err.status_code == 503
    assert err.detail == "embedding_admission_over_char_envelope"
    assert shed_delta == 1
    # In-flight never reached the 393 K kill-load — capped at the 200 K envelope.
    assert peak_inflight <= 200_000
    assert peak_inflight < 393_216


def test_computed_peak_under_cap_with_margin():
    """(c) Documented sizing invariant: warm base + the concurrent in-flight char budget,
    priced at the MEASURED per-char cost, stays under the 10 GiB cap with real margin.
    This encodes the envelope math so a future retune that breaks the memory budget fails
    loudly here."""
    service = _load_service(4)

    # Measured inputs (PM #390 X2/X4): 10 GiB cap, ~2.35 GiB warm base, 235 MiB per 8192-char
    # text. Per-text is capped at 8192 (EMBEDDING_MAX_TEXT_CHARS), so this per-char rate is
    # the worst case within the envelope — no O(L^2) extrapolation past the measured point.
    cap_gib = 10.0
    warm_base_gib = 2.35
    mib_per_8192_chars = 235.0
    assert service.EMBEDDING_MAX_TEXT_CHARS == 8192  # the anchor the rate is priced at
    mib_per_char = mib_per_8192_chars / service.EMBEDDING_MAX_TEXT_CHARS

    inflight_transient_gib = (
        service.EMBEDDING_SAFE_INFLIGHT_CHARS * mib_per_char / 1024.0
    )
    computed_peak_gib = warm_base_gib + inflight_transient_gib

    # ~7.95 GiB peak; assert it clears the cap with at least ~1.5 GiB of fragmentation
    # headroom (X2 overshot the cap by ~0.37 GiB, so the margin must comfortably exceed it).
    assert computed_peak_gib < cap_gib
    assert cap_gib - computed_peak_gib >= 1.5
    # And the lone-request ceiling cannot exceed the concurrent budget.
    assert service.EMBEDDING_MAX_INPUT_CHARS <= service.EMBEDDING_SAFE_INFLIGHT_CHARS


def _committed_memory_limit_gib(text):
    """Parse the EMBEDDING_MEMORY_LIMIT default (e.g. '10G') from a compose/.env file into
    GiB. Docker's 'G' suffix is GiB (1024^3)."""
    m = re.search(r"EMBEDDING_MEMORY_LIMIT(?:=|:-)(\d+)([GgMm])", text)
    assert m, "EMBEDDING_MEMORY_LIMIT default not found"
    value, unit = int(m.group(1)), m.group(2).upper()
    return value if unit == "G" else value / 1024.0


def test_envelope_consistent_with_committed_memory_limit():
    """Drift guard: the shipped EMBEDDING_MEMORY_LIMIT (the envelope's denominator) must
    equal the sizing basis in BOTH compose and .env.example, and the computed peak must fit
    under it with margin. Shipping a limit smaller than the envelope's basis is a latent OOM
    on a fresh install (base + budget >> limit) — this fails loudly if either drifts."""
    repo_root = Path(__file__).resolve().parents[1]
    compose = (repo_root / "docker" / "docker-compose.yml").read_text()
    env_example = (repo_root / "docker" / ".env.example").read_text()

    committed_compose = _committed_memory_limit_gib(compose)
    committed_env = _committed_memory_limit_gib(env_example)
    # No drift between the two files.
    assert committed_compose == committed_env
    committed_gib = committed_compose

    service = _load_service(4)
    mib_per_char = 235.0 / service.EMBEDDING_MAX_TEXT_CHARS
    peak_gib = 2.35 + service.EMBEDDING_SAFE_INFLIGHT_CHARS * mib_per_char / 1024.0

    # The envelope was sized against a 10 GiB basis; the committed limit must match it, and
    # the peak must clear it with fragmentation headroom.
    assert committed_gib == 10
    assert peak_gib < committed_gib
    assert committed_gib - peak_gib >= 1.5


# --- TD-795 friction 4: legitimate large texts are admitted, not false-rejected ---


def test_legit_max_size_text_admitted():
    """Friction 4: a text at the largest legitimate size is ADMITTED (not 413'd). The
    chunkers emit prose chunks <= 2048 chars and code chunks well under that; a text right
    at the 8192 per-text cap (>=3x the largest real chunk) must still pass."""
    service = _load_service(4)
    client = TestClient(service.app)

    # A realistic prose-sized chunk (~2 KB) — the actual production max — is admitted.
    prose = client.post("/embed/dense", json={"texts": ["p" * 2048], "model": "en"})
    assert prose.status_code == 200

    # A text exactly at the per-text cap boundary is admitted (cap is inclusive).
    at_cap = client.post(
        "/embed/dense",
        json={"texts": ["x" * service.EMBEDDING_MAX_TEXT_CHARS], "model": "en"},
    )
    assert at_cap.status_code == 200


def test_embed_chunked_large_document_split_is_admitted():
    """Friction 4: /embed/chunked receives a whole DOCUMENT (legitimately large) that it
    splits by offsets into in-cap chunks — the per-text cap must NOT false-reject the
    pre-split document. A 20 K-char document carved into 8 KB spans is embedded (200), while
    the no-offsets whole-document fallback still enforces the cap (a >cap whole-doc embed is
    the O(L^2) OOM vector and must be sent WITH offsets)."""
    service = _load_service(4)
    client = TestClient(service.app)

    big_doc = (
        "d" * 20_000
    )  # > EMBEDDING_MAX_TEXT_CHARS (8192), a legit document to split
    offsets = [[0, 8000], [8000, 16000], [16000, 20000]]  # each span <= 8192
    split = client.post(
        "/embed/chunked",
        json={"texts": [big_doc], "chunk_offsets": offsets, "late_chunking": True},
    )
    assert split.status_code == 200
    assert len(split.json()["embeddings"]) == len(offsets)

    # No-offsets fallback embeds the document WHOLE -> the per-text cap applies (protective).
    whole = client.post(
        "/embed/chunked", json={"texts": [big_doc], "chunk_offsets": []}
    )
    assert whole.status_code == 413
    assert "per text" in whole.json()["detail"]


# --- Phase 2: cgroup-v2 reader + memory-aware AIMD self-throttle ---


def _write_cgroup(
    base, current=None, mem_max=None, mem_high=None, events=None, psi=None
):
    """Materialize a fake cgroup-v2 memory dir for the reader under test."""
    base = Path(base)
    if current is not None:
        (base / "memory.current").write_text(str(current))
    if mem_max is not None:
        (base / "memory.max").write_text(str(mem_max))
    if mem_high is not None:
        (base / "memory.high").write_text(str(mem_high))
    if events is not None:
        (base / "memory.events").write_text(events)
    if psi is not None:
        (base / "memory.pressure").write_text(psi)


def test_read_cgroup_memory_parses_signals(tmp_path):
    """Reader parses current/limit/headroom/ratio/PSI and sums oom + oom_kill."""
    service = _load_service(4)
    _write_cgroup(
        tmp_path,
        current=2_000_000_000,
        mem_max=4_000_000_000,
        mem_high="max",  # unset -> falls back to memory.max as the threshold
        events="low 0\nhigh 5\nmax 2\noom 3\noom_kill 1\n",
        psi=(
            "some avg10=1.20 avg60=0.0 avg300=0.0 total=1\n"
            "full avg10=4.50 avg60=0.0 avg300=0.0 total=1\n"
        ),
    )
    sig = service.read_cgroup_memory(str(tmp_path))
    assert sig["current"] == 2_000_000_000
    assert sig["limit"] == 4_000_000_000
    assert sig["headroom"] == 2_000_000_000
    assert abs(sig["ratio"] - 0.5) < 1e-9
    assert sig["psi_full_avg10"] == 4.50
    assert sig["oom"] == 4
    assert sig["psi_available"] is True
    assert sig["ratio_available"] is True


def test_read_cgroup_memory_missing_files_degrade(tmp_path):
    """No cgroup files (non-cgroup-v2 / no-PSI host) -> all-None, both paths unavailable."""
    service = _load_service(4)
    sig = service.read_cgroup_memory(str(tmp_path))
    assert sig["current"] is None
    assert sig["limit"] is None
    assert sig["ratio"] is None
    assert sig["psi_full_avg10"] is None
    assert sig["psi_available"] is False
    assert sig["ratio_available"] is False
    assert sig["oom"] == 0


def test_decide_effective_limit_multiplicative_decrease_on_psi():
    service = _load_service(4)
    sig = {"psi_full_avg10": 50.0, "ratio": None}
    assert service._decide_effective_limit(4, sig) == 2
    assert service._decide_effective_limit(2, sig) == 1
    assert service._decide_effective_limit(1, sig) == 1  # floor at 1


def test_decide_effective_limit_multiplicative_decrease_on_ratio():
    service = _load_service(4)
    sig = {"psi_full_avg10": None, "ratio": 0.95}
    assert service._decide_effective_limit(4, sig) == 2


def test_decide_effective_limit_additive_increase_when_healthy():
    service = _load_service(4)
    sig = {"psi_full_avg10": 0.0, "ratio": 0.10}
    assert service._decide_effective_limit(2, sig) == 3
    assert service._decide_effective_limit(4, sig) == 4  # never above the ceiling


def test_decide_effective_limit_holds_without_signal():
    service = _load_service(4)
    sig = {"psi_full_avg10": None, "ratio": None}
    assert service._decide_effective_limit(3, sig) == 3  # never grow blind


def test_apply_effective_limit_parks_and_restores_permits():
    """Collapsing the effective limit parks permits; recovering unparks them."""
    service = _load_service(4)

    async def _drive():
        # ._value is the CPython-3.12 asyncio.Semaphore internal free-permit counter
        # (the container runs python:3.12-slim); we assert on it to witness that parking
        # actually removes/returns permits, not just that the bookkeeping ints changed.
        assert service._inference_semaphore._value == 4
        await service._apply_effective_limit(1)  # drain mode -> park 3
        assert service._effective_limit == 1
        assert service._inference_semaphore._value == 1
        await service._apply_effective_limit(4)  # recover -> unpark
        assert service._effective_limit == 4
        assert service._inference_semaphore._value == 4

    asyncio.run(_drive())


def test_pressure_decision_collapses_limit_and_counts_oom():
    """Under pressure the AIMD step halves the effective limit and counts OOM deltas."""
    service = _load_service(4)
    before_oom = service.embedding_oom_events_total._value.get()

    async def _drive():
        await service._apply_pressure_decision(
            {
                "current": 3_900_000_000,
                "limit": 4_000_000_000,
                "headroom": 100_000_000,
                "ratio": 0.975,
                "psi_full_avg10": 80.0,
                "oom": 2,
                "psi_available": True,
                "ratio_available": True,
            }
        )
        return service._effective_limit

    eff = asyncio.run(_drive())
    assert eff == 2
    assert service.embedding_oom_events_total._value.get() - before_oom == 2


def test_pressure_decision_does_not_recount_preexisting_ooms():
    """First-interval over-count guard: the OOM baseline that _lifespan seeds from the
    startup memory.events read is not re-counted as new on the next control tick."""
    service = _load_service(4)
    service._last_oom_total = 5  # as if startup observed 5 cumulative OOMs
    before_oom = service.embedding_oom_events_total._value.get()

    async def _drive():
        await service._apply_pressure_decision(
            {
                "current": None,
                "limit": None,
                "headroom": None,
                "ratio": None,
                "psi_full_avg10": None,
                "oom": 5,  # same cumulative total -> zero NEW OOMs
                "psi_available": False,
                "ratio_available": False,
            }
        )

    asyncio.run(_drive())
    assert service.embedding_oom_events_total._value.get() - before_oom == 0


# --- Cardinal end-to-end: real server shed (Phase 1) <-> real client retry (Phase 3) ---


def test_live_asgi_server_backpressure_then_client_retry_lands(monkeypatch):
    """THE integration proof: the REAL embedding app emits its own 503 + Retry-After
    under backpressure, and the REAL EmbeddingClient retries it so the memory lands —
    zero loss — composing Phase 1's shed with Phase 3's retry through the actual code on
    both sides (no mocks). TestClient is the sync->ASGI bridge that drives the real app.
    """
    from src.memory import embeddings as embeddings_mod
    from src.memory.config import MemoryConfig
    from src.memory.embeddings import EmbeddingClient

    # Real service app (stub models). A full wait-queue forces the real shed path.
    service = _load_service(1)
    service.EMBEDDING_MAX_WAITERS = 0  # queue full -> server sheds 503 + Retry-After
    service.EMBEDDING_RETRY_AFTER = 1  # the real header value the client will honor

    # Real client, driving the real app through TestClient (sync -> real ASGI app).
    client = EmbeddingClient(MemoryConfig())
    client.client = TestClient(service.app)
    client._max_retries = 3

    # Deterministic "transient backpressure": when the real client hits its retry-sleep
    # boundary, the pressure clears (a slot opens) — so the next attempt is admitted.
    # Hooking the client's own time.sleep ties the flip to the real retry, no timing race.
    # Note: patching the time module is process-global, so gate the flip to the client's
    # retry sleep (Retry-After == 1s) and ignore the stub model's short ~0.05s window.
    flips = {"n": 0}

    def fake_sleep(seconds):
        if seconds >= 0.5:
            flips["n"] += 1
            service.EMBEDDING_MAX_WAITERS = 64  # pressure cleared before the retry

    monkeypatch.setattr(embeddings_mod.time, "sleep", fake_sleep)

    result = client.embed(["a memory that must survive backpressure"], model="en")

    # The real server shed once, the real client retried once, and the memory landed.
    assert flips["n"] == 1
    assert len(result) == 1
    assert len(result[0]) == 768
    # TD-354 intact end-to-end: a real non-zero vector, never a degenerate placeholder.
    assert any(v != 0.0 for v in result[0])


# --- M1: exactly-once slot release on executor-thread completion, even under cancel ---


def test_cancelled_midinference_holds_slot_until_thread_completes():
    """M1: a request cancelled mid-inference (client disconnect) must NOT free its
    semaphore slot until the executor thread actually finishes.

    If the slot leaked on cancellation, a new request would over-admit while the worker
    thread is still running ``operation`` — growing the ThreadPoolExecutor's uncounted
    work queue past the memory bound. With a single slot the over-admit is directly
    observable: the next request is shed (503) while the cancelled inference is still in
    flight, then admitted once the thread completes (slot released exactly once).
    """
    service = _load_service(1, acquire_timeout=0.3)

    started = threading.Event()
    release = threading.Event()

    def blocking_op():
        started.set()
        release.wait(timeout=10)  # hold the inference open across the cancellation
        return [1]

    async def _drive():
        sem = service._inference_semaphore
        before_inflight = service.embedding_inflight._value.get()

        task = asyncio.create_task(service.run_inference_async(blocking_op))
        # Wait until the worker thread is actually inside the inference (slot held).
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 10)
        assert sem.locked()
        assert service.embedding_inflight._value.get() == before_inflight + 1

        # Client disconnect mid-inference.
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # CRITICAL (M1): the slot is still held — the worker thread has not completed, so
        # cancellation must not have released it.
        assert sem.locked(), "slot freed on cancel before the executor thread completed"
        assert service.embedding_inflight._value.get() == before_inflight + 1

        # No over-admit: a new request cannot acquire the (still-held) slot and is shed.
        with pytest.raises(HTTPException) as exc:
            await service.run_inference_async(lambda: [2])
        assert exc.value.status_code == 503

        # Let the worker thread finish; only now is the slot released — exactly once.
        release.set()
        for _ in range(200):
            if not sem.locked():
                break
            await asyncio.sleep(0.01)
        assert not sem.locked(), "slot not released after the executor thread completed"
        assert service.embedding_inflight._value.get() == before_inflight

        # The freed slot admits the next request normally; a double-release would have
        # corrupted the permit count, so a clean single free slot proves exactly-once.
        assert await service.run_inference_async(lambda: [3]) == [3]
        assert sem._value == 1

    asyncio.run(_drive())


def test_submit_failure_releases_slot_and_returns_503():
    """M1 regression: if the executor's submit() raises before the done-callback is
    registered (executor shutdown / BrokenThreadPool), the slot must be released exactly
    once and the error normalized to a 503 — not leaked under an unnormalized 500.

    With the slot anchored to the future's done-callback, a submit() that never returns a
    future would otherwise leave the acquired permit and the inflight gauge stranded
    forever. The release happens inline (no callback exists yet), so the next request must
    be admitted normally.
    """
    service = _load_service(1)

    def boom(_operation):
        raise RuntimeError("cannot schedule new futures after shutdown")

    async def _drive():
        sem = service._inference_semaphore
        before_inflight = service.embedding_inflight._value.get()

        service._inference_executor.submit = boom
        with pytest.raises(HTTPException) as exc:
            await service.run_inference_async(lambda: [1])

        # Slot released (not leaked), inflight back to baseline, 503 (not 500).
        assert exc.value.status_code == 503
        assert exc.value.headers["Retry-After"] == str(service.EMBEDDING_RETRY_AFTER)
        assert not sem.locked(), "slot leaked after submit() failure"
        assert sem._value == 1
        assert service.embedding_inflight._value.get() == before_inflight
        # BUG-327: the inline release on submit() failure also unwinds in-flight work
        # (incremented just before submit) back to zero — no work-unit leak.
        assert service._inflight_work == 0

    asyncio.run(_drive())


def test_max_waiters_floored_to_one(caplog):
    """L1: a configured EMBEDDING_MAX_WAITERS < 1 is floored to 1 (with a warning) so the
    admission check cannot shed every request even when a slot is free."""
    os.environ["EMBEDDING_MAX_WAITERS"] = "0"
    with caplog.at_level(logging.WARNING, logger="ai_memory.embedding"):
        service = _load_service(4)
    assert service.EMBEDDING_MAX_WAITERS == 1
    assert any(
        "embedding_max_waiters_floored" in r.getMessage() for r in caplog.records
    )


def test_blind_hold_at_one_logs_once_per_state_entry(caplog):
    """L7: when the AIMD effective limit is pinned at the floor of 1 with no pressure
    signal available, the throttled-blind state is logged ONCE per entry (on transition),
    not on every controller tick."""
    service = _load_service(4)
    no_signal = {
        "current": None,
        "limit": None,
        "headroom": None,
        "ratio": None,
        "psi_full_avg10": None,
        "oom": 0,
        "psi_available": False,
        "ratio_available": False,
    }

    async def _drive():
        # Pin the effective limit at the floor of 1, as a memory-pressure collapse would.
        await service._apply_effective_limit(1)
        with caplog.at_level(logging.WARNING, logger="ai_memory.embedding"):
            # First tick enters the blind-hold state -> logs once.
            await service._apply_pressure_decision(dict(no_signal))
            # Second tick is still in the state -> silent (no per-tick spam).
            await service._apply_pressure_decision(dict(no_signal))
        return [
            r
            for r in caplog.records
            if r.getMessage() == "embedding_effective_limit_held_blind"
        ]

    blind_logs = asyncio.run(_drive())
    assert len(blind_logs) == 1


# --- BUG-324: enable_cpu_mem_arena=False on both TextEmbedding constructors ---


def test_text_embedding_constructors_disable_cpu_mem_arena():
    """Both TextEmbedding constructors pass enable_cpu_mem_arena=False (BUG-324).

    Bypasses _load_service() so the spy TextEmbedding is not overwritten by
    _install_fake_fastembed() during module load.
    """
    call_kwargs = []

    class _SpyDenseModel(_StubDenseModel):
        def __init__(self, *args, **kwargs):
            call_kwargs.append(dict(kwargs))
            super().__init__(*args, **kwargs)

    spy_fastembed = ModuleType("fastembed")
    spy_fastembed.TextEmbedding = _SpyDenseModel
    spy_fastembed.SparseTextEmbedding = _StubSparseModel
    spy_fastembed.LateInteractionTextEmbedding = _StubLateModel
    sys.modules["fastembed"] = spy_fastembed

    os.environ["EMBEDDING_MAX_CONCURRENCY"] = "4"
    sys.modules.pop("embedding_main_under_test", None)
    spec = importlib.util.spec_from_file_location(
        "embedding_main_under_test", _MAIN_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # load_models() must call TextEmbedding for both "en" and "code" at startup.
    assert (
        len(call_kwargs) >= 2
    ), f"Expected ≥2 TextEmbedding calls, got {len(call_kwargs)}"
    for i, kwargs in enumerate(call_kwargs):
        assert (
            kwargs.get("enable_cpu_mem_arena") is False
        ), f"TextEmbedding call {i} must pass enable_cpu_mem_arena=False; got {kwargs}"
    # Confirm the module loaded cleanly (both registry keys present)
    assert "en" in module.MODEL_REGISTRY
    assert "code" in module.MODEL_REGISTRY


# --- TD-553: /health aliased-fallback detection ---


def test_health_both_models_loaded_returns_200():
    """Both models loaded and distinct → /health returns HTTP 200 (BUG-289 / TD-553)."""
    service = _load_service(4)
    client = TestClient(service.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["model_loaded"] is True


def test_health_code_aliased_to_en_returns_503():
    """Code model aliased to en model (fallback) → /health returns HTTP 503 (TD-553)."""
    service = _load_service(4)
    # Simulate aliased fallback: code model failed to load, registry entry aliased to en
    service.MODEL_REGISTRY["code"] = service.MODEL_REGISTRY["en"]
    client = TestClient(service.app)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"


def test_health_model_none_returns_503():
    """Any model None → /health returns HTTP 503 (existing BUG-289 case)."""
    service = _load_service(4)
    service.MODEL_REGISTRY["code"] = None
    client = TestClient(service.app)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "loading"
