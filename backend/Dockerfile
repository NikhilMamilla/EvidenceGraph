# =============================================================================
# EvidenceGraph Backend — Dockerfile
# Multi-stage build: builder + production
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: builder — install dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a prefix for copying
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: production image
# ---------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Non-root user for security
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
