# Competitor-Informed Design Refinements

Applied after deep research into Hasura, Supabase, Denodo, Prefect/Dagster, Redis patterns, and SSE/WebSocket state-of-the-art.

---

## 1. Real-Time Push: SSE Over HTTP/2 (Not WebSocket)

**Previous design**: "WebSocket push for real-time product updates (future)"

**Revised**: SSE over HTTP/2 for server→client push when cache updates.

```
GET /fabric/_events (SSE endpoint)

event: product_updated
data: {"product": "dashboard", "cached_at": "2026-04-02T14:30:00Z"}

event: source_health
data: {"source": "crm", "health": "unhealthy", "since": "2026-04-02T14:28:00Z"}

event: product_updated
data: {"product": "dashboard", "cached_at": "2026-04-02T14:35:00Z"}
```

**FE usage**:

```typescript
const events = new EventSource("/fabric/_events");

events.addEventListener("product_updated", (e) => {
  const data = JSON.parse(e.data);
  queryClient.invalidateQueries({ queryKey: ["fabric", data.product] });
});

events.addEventListener("source_health", (e) => {
  const data = JSON.parse(e.data);
  // Show/hide degraded source banner
});
```

**Why SSE over WebSocket** (per WunderGraph 2025 analysis):

- Standard HTTP — auth middleware works unchanged (no WS upgrade bypass)
- HTTP/2 multiplexes SSE streams over one TCP connection
- No custom protocol (no `graphql-ws` operation IDs)
- `EventSource` API has built-in auto-reconnection
- Simpler load balancer configuration (no WS upgrade)

**Implementation**: When `PipelineExecutor` performs an atomic cache swap, it publishes a `product_updated` event to all connected SSE clients. When `ChangeDetector` updates source health, it publishes a `source_health` event.

---

## 2. Cache Serialization: MessagePack (Not JSON)

**Previous design**: `json.dumps(result, default=str, sort_keys=True)`

**Revised**: MessagePack for cache storage. JSON for HTTP responses.

```python
import msgpack

async def _update_cache(self, product_name: str, result: Any, trace: PipelineTrace):
    # Serialize with msgpack for cache storage (6x faster, 30% smaller)
    serialized = msgpack.packb(result, default=str, use_bin_type=True)
    content_hash = hashlib.sha256(serialized).hexdigest()

    # ... hash comparison, Lua script atomic write ...

    # Redis stores msgpack bytes, not JSON strings

async def _serve_materialized(self, product_name: str, request):
    # Read msgpack bytes from cache
    raw = await self._cache.get(f"fabric:data:{product_name}")

    # Deserialize to Python dict
    result = msgpack.unpackb(raw, raw=False)

    # Serialize to JSON for HTTP response (FE expects JSON)
    body = json.dumps(result, default=str)

    return Response(status_code=200, body=body, headers={...})
```

**Why MessagePack**:

- 6x faster than JSON for serialize/deserialize
- 30% smaller wire format (less Redis memory, less network)
- Binary format — handles bytes natively (no base64 encoding)
- Widely supported (Python `msgpack`, JS `msgpack-lite`)

**Tradeoff**: Cache data is not human-readable in Redis CLI. Acceptable — use `/fabric/_trace` for debugging, not Redis CLI.

**Dependency**: `msgpack >= 1.0` added to `[fabric]` optional extra.

---

## 3. Redis Storage: Hash for Metadata, String for Data

**Previous design**: Three separate Redis String keys per product (data, hash, metadata).

**Revised**: One Redis Hash per product for metadata. One Redis String for data (binary msgpack).

```
Redis structure per product:

  fabric:data:dashboard           → msgpack bytes (the cached product result)
  fabric:meta:dashboard           → Redis Hash {
                                       cached_at: "2026-04-02T14:30:00Z"
                                       pipeline_ms: "847"
                                       trigger: "source_change:crm"
                                       content_hash: "a1b2c3..."
                                       mode: "materialized"
                                   }
```

**Why Hash for metadata**:

- Individual fields readable without deserializing entire blob
- Health endpoint reads `cached_at` + `pipeline_ms` without loading product data
- Redis Hash with < 128 entries uses listpack encoding (5-10x memory savings)
- `HGET fabric:meta:dashboard cached_at` is O(1)

**Why String for data** (not Hash):

- Product data is arbitrary shape — not flat key-value
- MessagePack binary format doesn't map to Hash fields
- Single GET/SET is simpler than HGETALL/HMSET for the main data

**Lua script updated**:

```lua
-- Atomic cache update: data (string) + metadata (hash)
redis.call('SET', KEYS[1], ARGV[1])           -- fabric:data:{product}
redis.call('HSET', KEYS[2],
    'cached_at', ARGV[2],
    'pipeline_ms', ARGV[3],
    'trigger', ARGV[4],
    'content_hash', ARGV[5],
    'mode', ARGV[6]
)
return 1
```

---

## 4. Batch Product Reads: Redis MGET

**New optimization**: When FE loads a page with multiple products, batch the Redis reads.

```
GET /fabric/_batch?products=dashboard,users,notifications
```

Instead of 3 sequential Redis GETs, the fabric issues one `MGET`:

