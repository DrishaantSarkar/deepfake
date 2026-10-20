# ==============================================================================
# TRUSTLENS Production Multi-Stage Containerfile
# ==============================================================================
FROM python:3.12-slim-bookworm AS base

# Prevent Python from writing .pyc and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install runtime OS dependencies: ffmpeg for video decoding, libgl1/libglib for OpenCV headless, curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root system user for security hardening
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Create directories for persistent storage and ephemeral media
RUN mkdir -p /app/data /app/temp /app/checkpoints && \
    chown -R appuser:appuser /app

# Copy application source code and checkpoints
COPY --chown=appuser:appuser trustlens/ ./trustlens/
COPY --chown=appuser:appuser checkpoints/ ./checkpoints/

# Default runtime configuration
ENV TRUSTLENS_HOST=0.0.0.0 \
    TRUSTLENS_PORT=8765 \
    TRUSTLENS_ALLOWED_HOSTS=* \
    TRUSTLENS_DB_PATH=/app/data/analyses.sqlite3 \
    TRUSTLENS_TEMP_DIR=/app/temp \
    TRUSTLENS_MODEL_PATH=/app/checkpoints/best_model.pt \
    TRUSTLENS_ENV=production

# Switch to non-privileged user
USER appuser

# Expose standard application port
EXPOSE 8765

# Container healthcheck using loopback API
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f "http://127.0.0.1:${TRUSTLENS_PORT:-8765}/api/health" || exit 1

# Production entrypoint
CMD ["python", "-m", "trustlens.web"]
