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

import importlib.util
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import numpy as np
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


class _RaisingModel:
    """Model whose inference always fails — simulates a bad/oversized request."""

    def embed(self, texts):
        raise RuntimeError("simulated inference failure")


def _install_fake_fastembed():
    """Inject a stub ``fastembed`` so the service imports without the real models."""
    module = ModuleType("fastembed")
    module.TextEmbedding = _StubDenseModel
    module.SparseTextEmbedding = _StubSparseModel
    module.LateInteractionTextEmbedding = _StubDenseModel
    sys.modules["fastembed"] = module


def _load_service(max_concurrency):
    """Import a fresh copy of the embedding service with the given concurrency cap."""
    _install_fake_fastembed()
    os.environ["EMBEDDING_MAX_CONCURRENCY"] = str(max_concurrency)
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


def test_concurrent_inference_never_exceeds_cap():
    """Simultaneous inference must stay at or below EMBEDDING_MAX_CONCURRENCY."""
    cap = 3
    service = _load_service(cap)
    _tracker.reset()
    request_cls = service.EmbedDenseRequest
    texts = _production_shaped_batch(count=4)

    def call():
        return service.embed_dense(request_cls(texts=list(texts), model="en"))

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = [f.result() for f in [executor.submit(call) for _ in range(12)]]

    assert all(len(r.embeddings) == len(texts) for r in results)
    # Core guard: the semaphore never let more than `cap` inferences run at once.
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
    """Many concurrent large requests all receive a clean response — none dropped."""
    service = _load_service(4)
    client = TestClient(service.app)
    texts = _production_shaped_batch(count=8)

    def call():
        response = client.post("/embed/dense", json={"texts": texts, "model": "en"})
        return response.status_code

    with ThreadPoolExecutor(max_workers=16) as executor:
        codes = [f.result() for f in [executor.submit(call) for _ in range(32)]]

    assert all(code == 200 for code in codes)
