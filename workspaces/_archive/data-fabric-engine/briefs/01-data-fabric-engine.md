# Data Fabric Engine — Brief

## Problem Statement

Three core problems observed in enterprise frontend-backend data architectures:

### 1. Frontend Direct Call Chaos

Frontend applications make direct calls to multiple backend services, APIs, and data sources. During development, things get missed — inconsistent error handling, missing fields, stale data, race conditions between calls. The FE becomes tightly coupled to backend implementation details.

**Solution**: FE consumes ONLY from fabric endpoints. One unified surface.

### 2. Heterogeneous Source Management

Backend logic for managing data sources — local files, Excel spreadsheets, cloud storage (S3, GCS), REST APIs, databases (PostgreSQL, MongoDB), SaaS integrations — is scattered across the application. Each source has its own connection logic, error handling, transformation, and caching strategy.

**Solution**: All source management lives in the fabric. Sources are registered, connectors handle ingestion, and the fabric normalizes everything into a unified data model.

### 3. TTL-Based Caching Is Wrong

Current caching approaches use TTL (time-to-live) which forces a trade-off: short TTL = frequent refetches = users wait; long TTL = stale data. Neither is acceptable.

**Solution**: The fabric operates asynchronously. Data pipelines poll or listen for changes in real-time. Cache is updated ONLY when the data pipeline succeeds — never with partial or failed data. FE reads from cache by default. Fabric pre-warms cache on startup. Users never wait for data to appear.

## Vision

A **Data Fabric Engine** — a reusable framework (not an application) that any Kailash SDK project can use to:

1. Register heterogeneous data sources (DB, API, file, cloud, Excel)
2. Define data products (materialized views over source data)
3. Continuously process and cache data products asynchronously
4. Expose data products as endpoints for frontend consumption
5. Pre-warm on startup so users never see loading states for known data

## Key Question

Should this be part of `kailash-dataflow` or a separate `kailash-fabric` package?

## Prior Art

- `~/repos/dev/aether` — Enterprise knowledge platform with a fabric layer (connection + fabric + exposure architecture)
- Aether's fabric layer includes: 7 source adapters, 6 AI agents, knowledge graph, reservoir, supervisor orchestration
- Aether's architecture validates the concept but is application-specific, not a reusable engine
