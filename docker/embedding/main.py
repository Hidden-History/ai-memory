"""
BMAD Memory Module - Embedding Service
FastAPI application for generating code embeddings using Jina v2 Base Code (768d)

Configuration via environment variables:
- MODEL_NAME: Model identifier (default: jinaai/jina-embeddings-v2-base-code)
- VECTOR_DIMENSIONS: Expected dimensions (default: 768)
- LOG_LEVEL: Logging verbosity (default: INFO)
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
    from memory import metrics  # noqa: F401 - imported for side effects
except ImportError:
    logger = logging.getLogger("bmad.embedding")
    logger.warning("metrics_import_failed", extra={
        "error_details": "Could not import memory.metrics module - metrics may be unavailable"
    })

# Configuration
MODEL_NAME = os.getenv("MODEL_NAME", "jinaai/jina-embeddings-v2-base-code")
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
    description="Code embedding generation using Jina v2 Base Code (768d)",
    version="2.0.0"
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
    model: str = "jina-embeddings-v2-base-code"
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
        model="jina-embeddings-v2-base-code",
        dimensions=VECTOR_DIMENSIONS,
        uptime_seconds=int(time.time() - model_loaded_at)
    )


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")

    try:
        # Generate embeddings (FastEmbed returns generator, convert to list)
        embeddings_list = list(model.embed(request.texts))
        # Convert numpy arrays to lists
        embeddings = [emb.tolist() for emb in embeddings_list]

        logger.info("embeddings_generated", extra={
            "text_count": len(request.texts),
            "dimensions": VECTOR_DIMENSIONS
        })

        return EmbedResponse(embeddings=embeddings)

    except Exception as e:
        logger.error("embedding_generation_failed", extra={
            "error": str(e),
            "error_code": "EMBEDDING_ERROR",
            "text_count": len(request.texts)
        })
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")


@app.get("/")
def root():
    return {
        "service": "BMAD Embedding Service",
        "model": "jina-embeddings-v2-base-code",
        "dimensions": VECTOR_DIMENSIONS,
        "endpoints": {
            "health": "/health",
            "embed": "/embed (POST)"
        }
    }
