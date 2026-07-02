---
type: CONNECTION
date: 2026-04-02
created_at: 2026-04-02T21:00:00+08:00
author: agent
session_turn: 17
project: data-fabric-engine
topic: Competitor runtime architectures validate and refine fabric design choices
phase: analyze
tags: [competitors, hasura, supabase, denodo, redis, sse, runtime]
---

# Connection: Competitor Patterns Inform Fabric Design

## Finding

Deep research into Hasura, Supabase, Denodo, Prefect/Dagster, and Redis patterns reveals that our fabric design is architecturally sound but should adopt three specific optimizations from competitors.

## Connections

### 1. Hasura Validates Our Poll-Based Architecture

Hasura's event triggers are NOT push-based internally. They poll an `event_log` table every 1 second with a configurable batch size (100 default). Their subscriptions are multiplexed polling — 1000 subscribers produce 10 SQL queries with batch=100, not 1000 queries.

**Connection to fabric**: Our poll-loop design (`poll_interval` per source) is architecturally equivalent to how Hasura works under the hood. The difference is we poll external sources, they poll an internal table. The approach is proven at scale (Hasura handles 1M live queries at 28% PG CPU load).

### 2. SSE Over HTTP/2 Should Replace WebSocket for Push Updates

WunderGraph's 2025 analysis and The Guild's `graphql-sse` library demonstrate that SSE over HTTP/2 is superior to WebSocket for server-push:

- Standard HTTP — existing auth/CORS/logging middleware works unchanged
- HTTP/2 multiplexes SSE streams over one TCP connection (same benefit as WS)
- No custom protocol (no `graphql-ws` operation ID tracking)
- Auto-reconnection built into browser `EventSource` API
- No load balancer upgrade complexity

**Connection to fabric**: If we add real-time push (notify FE when cache updates), use SSE over HTTP/2, not WebSocket. Simpler for operators, better for middleware compatibility.

### 3. Redis Serialization Should Use MessagePack, Not JSON

Research shows MessagePack is 6x faster than JSON for serialization/deserialization. Redis Hash with listpack encoding (< 128 entries, < 64 bytes per value) saves 5-10x memory vs string keys.

**Connection to fabric**: Product cache should use MessagePack for serialization (not `json.dumps`). Product metadata (freshness, pipeline duration) should be stored as Redis Hash fields, not as a separate JSON string. This improves both read latency and memory efficiency.

### 4. Denodo's Cache Is a Database, Not In-Memory

Denodo caches into PostgreSQL/Oracle/MySQL tables, not Redis or in-memory. Cache reads are SQL queries against a local database.

**Connection to fabric**: Our Redis-based approach is faster for reads (sub-ms vs SQL query latency). But Denodo's approach handles very large cached datasets (hundreds of GB) that wouldn't fit in Redis. Our `max_product_size` limit (10MB) is the right trade-off — products that exceed it should use `mode="virtual"` (pass-through, no cache).

### 5. Dagster's User Code Isolation Is Worth Noting

Dagster runs user code (asset/op definitions) in a separate gRPC process. User code crashes don't take down the control plane.

**Connection to fabric**: Our product functions run in-process. A crash in a product function is caught by the supervised task wrapper — it doesn't kill the fabric runtime. But for truly untrusted code (future plugin system), process isolation would be needed. Not for v1.

## Design Refinements

| Area                | Current Design                    | Refined By                                   |
| ------------------- | --------------------------------- | -------------------------------------------- |
| Real-time FE push   | Mentioned as "WebSocket (future)" | SSE over HTTP/2 — simpler, standard HTTP     |
| Cache serialization | `json.dumps(result)`              | MessagePack — 6x faster, 30% smaller         |
| Cache storage       | Redis String per product          | Redis Hash for metadata, String for data     |
| Pipeline debounce   | In-memory timer                   | Redis-based timer (survives leader failover) |

## For Discussion

1. Should MessagePack be a hard dependency of the fabric, or should serialization be pluggable (JSON default, MessagePack opt-in)?
2. SSE requires HTTP/2 for the "no connection limit" benefit. Should the fabric require HTTP/2, or support both HTTP/1.1 (with the 6-connection browser limit) and HTTP/2?
3. Hasura's batch-100 multiplexed subscription approach is clever — could we batch multiple product reads into a single Redis MGET? If FE loads a dashboard with 5 products simultaneously, one MGET is better than 5 GETs.
