# Kailash Python SDK — Full Image
# Includes Core SDK + DataFlow + Nexus + Kaizen + PACT + Trust
# Published to: docker.io/terrenefoundation/kailash
#
# Build:  docker build -t terrenefoundation/kailash .
# Run:    docker run -it --rm terrenefoundation/kailash python
# Shell:  docker run -it --rm terrenefoundation/kailash bash

# ============================================================================
# Stage 1: Builder — install all dependencies
# ============================================================================
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency metadata first (cache-friendly layer ordering)
COPY pyproject.toml README.md ./
COPY src ./src

# Install the full SDK with all extras
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir ".[all]"

# ============================================================================
# Stage 2: Runtime — lean production image
# ============================================================================
FROM python:3.12-slim

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -g 1000 kailash && \
    useradd -u 1000 -g kailash -m -s /bin/bash kailash && \
    mkdir -p /app && \
    chown -R kailash:kailash /app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source (production code only — tests/docs excluded via .dockerignore)
COPY --chown=kailash:kailash src ./src
COPY --chown=kailash:kailash pyproject.toml README.md ./

USER kailash

# Verify all frameworks import successfully
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "\
from kailash.workflow.builder import WorkflowBuilder; \
from kailash.runtime.local import LocalRuntime; \
print('healthy')" || exit 1

# Labels (OCI standard)
LABEL org.opencontainers.image.title="Kailash Python SDK"
LABEL org.opencontainers.image.description="Full Kailash SDK: workflow orchestration, DataFlow, Nexus, Kaizen AI agents, PACT governance, Trust/EATP"
LABEL org.opencontainers.image.vendor="Terrene Foundation"
LABEL org.opencontainers.image.url="https://github.com/terrene-foundation/kailash-py"
LABEL org.opencontainers.image.source="https://github.com/terrene-foundation/kailash-py"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Default: interactive Python with SDK loaded
CMD ["python"]
