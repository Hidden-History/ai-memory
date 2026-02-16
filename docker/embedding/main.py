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
from typing import List

from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding
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
    version="2.1.0",
)

# Mount Prometheus metrics endpoint (AC 6.1.5, AC 6.1.1)
# Uses ASGI app for FastAPI compatibility (prometheus_client 0.24.0)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Both models loaded at startup (SPEC-010 Section 3.2)
MODEL_REGISTRY: dict[str, TextEmbedding] = {}
models_ready_time: float = 0.0

def load_models():
    """Load both embedding models at startup."""
    global models_ready_time
    for key, name in MODEL_NAMES.items():
        logger.info("model_loading", extra={"model": name, "key": key})
        start_load = time.time()
        MODEL_REGISTRY[key] = TextEmbedding(name)
        load_duration = time.time() - start_load
        logger.info("model_loaded", extra={"model": name, "key": key, "load_time_seconds": round(load_duration, 2)})
    models_ready_time = time.time()

load_models()  # Called at module init


class EmbedRequest(BaseModel):
    texts: List[str]


class EmbedDenseRequest(BaseModel):
    texts: List[str]
    model: str = "en"  # "en" or "code"


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str = "jina-embeddings-v2-base-en"
    dimensions: int = VECTOR_DIMENSIONS


class EmbedDenseResponse(BaseModel):
    embeddings: List[List[float]]
    model: str  # Full model name used
    dimensions: int  # 768


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model: str  # Backward compat - returns first loaded model
    models: List[str]  # NEW: list both models
    dimensions: int
    uptime_seconds: int


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


@app.get("/")
def root():
    return {
        "service": "AI Memory Embedding Service",
        "models": MODEL_NAMES,
        "dimensions": VECTOR_DIMENSIONS,
        "endpoints": {
            "health": "/health",
            "embed": "/embed (POST) - backward compatible, uses model=en",
            "embed_dense": "/embed/dense (POST) - new dual-model endpoint"
        },
    }
