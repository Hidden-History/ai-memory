"""
AI Memory Module - Embedding Service
FastAPI application for dual embedding model support (Jina v2 Base EN + Base Code, 768d)

Configuration via environment variables:
- MODEL_NAME_EN: Prose model (default: jinaai/jina-embeddings-v2-base-en)
- MODEL_NAME_CODE: Code model (default: jinaai/jina-embeddings-v2-base-code)
- MODEL_NAME: Legacy fallback for MODEL_NAME_EN (backward compatibility)
- VECTOR_DIMENSIONS: Expected dimensions (default: 768)
- LOG_LEVEL: Logging verbosity (default: INFO)

SPEC-010: Dual Embedding Routing - Both models loaded at startup for immediate availability.
"""

import logging
import os
import sys
import threading
import time

from fastapi import FastAPI, HTTPException
from fastembed import LateInteractionTextEmbedding, SparseTextEmbedding, TextEmbedding
from prometheus_client import make_asgi_app
from pydantic import BaseModel

# Add project root to path for metrics import
sys.path.insert(0, "/app/src")

# Import metrics to register them with prometheus_client (AC 6.1.2)
try:
    from memory.metrics import embedding_duration_seconds, embedding_requests_total

    metrics_available = True
except ImportError:
    logger = logging.getLogger("ai_memory.embedding")
    logger.warning(
        "metrics_import_failed",
        extra={
            "error_details": "Could not import memory.metrics module - metrics may be unavailable"
        },
    )
    metrics_available = False
    embedding_requests_total = None
    embedding_duration_seconds = None

# Model configuration with backward-compatible fallback chain (SPEC-010 Section 3.2)
MODEL_NAMES = {
    "en": os.getenv(
        "MODEL_NAME_EN", os.getenv("MODEL_NAME", "jinaai/jina-embeddings-v2-base-en")
    ),
    "code": os.getenv("MODEL_NAME_CODE", "jinaai/jina-embeddings-v2-base-code"),
}

VECTOR_DIMENSIONS = int(os.getenv("VECTOR_DIMENSIONS", "768"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# TD-670: Bound concurrent model inference. The sync request handlers run in the
# anyio threadpool (~40 threads), so without a limit many concurrent embed requests
# drive the shared ONNX models in parallel and each materializes a full batch of
# vectors at once — peak memory spikes toward the container limit (suspected clean-exit
# trigger) and the shared fastembed model objects are exercised concurrently. A
# process-wide semaphore caps simultaneous inference; requests beyond the cap wait up
# to EMBEDDING_ACQUIRE_TIMEOUT seconds for a slot, then receive a 503 rather than
# blocking forever or crashing the worker.
EMBEDDING_MAX_CONCURRENCY = int(os.getenv("EMBEDDING_MAX_CONCURRENCY", "4"))
EMBEDDING_ACQUIRE_TIMEOUT = float(os.getenv("EMBEDDING_ACQUIRE_TIMEOUT", "30"))
_inference_semaphore = threading.Semaphore(EMBEDDING_MAX_CONCURRENCY)

# TD-670: Reject oversized payloads up front so a single huge request cannot drive the
# worker into an OS-level OOM SIGKILL (which the 503 fault-isolation in run_inference
# cannot catch). Bound both the batch size (number of texts -> number of vectors
# materialized) and the total input size (chars -> model working memory). Defaults are
# provisional and meant to be tuned against real saturation behaviour during live load
# testing.
EMBEDDING_MAX_BATCH_TEXTS = int(os.getenv("EMBEDDING_MAX_BATCH_TEXTS", "256"))
EMBEDDING_MAX_INPUT_CHARS = int(os.getenv("EMBEDDING_MAX_INPUT_CHARS", "1000000"))

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ai_memory.embedding")


def run_inference(operation):
    """Execute a model inference call with TD-670 resilience guarantees.

    Bounds concurrency via the process-wide semaphore (peak-memory + shared-model
    access guard): a caller waits at most ``EMBEDDING_ACQUIRE_TIMEOUT`` seconds for a
    slot and otherwise receives an HTTP 503 instead of blocking forever. Faults are
    isolated — any Python-level exception raised inside ``operation`` becomes an HTTP
    503 so a request that fails inside the model call cannot crash the worker; the
    service keeps serving other requests. An ``HTTPException`` raised inside
    ``operation`` (e.g. a validation error) passes through unchanged.

    This isolation is Python-level only: it does NOT protect against an OS-level OOM
    SIGKILL, which is uncatchable. Oversized payloads are rejected up front with HTTP
    413 by ``_enforce_payload_limits`` to keep a single request from reaching that
    point.

    Args:
        operation: Zero-arg callable performing the model inference.

    Returns:
        Whatever ``operation`` returns.

    Raises:
        HTTPException: 503 if no inference slot becomes available within the timeout,
            or if the inference call raises any non-HTTPException error.
    """
    if not _inference_semaphore.acquire(timeout=EMBEDDING_ACQUIRE_TIMEOUT):
        logger.warning("embedding_inference_busy")
        raise HTTPException(status_code=503, detail="embedding_inference_busy")
    try:
        return operation()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "embedding_inference_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise HTTPException(status_code=503, detail="embedding_inference_failed") from e
    finally:
        _inference_semaphore.release()


def _enforce_payload_limits(texts: list[str]) -> None:
    """Reject oversized embed payloads with HTTP 413 before any model work (TD-670).

    Bounds both the number of texts in the batch and the total input size in
    characters, closing the single-request OOM vector by refusing a huge batch before
    it is materialized into vectors. Limits are configured via
    ``EMBEDDING_MAX_BATCH_TEXTS`` and ``EMBEDDING_MAX_INPUT_CHARS``.

    Raises:
        HTTPException: 413 if the batch has too many texts or too many total chars.
    """
    if len(texts) > EMBEDDING_MAX_BATCH_TEXTS:
        raise HTTPException(
            status_code=413,
            detail=f"Too many texts: {len(texts)} > max {EMBEDDING_MAX_BATCH_TEXTS}",
        )
    total_chars = sum(len(t) for t in texts)
    if total_chars > EMBEDDING_MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Input too large: {total_chars} chars > "
                f"max {EMBEDDING_MAX_INPUT_CHARS}"
            ),
        )


