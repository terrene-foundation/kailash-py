# Competitive Landscape — Data Fabric Engines

## The Definitional Boundary

| Concept            | Core Idea                                | Data Movement                         | Query Pattern                     |
| ------------------ | ---------------------------------------- | ------------------------------------- | --------------------------------- |
| **Data Lake**      | Store everything raw, query later        | Copy all data in                      | Schema-on-read, batch             |
| **Data Warehouse** | Store structured, query fast             | ETL transforms in                     | Schema-on-write, SQL              |
| **ETL Pipeline**   | Move data between systems                | Batch/micro-batch copy                | Source-to-target                  |
| **Data Mesh**      | Decentralized ownership, domain-oriented | Each domain publishes data products   | Federated, domain APIs            |
| **Data Fabric**    | Unified access layer across all sources  | Minimal movement — virtualize + cache | Single semantic layer, any source |

**Key differentiator**: A data fabric does NOT require moving data to make it queryable. It virtualizes heterogeneous sources behind a unified semantic layer, uses metadata-driven automation, and caches intelligently for performance without full materialization.

---

## Open-Source Frameworks

### Trino (PrestoSQL)

- **Architecture**: Distributed SQL query engine, 30+ connectors (PostgreSQL, MySQL, S3, MongoDB, Kafka)
- **Caching**: None built-in. Every query hits source. Third-party (Alluxio) adds caching
- **FE consumption**: JDBC/ODBC only. No REST/GraphQL
- **Mid-market fit**: Strong for ad-hoc analytics, weak for app serving. High ops burden

### RisingWave (2022-2026)

- **Architecture**: Cloud-native streaming database. PostgreSQL-compatible. Materialized views update incrementally
- **Caching**: Materialized views ARE the cache. Continuously updated on source events
- **FE consumption**: PostgreSQL wire protocol. Any PG client works
- **TTL vs event-driven**: Event-driven. Sub-second freshness from streaming sources
- **Mid-market fit**: **Closest to our vision** for streaming sources. But weak on files, Excel, REST APIs

### Materialize (acquired by Confluent 2025)

- **Architecture**: Streaming SQL over Timely Dataflow (Rust). Incrementally maintained materialized views
- **Caching**: Same as RisingWave — materialized views
- **FE consumption**: PostgreSQL protocol + SUBSCRIBE for real-time push
- **Mid-market fit**: Architecture pattern is right. Future uncertain post-acquisition

### DuckDB + Polars (2024-2026 trend)

- **Architecture**: In-process analytical engines. DuckDB reads Parquet/CSV/JSON/Excel directly, attaches to PostgreSQL/MySQL
- **Caching**: None. Query engine, not serving layer
- **Mid-market fit**: Excellent for files and local data. No API serving, no CDC, no caching

### Apache Arrow / DataFusion

- **Architecture**: In-memory columnar format (Arrow) + Rust-based query engine (DataFusion)
- **Caching**: Arrow Flight can serve cached data. No built-in TTL/invalidation
- **Mid-market fit**: Building blocks, not a product. Excellent engine for building a fabric

---

## Commercial Platforms

### Denodo — CLOSEST COMPETITOR

- **Architecture**: Pure data virtualization. No data movement. Virtual layer over 40+ source types
- **Caching**: Multi-level — full cache, partial cache, query-level cache
- **Invalidation**: TTL (configurable per view) + event-driven (JMS/Kafka listeners) + "Smart cache"
- **FE consumption**: REST, OData, GraphQL, JDBC/ODBC auto-generated from virtual views
- **Mid-market fit**: **Best-in-class for our problem space.** But commercial, expensive

### Palantir Foundry

- **Architecture**: Ontology-driven. Data modeled as business objects with actions
- **Caching**: Ontology objects materialized and incrementally updated
- **FE consumption**: Workshop (no-code), OSDK (TypeScript SDK from Ontology)
- **Mid-market fit**: **Architecture ideas worth studying** (Ontology = semantic layer). But $1M+ licensing

### Microsoft Fabric

- **Architecture**: Unified SaaS — Power BI + Data Factory + Synapse + Real-Time Intelligence
- **Caching**: DirectLake mode, automatic refresh on data change
- **FE consumption**: REST endpoints, SQL endpoint per Lakehouse
- **Mid-market fit**: Strong for Microsoft shops. Vendor lock-in

### Hasura

- **Architecture**: GraphQL engine over databases. Auto-generates API from schema
- **Caching**: Response TTL caching. Event Triggers for webhook invalidation. Subscriptions for real-time
- **FE consumption**: GraphQL queries/mutations/subscriptions
- **Mid-market fit**: **Strong for database-only scenarios.** But no file/API/cloud source support

### Supabase

- **Architecture**: PostgreSQL + PostgREST + Realtime + Auth + Storage
- **Caching**: None. PostgREST hits PG directly. Realtime via WebSocket
- **Mid-market fit**: Excellent DX, PG-only. Not a fabric

---

## Competitive Matrix

| Solution         | Open Source | Virtualization | Caching           | Real-time  | FE-Ready API   | Heterogeneous Sources | Mid-Market         |
| ---------------- | ----------- | -------------- | ----------------- | ---------- | -------------- | --------------------- | ------------------ |
| Trino            | Yes         | Federation     | No                | No         | No (JDBC)      | Strong (DBs)          | Moderate           |
| **Denodo**       | No          | Best-in-class  | Yes (multi-level) | Partial    | Yes (REST/GQL) | **Best**              | Strong             |
| RisingWave       | Yes         | Partial        | Yes (mat. views)  | Yes        | Partial (PG)   | Weak                  | Strong potential   |
| Materialize      | Partial     | Partial        | Yes               | Yes        | Yes (PG+SUB)   | Weak                  | Uncertain          |
| Microsoft Fabric | No          | Partial        | Partial           | Yes        | Partial        | Moderate              | Strong (MS)        |
| Palantir         | No          | Yes            | Yes               | Partial    | Yes (OSDK)     | Strong                | Poor (cost)        |
| Hasura           | Yes         | No             | TTL only          | Yes (subs) | Yes (GQL)      | No (DB only)          | Strong             |
| Supabase         | Yes         | No             | No                | Partial    | Yes (REST)     | No (PG only)          | Strong             |
| DuckDB/Polars    | Yes         | Partial        | No                | No         | No             | Moderate              | Strong (analytics) |

---

## The Gap

**No existing solution provides ALL of:**

1. True heterogeneous source virtualization (files, APIs, databases, cloud storage)
2. Continuous cache materialization (not just on-demand)
3. Event-driven + TTL hybrid invalidation
4. Simple FE consumption (REST/GraphQL endpoints, not JDBC/SQL)
5. Mid-market accessible (not $1M+ license, not 10-person ops team)
6. Open-source or source-available

Denodo comes closest on 1-4 but fails on 5-6. RisingWave/Materialize come closest on 2-4 but fail on 1. DuckDB/Polars handle 1 but have no caching or serving layer.

**This is the gap a Kailash Data Fabric Engine fills.**
