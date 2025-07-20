# Multi-stage production Dockerfile for Kailash SDK Template
# Enterprise-grade deployment configuration

# Build stage
FROM python:3.11-slim as builder

# Build arguments
ARG BUILD_VERSION=latest
ARG BUILD_DATE
ARG BUILD_REVISION

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements files
COPY pyproject.toml ./

# Install dependencies directly from pyproject.toml
RUN pip install --no-cache-dir .

# Production stage
FROM python:3.11-slim as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r app && useradd -r -g app app

# Set work directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY sdk-users/ ./sdk-users/
COPY data/ ./data/
COPY pyproject.toml ./
COPY CLAUDE.md ./

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/outputs /app/.matplotlib

# Set ownership
RUN chown -R app:app /app

# Switch to non-root user
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/workflows/get_status/execute || exit 1

# Environment variables
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    LOG_LEVEL=info \
    HOME=/app \
    MPLCONFIGDIR=/app/.matplotlib

# Labels for metadata
LABEL version="${BUILD_VERSION}" \
      build_date="${BUILD_DATE}" \
      build_revision="${BUILD_REVISION}" \
      maintainer="Kailash SDK Team"

# Default command
CMD ["python", "-m", "uvicorn", "src.new_project.core.gateway:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]