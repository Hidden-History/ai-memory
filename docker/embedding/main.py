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
import time

from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding, SparseTextEmbedding, LateInteractionTextEmbedding
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
    "en": os.getenv("MODEL_NAME_EN",
                    os.getenv("MODEL_NAME",
                              "jinaai/jina-embeddings-v2-base-en")),
    "code": os.getenv("MODEL_NAME_CODE",
                      "jinaai/jina-embeddings-v2-base-code"),
}

VECTOR_DIMENSIONS = int(os.getenv("VECTOR_DIMENSIONS", "768"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ai_memory.embedding")

app = FastAPI(
    title="AI Memory Embedding Service",
    description="Dual embedding generation using Jina v2 Base EN (prose) + Base Code (code) - 768d",
    version="2.2.1",
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
    logger.info("model_loaded", extra={"model": en_name, "key": "en", "load_time_seconds": round(load_duration, 2)})

    # Load optional 'code' model with fallback to 'en'
    code_name = MODEL_NAMES["code"]
    try:
        logger.info("model_loading", extra={"model": code_name, "key": "code"})
        start_load = time.time()
        MODEL_REGISTRY["code"] = TextEmbedding(code_name)
        load_duration = time.time() - start_load
        logger.info("model_loaded", extra={"model": code_name, "key": "code", "load_time_seconds": round(load_duration, 2)})
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
    logger.info("model_loaded", extra={"model": "Qdrant/bm25", "key": "bm25", "load_time_seconds": round(time.time() - start, 2)})

    if os.getenv("COLBERT_ENABLED", "false").lower() == "true":
        logger.info("model_loading", extra={"model": "colbert-ir/colbertv2.0", "key": "colbert"})
        start = time.time()
        LATE_REGISTRY["colbert"] = LateInteractionTextEmbedding("colbert-ir/colbertv2.0")
        logger.info("model_loaded", extra={"model": "colbert-ir/colbertv2.0", "key": "colbert", "load_time_seconds": round(time.time() - start, 2)})


try:
    load_sparse_models()
except Exception as e:
    logger.error("sparse_model_load_failed", extra={"error": str(e)})
    # Service continues with dense-only capability


class EmbedRequest(BaseModel):
    texts: list[str]


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
def health():
    """Health check endpoint with backward-compatible model field + new models list."""
    return HealthResponse(
        status="healthy",
        model_loaded=all(m is not None for m in MODEL_REGISTRY.values()),
        model=MODEL_NAMES["en"],  # KEPT: backward compat for existing monitors
        models=list(MODEL_NAMES.values()),  # NEW: list both models
        dimensions=VECTOR_DIMENSIONS,
        uptime_seconds=int(time.time() - models_ready_time),
        sparse_models=list(SPARSE_REGISTRY.keys()),
        late_models=list(LATE_REGISTRY.keys()),
    )


@app.post("/embed/dense", response_model=EmbedDenseResponse)
def embed_dense(request: EmbedDenseRequest) -> EmbedDenseResponse:
    """New dual-model embedding endpoint (SPEC-010)."""
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    if request.model not in MODEL_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model: {request.model}. Available: {list(MODEL_REGISTRY.keys())}"
        )

    model = MODEL_REGISTRY[request.model]
    embeddings = list(model.embed(request.texts))
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


@app.post("/embed/sparse", response_model=EmbedSparseResponse)
def embed_sparse(request: EmbedSparseRequest):
    """Generate BM25 sparse embeddings for keyword-aware hybrid search."""
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    if "bm25" not in SPARSE_REGISTRY:
        raise HTTPException(status_code=503, detail="BM25 model not loaded")
    model = SPARSE_REGISTRY["bm25"]
    results = list(model.embed(request.texts))
    return EmbedSparseResponse(
        embeddings=[SparseEmbeddingResult(indices=r.indices.tolist(), values=r.values.tolist()) for r in results],
        model="Qdrant/bm25",
    )


@app.post("/embed/late", response_model=EmbedLateResponse)
def embed_late(request: EmbedLateRequest):
    """Generate ColBERT late interaction embeddings (conditional on COLBERT_ENABLED)."""
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    if "colbert" not in LATE_REGISTRY:
        raise HTTPException(status_code=503, detail="ColBERT model not loaded (set COLBERT_ENABLED=true)")
    model = LATE_REGISTRY["colbert"]
    results = list(model.embed(request.texts))
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
