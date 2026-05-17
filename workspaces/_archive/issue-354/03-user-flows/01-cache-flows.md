# Issue #354 — Cache Flow Diagrams

Three flows that change materially between the current (broken) state and the post-fix state.

## Flow 1: Single-process dev mode — UNCHANGED

```
Developer:  db = DataFlow("sqlite:///./dev.db")          # no redis_url
            await db.start(dev_mode=True)

FabricRuntime.start()
  └── PipelineExecutor(
        dataflow=db,
        redis_url=None,
        dev_mode=True,
      )
        └── _cache = InMemoryFabricCacheBackend()   # LRU OrderedDict

User request → serving.py
  └── await pipeline.get_cached(name)
        └── await _cache.get(key)            # OrderedDict lookup, no await
```

**Post-fix behavior**: Identical to today for the "no redis" case. Zero behavior change for dev users. The only observable difference is a new log line at `PipelineExecutor.__init__`: `"Fabric cache backend: in-memory (reason: redis_url not provided)"`.

## Flow 2: Multi-replica production with `redis_url` — BROKEN → FIXED

### Current (broken)

```
Replica A:
  db = DataFlow("postgresql://prod", redis_url="redis://prod-cache:6379/0")
   └── DataFlow.__init__() stores redis_url for Express, NOT for self._redis_url
   └── engine.py:2018 hasattr(self, '_redis_url') → FALSE (never assigned)
   └── db.start() resolves redis_url from config → maybe NONE if user only passed kwarg
   └── FabricRuntime(redis_url=X or None)
        └── PipelineExecutor(redis_url=X) → stores and IGNORES
              └── _cache_data = OrderedDict()          # in-memory, per-replica

Replica B: (identical — separate OrderedDict, separate leader, separate everything)

User request hits replica B:
  └── serving.py → pipeline.get_cached("products_by_region")
        └── OrderedDict.get(key) → None                # cold cache on this replica
        └── 202 "warming" response
        └── OR blocking pipeline re-execution if on-demand

Replica A was warm. Replica B cold. User sees inconsistent latency.
Redis is provisioned, paid for, and idle.
```

### Post-fix

```
Replica A:
  db = DataFlow("postgresql://prod", redis_url="redis://prod-cache:6379/0")
   └── DataFlow.__init__() stores self._redis_url = redis_url          # NEW
   └── db.start() resolves redis_url → "redis://prod-cache:6379/0"
   └── FabricRuntime(redis_url=X)
        └── _get_or_create_redis_client() → redis.asyncio.Redis         # NEW helper
        └── PipelineExecutor(cache_backend=RedisFabricCacheBackend(client))
              └── _cache = RedisFabricCacheBackend
        └── WebhookReceiver(redis_client=client)                        # NEW wiring
              └── _nonce_backend = _RedisNonceBackend(client)           # was always
                                                                          silently
                                                                          in-memory

Replica A (leader): _prewarm_products()
  └── For each materialized product:
        └── await pipeline.execute_product(...)
              └── data = await product_fn(context)
              └── data_bytes = _serialize(data)
              └── new_hash = _content_hash(data_bytes)
              └── old_hash = await _cache.get_hash(key)                 # HGET
              └── if old_hash == new_hash: skip_unchanged                # no write
              └── else: await _cache.set(key, data_bytes, new_hash, meta) # HMSET + EXPIRE

Replica B (follower): _prewarm_products()
  └── NEW branch: if not self._leader.is_leader:
        └── await pipeline.warm_from_cache()                            # NEW
              └── For each materialized product:
                    └── entry = await _cache.get(key)                   # HGETALL
                    └── if entry: record in local trace, NO execution
                    └── else: skip (serving layer returns 202 on miss)
        └── Follower start completes in < 10s — no pipeline work
  └── Container Apps startup probe PASSES

User request hits replica B:
  └── serving.py → await pipeline.get_cached("products_by_region", tenant_id=req.tenant)
        └── await _cache.get("fabric:product:prod:tenant42:products_by_region")
        └── HGETALL → hit
        └── Return data_bytes + metadata
        └── Serving layer computes staleness from metadata.cached_at
        └── Respond 200 with freshness header

Webhook arrives at replica B:
  └── WebhookReceiver._handle_delivery
        └── _RedisNonceBackend.contains(delivery_id)                   # cross-replica
        └── If replica A already processed it → return 200, skip       # NEW: dedup works
```

## Flow 3: Multi-tenant product — LATENT DATA LEAK → SAFE

### Current (latent bug; becomes active data leak post-naive-fix)

```
Tenant X request: GET /fabric/my_product
  └── _cache_key("my_product", params={"region": "EU"})
  └── key = "my_product:{\"region\": \"EU\"}"                  # NO TENANT DIMENSION
  └── Hits in-memory cache
  └── Returns tenant X's data

Tenant Y request: GET /fabric/my_product?region=EU
  └── Same _cache_key → same key
  └── Hits in-memory cache
  └── Returns TENANT X's DATA to tenant Y     # SILENT DATA LEAK
```

Today this is masked in practice because:

1. Tenant dispatch usually happens at a higher layer (Nexus middleware) before hitting fabric.
2. Each process has its own in-memory cache, so the collision radius is small.

**Once #354 naive fix lands without tenant partitioning**: the Redis cache is shared across all replicas, all tenants, all products. The collision radius becomes the entire deployment. Any product declared `multi_tenant=True` (which `products.py:52,111` says should be "partitioned per tenant") would leak cross-tenant.

