# monitoring/Dockerfile
FROM python:3.11-slim

# Metadata labels (2026 best practice)
LABEL maintainer="bmad-memory-module"
LABEL version="1.0.0"
LABEL description="Monitoring API for BMAD Memory Module"

# Non-root user for security (2026 security standard)
RUN groupadd -r bmad && useradd -r -g bmad bmad

WORKDIR /app

# Copy requirements first for better layer caching
COPY monitoring/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY monitoring/*.py .

# Copy src directory for memory module imports (Story 6.6)
COPY src /app/src

# Change ownership to non-root user
RUN chown -R bmad:bmad /app

# Switch to non-root user
USER bmad

# Health check (2026 best practice)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; exit(0 if httpx.get('http://localhost:8000/health', timeout=5).status_code == 200 else 1)"

EXPOSE 8000

# Use exec form for proper signal handling (2026 best practice)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
