# Milestone 6: Security, Gaps & Polish

Red team identified 2 missing todos and several incomplete items. This milestone closes them.

---

## TODO-34: Build product dependency graph with topological ordering

**Layer**: 6-10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/products.py` (extend)

Product-to-product composition via `ctx.product("other")` creates a dependency DAG.

Implement:
1. **Circular dependency detection** at `@db.product()` registration time — if product A depends_on product B and product B depends_on product A, raise `ValueError` immediately
2. **Topological sort** for pre-warming order — if product B depends_on product A, warm A first
3. **Cascade refresh ordering** — when source changes, products refresh in topological order so downstream products see upstream's latest cache

```python
# Registration-time check:
@db.product("summary", depends_on=["dashboard"])
# → Checks: does "dashboard" product exist? Does it depend_on "summary" (cycle)?

# Pre-warm order:
# If dashboard depends_on ["User", "crm"]
# And summary depends_on ["dashboard"]
# Pre-warm order: dashboard first, then summary

# Cascade refresh:
# CRM changes → dashboard refreshes → summary refreshes (in order, not parallel)
```

Use `graphlib.TopologicalSorter` (Python 3.9+ stdlib) for the sort. `CycleError` on cycles.

**Test**: Tier 1 — test cycle detection, topological sort, cascade ordering.

---

## TODO-35: Build filter allowlist for parameterized products

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/serving.py` (extend)

Security H6: parameterized product query filters must be validated.

Implement:
1. **Operator allowlist**: only `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin` allowed. Reject `$where`, `$regex`, and any operator not in the list.
2. **Max limit enforcement**: `limit` parameter clamped to `rate_limit.max_limit` (default 1000). Values above are silently clamped.
3. **Page parameter validation**: `page` must be positive integer. Non-numeric or negative values → 400 error.
4. **Cache key canonicalization**: `json.dumps(filter, sort_keys=True, default=str)` for deterministic cache keys. Prevents `{"a":1,"b":2}` vs `{"b":2,"a":1}` producing different keys.

```python
ALLOWED_OPERATORS = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"}

def validate_filter(filter_dict: dict) -> dict:
    """Validate and sanitize filter operators. Raises ValueError on disallowed operators."""
    for key, value in filter_dict.items():
        if isinstance(value, dict):
            for op in value:
                if op.startswith("$") and op not in ALLOWED_OPERATORS:
                    raise ValueError(f"Disallowed filter operator: {op}")
    return filter_dict
```

**Test**: Tier 1 — test allowlist enforcement, limit clamping, cache key canonicalization. Tier 2 — test with real parameterized product endpoint.

---

## TODO-36: Build OAuth2Auth token lifecycle manager

**Layer**: 2-3
**File**: `packages/kailash-dataflow/src/dataflow/fabric/auth.py`

OAuth2 client credentials flow with auto-refresh (doc 04, Resolution 8):

1. **Token acquisition**: POST to `token_url` with client_id and client_secret (read from env per-request)
2. **Token caching**: in-memory only (never Redis, never disk — doc 01-redteam H5)
3. **Expiry tracking**: parse `expires_in` from token response, refresh 60s before expiry
4. **Auto-refresh**: transparent to callers — `get_access_token()` returns valid token or refreshes first
5. **Token URL validation**: same SSRF checks as source URLs (no private IPs)
6. **Client secret handling**: re-read from env var at refresh time, not cached

```python
class OAuth2Auth:
    async def get_access_token(self) -> str:
        if self._token and self._expires_at > datetime.now(timezone.utc) + timedelta(seconds=60):
            return self._token
        return await self._refresh()
```

**Test**: Tier 2 — test against real OAuth2 token endpoint (or local mock server). Test refresh lifecycle, expiry handling.

---

## TODO-37: Specify webhook nonce storage backend

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/webhooks.py` (extend TODO-16)

Webhook nonce tracking must work across multiple workers.

- **Storage**: Redis set with TTL (5 minutes — matching the timestamp rejection window)
- **Key**: `fabric:webhook:nonces:{source_name}`
- **On receive**: `SADD` nonce to set. If already exists → reject (duplicate delivery)
- **TTL**: set expires after 5 minutes (auto-cleanup)
- **Dev mode**: in-memory set (single worker assumed)

**Test**: Tier 2 — test duplicate rejection with real Redis.

---

## TODO-38: Resolve db.start() canonical parameter table

**Layer**: 6
**File**: `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`

Create the canonical parameter specification:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nexus` | `Optional[Nexus]` | `None` | Existing Nexus to attach to (Option B). None = create internal (Option A) |
| `fail_fast` | `bool` | `True` | Raise on source health check failure. False = skip unhealthy, log warning |
| `dev_mode` | `bool` | `False` | Skip pre-warming, in-memory cache, reduced poll intervals (5s), verbose logging |
| `coordination` | `Optional[str]` | `None` (auto) | "redis" or "postgresql". Auto = Redis if redis_url, else PostgreSQL |
| `host` | `str` | `"127.0.0.1"` | Bind address for internal Nexus (Option A only) |
| `port` | `int` | `8000` | Port for internal Nexus (Option A only) |
| `enable_writes` | `bool` | `False` | Enable write pass-through endpoints |
| `tenant_extractor` | `Optional[Callable]` | `None` | Lambda to extract tenant_id from request. Required if any product has `multi_tenant=True` |

Validate parameter combinations at startup:
- `enable_writes=True` without auth middleware → log WARNING
- `multi_tenant=True` product without `tenant_extractor` → raise `ValueError`
- `host="0.0.0.0"` without auth middleware → log WARNING

**Test**: Tier 1 — test parameter validation logic, warning emissions.

---

## TODO-39: Build dev-mode in-memory debounce fallback

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py` (extend TODO-11)

When `dev_mode=True` and no Redis is available, debounce uses in-memory timers instead of Redis sorted set.

```python
class InMemoryDebouncer:
    """Fallback debouncer for dev mode (no Redis)."""
    
    def __init__(self):
        self._timers: Dict[str, asyncio.TimerHandle] = {}
    
    async def enqueue(self, product_name: str, debounce_seconds: float, callback):
        if product_name in self._timers:
            self._timers[product_name].cancel()
        loop = asyncio.get_running_loop()
        self._timers[product_name] = loop.call_later(
            debounce_seconds,
            lambda: asyncio.create_task(callback(product_name))
        )
```

Automatically selected when Redis is not available. Logs: "Using in-memory debounce (dev mode). Debounce state will not survive process restart."

**Test**: Tier 1 — test in-memory debounce without Redis.
