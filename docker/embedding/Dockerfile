# Multi-stage build for optimized image size (2025 best practices)
# Stage 1: Builder - Install dependencies and download model
FROM python:3.12-slim AS builder

WORKDIR /app

# Python environment optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first for better layer caching
COPY docker/embedding/requirements.txt .

# Install Python dependencies
RUN pip install --upgrade --no-cache-dir -r requirements.txt

# Pre-download Jina v2 Base Code model
# NOTE: Temporarily disabled due to network timeouts - model will download at runtime
# RUN python -c "from fastembed import TextEmbedding; TextEmbedding('jinaai/jina-embeddings-v2-base-code')"

# Stage 2: Runtime - Minimal production image
FROM python:3.12-slim

WORKDIR /app

# Python runtime optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Install only runtime dependencies (curl for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash embedding && \
    chown -R embedding:embedding /app

# Copy virtual environment from builder
COPY --from=builder --chown=embedding:embedding /opt/venv /opt/venv

# Copy model cache from builder (disabled - model downloads at runtime)
# COPY --from=builder --chown=embedding:embedding /root/.cache /home/embedding/.cache

# Copy application code
COPY --chown=embedding:embedding docker/embedding/main.py .

# Copy metrics module for Prometheus integration (Story 6.1)
COPY --chown=embedding:embedding src /app/src

# Switch to non-root user
USER embedding

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
