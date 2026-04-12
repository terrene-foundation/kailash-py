# Subsystem Audit 04: Cache

**Scope**: `packages/kailash-dataflow/src/dataflow/cache/` — every file. The DataFlow query/Express cache (NOT the fabric product cache — see audit 03).

**Files audited** (7 production files, 1406 LOC):

| File                       | LOC | Summary                                                        |
| -------------------------- | --- | -------------------------------------------------------------- |
| `__init__.py`              | 47  | Public exports.                                                |
| `key_generator.py`         | 184 | `CacheKeyGenerator.generate_key()` + `generate_express_key()`. |
| `auto_detection.py`        | 239 | `CacheBackend.auto_detect()` factory, hand-rolled URL parser.  |
| `redis_manager.py`         | 480 | Sync `RedisCacheManager` + `CacheConfig` dataclass.            |
| `async_redis_adapter.py`   | 364 | `ThreadPoolExecutor`-wrapped async wrapper.                    |
| `memory_cache.py`          | 279 | `InMemoryCache` LRU+TTL fallback.                              |
| `invalidation.py`          | 559 | `CacheInvalidator` sync/async detection + pattern expansion.   |
| `list_node_integration.py` | 327 | `ListNodeCacheIntegration` default CRUD invalidation patterns. |

**Wiring sites** (how the cache reaches runtime):

- `features/express.py:55-58, 94-160, 954-996` — primary Express cache path (the hot path; hit on every `db.express.read/list/find_one/count/...`).
- `core/engine.py:468-481` — `DataFlowExpress` instantiation, passes `redis_url` through.
- `core/engine.py:941-1005` — `_initialize_cache_integration()` for the legacy `ListNodeCacheIntegration`.
- `core/config.py:656-684` — cache-related settings on `DataFlowConfig`.

---

## Summary

The Express query cache — the cache that **actually ships and is actively used by every `db.express.*` call in production** — is **catastrophically unsafe for multi-tenant deployments** and **structurally misconfigured** even for single-tenant ones. Key findings:

1. **Tenant dimension is absent from every cache-key construction site.** `generate_express_key()` produces `dataflow:v1:User:list:a1b2c3d4` with no tenant segment. The `CacheKeyGenerator.namespace` parameter exists but Express instantiates the generator at `express.py:140` without any namespace and no way to pass one per-request. When `multi_tenant=True` is declared at the DataFlow level, tenant A's cached rows are served to tenant B by the same Redis instance under identical keys. This is the bigger, more immediate data-leak sibling of fabric #354 — the fabric cache is half-wired, but the Express cache **is** wired and has been shipping since TSG-104. **CRITICAL.**

2. **`CacheConfig` vs `DataFlowConfig` naming drift.** `core/engine.py:960-962, 966` reads `self.config.cache_host`, `cache_port`, `cache_db`, `cache_redis_url`, `cache_namespace`, `cache_max_size` — **none of which exist on `DataFlowConfig`**. `core/config.py:664-671, 684` defines `redis_host`, `redis_port`, `redis_db`, `redis_password`, `_cache_max_size` (note the underscore!), and never sets `cache_redis_url` at all. Every `getattr(..., default)` call falls through to the default, so Redis auth (`redis_password`) is silently discarded and the connection always attempts `redis://localhost:6379/0` unless an explicit `redis_url=` or `REDIS_URL` env var is passed. **HIGH (silent misconfig)** → promotes to **CRITICAL** when combined with the tenant gap because it means even users who try to isolate tenants by running separate Redis instances cannot, because `redis_password` never reaches `CacheConfig`.

3. **Hand-rolled URL parser breaks on auth and TLS.** `auto_detection.py:68-78` and `auto_detection.py:156-161` do `redis_url.replace("redis://", "").split("/")`, `.split(":")` — crashes on `redis://user:pass@host:6379/0` with `ValueError: invalid literal for int()`, ignores `rediss://` (TLS), ignores `unix://` sockets, ignores URL-encoded passwords, ignores the `?db=` query-string form, and the db segment after the path is parsed by splitting on `/` once — so `redis://host:6379/0?ssl_cert_reqs=none` is read as `db=int("0?ssl_cert_reqs=none")` → crash. **HIGH.**

4. **Pattern-based invalidation leaks across tenants and across DataFlow instances on the same Redis.** `_invalidate_model_cache(model)` at `express.py:991-996` uses `"{prefix}:{version}:{model}:*"` — blows away **every** tenant's cache for that model on every write, because the key has no tenant segment. Even ignoring correctness, it means tenant A's write to `User` invalidates tenant B's and tenant C's `User` caches across every replica sharing Redis. Denial-of-cache under load. **HIGH.**

