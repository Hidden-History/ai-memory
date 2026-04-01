# Dockerfile for AI Memory Browser (Streamlit)
# Story 6.4: Streamlit Memory Browser
# 2026 Best Practices:
# - Python 3.12-slim (standardized, TD-343)
# - Non-root user for security
# - WORKDIR /app (security best practice: non-root user)
# - Compose healthcheck via _stcore/health endpoint (TD-349)
# - Explicit server binding for container access

FROM python:3.12-slim

LABEL ai-memory.managed="true"
LABEL ai-memory.wipe-policy="exclude"
LABEL org.opencontainers.image.vendor="ai-memory"

# Security: Create non-root user
RUN useradd -m -u 1000 streamlit

# Set working directory
WORKDIR /app

# Install system dependencies (curl for compose healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Change ownership to non-root user
RUN chown -R streamlit:streamlit /app

# Switch to non-root user
USER streamlit

# Expose Streamlit port
EXPOSE 8501

# Entry point with explicit binding
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.address=0.0.0.0", \
    "--server.port=8501", \
    "--server.headless=true"]
