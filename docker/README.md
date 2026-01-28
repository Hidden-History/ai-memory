# AI Memory Module - Docker Stack

This directory contains the Docker Compose configuration for the AI Memory Module infrastructure.

## Quick Start

```bash
# Copy environment template
cp .env.example .env

# Start the stack (Qdrant + Embedding only)
docker compose up -d

# Verify Qdrant is healthy
curl http://localhost:26350/health

# Verify Embedding service is healthy
curl http://localhost:28080/health

# Optional: Start with testing profile (includes Monitoring API)
docker compose --profile testing up -d

# Verify Monitoring API is healthy
curl http://localhost:28000/health
```

## Services

### Monitoring API (Testing Profile Only)

The Monitoring API provides testing and verification endpoints for the AI Memory Module. It follows 2026 FastAPI best practices including Kubernetes health probes, async-first design, and Pydantic response models.

**Profile:** `testing` or `monitoring` (optional service)

**Default behavior:** The monitoring API is NOT started by default. Use `--profile testing` to enable.

**Ports:**
- HTTP API: `28000` (host) → `8000` (container)

**Endpoints:**
- `GET /health` - Health check with Qdrant availability
- `GET /live` - Kubernetes liveness probe
- `GET /ready` - Kubernetes readiness probe
- `GET /memory/{id}` - Retrieve specific memory for verification
- `GET /stats/{collection}` - Collection statistics
- `GET /docs` - Swagger UI (OpenAPI documentation)
- `GET /redoc` - ReDoc alternative documentation

**Security:**
- Non-root user (`bmad:bmad`)
- Exec form CMD for proper signal handling
- Read-only verification API (no write operations)

**Dependencies:**
- Waits for Qdrant to be healthy before starting
- Internal network connection to Qdrant

**Usage:**
```bash
# Start with testing profile (includes monitoring API)
docker compose --profile testing up -d

# Test health endpoint
curl http://localhost:28000/health

# View OpenAPI docs
open http://localhost:28000/docs

# Get collection statistics
curl http://localhost:28000/stats/implementations
```

### Qdrant Vector Database (v1.16.3)

**Ports:**
- HTTP API: `26350` (default, configurable via `QDRANT_PORT`)
- gRPC: `26351` (default, configurable via `QDRANT_GRPC_PORT`)

**Storage:**
- Named volume: `qdrant_storage`
- Location: `/qdrant/storage` (inside container)
- Persistence: Data survives container restarts and `docker compose down`

**Health Check:**
- Endpoint: `http://localhost:6333/health` (internal)
- Interval: 30s
- Timeout: 10s
- Retries: 3
- Start period: 10s

### Embedding Service (Jina AI Embeddings)

**Architecture:**
- Multi-stage Docker build (Python 3.12)
- Pre-warmed model: Jina AI jina-embeddings-v2-base-en (768 dimensions)
- FastAPI application with Pydantic v2
- Non-root user security (UID 1000)
- Virtual environment isolation

**Ports:**
- HTTP API: `28080` (default, configurable via `EMBEDDING_PORT`)

**Model Details:**
- Model: `jinaai/jina-embeddings-v2-base-en`
- Dimensions: 768
- Parameter count: 137M
- Specialization: General purpose embeddings with code support
- Load time: ~5-15s (varies by hardware)

**Health Check:**
- Endpoint: `http://localhost:8080/health`
- Interval: 30s
- Timeout: 10s
- Retries: 5
- Start period: 60s (allows time for model loading)

**API Endpoints:**
- `GET /health` - Health check with model info
- `POST /embed` - Generate embeddings (batch supported)
- `GET /` - Service info

**Performance:**
- NFR-P2 requirement: <2s per embedding generation **with GPU**
- CPU-only performance: ~20-30s per embedding (7B parameter model)
- GPU required for production use meeting NFR-P2
- Batch processing supported
- Model pre-loaded at startup (no cold start)

