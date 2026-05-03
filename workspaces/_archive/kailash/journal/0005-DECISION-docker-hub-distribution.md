---
type: DECISION
date: 2026-03-30
project: kailash
topic: Docker Hub distribution for full SDK image
phase: implement
tags: [docker, distribution, ci, release]
---

# Decision: Publish Full SDK Image to Docker Hub

## Context

The Kailash Python SDK was only distributed via PyPI. Users wanting containerized deployments had to build their own images. The existing Dockerfiles in the repo (MCP server, Kaizen) were component-specific, not general-purpose.

## Decision

Created a general-purpose `Dockerfile` at the repo root that bundles `kailash[all]` and publishes to `terrenefoundation/kailash` on Docker Hub. CI publishes automatically on `v*` tags (same trigger as PyPI), with manual dispatch available.

## Alternatives Considered

1. **Per-framework images** (kailash-core, kailash-kaizen, etc.) — rejected as premature; one full image is simpler to start with
2. **Alpine-based runtime stage** (as Kaizen Dockerfile uses) — rejected; `python:3.12-slim` avoids musl compatibility issues with C extensions (asyncpg, cryptography, pynacl)
3. **PyPI-only distribution** — rejected; Docker is standard for containerized deployments

## Key Choices

- Multi-arch: `linux/amd64` + `linux/arm64`
- Non-root user: `kailash` (UID 1000)
- GHA build cache for fast rebuilds
- `docker/README.md` auto-synced to Docker Hub overview via `peter-evans/dockerhub-description@v4`
- Docker Hub org: `terrenefoundation` (DSOS application pending for verified badge + unlimited pulls)
- Image size: ~663MB (full SDK with all extras)

## Consequences

- Users can `docker pull terrenefoundation/kailash` for immediate use
- Every PyPI release automatically produces a matching Docker image
- Docker Hub description stays in sync with `docker/README.md`
