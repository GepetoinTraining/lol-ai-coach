# Multi-stage Dockerfile for LoL AI Coach
# Build: docker build -t lol-ai-coach .
# Run: docker run -it --env-file .env lol-ai-coach "Player#TAG"

# ==================== Stage 1: Builder ====================
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ==================== Stage 2: Runtime ====================
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user for security
RUN groupadd --gid 1000 coach \
    && useradd --uid 1000 --gid coach --shell /bin/bash --create-home coach

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=coach:coach src/ ./src/
COPY --chown=coach:coach scripts/ ./scripts/
COPY --chown=coach:coach knowledge/ ./knowledge/
COPY --chown=coach:coach pyproject.toml ./

# Create data directory for local storage
RUN mkdir -p /app/data && chown coach:coach /app/data

# Switch to non-root user
USER coach

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    APP_ENV=production \
    LOG_LEVEL=INFO

# Health check (basic Python import check)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.config import get_config; print('healthy')" || exit 1

# Default command - show help
ENTRYPOINT ["python", "scripts/analyze_player.py"]
CMD ["--help"]