app = FastAPI(
    title="AI Memory Embedding Service",
    description="Dual embedding generation using Jina v2 Base EN (prose) + Base Code (code) - 768d",
    version="2.3.2",
)

# Mount Prometheus metrics endpoint (AC 6.1.5, AC 6.1.1)
# Uses ASGI app for FastAPI compatibility (prometheus_client 0.24.0)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Both models loaded at startup (SPEC-010 Section 3.2)
MODEL_REGISTRY: dict[str, TextEmbedding] = {}
models_ready_time: float = 0.0


def load_models():
    """Load both embedding models at startup with graceful fallback.

    The 'en' model is required — if it fails, the service cannot start.
    The 'code' model is optional — if it fails, 'en' is used as fallback.
    """
    global models_ready_time

    # Load the required 'en' model first
    en_name = MODEL_NAMES["en"]
    logger.info("model_loading", extra={"model": en_name, "key": "en"})
    start_load = time.time()
    MODEL_REGISTRY["en"] = TextEmbedding(en_name)
    load_duration = time.time() - start_load
    logger.info(
        "model_loaded",
        extra={
            "model": en_name,
            "key": "en",
            "load_time_seconds": round(load_duration, 2),
        },
    )

    # Load optional 'code' model with fallback to 'en'
    code_name = MODEL_NAMES["code"]
    try:
        logger.info("model_loading", extra={"model": code_name, "key": "code"})
        start_load = time.time()
        MODEL_REGISTRY["code"] = TextEmbedding(code_name)
        load_duration = time.time() - start_load
        logger.info(
            "model_loaded",
            extra={
                "model": code_name,
                "key": "code",
                "load_time_seconds": round(load_duration, 2),
            },
        )
    except Exception as e:
        logger.warning(
            "model_load_fallback",
            extra={
                "model": code_name,
                "key": "code",
                "error": str(e),
                "fallback": "Using 'en' model for code embeddings",
            },
        )
        MODEL_REGISTRY["code"] = MODEL_REGISTRY["en"]

    models_ready_time = time.time()


load_models()  # Called at module init

# Sparse and late interaction model registries (T-017/T-018)
SPARSE_REGISTRY: dict[str, SparseTextEmbedding] = {}
LATE_REGISTRY: dict[str, LateInteractionTextEmbedding] = {}