```python
async def _serve_batch(self, product_names: list[str], request):
    keys = [f"fabric:data:{name}" for name in product_names]
    results = await self._cache.mget(keys)  # Single Redis roundtrip

    # Also batch metadata reads
    pipe = self._cache.pipeline()
    for name in product_names:
        pipe.hgetall(f"fabric:meta:{name}")
    metas = await pipe.execute()

    # Build response
    return Response(
        status_code=200,
        body=json.dumps({
            name: msgpack.unpackb(data, raw=False) if data else None
            for name, data in zip(product_names, results)
        }),
        headers={
            "X-Fabric-Freshness": self._aggregate_freshness(metas),
            "X-Fabric-Mode": "batch",
        },
    )
```

**FE usage**:

```typescript
function useFabricBatch(products: string[]) {
  return useQuery({
    queryKey: ["fabric-batch", products],
    queryFn: () => api.get(`/fabric/_batch?products=${products.join(",")}`),
    staleTime: 60_000,
  });
}

// Load dashboard page with one request
const { data } = useFabricBatch(["dashboard", "users", "notifications"]);
```

**Why this matters**: A dashboard page typically shows 3-8 data products. Without batching, that's 3-8 sequential HTTP requests + 3-8 Redis GETs. With batching: 1 HTTP request + 1 Redis MGET.

---

## 5. Debounce Timers: Redis-Based (Survives Leader Failover)

**Previous design**: In-memory `asyncio.TimerHandle` per product.

**Problem**: If leader dies, all pending debounce timers are lost.

**Revised**: Redis-based debounce using sorted sets.

```python
async def _enqueue_debounced(self, product_name: str, trigger: str):
    """Enqueue a pipeline execution with Redis-based debounce."""
    debounce_key = f"fabric:debounce:{product_name}"
    debounce_seconds = self._products[product_name].write_debounce.total_seconds()
    execute_at = time.time() + debounce_seconds

    # ZADD with NX — only set if no existing timer
    # If timer exists, it keeps the earlier execute_at (first trigger wins)
    # If timer doesn't exist, set new one
    await self._cache.zadd(
        "fabric:debounce_queue",
        {product_name: execute_at},
        nx=True,  # Don't overwrite if exists — keeps earliest trigger
    )

async def _debounce_consumer(self):
    """Background task that processes debounced pipeline executions."""
    while not self._shutting_down:
        # Get products whose debounce window has expired
        now = time.time()
        ready = await self._cache.zrangebyscore(
            "fabric:debounce_queue", "-inf", now
        )

        for product_name in ready:
            # Remove from queue and execute
            removed = await self._cache.zrem("fabric:debounce_queue", product_name)
            if removed:  # Only execute if we won the race
                await self._pipeline_executor.execute(
                    product_name, trigger="debounced"
                )

        await asyncio.sleep(0.5)  # Check every 500ms
```

**Why Redis-based debounce**:

- Survives leader failover (debounce state in Redis, not in-memory)
- Works across multiple workers (sorted set is shared)
- Race-safe (ZREM returns whether we removed it — only the winner executes)

---

## 6. Hasura-Inspired Change Detection for Database Sources

**Insight from Hasura**: Instead of `SELECT MAX(updated_at)` (which misses DELETEs), use a change counter.

```python
class DatabaseSourceAdapter(BaseSourceAdapter):
    async def detect_change(self) -> bool:
        """Detect changes using a lightweight change counter.

        Three strategies, tried in order:
        1. Change counter table (fastest, if available)
        2. MAX(updated_at) (fast, misses deletes)
        3. COUNT(*) (slowest, catches everything)
        """
        if self._has_change_counter:
            # Best: application maintains a change_counter table
            # Any write increments the counter. One SELECT to detect.
            row = await self._db_query(
                "SELECT counter FROM _fabric_changes WHERE table_name = ?",
                [self._table_name]
            )
            counter = row["counter"] if row else 0
            if counter != self._last_counter:
                self._last_counter = counter
                return True
            return False

        elif self._has_updated_at:
            # Good: check MAX(updated_at)
            row = await self._db_query(
                f"SELECT MAX(updated_at) as max_ts FROM {self._table_name}"
            )
            max_ts = row["max_ts"]
            if max_ts != self._last_max_ts:
                self._last_max_ts = max_ts
                return True
            return False

        else:
            # Fallback: check COUNT(*)
            row = await self._db_query(
                f"SELECT COUNT(*) as cnt FROM {self._table_name}"
            )
            cnt = row["cnt"]
            if cnt != self._last_count:
                self._last_count = cnt
                return True
            return False
```

**Optional enhancement**: Fabric can auto-create a `_fabric_changes` table in the primary database. Express write hooks increment the counter. This gives Hasura-like change detection speed (one SELECT, catches all mutations including deletes) without WAL/CDC complexity.

---

## Summary: What Changed From Competitor Research

| Area                | Before                       | After                                       | Source                           |
| ------------------- | ---------------------------- | ------------------------------------------- | -------------------------------- |
| Real-time push      | WebSocket (future)           | SSE over HTTP/2                             | WunderGraph, The Guild           |
| Cache serialization | JSON                         | MessagePack (6x faster)                     | Redis best practices             |
| Cache metadata      | Separate JSON string         | Redis Hash (listpack, 5-10x memory)         | Redis documentation              |
| Multi-product reads | N sequential GETs            | MGET batch endpoint                         | Hasura multiplexed subscriptions |
| Debounce timers     | In-memory (lost on failover) | Redis sorted set (durable)                  | Prefect/Dagster orchestration    |
| DB change detection | MAX(updated_at) only         | Change counter table + MAX + COUNT fallback | Hasura event_log pattern         |
