# Design Patterns for the Fabric Engine

## Core Design Decisions

### 1. Cache Granularity

| Level             | Description               | Invalidation                               | Memory | Fit          |
| ----------------- | ------------------------- | ------------------------------------------ | ------ | ------------ |
| **Row-level**     | Redis hash per entity     | Fine-grained (update one row)              | High   | Hot entities |
| **Query-level**   | Cache per query signature | Must know which queries a change affects   | Medium | Read-heavy   |
| **Product-level** | Cache per data product    | Invalidate product when any source changes | Low    | Best balance |

**Recommendation**: **Product-level materialization** with optional row-level cache for hot paths.

A "data product" is a defined view over one or more sources. When any source changes, the product is re-materialized. This is the RisingWave/Materialize pattern applied to heterogeneous sources.

### 2. Invalidation Strategy

| Strategy       | How                                   | Works For                  | Doesn't Work For                  |
| -------------- | ------------------------------------- | -------------------------- | --------------------------------- |
| **CDC**        | Listen to database WAL                | Databases with CDC support | REST APIs, files                  |
| **Webhook**    | Source pushes change events           | APIs with webhook support  | Files, databases without triggers |
| **Polling**    | Periodic fetch + content hash compare | Everything                 | Real-time freshness               |
| **File watch** | OS-level file system events           | Local files                | Cloud storage                     |

**Recommendation**: **Hybrid strategy** per source type.

```python
# Source type → invalidation strategy (auto-selected)
STRATEGIES = {
    "database":   CDCStrategy,      # Listen to WAL/binlog
    "rest_api":   PollStrategy,     # Poll + content hash
    "file":       WatchStrategy,    # fsnotify/watchdog
    "cloud":      PollStrategy,     # S3 list + etag compare
    "excel":      WatchStrategy,    # File watch on .xlsx
    "webhook":    WebhookStrategy,  # Source pushes events
    "stream":     StreamStrategy,   # Continuous consumption
}
```

### 3. Cache Update Flow (The Key Innovation)

```
Source Change Detected
       │
       ▼
Pipeline Triggered (async)
       │
       ├── Fetch from source
       │       │
       │       ▼
       ├── Transform (optional user hooks)
       │       │
       │       ▼
       ├── Validate (optional)
       │       │
       │       ▼
       ├── Content hash compare
       │       │
       │  ┌────┴────┐
       │  │ Changed? │
       │  └────┬────┘
       │   No  │  Yes
       │   │   │
       │   │   ▼
       │   │  Write to cache (atomic swap)
       │   │   │
       │   │   ▼
       │   │  Notify subscribers (optional)
       │   │
       │   ▼
       │  Skip (no-op)
       │
       ▼
Pipeline complete
```

**Key guarantees**:

1. **Cache never contains partial data** — atomic swap on success only
2. **Cache never contains failed pipeline data** — failure = keep old cache
3. **Content hash prevents redundant updates** — no change = no write
4. **FE always reads from cache** — never from source directly

### 4. Pre-Warming Strategy

On startup:

```
1. Read product definitions
2. For each product:
   a. Check if cache exists (Redis/memory)
   b. If cache exists and not expired: use it (instant startup)
   c. If no cache: trigger immediate pipeline (blocking first request)
3. Start source watchers/pollers (async, non-blocking)
4. Fabric ready — all products servable from cache
```

**Warm cache persistence**: Cache survives restarts if backed by Redis. Memory-backed cache requires re-warming.

### 5. FE Consumption Model

```
Frontend Request
       │
       ▼
Fabric Endpoint (auto-generated)
       │
       ├── Read from cache
       │       │
       │  ┌────┴─────────┐
       │  │ Cache exists? │
       │  └────┬─────────┘
       │   Yes │  No (cold start only)
       │   │   │
       │   │   ▼
       │   │  Return 202 + trigger pipeline
       │   │  (or block if pre-warm enabled)
       │   │
       │   ▼
       │  Return 200 + cached data
       │  + X-Fabric-Freshness: <timestamp>
       │  + X-Fabric-Source: cache
       │
       ▼
Response to FE
```

**Headers** the fabric adds:

- `X-Fabric-Freshness` — when the data was last refreshed
- `X-Fabric-Source` — `cache` (normal) or `pipeline` (cold start fallback)
- `X-Fabric-Product` — name of the data product

### 6. The Semantic Layer (Learning from Palantir)

Instead of raw source data, fabric serves **data products** — named, versioned, typed views:

```python
@fabric.product("active_users")
async def active_users(ctx: FabricContext) -> list[dict]:
    """Active users with their recent activity."""
    users = await ctx.source("users_db").list(filter={"active": True})
    activity = await ctx.source("activity_api").fetch()

    # Join in Python (fabric does the composition)
    for user in users:
        user["last_activity"] = next(
            (a for a in activity if a["user_id"] == user["id"]), None
        )
    return users
```

The product function:

- Receives a `FabricContext` with access to all registered sources
- Returns the materialized data
- Is re-executed when any referenced source changes
- Result is cached and served via auto-generated endpoint

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Serving Layer                             │
│   Auto-generated REST endpoints via Nexus                   │
│   GET /fabric/<product>  →  returns cached data             │
│   WebSocket /fabric/ws   →  push updates (optional)         │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                    Cache Layer                               │
│   Product-level cache (Redis or in-memory)                  │
│   Atomic swap on pipeline success                           │
│   Content hash dedup                                        │
│   Pre-warming on startup                                    │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                    Pipeline Layer                            │
│   Async pipeline runner (per source or per product)         │
│   Backpressure controller                                   │
│   Circuit breaker per source                                │
│   Content hash comparison (skip if unchanged)               │
│   User transform hooks (optional enrichment)                │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                    Source Layer                              │
│   Pluggable source adapters                                 │
│   Database (via DataFlow)  │  REST API  │  File/Excel       │
│   Cloud Storage (S3/GCS)   │  Stream    │  Custom           │
│   Each source has:                                          │
│   - Connection config                                       │
│   - Invalidation strategy (CDC/poll/watch/webhook)          │
│   - State machine (configured → active → paused → error)   │
│   - Health check                                            │
│   - Circuit breaker                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Design Principles

1. **Cache-first, always** — FE reads from cache. Source fetches happen in background pipelines.
2. **Atomic updates** — Cache is updated only on successful pipeline completion. Never partial data.
3. **Content-aware** — Content hash comparison skips redundant cache writes.
4. **Hybrid invalidation** — CDC for databases, polling for APIs, file watch for files. Auto-selected per source type.
5. **Declarative products** — Users define WHAT data they want, not HOW to fetch it.
6. **Zero-config possible** — Register sources, define products, start. Fabric handles the rest.
7. **Progressive complexity** — Simple cases are simple. Complex cases (transforms, multi-source joins) are possible.