def load_sparse_models():
    """Load BM25 sparse embedding model at startup."""
    logger.info("model_loading", extra={"model": "Qdrant/bm25", "key": "bm25"})
    start = time.time()
    SPARSE_REGISTRY["bm25"] = SparseTextEmbedding("Qdrant/bm25")
    logger.info(
        "model_loaded",
        extra={
            "model": "Qdrant/bm25",
            "key": "bm25",
            "load_time_seconds": round(time.time() - start, 2),
        },
    )

    if os.getenv("COLBERT_ENABLED", "false").lower() == "true":
        logger.info(
            "model_loading", extra={"model": "colbert-ir/colbertv2.0", "key": "colbert"}
        )
        start = time.time()
        LATE_REGISTRY["colbert"] = LateInteractionTextEmbedding(
            "colbert-ir/colbertv2.0"
        )
        logger.info(
            "model_loaded",
            extra={
                "model": "colbert-ir/colbertv2.0",
                "key": "colbert",
                "load_time_seconds": round(time.time() - start, 2),
            },
        )


try:
    load_sparse_models()
except Exception as e:
    logger.error("sparse_model_load_failed", extra={"error": str(e)})
    # Service continues with dense-only capability


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedWithOffsetsRequest(BaseModel):
    texts: list[str]
    chunk_offsets: list[list[int]]
    late_chunking: bool = True


class EmbedDenseRequest(BaseModel):
    texts: list[str]
    model: str = "en"  # "en" or "code"


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str = "jina-embeddings-v2-base-en"
    dimensions: int = VECTOR_DIMENSIONS


class EmbedDenseResponse(BaseModel):
    embeddings: list[list[float]]
    model: str  # Full model name used
    dimensions: int  # 768


class EmbedSparseRequest(BaseModel):
    texts: list[str]


class SparseEmbeddingResult(BaseModel):
    indices: list[int]
    values: list[float]


class EmbedSparseResponse(BaseModel):
    embeddings: list[SparseEmbeddingResult]
    model: str


class EmbedLateRequest(BaseModel):
    texts: list[str]


class LateEmbeddingResult(BaseModel):
    embeddings: list[list[float]]


