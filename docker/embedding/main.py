"""
BMAD Memory Module - Embedding Service
FastAPI application for generating embeddings using Jina v2 Base EN (768d)

Configuration via environment variables:
- MODEL_NAME: Model identifier (default: jinaai/jina-embeddings-v2-base-en)
- VECTOR_DIMENSIONS: Expected dimensions (default: 768)
- LOG_LEVEL: Logging verbosity (default: INFO)

Note: EN model chosen over code model for better natural language query support.
Memory content is primarily English text describing code, not raw code.
See TECH-DEBT-002 for rationale.
"""
import os
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastembed import TextEmbedding
from prometheus_client import make_asgi_app
import time
import logging
import sys

# Add project root to path for metrics import
sys.path.insert(0, '/app/src')

# Import metrics to register them with prometheus_client (AC 6.1.2)
try:
    from memory.metrics import embedding_requests_total, embedding_duration_seconds
    metrics_available = True
except ImportError:
    logger = logging.getLogger("bmad.embedding")
    logger.warning("metrics_import_failed", extra={
        "error_details": "Could not import memory.metrics module - metrics may be unavailable"
    })
    metrics_available = False
    embedding_requests_total = None
    embedding_duration_seconds = None

# Configuration
MODEL_NAME = os.getenv("MODEL_NAME", "jinaai/jina-embeddings-v2-base-en")
VECTOR_DIMENSIONS = int(os.getenv("VECTOR_DIMENSIONS", "768"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("bmad.embedding")

app = FastAPI(
    title="BMAD Embedding Service",
    description="Text embedding generation using Jina v2 Base EN (768d)",
    version="2.1.0"
)

# Mount Prometheus metrics endpoint (AC 6.1.5, AC 6.1.1)
# Uses ASGI app for FastAPI compatibility (prometheus_client 0.24.0)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Load model at startup
logger.info("model_loading", extra={"model": MODEL_NAME, "status": "starting"})
start_load = time.time()
model = TextEmbedding(MODEL_NAME)
model_loaded_at = time.time()
load_duration = model_loaded_at - start_load
logger.info("model_loaded", extra={
    "model": MODEL_NAME,
    "dimensions": VECTOR_DIMENSIONS,
    "load_time_seconds": round(load_duration, 2)
})


class EmbedRequest(BaseModel):
    texts: List[str]


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str = "jina-embeddings-v2-base-en"
    dimensions: int = VECTOR_DIMENSIONS


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model: str
    dimensions: int
    uptime_seconds: int


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="healthy",
        model_loaded=True,
        model=MODEL_NAME,
        dimensions=VECTOR_DIMENSIONS,
        uptime_seconds=int(time.time() - model_loaded_at)
    )


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")

    # Start timing for metrics
    start_time = time.perf_counter()

    try:
        # Generate embeddings (FastEmbed returns generator, convert to list)
        embeddings_list = list(model.embed(request.texts))
        # Convert numpy arrays to lists
        embeddings = [emb.tolist() for emb in embeddings_list]

        # Record successful embedding generation
        duration = time.perf_counter() - start_time

        # Increment metrics
        if metrics_available and embedding_requests_total:
            embedding_requests_total.labels(status="success").inc()
        if metrics_available and embedding_duration_seconds:
            embedding_duration_seconds.observe(duration)

        logger.info("embeddings_generated", extra={
            "text_count": len(request.texts),
            "dimensions": VECTOR_DIMENSIONS,
            "duration_seconds": round(duration, 3)
        })

        return EmbedResponse(embeddings=embeddings)

    except Exception as e:
        duration = time.perf_counter() - start_time

        # Increment failure metrics
        if metrics_available and embedding_requests_total:
            embedding_requests_total.labels(status="failed").inc()
        if metrics_available and embedding_duration_seconds:
            embedding_duration_seconds.observe(duration)

        logger.error("embedding_generation_failed", extra={
            "error": str(e),
            "error_code": "EMBEDDING_ERROR",
            "text_count": len(request.texts),
            "duration_seconds": round(duration, 3)
        })
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")


@app.get("/")
def root():
    return {
        "service": "BMAD Embedding Service",
        "model": MODEL_NAME,
        "dimensions": VECTOR_DIMENSIONS,
        "endpoints": {
            "health": "/health",
            "embed": "/embed (POST)"
        }
    }
