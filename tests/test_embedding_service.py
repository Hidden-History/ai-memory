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
        "EMBEDDING_MAX_WAITERS",
        "EMBEDDING_RETRY_AFTER",
        "EMBEDDING_INFERENCE_THREADS",
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
    # And the cap was actually exercised under real concurrency (not a vacuous bound).
    assert _tracker.max_active >= 2
    # Backpressure engaged (callers were made to wait) but NOTHING was shed.
    assert _backpressure_count(service, "shed") - before_shed == 0
    assert _backpressure_count(service, "waited") - before_waited > 0


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