class EmbedLateResponse(BaseModel):
    embeddings: list[LateEmbeddingResult]
    model: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model: str  # Backward compat - returns first loaded model
    models: list[str]  # NEW: list both models
    dimensions: int
    uptime_seconds: int
    sparse_models: list[str]  # BM25 model status
    late_models: list[str]  # ColBERT model status


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint with backward-compatible model field + new models list.

    BUG-289: Returns HTTP 503 when models are not yet loaded so that Docker
    Compose ``depends_on: condition: service_healthy`` (``curl -f``) correctly
    gates dependent services on actual model readiness rather than mere process
    liveness.

    TD-670: Declared ``async`` so it runs on the event loop rather than the anyio
    threadpool; under saturation the sync embed handlers can occupy every threadpool
    token while blocked on the inference semaphore, which would otherwise starve the
    healthcheck. This handler does only trivial in-memory work, so running it on the
    loop is safe.
    """
    model_loaded = all(m is not None for m in MODEL_REGISTRY.values())
    response = HealthResponse(
        status="healthy" if model_loaded else "loading",
        model_loaded=model_loaded,
        model=MODEL_NAMES["en"],  # KEPT: backward compat for existing monitors
        models=list(MODEL_NAMES.values()),  # NEW: list both models
        dimensions=VECTOR_DIMENSIONS,
        uptime_seconds=int(time.time() - models_ready_time),
        sparse_models=list(SPARSE_REGISTRY.keys()),
        late_models=list(LATE_REGISTRY.keys()),
    )
    if not model_loaded:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            content=response.model_dump(),
            status_code=503,
        )
    return response


@app.post("/embed/dense", response_model=EmbedDenseResponse)
def embed_dense(request: EmbedDenseRequest) -> EmbedDenseResponse:
    """New dual-model embedding endpoint (SPEC-010)."""
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    if request.model not in MODEL_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model: {request.model}. Available: {list(MODEL_REGISTRY.keys())}",
        )
    _enforce_payload_limits(request.texts)

    model = MODEL_REGISTRY[request.model]
    embeddings = run_inference(lambda: list(model.embed(request.texts)))
    return EmbedDenseResponse(
        embeddings=[e.tolist() for e in embeddings],
        model=MODEL_NAMES[request.model],
        dimensions=VECTOR_DIMENSIONS,
    )


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    """Backward-compatible alias. Routes to /embed/dense with model=en."""
    dense_request = EmbedDenseRequest(texts=request.texts, model="en")
    result = embed_dense(dense_request)
    return EmbedResponse(
        embeddings=result.embeddings,
        model=result.model,
        dimensions=result.dimensions,
    )


@app.post("/embed/chunked", response_model=EmbedResponse)
def embed_chunked(request: EmbedWithOffsetsRequest):
    """Chunked embedding endpoint: returns one embedding per chunk offset (BP-028).

    Accepts a document (single text) and a list of [start, end] character offsets
    defining chunk boundaries. Returns N embeddings for N chunk offsets by embedding
    each character span as an independent segment. This ensures callers always receive
    exactly one vector per chunk, not one vector for the whole document.

    Note: This is independent chunk embedding, not true late chunking. True late
    chunking (single transformer pass with per-chunk mean pooling of token embeddings)
    is deferred to v2.3.0. See TD-274.

    Falls back to embedding whole document if no offsets are provided.
    """
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    _enforce_payload_limits(request.texts)

    document = request.texts[0]
    model = MODEL_REGISTRY["en"]

    if not request.chunk_offsets:
        # No offsets — embed whole document as single vector
        embeddings = run_inference(lambda: list(model.embed([document])))
        return EmbedResponse(
            embeddings=[e.tolist() for e in embeddings],
            model=MODEL_NAMES["en"],
            dimensions=VECTOR_DIMENSIONS,
        )

    # Embed each character span as a separate text segment
    # This produces N vectors for N chunk offsets (independent chunked embedding)
    chunk_texts = []
    for offset_pair in request.chunk_offsets:
        start = offset_pair[0]
        end = offset_pair[1] if len(offset_pair) > 1 else len(document)
        chunk_texts.append(document[start:end])
    _enforce_payload_limits(chunk_texts)

    embeddings = run_inference(lambda: list(model.embed(chunk_texts)))
    return EmbedResponse(
        embeddings=[e.tolist() for e in embeddings],
        model=MODEL_NAMES["en"],
        dimensions=VECTOR_DIMENSIONS,
    )


@app.post("/embed/sparse", response_model=EmbedSparseResponse)
def embed_sparse(request: EmbedSparseRequest):
    """Generate BM25 sparse embeddings for keyword-aware hybrid search."""
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    if "bm25" not in SPARSE_REGISTRY:
        raise HTTPException(status_code=503, detail="BM25 model not loaded")
    _enforce_payload_limits(request.texts)
    model = SPARSE_REGISTRY["bm25"]
    results = run_inference(lambda: list(model.embed(request.texts)))
    return EmbedSparseResponse(
        embeddings=[
            SparseEmbeddingResult(indices=r.indices.tolist(), values=r.values.tolist())
            for r in results
        ],
        model="Qdrant/bm25",
    )


@app.post("/embed/late", response_model=EmbedLateResponse)
def embed_late(request: EmbedLateRequest):
    """Generate ColBERT late interaction embeddings (conditional on COLBERT_ENABLED)."""
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    if "colbert" not in LATE_REGISTRY:
        raise HTTPException(
            status_code=503,
            detail="ColBERT model not loaded (set COLBERT_ENABLED=true)",
        )
    _enforce_payload_limits(request.texts)
    model = LATE_REGISTRY["colbert"]
    results = run_inference(lambda: list(model.embed(request.texts)))
    return EmbedLateResponse(
        embeddings=[LateEmbeddingResult(embeddings=r.tolist()) for r in results],
        model="colbert-ir/colbertv2.0",
    )


@app.get("/")
def root():
    return {
        "service": "AI Memory Embedding Service",
        "models": MODEL_NAMES,
        "dimensions": VECTOR_DIMENSIONS,
        "endpoints": {
            "health": "/health",
            "embed": "/embed (POST) - backward compatible, uses model=en",
            "embed_dense": "/embed/dense (POST) - new dual-model endpoint",
            "embed_sparse": "/embed/sparse (POST) - BM25 sparse embeddings",
            "embed_late": "/embed/late (POST) - ColBERT late interaction embeddings (conditional)",
        },
    }
