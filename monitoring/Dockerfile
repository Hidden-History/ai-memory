# monitoring/Dockerfile
FROM python:3.12-slim

# Metadata labels (2026 best practice)
LABEL maintainer="ai-memory"
LABEL version="1.0.0"
LABEL description="Monitoring API for AI Memory Module"
LABEL ai-memory.managed="true"
LABEL ai-memory.wipe-policy="exclude"
LABEL org.opencontainers.image.vendor="ai-memory"

# Non-root user for security (2026 security standard)
RUN groupadd -r memory && useradd -r -g memory memory

WORKDIR /app

# Copy requirements first for better layer caching
COPY monitoring/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY monitoring/*.py .

# Copy src directory for memory module imports (Story 6.6)
COPY src /app/src

# Change ownership to non-root user
RUN chown -R memory:memory /app

# Switch to non-root user
USER memory

EXPOSE 8000

# Use exec form for proper signal handling (2026 best practice)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
