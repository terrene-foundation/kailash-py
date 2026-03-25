# Multi-stage build for production-ready Kaizen container
# PROD-001: Containerization - Production-ready Dockerfile
# Target: <500MB, non-root user, security scanning passing

# ============================================================================
# Stage 1: Builder - Build dependencies and install packages
# ============================================================================
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy dependency files first (for better caching)
COPY pyproject.toml README.md ./

# Copy source code
COPY src ./src

# Install package with minimal dependencies
# Use --no-deps to avoid pulling in heavy dev dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --no-deps . && \
    pip install --no-cache-dir \
        "kailash>=0.9.19" \
        "pydantic>=2.0.0" \
        "typing-extensions>=4.5.0" \
        "PyJWT>=2.8.0" \
        "bcrypt>=4.0.0"

# ============================================================================
# Stage 2: Runtime - Minimal production image with Alpine for smaller size
# ============================================================================
FROM python:3.12-alpine

# Install runtime dependencies only
RUN apk add --no-cache \
    postgresql-client \
    libpq \
    curl \
    && rm -rf /var/cache/apk/*

# Create non-root user for security
RUN addgroup -g 1000 kaizen && \
    adduser -D -u 1000 -G kaizen kaizen && \
    mkdir -p /app && \
    chown -R kaizen:kaizen /app

# Set working directory
WORKDIR /app

# Copy only essential Python packages from builder stage
# Exclude heavy dependencies not needed for core functionality
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy only source code (not tests, docs, examples)
COPY --chown=kaizen:kaizen src ./src
COPY --chown=kaizen:kaizen pyproject.toml setup.py README.md ./

# Switch to non-root user
USER kaizen

# Health check - verify Kaizen can import successfully
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; from kaizen.core.base_agent import BaseAgent; print('healthy'); sys.exit(0)" || exit 1

# Expose default port (if needed for future API service)
EXPOSE 8000

# Default command - keeps container running
# In production, this would be replaced with actual service (API server, worker, etc.)
CMD ["sh", "-c", "python -c 'from kaizen.core.base_agent import BaseAgent; print(\"Kaizen container ready - BaseAgent imported successfully\")' && echo 'Container running. Press Ctrl+C to stop.' && tail -f /dev/null"]
