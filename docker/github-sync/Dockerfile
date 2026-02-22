FROM python:3.12.8-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck fallback)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY docker/github-sync/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# SPEC-009: Download SpaCy NER model for security scanning Layer 3
# en_core_web_sm: Small English model (~12MB) optimized for NER
RUN python3 -m spacy download en_core_web_sm

# Copy application code
COPY src/ /app/src/
COPY scripts/ /app/scripts/

# Create state directory matching engine's Path.cwd() / ".audit" / "state" path
# GitHubSyncEngine resolves state via: Path.cwd() / ".audit" / "state"
# With WORKDIR /app, that becomes /app/.audit/state/
RUN mkdir -p /app/.audit/state /tmp

# Create non-root user (security hardening)
RUN useradd -u 1001 -g users -s /usr/sbin/nologin ghsync && \
    chown -R ghsync:users /app /tmp

# Set Python path to include src directory where memory module lives
ENV PYTHONPATH=/app/src

# Switch to non-root user
USER ghsync

CMD ["python3", "scripts/github_sync_service.py"]
