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
import os
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

    def __init__(self, name="stub", delay=0.05):
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

    def __init__(self, name="stub-bm25"):
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

    def __init__(self, name="stub-colbert", n_tokens=4):
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
        "EMBEDDING_MAX_WAITERS",
        "EMBEDDING_RETRY_AFTER",
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
        async def call():
            return await service.embed_dense(request_cls(texts=list(texts), model="en"))

        return await asyncio.gather(*[call() for _ in range(concurrency)])

    results = asyncio.run(_drive())

    # No dropped embed: every request returned a full set of vectors.
    assert len(results) == concurrency
    assert all(len(r.embeddings) == len(texts) for r in results)
    # Memory stayed bounded: inference never exceeded the slot cap (peak-memory proxy).
    assert _tracker.max_active <= cap
    # Backpressure engaged (callers were made to wait) but NOTHING was shed.
    assert _backpressure_count(service, "shed") - before_shed == 0
    assert _backpressure_count(service, "waited") - before_waited > 0