**Example Usage:**
```bash
# Test embedding generation
curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["def hello(): return '\''world'\''"]}'
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_PORT` | `26350` | HTTP API port (localhost-only binding) |
| `QDRANT_GRPC_PORT` | `26351` | gRPC port (localhost-only binding) |
| `QDRANT_LOG_LEVEL` | `INFO` | Log level (TRACE, DEBUG, INFO, WARN, ERROR) |
| `EMBEDDING_PORT` | `28080` | Embedding service HTTP API port (localhost-only) |
| `BMAD_LOG_LEVEL` | `INFO` | Log level for BMAD services (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

## Persistence Behavior

The Qdrant service uses a named Docker volume (`qdrant_storage`) for data persistence:

- **Survives `docker compose down`**: Data is retained when containers are stopped
- **Survives `docker compose down --volumes`**: Data is DELETED when volumes are explicitly removed
- **Survives container restarts**: Automatic restart on failure preserves data

### Verify Persistence

```bash
# Create test collection
curl -X PUT http://localhost:26350/collections/test \
  -H "Content-Type: application/json" \
  -d '{"vectors": {"size": 768, "distance": "Cosine"}}'

# Restart stack
docker compose down && docker compose up -d

# Verify collection still exists
curl http://localhost:26350/collections/test
```

## Security

- **Localhost-only binding**: Ports are bound to `127.0.0.1` to prevent external access
- **No API key**: Not configured for MVP (add for production deployments)
- **Network isolation**: Services use default bridge network

## Troubleshooting

### Port Already in Use

If port 26350 is already in use:

```bash
# Set custom port in .env
echo "QDRANT_PORT=16360" >> .env
docker compose up -d
```

### Health Check Failing

```bash
# Check container logs
docker compose logs qdrant

# Test health endpoint from host (Qdrant images exclude curl for security)
curl -f http://localhost:26350/healthz

# Or check Docker's view of container health
docker inspect --format='{{.State.Health.Status}}' memory-qdrant
```

### Data Persistence Issues

```bash
# List volumes
docker volume ls | grep qdrant

# Inspect volume
docker volume inspect docker_qdrant_storage

# Remove volume (WARNING: deletes all data)
docker compose down --volumes
```

### Embedding Service Issues

#### Port Already in Use

If port 28080 is already in use:

```bash
# Set custom port in .env
echo "EMBEDDING_PORT=8081" >> .env
docker compose up -d
```

#### Model Loading Timeout

If the embedding service health check fails during startup:

```bash
# Check container logs
docker compose logs embedding

# Common issues:
# 1. Model download in progress (first run takes longer)
# 2. Insufficient memory (requires ~4GB)
# 3. Network issues downloading model from HuggingFace

# Wait for model to load (can take 30-60s on first run)
docker compose logs -f embedding
```

#### Memory Issues

The embedding service requires ~4GB RAM for the Nomic Embed Code model:

```bash
# Check container memory usage
docker stats memory-embedding

# If out of memory, increase Docker Desktop memory allocation
# or set a lower memory limit in docker-compose.yml (may cause OOM)
```

#### Slow Embedding Generation

If embeddings take >2 seconds (violates NFR-P2):

```bash
# Check if model is actually loaded
curl http://localhost:28080/health | jq '.model_loaded'

# Verify CPU/memory availability
docker stats memory-embedding

# Common causes:
# - Cold start (first request loads model - should not happen with pre-warming)
# - Insufficient CPU allocation
# - Memory swapping (increase Docker memory)
```

#### Testing Embedding Service

```bash
# Test health endpoint
curl http://localhost:28080/health

# Test single embedding
curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["import torch"]}'

# Test batch embeddings
curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["def foo():", "class Bar:", "x = 42"]}'
```

## GPU Configuration (Optional)

The embedding service currently runs on CPU. For production use meeting NFR-P2 (<2s per embedding), GPU acceleration is required.

**To enable GPU support:**

1. Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

2. Update `docker/docker-compose.yml` to add GPU configuration:

```yaml
embedding:
  # ... existing configuration ...
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

3. Restart the stack:
```bash
docker compose -f docker/docker-compose.yml up -d
```

4. Verify GPU usage:
```bash
docker compose -f docker/docker-compose.yml logs embedding | grep "device_name"
# Should show: "Use pytorch device_name: cuda"
```

**Expected Performance:**
- CPU: ~20-30s per embedding
- GPU: <2s per embedding (NFR-P2 compliant)

## Docker Compose Profiles

Docker Compose profiles allow optional services to be started only when needed (2026 best practice).

**Available Profiles:**
- `testing` - Includes monitoring API for integration testing and development verification
- `monitoring` - Alias for testing profile (same services)

**Usage:**
```bash
# Default: Only core services (Qdrant + Embedding)
docker compose up -d

# Testing profile: Core services + Monitoring API
docker compose --profile testing up -d

# Multiple profiles (future use)
docker compose --profile testing --profile debug up -d

# Verify profile isolation
docker compose ps  # Shows only core services
docker compose --profile testing ps  # Shows core + monitoring-api
```

**Profile Benefits:**
- Resource optimization (monitoring API only runs when needed)
- Clean separation of concerns (testing vs production services)
- No port conflicts (8000 only bound when profile active)
- Single docker-compose.yml for all environments

## Monitoring (Future)

Future stories will add:
- Prometheus metrics exporter (Story 6.1)
- Grafana dashboards (Story 6.3)
- Use `docker compose --profile monitoring up -d` to enable additional observability services

## References

### Qdrant
- [Qdrant Installation Guide](https://qdrant.tech/documentation/guides/installation/)
- [Qdrant Docker Hub](https://hub.docker.com/r/qdrant/qdrant)
- [Qdrant v1.16.3 Release Notes](https://github.com/qdrant/qdrant/releases/tag/v1.16.3)

### Embedding Service
- [Jina AI Embeddings v2 Base EN](https://huggingface.co/jinaai/jina-embeddings-v2-base-en)
- [Sentence Transformers Documentation](https://www.sbert.net/)
- [Sentence Transformers v5.2.0+ (Sparse Embeddings)](https://github.com/UKPLab/sentence-transformers/releases)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Multi-stage Docker Builds Best Practices](https://docs.docker.com/build/building/multi-stage/)

### General
- [Docker Compose Healthcheck Best Practices](https://last9.io/blog/docker-compose-health-checks/)
- [Python 3.12 Release Notes](https://docs.python.org/3.12/whatsnew/3.12.html)
