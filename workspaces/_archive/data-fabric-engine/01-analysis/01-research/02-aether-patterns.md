# Patterns from Aether — Prior Art Analysis

## What Aether Built

Aether (`~/repos/dev/aether`) is a full enterprise knowledge management platform on Kailash SDK with a three-layer architecture:

```
Exposure Layer (Nexus)  →  REST API / CLI / MCP
Fabric Layer            →  Agents / Knowledge Graph / Reservoir
Connection Layer        →  7 Adapters / Pipeline / Sync / Encrypt
```

## Patterns Worth Extracting into Fabric Engine

### 1. CanonicalRecord Pipeline

Aether normalizes all ingested data into a `CanonicalRecord` format:

```
Raw Data → classify_record_type() → transform_to_canonical() → validate() → quality_score() → Store
```

**Applicable**: Every fabric needs a canonical intermediate format. The question is how opinionated it should be.

**For fabric engine**: Define a lightweight `FabricRecord` that carries source metadata, content hash, and quality signals without forcing a specific schema.

### 2. Provider Adapter Pattern

Seven adapters (LocalFile, S3, SharePoint, PostgreSQL, REST, Slack, Teams) all implement a common interface with:

- Connection configuration
- Authentication handling
- Incremental sync support (5 cursor types: OFFSET, TOKEN, TIMESTAMP, KEY, COMPOSITE)
- Health checking
- Circuit breaker

**Applicable**: The adapter abstraction is solid. But Aether's adapters are application-specific (they produce Aether-specific records).

**For fabric engine**: Generalize the adapter interface. Each adapter produces `FabricRecord` objects with source-specific metadata. The fabric engine handles the rest.

### 3. Sync Engine with Cursor Types

Five cursor strategies for incremental sync:

1. **OFFSET** — numeric pagination (simple, fragile under concurrent writes)
2. **TOKEN** — opaque continuation token (API-friendly)
3. **TIMESTAMP** — timestamp-based delta (good for databases with `updated_at`)
4. **KEY** — primary key-based (guaranteed no duplicates)
5. **COMPOSITE** — multi-field cursor (complex sources)

**Applicable**: Critical for the fabric's "continuous update" model. Different sources need different sync strategies.

### 4. Backpressure Controller

Adaptive batch sizing based on downstream queue depth:

- Target: 100 items in queue
- Queue > target: reduce batch by 25% (min 50)
- Queue < target × 0.5: increase batch by 25% (max 5000)
- Stable zone: keep current size

**Applicable**: Essential for a fabric that processes heterogeneous sources at different speeds.

### 5. Distributed Locking (Sync Lock)

Redis SETNX with TTL to prevent concurrent syncs of the same connector.

**Applicable**: Fabric engine needs this for concurrent source refresh operations.

### 6. Circuit Breaker

3 failure threshold triggers auto-pause. Protects downstream systems from cascading failures.

**Applicable**: Essential when the fabric connects to unreliable external APIs.

### 7. State Machine for Connector Lifecycle

```
configured → testing → active → paused ↔ error
```

**Applicable**: Every source in the fabric needs lifecycle management.

### 8. Content Hashing for Deduplication

SHA-256 content hashing of every record. Used for dedup and integrity.

**Applicable**: The fabric cache should only update when content actually changes, not on every poll.

## Patterns NOT to Extract

### 1. AI Agents (Quality, Ontology, etc.)

These are Aether-specific enrichment. The fabric engine should be AI-agnostic — it processes and caches data, it doesn't enrich it.

### 2. Knowledge Graph

Application-specific. The fabric engine provides data access, not knowledge modeling.

### 3. Complex Governance (EATP Trust Chains)

Overkill for a fabric engine. Observability and audit logging yes, cryptographic trust chains no.

### 4. In-Memory Stores

Aether uses in-memory stores as a development convenience. The fabric engine should use DataFlow for persistence.

## Architecture Differences

| Aspect         | Aether                        | Fabric Engine               |
| -------------- | ----------------------------- | --------------------------- |
| **Purpose**    | Enterprise knowledge platform | Reusable data access layer  |
| **Sources**    | 7 specific adapters           | Pluggable adapter interface |
| **Processing** | AI agent enrichment           | None — raw data through     |
| **Storage**    | PostgreSQL reservoir          | Cache layer (Redis/memory)  |
| **API**        | 15 custom handlers            | Auto-generated from views   |
| **Scope**      | Application                   | Framework/engine            |
| **Coupling**   | Tightly coupled layers        | Loosely coupled, composable |

## Key Insight

Aether proves the three-layer pattern (connect → process → serve) works. But Aether is an application, not a framework. The fabric engine extracts the **connect** and **serve** layers as a reusable engine, leaving the **process** layer to application code.