### Post-fix (correct)

```
Tenant X request: GET /fabric/my_product
  └── Middleware extracts tenant_id = "X" from request
  └── await pipeline.get_cached("my_product", params={"region": "EU"}, tenant_id="X")
  └── _cache_key → "my_product:X:{params_hash_16}"
  └── Redis key: fabric:product:prod:X:my_product:{params_hash_16}
  └── HGETALL → tenant X's data

Tenant Y request: GET /fabric/my_product?region=EU
  └── Middleware extracts tenant_id = "Y"
  └── await pipeline.get_cached("my_product", params={"region": "EU"}, tenant_id="Y")
  └── _cache_key → "my_product:Y:{params_hash_16}"
  └── Redis key: fabric:product:prod:Y:my_product:{params_hash_16}
  └── HGETALL → MISS → pipeline executes for tenant Y's scope
  └── Returns tenant Y's data

Enforcement:
  └── If a product is declared `multi_tenant=True` and no tenant_id is provided to get_cached,
      pipeline.get_cached RAISES FabricTenantRequiredError.
  └── This is a hard failure, not a silent cross-tenant hit. Loud breakage > silent leak.
```

## Flow 4: Startup race — follower before leader finishes prewarm

### Current

```
t=0s   Replica A starts, elects leader
t=0s   _prewarm_products begins (serial, 26 products × 10s each = 260s)
t=30s  Replica B starts (rolling deploy)
t=30s  Replica B skips prewarm (not leader)
t=30s  Replica B's serving layer is LIVE
t=30s  First user request hits replica B
t=30s  pipeline.get_cached(name) → None (cold OrderedDict, per-replica)
t=30s  Serving layer returns 202 "warming"
t=30s…240s  Every request hitting B returns 202
t=240s Container Apps startup probe timeout on replica B
t=240s Replica B killed and restarted
t=240s…∞ Crash loop
```

### Post-fix

```
t=0s   Replica A starts, elects leader
t=0s   _prewarm_products begins (serial, 26 × 10s = 260s), writes to Redis
t=30s  Replica B starts (rolling deploy)
t=30s  Replica B skips leader election (A holds the lock)
t=30s  Replica B enters follower-prewarm branch
t=30s  for product in materialized_products: await _cache.get(key)  # ~1ms each
t=30.5s Follower prewarm done. Local trace recorded for N found entries.
t=30.5s Serving layer LIVE
t=30.5s First user request hits replica B:
       └── await pipeline.get_cached(name)
       └── HGETALL → HIT (leader A wrote it at t=0-260s, already in Redis)
       └── Returns 200 with data
t=<31s Container Apps startup probe PASSES
t=260s Leader A finishes prewarm
t=260s Both replicas serving fast
```

**Key insight**: Follower-side lazy prewarm is the impact-verse regression guard. Redis alone does not fix the crash loop — follower replicas need a code path that reads from Redis instead of re-executing pipelines. This is an architectural change, not a new backend wire.

## Flow 5: Invalidation fanout across replicas

### Current

```
User calls db.fabric.invalidate("my_product") on replica A
  └── pipeline.invalidate("my_product")
  └── del self._cache_data[key]
  └── Returns True

Replica B still has the entry in its own OrderedDict.
User hits replica B, gets STALE data.
No cross-replica invalidation exists.
```

### Post-fix

```
User calls await db.fabric.invalidate("my_product") on replica A
  └── await pipeline.invalidate("my_product")
  └── await _cache.invalidate(key)
  └── Redis DEL fabric:product:prod:*:my_product*        # SCAN + DEL per key
  └── Returns True

Replica B: next get_cached call
  └── await _cache.get(key)
  └── Redis HGETALL → empty → None
  └── Serving layer returns 202 or triggers refresh
  └── Fresh data
```

Cross-replica invalidation is free because it's all one Redis. No pub/sub needed for this flow.

## Observability changes (logged to stdout for all flows)

Every cache operation now logs one structured line:

```
INFO fabric.cache product=my_product tenant=X cache_hit=true source=redis mode=real latency_ms=1.2
INFO fabric.cache product=my_product tenant=X cache_hit=false source=redis mode=real latency_ms=0.8
WARN fabric.cache product=my_product tenant=X cache_hit=false source=redis mode=degraded error="Connection refused"
INFO fabric.pipeline.executor.init backend=redis redis_url_masked="redis://prod-cache:6379/***" instance_name=prod
INFO fabric.runtime.start leader=true prewarm_products_count=26 cache_backend=redis
INFO fabric.runtime.start leader=false prewarm_mode=follower_lazy_warmup entries_found=24 entries_missing=2
```

Plus Prometheus metrics:

- `fabric_cache_hits_total{backend="redis",product=...}`
- `fabric_cache_misses_total{backend="redis",product=...}`
- `fabric_cache_dedup_skips_total{product=...}`
- `fabric_cache_writes_total{backend="redis",product=...}`
- `fabric_cache_errors_total{backend="redis",error_type=...}`
- `fabric_cache_backend_info{backend="redis|memory|degraded"}` (gauge, always 1)
- `fabric_prewarm_duration_seconds{replica_role="leader|follower"}`

Dashboard signal for "each replica has its own cache" regression: `count(fabric_cache_backend_info{backend="memory"}) > 0` AND `fabric_cache_entries > 0` across two or more replica labels. One alert, done.
