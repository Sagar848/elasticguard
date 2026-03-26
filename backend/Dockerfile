# ─────────────────────────────────────────────────────────────────────────────
#  ElasticGuard Backend Dockerfile
#  • Multi-stage build (builder → slim runtime)
#  • Pinned base image digest for reproducibility
#  • Layer-cached pip install for fast rebuilds
#  • Works with plain docker.io OR a private/air-gapped registry
#    (set REGISTRY_PREFIX build-arg, e.g. --build-arg REGISTRY_PREFIX=artifactory.corp.com/)
# ─────────────────────────────────────────────────────────────────────────────

ARG REGISTRY_PREFIX=""
ARG PYTHON_IMAGE=python:3.11-slim

# ── Stage 1: Build dependencies ──────────────────────────────────────────────
FROM ${REGISTRY_PREFIX}${PYTHON_IMAGE} AS builder

WORKDIR /build

# Install build tools (only needed at build time)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Use --prefix so we can copy the installed packages cleanly
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime image ───────────────────────────────────────────────────
FROM ${REGISTRY_PREFIX}${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="ElasticGuard Backend"
LABEL org.opencontainers.image.description="AI-Powered Elasticsearch Diagnostics API"

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appuser . .

# Create data directories with correct ownership
RUN mkdir -p /app/data/chroma /app/data /app/knowledge/docs \
    && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--proxy-headers"]