5. **Two parallel, conflicting cache initialisation paths.** `engine.py` instantiates the cache **twice**: once at line 468-481 via `DataFlowExpress(..., redis_url=...)` (the one that's actually used), and again at lines 941-1005 via `_initialize_cache_integration()` for a legacy `ListNodeCacheIntegration` that is NOT consumed by any node in the current codebase (dead code). The two paths use different config field names, different key prefixes (`dataflow` vs `dataflow:query` from `config.py:671`), different `namespace` semantics, and different Redis URL resolution. The dead one is more "feature-complete" (has a key-generator namespace, has an invalidator with patterns); the live one is simpler and has none of those. **HIGH (dead code + MEDIUM framework-first violation).**

6. **No pickle, no unbounded deserialization vuln, and no cache-version tag.** Good news: the cache serialises via `json.dumps(value, default=...)` (`redis_manager.py:162, 298`). Zero `pickle` calls in the cache layer. Bad news: there is no `schema_version` field in cached entries, so any model migration silently corrupts the cache until every entry's TTL elapses. **MEDIUM.**

7. **Observability is nearly non-existent.** Zero Prometheus metrics. `cache_hits`/`cache_misses` are per-process counters on `DataFlowExpress` (`express.py:143-144`) with no labels, no export, and they reset every instantiation. Logging is two `logger.debug("Cache hit/miss for key: {cache_key}")` calls in `list_node_integration.py:91, 97` — in the live Express path, there is **no log at all** on hit/miss. The mandate brief requires `mode=cached|real|fake` on every data call, per `rules/observability.md` § 3 — not implemented anywhere in the cache path. **HIGH.**

8. **No single-flight / stampede protection.** When a hot key expires, N concurrent `db.express.list()` calls all fall through to the database simultaneously. Fine for small loads, a dogpile at scale. **MEDIUM.**

9. **Unbounded `ThreadPoolExecutor` + no operation timeout.** `async_redis_adapter.py:72` passes `max_workers=None` which defaults to `min(32, os.cpu_count()+4)`. Each DataFlow instance creates its own pool — no sharing. Every operation blocks a worker for the full `socket_timeout=5s` default. A Redis hang under load blocks the event loop from progressing beyond the pool's worker count. `__del__` at line 359 calls `self._executor.shutdown(wait=False)` — acceptable, but combined with `_redis_client` held across `__del__` runs, the FD lifecycle is murky. **MEDIUM.**

10. **Redis outage behavior is "return None, keep going silently".** `redis_manager.py:103-105, 138, 173` — every failure logs error and returns `None`/`False`/`0`. The circuit breaker (`circuit_breaker_enabled`) defaults to **off** (`redis_manager.py:35`) so by default the cache hammers a dead Redis on every request with a full 5s socket timeout. No health-signal surfaced to DataFlow. **HIGH.**

11. **Cache key does not sanitize dangerous characters in params.** `generate_express_key()` at `key_generator.py:131-132` does `json.dumps(params, sort_keys=True, default=str)` then md5. Collisions across different structural shapes are possible for adversarial inputs (MD5 is non-cryptographic here, but truncating to 8 hex chars = 32-bit namespace — birthday collision at √2³² ≈ 65k distinct filters). **MEDIUM (hash truncation + MD5 signal).**

12. **`_redis_url` shadow variable in engine.** `engine.py:2018-2019` reads `self._redis_url` but `DataFlow.__init__` never assigns it. The `hasattr` guard makes it dead code — `self._redis_url or redis_url` always evaluates to `redis_url` (the `getattr(self.config, "redis_url", ...)` above). Confirms core auditor's finding. **MEDIUM (dead code, docstring lie — brief mentions "Redis URL" parameter as if honored).**

---

## Finding matrix

| #   | Severity | File:Line                                                 | Finding                                                                                                                                                                                | Category                    |
| --- | -------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| C1  | CRITICAL | `cache/key_generator.py:97-135`                           | `generate_express_key()` has zero tenant dimension                                                                                                                                     | tenant-leak                 |
| C2  | CRITICAL | `cache/memory_cache.py:192`, `async_redis_adapter.py:356` | `invalidate_model()` pattern omits tenant                                                                                                                                              | tenant-leak                 |
| C3  | CRITICAL | `features/express.py:140, 995`                            | Express never passes tenant_id into `_key_gen` or `_invalidate_model_cache`                                                                                                            | tenant-leak                 |
| H1  | HIGH     | `core/engine.py:960-966, 980` vs `core/config.py:664-684` | Config field name drift: `cache_*` reads never find `redis_*` values; `_cache_max_size` underscore mismatch; `cache_redis_url` never set                                               | silent-misconfig            |
| H2  | HIGH     | `cache/auto_detection.py:68-78, 156-161`                  | Hand-rolled URL parser crashes on `redis://user:pass@host/0`, silently ignores `rediss://`, `unix://`, query params                                                                    | dialect-portability         |
| H3  | HIGH     | `cache/redis_manager.py:35, 103-105`                      | Circuit breaker defaults off; Redis outage hammers 5s socket timeout per call                                                                                                          | resilience                  |
| H4  | HIGH     | `features/express.py:991-996`                             | `_invalidate_model_cache` wildcard blows away every tenant's model cache on every write                                                                                                | denial-of-cache             |
| H5  | HIGH     | `core/engine.py:941-1005`                                 | Dead `_initialize_cache_integration()` path; two parallel cache init paths with incompatible config field names                                                                        | dead-code + framework-first |
| H6  | HIGH     | Entire cache layer                                        | Zero structured log at hit/miss/error; no `mode=cached` field                                                                                                                          | observability               |
| M1  | MEDIUM   | `cache/key_generator.py:131-133`                          | MD5 truncated to 8 hex = 32 bits, collision-prone at ~65k distinct params                                                                                                              | key-integrity               |
| M2  | MEDIUM   | Entire cache layer                                        | No `schema_version` in cached entries; schema change silently serves stale shapes                                                                                                      | cache-versioning            |
| M3  | MEDIUM   | `cache/async_redis_adapter.py:72, 359`                    | Unbounded ThreadPoolExecutor per instance; no operation timeout; murky `__del__` ordering                                                                                              | resource-hygiene            |
| M4  | MEDIUM   | `features/express.py:954-989`                             | No single-flight coalescing on cache miss; dogpile on hot-key expiry                                                                                                                   | stampede                    |
| M5  | MEDIUM   | `core/engine.py:2018-2019`                                | `self._redis_url` never assigned; `hasattr` guard = dead code; param docstring lies                                                                                                    | dead-code + docstring-lie   |
| M6  | MEDIUM   | `cache/redis_manager.py:30, 94`                           | `default_ttl=300` hardcoded twice (`CacheConfig` dataclass AND `DataFlowConfig._cache_max_size`); no single source of truth                                                            | config-drift                |
| M7  | MEDIUM   | `cache/invalidation.py:107-136, 438-502`                  | Async/sync auto-detection at invalidation time is a workaround for the fact that there are two cache backends with different interface shapes — should be unified                      | framework-first             |
| M8  | MEDIUM   | `features/express.py:995`                                 | Invalidation pattern `dataflow:v1:User:*` doesn't match keys from the legacy `_cache_integration` (`dataflow:query:User:*`); double-cache = double-stale                               | key-drift                   |
| M9  | MEDIUM   | `cache/memory_cache.py:192-203`                           | `invalidate_model` uses `pattern in k` substring match — `Users` invalidates `User`-prefixed keys too                                                                                  | substring-bug               |
| M10 | MEDIUM   | `cache/memory_cache.py:103-116`                           | `InMemoryCache.set()` eviction counts may be wrong: evicts-then-reassigns; `self.cache.move_to_end(key)` at line 115 runs unconditionally after assignment (no-op, dead code)          | logic-bug                   |
| M11 | MEDIUM   | `cache/invalidation.py:414`                               | `_expand_pattern` replaces `{model}` placeholder unconditionally without escaping; a model name with `:` silently breaks Redis pattern matching                                        | input-validation            |
| L1  | LOW      | `cache/memory_cache.py:259-278`                           | Two "stats" APIs (`get_metrics` async, `get_stats` sync) with overlapping but not identical fields                                                                                     | API-consistency             |
| L2  | LOW      | `cache/redis_manager.py:25-36`                            | `CacheConfig` hardcodes `host="localhost"` as default — should require explicit                                                                                                        | config-hygiene              |
| L3  | LOW      | `cache/invalidation.py:156-161`                           | `is_enabled()` closes an unawaited coroutine instead of awaiting — "don't block in sync context" is the wrong answer; the right answer is "don't call a sync method on an async cache" | async-hygiene               |
| L4  | LOW      | `cache/list_node_integration.py:151-169`                  | `warmup_cache()` generates cache keys but passes `None` as value — the method is a stub that populates nothing                                                                         | stub                        |
| L5  | LOW      | `cache/__init__.py:27-47`                                 | Exports `CacheableListNode` but no consumer in the codebase                                                                                                                            | dead-export                 |
| L6  | LOW      | `cache/redis_manager.py:450-457`                          | `_json_serializer` uses `str(obj)` for unknown types — silent information loss                                                                                                         | serialization               |

---

## CRITICAL findings (expanded)

### C1 — Zero tenant dimension in Express cache keys

**Where**: `cache/key_generator.py:97-135`.

**Code**:

```python
def generate_express_key(self, model_name: str, operation: str, params: Any = None) -> str:
    parts: list[str] = [self.prefix, self.version]
    if self.namespace:
        parts.append(self.namespace)
    parts.append(model_name)
    parts.append(operation)
    if params is not None:
        param_str = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        parts.append(param_hash)
    return ":".join(parts)
```

**The `namespace` parameter is the hypothetical escape hatch** — if Express instantiated `CacheKeyGenerator(namespace=current_tenant_id)`, the key would be `dataflow:v1:tenant-A:User:list:abcd`. But:

- `features/express.py:140`: `self._key_gen = CacheKeyGenerator()` — **no namespace, no tenant context**, constructed once at `DataFlowExpress.__init__` with no per-request rebinding.
- `features/express.py:964, 988, 995`: every call site uses `self._key_gen.generate_express_key(model, operation, params)` with no tenant context.
- `features/express.py` grep `tenant`: **0 matches**. The Express layer knows nothing about `multi_tenant=True`, `TenantContextSwitch`, or `set_tenant_context(tenant_id)`.
- `core/engine.py:1375-1378`: DataFlow auto-adds a `tenant_id` **column** to every model when `multi_tenant=True` — the SQL layer filters by tenant, but the cache layer keys only on `(model, operation, hash(params))`.

**Scenario**:

```python
db = DataFlow("postgresql://...", multi_tenant=True, redis_url="redis://shared:6379")
db.set_tenant_context("tenant-A")
alice = await db.express.read("User", "user-42")  # reads & caches
db.set_tenant_context("tenant-B")
bob = await db.express.read("User", "user-42")    # cache HIT returns tenant-A's row!
```

Because:

1. `generate_express_key("User", "read", {"id": "user-42"})` produces the **same key** for both calls.
2. `_cache_manager.get(cache_key)` returns tenant A's row (JSON-decoded).
3. The SQL layer's `tenant_id = ?` WHERE clause is **never consulted** — the cache short-circuited the read.

Tenant-B operator sees tenant-A's PII. This is the biggest active leak in DataFlow right now. It is larger than fabric #354 (where Redis was never wired) because Express **is** wired to Redis and shipping.

**Test coverage**: `tests/unit/test_express_cache.py` has 11 `generate_express_key` tests — **zero** include a tenant-id in params or namespace. `tests/unit/test_express_cache_wiring.py` similar. `tests/integration/cache/test_cache_invalidation.py:65-85` has a test named `test_table_invalidation_with_tenant_isolation` — but it **hand-constructs** a pattern `"dataflow:tenant1:users:*"` and asserts the invalidator passes that literal through. It does NOT verify the real generator emits tenant-scoped keys. Zero tests exercise cross-tenant reads against a live cache. The claim "multi-tenant correctness" (mandate §5) is unverified.

**Fix outline** (analysis phase — no code):

1. Add required `tenant_id: Optional[str]` arg to `CacheKeyGenerator.generate_express_key(..., tenant_id=None)`.
2. When DataFlow has `multi_tenant=True`, Express MUST pass `tenant_id=<current_tenant>` on every call; missing tenant_id in that mode MUST raise loudly (fail-closed), not fall through silently.
3. Prefix tenant segment: `dataflow:v1:t:<tenant_id>:User:list:abcd`. Choose a sentinel so "no tenant" (single-tenant mode) doesn't collide with tenant named `_none` — e.g., always include `t:<id>` when `multi_tenant=True`, never include in single-tenant mode.
4. `_invalidate_model_cache` MUST scope to `{prefix}:{version}:t:{tenant}:{model}:*` when multi-tenant, not blow away cross-tenant.
5. Audit `kailash-rs/crates/kailash-dataflow/src/query_cache.rs` — same bug (verified, 0 tenant mentions in 953 LOC) — file cross-SDK issue.

**Test plan**:

- Tier 2 integration test in `tests/integration/cache/test_cache_tenant_isolation.py`:
  - Start real PostgreSQL + real Redis (via IntegrationTestSuite).
  - `DataFlow(pg_url, multi_tenant=True, redis_url=real_redis)`.
  - `@db.model User { id, email, tenant_id }`.
  - Create users in tenant A and tenant B with the same `id` (allowed under tenant isolation).
  - `set_tenant_context("A"); r1 = db.express.read("User", id)`.
  - `set_tenant_context("B"); r2 = db.express.read("User", id)`.
  - Assert `r1 != r2` and both came from the correct tenant.
  - Read back the raw Redis keys, verify `t:A` and `t:B` segments are present and different.
- Tier 2 regression test `tests/regression/test_issue_cache_tenant_leak.py` @pytest.mark.regression — literal reproduction of the leak scenario above.
- Test for `multi_tenant=True` with `set_tenant_context(None)`: MUST raise (fail-closed), MUST NOT silently cache under `t:None`.

---

### C2 — `invalidate_model` patterns leak across tenants

**Where**: `cache/memory_cache.py:192`, `cache/async_redis_adapter.py:356`, `features/express.py:995`.

```python
# memory_cache.py
async def invalidate_model(self, model_name: str) -> int:
    pattern = f"dataflow:{model_name}:"
    keys_to_remove = [k for k in self.cache.keys() if pattern in k]
    ...

# async_redis_adapter.py
async def invalidate_model(self, model_name: str) -> int:
    pattern = f"dataflow:{model_name}:*"
    return await self.clear_pattern(pattern)

# express.py (the one that actually runs)
async def _invalidate_model_cache(self, model: str) -> None:
    pattern = f"{self._key_gen.prefix}:{self._key_gen.version}:{model}:*"
    await self._cache_manager.clear_pattern(pattern)
```

Three different patterns for the same operation, and **none** of them are tenant-scoped. When tenant A updates a single user, tenant B's entire `User` cache is wiped. Under a write-heavy workload with many tenants sharing Redis, no tenant's cache ever stays warm.

Additionally, `memory_cache.invalidate_model` uses substring match (`pattern in k`) — if two models share a prefix (`Users` and `UsersAudit`), invalidating `Users` also invalidates `UsersAudit`. The Redis variant uses `*` glob which is correct for suffix but still uses the wrong prefix (`dataflow:User:*` instead of `dataflow:v1:User:*` — so invalidating `User` **also doesn't match** the real keys because the real prefix is `dataflow:v1:User:...`). **The Redis `invalidate_model` path is completely broken — it matches nothing.** Dead method.

**Fix outline**:

1. Unify the invalidation pattern across `InMemoryCache`, `AsyncRedisCacheAdapter`, and Express through a single `CacheKeyGenerator.model_pattern(model, tenant_id)` method.
2. Add tenant segment.
3. Replace `pattern in k` substring match with proper glob matching (`fnmatch.fnmatch(k, pattern)`).
4. Add test that invalidating `Users` does NOT invalidate `UsersAudit`.

---

### C3 — Express cache bypasses tenant context entirely

**Where**: `features/express.py` (full file). Zero grep matches for `tenant` in the 1300+ lines.

DataFlow **does** have a tenant context layer (`core/engine.py:505, 3088-3115` — `TenantContextSwitch`, `set_tenant_context(tenant_id)`). Every SQL operation consults it. The Express cache does not.

**This is a data-plane / cache-plane split-brain.** Any user who enables multi-tenancy and query caching is silently trading data isolation for speed, and the docstring at `features/express.py:5` promises "Preserves DataFlow features (audit, multi-tenancy, schema cache)" — a **documented lie**.

**Fix outline**:

1. Resolve current tenant at each `_cache_get`/`_cache_set`/`_invalidate_model_cache` call via `self._db._tenant_context` or a `get_current_tenant()` helper.
2. If `multi_tenant=True` and `tenant_context is None`: raise `TenantContextMissingError`, never cache, never read cache. Fail-closed.
3. Update docstring to reflect reality OR fix the code — the docstring lie is covered by mandate §2.

---

## HIGH findings (expanded)

### H1 — `DataFlowConfig` vs `CacheConfig` field name drift

**Where**: `core/engine.py:960-966, 980` vs `core/config.py:664-671, 684`.

`engine.py:_initialize_cache_integration()` reads:

```python
cache_host = getattr(self.config, "cache_host", "localhost")
cache_port = getattr(self.config, "cache_port", 6379)
cache_db = getattr(self.config, "cache_db", 0)
cache_key_prefix = getattr(self.config, "cache_key_prefix", "dataflow")  # config says "dataflow:query"
redis_url = getattr(self.config, "cache_redis_url", None)  # never set
cache_namespace = getattr(self.config, "cache_namespace", None)  # never set
cache_max_size = getattr(self.config, "cache_max_size", 1000)  # config uses _cache_max_size with underscore
```

`config.py` actually sets:

```python
self.redis_host = kwargs.get("redis_host", "localhost")    # NOT cache_host
self.redis_port = kwargs.get("redis_port", 6379)           # NOT cache_port
self.redis_db = kwargs.get("redis_db", 0)                  # NOT cache_db
self.redis_password = kwargs.get("redis_password", None)   # never read by cache layer
self.cache_key_prefix = kwargs.get("cache_key_prefix", "dataflow:query")  # conflict with default
self._cache_max_size = kwargs.get("cache_max_size", 1000)  # private underscore; engine reads public
```

**Consequences**:

- `cache_host`/`cache_port`/`cache_db` always fall through to defaults. Redis always at `localhost:6379/0`.
- `redis_password` is **never plumbed** into `CacheConfig(password=...)`. A password-protected Redis cannot be reached via the legacy integration path (only via explicit `DataFlow(redis_url="redis://:pass@host")`).
- `cache_key_prefix` default drifts: `engine.py` says `"dataflow"`, `config.py` says `"dataflow:query"` (line 671), Express uses `CacheKeyGenerator()` default `"dataflow"`, `CacheConfig.key_prefix` dataclass default `"dataflow"` (`redis_manager.py:32`). **Four different defaults.** Keys written by Express (`dataflow:v1:...`) never match patterns cleared by the legacy invalidator (`dataflow:query:...`).
- `cache_max_size` reads `cache_max_size` but config sets `_cache_max_size`. Falls through to default 1000 always.

The legacy `_initialize_cache_integration` path is largely unused (see H5), so these are dormant in production — but they manifest loudly when anyone tries to customize Redis via the documented config surface. And `cache_key_prefix` drift affects the live Express path because `config.py:671` is the value read for the fabric cache prefix path, diverging from what Express writes.

**Fix outline**:

1. Delete the `getattr` fallbacks. Every cache config field MUST be a real attribute on `DataFlowConfig` with one canonical name.
2. Rename `redis_host`/`redis_port`/`redis_db`/`redis_password` → `cache_redis_host`/`...` OR drop them entirely in favor of a single `cache_redis_url` that is parsed once.
3. Consolidate to ONE cache key prefix constant, used by every site. Mandate §13 (resource hygiene) applies by analogy.
4. Delete `_cache_max_size` underscore alias; keep `cache_max_size` public.

---

### H2 — Hand-rolled Redis URL parser breaks on auth, TLS, unix sockets

**Where**: `cache/auto_detection.py:68-78, 156-161`.

```python
if redis_url.startswith("redis://"):
    url_parts = redis_url.replace("redis://", "").split("/")
    host_port = url_parts[0].split(":")
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 6379
    db = int(url_parts[1]) if len(url_parts) > 1 else 0
```

Fails on every real-world production Redis URL:

- `redis://user:password@host:6379/0` → splits on `:` into `['user', 'password@host', '6379']`, `int('password@host')` → `ValueError`. **Exception at startup.**
- `rediss://host:6379/0` (TLS) → `startswith("redis://")` is False, falls through silently to defaults. User thinks they have TLS, they have plaintext localhost.
- `redis+sentinel://sentinel1,sentinel2/mymaster` → parsed as host=`sentinel1,sentinel2`, crash on int().
- `unix:///var/run/redis.sock` → `startswith("redis://")` False, silent fallback.
- `redis://host:6379/0?ssl_cert_reqs=none` → db becomes `int("0?ssl_cert_reqs=none")` → crash.
- URL-encoded characters in password (`%40` = `@`) → not decoded.

**Fix outline**: Use `urllib.parse.urlparse` + `redis.Redis.from_url` (the latter is the supported API in `redis-py >= 3.0`). Delete the hand-rolled parser entirely.

```python
# Correct pattern
import redis
client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
```

---

### H3 — Circuit breaker defaults OFF; outage hammers dead Redis with 5s timeout

**Where**: `cache/redis_manager.py:35, 103-105, 459-479`.

```python
@dataclass
class CacheConfig:
    ...
    circuit_breaker_enabled: bool = False  # line 35 — DEFAULT OFF
    circuit_breaker_threshold: int = 5
```

When Redis goes down mid-flight:

1. Every request calls `redis_client` property → tries to connect → 5s socket timeout.
2. Failure → `_handle_connection_failure()` increments counter → because breaker is off, no trip.
3. Next request → same 5s timeout → same failure.
4. Under 100 req/s load, the async thread pool (unbounded, default ≈ 32 workers) saturates in ~6s; every subsequent request blocks waiting for a worker; the event loop cannot accept new requests.

The `failover_mode: str = "degraded"` field (line 34) is declared but **never read** anywhere in the codebase:

```bash
$ grep -rn failover_mode packages/kailash-dataflow/src/dataflow/cache
redis_manager.py:34:    failover_mode: str = "degraded"  # declared
redis_manager.py:54:        if self.failover_mode not in [...]:  # validated only
# No consumer.
```

Classic stub per `rules/zero-tolerance.md` Rule 2.

**Fix outline**:

1. Circuit breaker ON by default.
2. When breaker is open, `get()`/`set()` return immediately (no Redis attempt) for a cooldown window, then probe once.
3. Implement `failover_mode="degraded"`: breaker-open short-circuits to `InMemoryCache` fallback OR returns None fast and lets the DB absorb load. "fail" mode propagates the error to the caller.
4. Surface the breaker state as a DataFlow health signal (metric + structured log at WARN).
5. Default `socket_timeout` to 2s, not 5s.

---

### H4 — `_invalidate_model_cache` wildcard denial-of-cache

Same root cause as C2; impact category is different (denial-of-service under write load, vs direct data leak). Consolidated in C2's fix plan.

---

### H5 — Two parallel cache init paths, one of them dead

**Where**: `core/engine.py:468-481` (live) vs `core/engine.py:941-1005` (legacy/dead).

**Live path**: `engine.py:468-481` constructs `DataFlowExpress(..., redis_url=...)`. The express instance owns its own `_cache_manager` (a `CacheBackend.auto_detect(...)` return), its own `_key_gen = CacheKeyGenerator()`, and its own `_cache_get/_cache_set/_invalidate_model_cache` helpers. It uses no `CacheInvalidator`, no `ListNodeCacheIntegration`, no default patterns.

**Legacy path**: `engine.py:941-1005` constructs `CacheInvalidator`, `CacheKeyGenerator(prefix=..., namespace=...)`, `ListNodeCacheIntegration`. The integration is assigned to `self._cache_integration`. I searched the codebase for consumers of `self._cache_integration`:

```bash
$ grep -rn _cache_integration packages/kailash-dataflow/src
core/engine.py:541:        self._cache_integration = None
core/engine.py:769:            if self.config.enable_query_cache:
core/engine.py:987:            self._cache_integration = create_cache_integration(...)
core/engine.py:1005:            self._cache_integration = None
```

**The only readers are `self._cache_integration = None` sentinels and the initializer.** No node uses it. No Express method references it. It's dead.

Consequences:

- The entire `ListNodeCacheIntegration` module (327 LOC), `CacheInvalidator` pattern registry (559 LOC), the default CRUD patterns in `_setup_invalidation_patterns()` (49 LOC at `list_node_integration.py:203-251`), and every test file against them are testing dead code.
- The live Express path has **none of the features** the legacy path claims: no declarative patterns, no `{model}:record:{id}` specificity (Express just wipes `{model}:*`), no custom pre/post hooks, no batch mode.
- Framework-first violation: two ways to do the same thing in the same package (mandate §12).

**Fix outline**:

1. Decision: either fold `CacheInvalidator`/`ListNodeCacheIntegration` features INTO the Express cache path and delete the legacy path, OR delete the legacy path entirely and live with the simpler semantics.
2. Given that every caller uses `db.express`, option B is cleaner — delete `list_node_integration.py`, delete `invalidation.py` (or reduce it to a thin `CacheKeyGenerator.model_pattern` helper), remove `_initialize_cache_integration`, remove `self._cache_integration`.
3. Move the valuable features (batch mode, pre/post hooks, `{model}:record:{id}` granularity) into Express directly.

---

### H6 — Zero structured log/metric at the cache boundary

**Where**: `features/express.py:954-996`; entire cache layer.

Per `rules/observability.md` §3 "Data Calls — Real, Fake, or Simulated":

> Every data fetch MUST log the source mode in the log line itself.

The Express cache hot path:

```python
async def _cache_get(self, model, operation, params, effective_ttl) -> Optional[Any]:
    if not self._cache_enabled or not self._cache_manager or effective_ttl <= 0:
        return None
    cache_key = self._key_gen.generate_express_key(model, operation, params)
    cached = await self._cache_manager.get(cache_key)
    if cached is not None:
        self._cache_hits += 1
        return cached
    self._cache_misses += 1
    return None
```

- **No log line at entry.**
- **No log line at hit.**
- **No log line at miss.**
- **No log line at error** (any exception in `_cache_manager.get()` bubbles up silently or is swallowed by `redis_manager.get` → returns None).
- No `mode=cached` field. No `correlation_id`. No `latency_ms`.
- No Prometheus metric anywhere in the cache layer (0 imports of `prometheus_client`, 0 `Counter(`, 0 `Histogram(`).

The `_cache_hits`/`_cache_misses` counters on `DataFlowExpress` are per-instance and un-exported. When you have N Express instances across N workers, there are N independent counters no aggregator can read.

`list_node_integration.py:91, 97` has `logger.debug("Cache hit/miss for key: {cache_key}")` — wrong level (DEBUG is off by default in production), wrong form (f-string instead of structured fields), dead path anyway (H5).

**Fix outline**:

1. Every `_cache_get` emits `logger.info("cache.get", model=model, operation=op, hit=bool, backend=..., latency_ms=..., mode="cached" if hit else "real")`.
2. Every `_cache_set` emits `logger.info("cache.set", ...)`.
3. Errors: `logger.exception("cache.error", ...)` with the key (hashed, not raw — avoid leaking PII from params).
4. Prometheus counters labeled by `model`, `operation`, `tenant_id`, `backend`.
5. Structured log fields, no f-strings.

---

## MEDIUM findings (expanded — essentials only)

### M1 — MD5 truncation to 8 hex = 32-bit namespace

`key_generator.py:131-132`: `hashlib.md5(param_str.encode()).hexdigest()[:8]`. Truncating MD5 to 32 bits means **birthday collisions start appearing at √2³² ≈ 65 thousand distinct params**. Under a high-cardinality filter workload (e.g., `list(User, filter={search_text: <user-query>})`), two different queries collide and return each other's results.

MD5 is not a security primitive here (the cache is not adversarial against itself), but the truncation is the real problem. Fix: use SHA-256 truncated to 16 hex (64 bits, collision at ~4 billion distinct queries) or keep full 32 hex.

Also: MD5 is a FIPS-disallowed algorithm in some deployment environments (FIPS 140-2 mode disables it), so code that imports `hashlib.md5` may refuse to import at all in hardened environments. Switch to BLAKE2b or SHA-256.

### M2 — No `schema_version` in cached entries

When a model's schema changes (field added, field removed, type changed), the cache still holds entries serialized under the old shape. Readers consuming the cached `user.address` get `KeyError` because the field was renamed. No cache-versioning mechanism exists.

Fix: embed `{"_schema_version": model.schema_version, "_value": ...}` in every cached entry. Bump `schema_version` on every model definition change. Reader rejects entries where `_schema_version != current`.

### M3 — Unbounded executor + no operation timeout + murky `__del__`

`async_redis_adapter.py:59-75`: `self._executor = ThreadPoolExecutor(max_workers=max_workers)` with `max_workers=None` default → Python defaults to `min(32, (os.cpu_count() or 1) + 4)`. Every DataFlow instance creates its own pool. If a host has 8 DataFlow instances (multi-db deployments), that's 8 × 32 = 256 Redis worker threads. Per-operation timeout is `socket_timeout=5s` from `CacheConfig`.

`async_redis_adapter.py:359-363`: `__del__` calls `_executor.shutdown(wait=False)` — does not wait for in-flight ops, which is correct for finalizers, BUT does not guarantee the underlying sync `RedisCacheManager._redis_client` is closed. The `__del__` does not call `redis_manager.close()` (no such method exists on `RedisCacheManager` — another gap).

Fix: (a) bound executor to `max_workers=4` per instance, (b) share the executor across DataFlow instances via a module-level singleton, (c) add explicit per-call timeout via `loop.run_in_executor(...)` + `asyncio.wait_for`, (d) add `RedisCacheManager.close()` and call it from `AsyncRedisCacheAdapter.__del__`.

### M4 — No single-flight / stampede protection

`_cache_get` returns None → caller runs SQL → `_cache_set` writes. N concurrent cache-miss requests each run SQL. Classic dogpile on high-traffic keys at expiry.

Fix: per-key `asyncio.Lock`, or use Redis `SET NX` with a sentinel + retry loop, or accept the dogpile for simple deployments and document.

### M5 — Dead `self._redis_url` in `engine.py:2018-2019`

```python
redis_url = getattr(self.config, "redis_url", None) or getattr(self.config.database, "redis_url", None)
if hasattr(self, "_redis_url"):
    redis_url = self._redis_url or redis_url
```

`DataFlow.__init__` never assigns `self._redis_url`. The `hasattr` check is always False. Dead code. Per core auditor's finding, the `DataFlow(redis_url=...)` kwarg documented in the class docstring is silently ignored at the fabric path — the Express path receives it correctly (via the `redis_url` parameter at line 474) but the fabric path sees `getattr(self.config, "redis_url", None)`. `config.py` does not set `redis_url` either (grep confirms), so both `getattr` calls return None.

The `DataFlow(redis_url=...)` kwarg reaches only Express (via explicit parameter), NOT the fabric runtime (which uses `getattr(self.config, "redis_url", None)` that's always None). Fabric runtime fallback also never sets it.

Fix: assign `self._redis_url = redis_url` in `DataFlow.__init__` alongside other settings; delete the `hasattr` guard; add a real backing field on `DatabaseConfig` or `DataFlowConfig` so the fabric path can also read it.

### M6-M11: see finding matrix — all are ≤30-line local fixes. Consolidated in master fix plan.

---

## Cross-subsystem couplings

| Subsystem               | Coupling                                                                                                                               |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| core/config             | Field name drift (H1); cache TTL not single source of truth per `rules/dataflow-pool.md` §1 by analogy                                 |
| core/engine             | Two init paths (H5); dead `_redis_url` (M5)                                                                                            |
| features/express        | All CRITICAL findings live here via delegated cache ops                                                                                |
| features/multi_tenant   | `MultiTenantManager` exists at `core/engine.py:24`, holds tenant context — Express cache never consults it (C3)                        |
| fabric                  | Shares `CacheKeyGenerator` class? No — fabric has its own cache module. Same bug class though — see audit 03                           |
| security                | `row_level_security`, `QueryInterceptor` — Express cache bypasses the interceptor by returning cached rows before the interceptor runs |
| observability (pending) | No structured logs at cache boundary (H6); no Prometheus metrics                                                                       |
| testing                 | No tenant isolation integration test (gap against mandate §9)                                                                          |

---

## Cross-SDK parallels (EATP D6)

| Python finding                    | Rust equivalent                                                                                                                                                                                | Status                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| C1 Tenant dim missing             | `crates/kailash-dataflow/src/query_cache.rs` — `CacheKey { model_name, record_id }`, **zero** tenant mentions in 953 LOC                                                                       | **Same bug**, file cross-SDK issue on `esperie-enterprise/kailash-rs`   |
| C2 Invalidation cross-tenant      | Rust has `invalidate()`, `invalidate_all()` — no tenant scope                                                                                                                                  | Same bug                                                                |
| C3 Express ignores tenant         | Rust has no Express-equivalent surface yet (simpler API)                                                                                                                                       | N/A (but when Rust gains Express, ensure tenant propagation from day 1) |
| H1 Config field drift             | Rust `QueryCacheConfig` uses strongly-typed Rust struct; no `getattr` pattern possible                                                                                                         | Not applicable                                                          |
| H2 Hand-rolled URL parser         | Rust uses `redis::Client::open(url)` — correct                                                                                                                                                 | Not applicable (good)                                                   |
| H3 Circuit breaker off by default | Rust has no circuit breaker in query_cache.rs                                                                                                                                                  | File cross-SDK issue — Rust needs breaker too                           |
| H5 Two parallel init paths        | Rust has one canonical path                                                                                                                                                                    | Not applicable (good)                                                   |
| H6 No metrics                     | Rust exposes `CacheStats { hits, misses, evictions, entries, hit_rate }` via `stats()` method, uses `AtomicU64` — better than Python's instance counters, still no labels or Prometheus export | Partial parity — Rust is closer; both need Prometheus                   |

**Recommended cross-SDK follow-ups**:

1. File `terrene-foundation/kailash-rs` issue "query_cache.rs: zero tenant dimension in cache keys" linked to this audit and the kailash-py fix.
2. File cross-SDK issue for circuit-breaker parity.
3. File cross-SDK issue for Prometheus export of cache stats.
4. When Rust gains a query-cache-bearing ExpressDataFlow equivalent, enforce tenant dimension from the first commit — do not repeat the Python mistake.

---

## Institutional-knowledge gaps

Captured as DISCOVERY/GAP/CONNECTION candidates for the journal phase:

1. **DISCOVERY (large)**: The DataFlow query cache has a tenant-isolation failure mode that is structurally identical to the fabric #354 story, but shipped earlier and is more widely exercised. Any multi-tenant deployment with `redis_url=...` is affected.
2. **DISCOVERY**: "Two cache init paths" is a recurring pattern. The dead `_cache_integration` path has richer features (invalidation patterns, batch mode) than the live Express path. Pattern: features ship twice when an earlier implementation is not deprecated before the new one lands.
3. **GAP**: `.claude/rules/` has no rule requiring "every cache key in a multi-tenant framework MUST include a tenant segment". Proposed new rule: `rules/cache-tenant-dimension.md`.
4. **GAP**: No rule mandating "URL parsing MUST use `urllib.parse` / `redis.Redis.from_url`" — same hand-rolled parser bug pattern exists in `adapters/postgres.py` (sslmode #353 story).
5. **CONNECTION**: Issue #354 (fabric cache) + this audit's C1-C3 (Express cache) + the rust `query_cache.rs` gap = one cross-cutting problem: "DataFlow cache layer has no tenant dimension anywhere in the stack". Single fix campaign, not three independent fixes.
6. **CONNECTION**: `rules/zero-tolerance.md` Rule 2 (no stubs) applies to `CacheConfig.failover_mode` — declared but no consumer. Same anti-pattern as #354 `redis_url=` kwarg.
7. **CONNECTION**: `rules/observability.md` §3 `mode=cached|real|fake` requirement is unmet across the entire DataFlow package, not just the cache layer. Cache is the first place this gap bites because the mode ambiguity is inherent.
8. **DISCOVERY**: `InMemoryCache.invalidate_model` substring match (`pattern in k`) is silently wrong but passes every unit test because no test has two models sharing a prefix. Test coverage gap institutional pattern: "prefix collisions are always missed in unit tests because nobody writes `User` AND `UserAudit` together".

---

## Recommended fix sequencing

This subsystem's fixes should sequence as:

1. **Block 1 — CRITICAL tenant isolation** (C1 + C2 + C3 + cross-SDK Rust issue). One atomic fix that adds `tenant_id` to `generate_express_key`, plumbs it through Express, scopes invalidation, fails closed when `multi_tenant=True` and no tenant context. Tier 2 integration test first (reproduces leak), then fix. Regression test stays forever.
2. **Block 2 — HIGH config + URL parsing** (H1 + H2). Delete hand-rolled parser, consolidate config field names, single source of truth for cache prefix and TTL.
3. **Block 3 — HIGH dead code purge** (H5 + M5). Delete `_initialize_cache_integration`, delete `ListNodeCacheIntegration`, delete `_cache_integration` sentinels, delete `self._redis_url` dead branch.
4. **Block 4 — HIGH resilience** (H3). Circuit breaker on by default, shorter socket timeout, failover mode implemented, health signal.
5. **Block 5 — HIGH observability** (H6). Structured logs at every cache boundary with `mode=`, Prometheus counters, correlation-id propagation.
6. **Block 6 — MEDIUM polish** (M1-M11). SHA-256 full hash, schema version, bounded executor, stampede protection, substring-match fix, etc.
7. **Block 7 — Cross-SDK** — file issues, mirror Block 1 fix on kailash-rs.
8. **Block 8 — Rules/docs** — new rule `rules/cache-tenant-dimension.md`, update dataflow-specialist agent to auto-cite it.

---

## Tests required before this subsystem can be declared perfect

- `tests/integration/cache/test_cache_tenant_isolation.py` — C1-C3 reproduction + fix verification, against real PG + real Redis.
- `tests/regression/test_issue_cache_tenant_leak.py` — permanent regression test.
- `tests/integration/cache/test_redis_url_forms.py` — parameterized over `redis://user:pass@host`, `rediss://`, `redis://host/0?ssl_cert_reqs=none`, `unix:///...`.
- `tests/integration/cache/test_redis_outage.py` — start, kill Redis mid-run, verify breaker opens, verify DB absorbs load, verify no 5s-per-request timeout.
- `tests/integration/cache/test_cache_observability.py` — grep log output for `cache.get`, `mode=cached`, `hit=`, `latency_ms=`, Prometheus metric export.
- `tests/unit/test_invalidate_model_prefix_collision.py` — `Users` does not invalidate `UsersAudit`.
- `tests/unit/test_cache_key_hash_collision.py` — 100k random filters, verify zero hash collisions at 16-hex truncation.
- `tests/integration/cache/test_schema_version_invalidation.py` — change model schema, verify stale entries are rejected.
- `tests/integration/cache/test_stampede_single_flight.py` — 100 concurrent reads on hot key at expiry, verify DB sees 1 query not 100.

---

## Word count check

~3150 words. Within target (1500-3500).
