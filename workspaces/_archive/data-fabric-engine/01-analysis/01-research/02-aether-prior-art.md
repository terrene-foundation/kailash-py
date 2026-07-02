# Aether Prior Art Analysis

## Overview

Aether (`~/repos/dev/aether`) is an enterprise knowledge management platform built on Kailash SDK. It implements a three-layer architecture: Connection → Fabric → Exposure.

This analysis extracts what is reusable as a generic engine versus what is application-specific.

---

## Aether's Architecture (What Exists)

```
┌─────────────────────────────────────────┐
│     Exposure Layer (Nexus)              │
│  15 handlers, REST + CLI + MCP          │
│  JWT auth, 8 RBAC roles                 │
└─────────────────────────────────────────┘
           │
┌─────────────────────────────────────────┐
│      Fabric Layer (DataFlow + Kaizen)   │
│  6 AI Agents + Knowledge Graph          │
│  Reservoir (5 DataFlow models)          │
│  Document Processing Pipeline           │
└─────────────────────────────────────────┘
           │
┌─────────────────────────────────────────┐
│   Connection Layer (Core SDK)           │
│  7 Adapters (local, S3, SharePoint,     │
│  PostgreSQL, REST, Slack, Teams)        │
│  Sync Engine, Circuit Breaker           │
└─────────────────────────────────────────┘
```

---

## What Is Reusable (Engine-Level Concepts)

### 1. Source Connector Architecture

- **ProviderAdapter interface** — standardized connect/fetch/sync per source
- **7 adapters** — local file, S3, SharePoint, PostgreSQL, REST, Slack, Teams
- **State machine** — configured → testing → active → paused ↔ error
- **Sync engine** — 5 cursor types (OFFSET, TOKEN, TIMESTAMP, KEY, COMPOSITE)
- **Circuit breaker** — 3-failure threshold auto-pause
- **Distributed locking** — Redis SETNX for concurrent sync prevention

### 2. Data Normalization

- **CanonicalRecord** — normalized record format for all sources
- **Pipeline**: raw → classify → transform → validate → quality score → load
- **Content hashing** — SHA-256 for deduplication

### 3. Background Processing

- **Celery worker** — 4 queues (default, connectors, agents, documents)
- **Scheduled tasks** — health checks, cleanup
- **Backpressure controller** — adaptive batch sizing (min=50, max=5000)

### 4. Caching Patterns

- **Redis** — sync locks (SETNX), Celery broker/results
- **TanStack Query** — 30s stale time on frontend
- **Note**: Aether does NOT implement the "fabric-first caching" pattern — FE still calls API which hits DB

### 5. Multi-Tenancy

- `tenant_id` on all models, query-level isolation

---

## What Is Application-Specific (NOT Reusable)

### 1. AI Agents (quality, ontology, structure, insight, lineage, security)

- These are Aether-specific business logic
- A fabric engine should NOT include AI enrichment agents
- Instead: provide hooks for user-defined transformation/enrichment

### 2. Knowledge Graph

- OntologyEntity, OntologyRelationship, KnowledgeNode, KnowledgeEdge
- This is an Aether domain model, not a fabric concept

### 3. Document Processing Pipeline

- OCR, chunking, embedding — RAG-specific
- Not part of a data fabric engine

### 4. RBAC / Auth / SSO

- Application-level concerns
- Fabric engine should be auth-agnostic (integrate with whatever auth the app uses)

### 5. Governance (trust chains, audit, attestation)

- Uses CARE/EATP — this is application governance, not fabric governance
- Fabric engine may need its own lightweight governance (lineage, quality scores)

---

## Key Lessons from Aether

### What Aether Got Right

1. **Source adapter abstraction** — the ProviderAdapter interface is clean and extensible
2. **State machine for connectors** — lifecycle management prevents half-configured sources
3. **Backpressure control** — adaptive batch sizing prevents downstream overwhelm
4. **Multi-tenant isolation** — built into the data model, not bolted on

### What Aether Got Wrong (for a fabric engine)

1. **No cache-first serving** — FE calls API → API hits DB → returns. No pre-warming, no cache-only reads
2. **TTL-based caching** — TanStack Query 30s stale time is exactly the problem we want to solve
3. **Tight coupling** — fabric agents are wired to Aether domain models, not pluggable
4. **No data product concept** — data is in reservoir tables, not in defined "products" that the fabric serves

### The Missing Piece in Aether

Aether has the plumbing (connectors, pipeline, reservoir) but NOT the **fabric serving layer** — the component that:

- Defines data products from source data
- Materializes them into cache
- Serves them as endpoints
- Pre-warms on startup
- Updates cache only on successful pipeline completion

This is exactly what the Data Fabric Engine needs to be.
