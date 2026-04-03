# Final Convergence: All Gaps Resolved

Three red team rounds produced 23 findings. This document resolves every CRITICAL and MAJOR finding into a single coherent design.

---

## Resolution 1: Response Format — Headers, Not Body Envelope

**Problem**: `_fabric` body envelope breaks API contracts. Headers are the right place for transport metadata.

**Resolution**: Use HTTP headers. Response body is CLEAN — exactly what the product function returns.

```
GET /fabric/dashboard

HTTP/1.1 200 OK
X-Fabric-Freshness: fresh
X-Fabric-Age: 127
X-Fabric-Cached-At: 2026-04-02T14:30:00Z
X-Fabric-Pipeline-Ms: 847
X-Fabric-Mode: materialized
Content-Type: application/json

{
  "total_mrr": 125000,
  "paying_customers": 342,
  "deals_closed_this_month": 7,
  "degraded": false
}
```

Cold product:

```
HTTP/1.1 202 Accepted
X-Fabric-Freshness: cold
Retry-After: 5

{"status": "warming", "product": "dashboard"}
```

FE reads headers:

```typescript
const response = await fetch("/fabric/dashboard");
const isFresh = response.headers.get("X-Fabric-Freshness") === "fresh";
const age = parseInt(response.headers.get("X-Fabric-Age") || "0");
const data = await response.json(); // Clean — no envelope to unwrap
```

---

## Resolution 2: Authentication on Fabric Endpoints

**Problem**: Zero auth on auto-generated endpoints means anyone can access any product.

**Resolution**: Products inherit the application's auth middleware. Products can optionally declare required roles.

```python
# Option A: Inherit from Nexus middleware (default)
# If the app has auth middleware on Nexus, fabric endpoints inherit it automatically
app = Nexus("MyApp", middleware=[auth_middleware])
await db.start(nexus=app)
# All fabric endpoints now require authentication

# Option B: Per-product role requirements
@db.product("admin_metrics",
    depends_on=["User", "billing"],
    auth={"roles": ["admin", "super_admin"]},  # Only these roles can access
)
async def admin_metrics(ctx): ...

# Option C: Public products (explicitly opted in)
@db.product("public_status",
    depends_on=["health"],
    auth={"public": True},  # No auth required
)
async def public_status(ctx): ...
```

Internal endpoints (`/fabric/_health`, `/fabric/_trace`) require admin role by default.

---

## Resolution 3: Rate Limiting

**Problem**: Parameterized products can be abused by enumerating parameter space.

**Resolution**: Built-in rate limiting per product, per client.

```python
@db.product("users",
    mode="parameterized",
    depends_on=["User"],
    rate_limit=RateLimit(
        max_requests=100,       # per client per minute
        max_unique_params=50,   # max distinct parameter combos cached
    ),
)
async def users(ctx, filter=None, page=1, limit=50): ...
```

Default rate limits: 1000 req/min per client for materialized, 100 req/min for parameterized. Configurable globally and per-product.

Cache cardinality limit: parameterized products have `max_unique_params` (default: 1000). LRU eviction of least-recently-accessed parameter combos.

---

## Resolution 4: Large-Source Pagination

**Problem**: `ctx.source("crm").fetch("contacts")` with 50K contacts — returns what?

**Resolution**: Source handles support pagination natively. Product functions control how they consume.

```python
# Option A: Fetch single page (default, explicit)
page_1 = await ctx.source("crm").fetch("contacts", params={"limit": 100, "offset": 0})

# Option B: Fetch all pages (auto-pagination)
all_contacts = await ctx.source("crm").fetch_all("contacts", page_size=100)
# Internally: fetches page 1, 2, 3... until no more results
# Memory guard: max_records=100_000 (configurable, raises if exceeded)
# Backpressure: 100ms delay between pages to avoid rate limits

# Option C: Stream pages (for very large sources)
async for page in ctx.source("crm").fetch_pages("contacts", page_size=100):
    # Process page by page — never holds all records in memory
    for contact in page:
        process(contact)
```

`fetch()` returns a single request response (one page).
`fetch_all()` returns all pages collected into a list (convenience, has memory guard).
`fetch_pages()` returns an async iterator (memory-efficient for large sources).

Added to `SourceHandle` spec:

```python
class SourceHandle:
    async def fetch(self, path, params=None) -> Any         # Single request
    async def fetch_all(self, path, page_size=100, max_records=100_000) -> list  # All pages
    async def fetch_pages(self, path, page_size=100) -> AsyncIterator  # Stream pages
    async def read(self) -> Any                              # Read entire source
    async def list(self, prefix="", limit=100) -> list       # List items
    async def write(self, path, data) -> Any                 # Write
    def last_successful_data(self, path="") -> Optional[Any] # Last known good
```

---

## Resolution 5: Multi-Worker / Multi-Replica Coordination

**Problem**: Multiple processes = duplicate polling, duplicate pipelines, wasted API calls.

**Resolution**: Leader election via Redis or PostgreSQL. Only the leader runs fabric background tasks.

```python
await db.start(
    nexus=app,
    coordination="redis",  # or "postgresql" (uses advisory locks)
    # Default: "redis" if redis_url configured, else "postgresql"
)
```

**How it works:**

- On `db.start()`, each worker attempts to acquire a coordination lock
- **Leader worker**: Runs poll timers, file watchers, webhook listeners, pipeline executions
- **Follower workers**: Serve from shared cache (Redis). Do NOT poll or run pipelines
- Leader heartbeat: every 10 seconds. If leader dies, followers compete for leadership
- Lock backend: Redis (`SETNX` with TTL) or PostgreSQL (`pg_advisory_lock`)

**All workers serve endpoints.** Cache is shared (Redis). Only one worker polls and refreshes.

```
Worker 1 (leader):  polls sources, runs pipelines, writes cache
Worker 2 (follower): serves /fabric/* from Redis cache
Worker 3 (follower): serves /fabric/* from Redis cache
```

**In-memory cache mode** (dev): No coordination needed — single process assumed.

---

## Resolution 6: Multi-Tenancy

**Problem**: SaaS apps need tenant-isolated data. One cache key per product is wrong.

**Resolution**: Tenant context flows through the entire fabric.

```python
# Tenant-aware product
@db.product("dashboard",
    depends_on=["Customer", "crm"],
    multi_tenant=True,  # Cache is per-tenant
)
async def dashboard(ctx: FabricContext) -> dict:
    # ctx.tenant_id is set from the request's auth context
    customers = await ctx.express.list("Customer", filter={
        "tenant_id": ctx.tenant_id,
        "active": True,
    })
    return {"customer_count": len(customers)}
```

Cache key becomes: `fabric:{tenant_id}:dashboard`
Pre-warming warms for ALL known tenants (or a configured set).
Products without `multi_tenant=True` are shared across tenants (e.g., public config).

Tenant ID extraction: from JWT claim, from header, or from query param — configured at `db.start()`:

```python
await db.start(
    nexus=app,
    tenant_extractor=lambda request: request.state.jwt_payload.get("tenant_id"),
)
```

---

## Resolution 7: Scheduled Products

**Problem**: Some products need time-triggered refresh (daily summaries, weekly reports), not just source-change-triggered.

**Resolution**: Products can declare a schedule alongside their source dependencies.

```python
@db.product("daily_summary",
    depends_on=["Order", "billing"],
    schedule="0 0 * * *",  # Cron: midnight daily
)
async def daily_summary(ctx: FabricContext) -> dict:
    today = date.today()
    orders = await ctx.express.list("Order", filter={
        "created_at": {"$gte": today.isoformat()},
    })
    return {
        "date": today.isoformat(),
        "orders_today": len(orders),
        "revenue_today": sum(o["total"] for o in orders),
    }
```

The product refreshes:

- When any source in `depends_on` changes (normal flow)
- AND at the scheduled time (cron trigger)

The cron scheduler runs on the leader worker only (no duplicate execution).

---

## Resolution 8: Source Credential Rotation

**Problem**: OAuth2 tokens expire. Env vars change. Running fabric has no way to pick up new credentials.

**Resolution**: Auth objects support refresh flows.

```python
# Static token (reads env var on each request — picks up changes)
db.source("crm", RestSource(
    auth=BearerAuth(token_env="CRM_TOKEN"),
    # On every request, reads os.environ["CRM_TOKEN"]
    # If the token is rotated by a sidecar or secrets manager, fabric picks it up
))

# OAuth2 with auto-refresh
db.source("erp", RestSource(
    auth=OAuth2Auth(
        client_id_env="ERP_CLIENT_ID",
        client_secret_env="ERP_CLIENT_SECRET",
        token_url="https://erp.example.com/oauth/token",
        # Fabric manages token refresh automatically
    ),
))
```

`BearerAuth` reads the env var on EACH request, not once at registration. Token rotation via env var injection (Kubernetes secrets, Vault sidecar) works without restart.

`OAuth2Auth` manages the token lifecycle: acquires, caches, refreshes before expiry.

---

## Resolution 9: Cross-Document Contradictions Fixed

| Contradiction                             | Resolution                                                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Auth: typed objects vs dicts              | **Typed objects only.** Architecture plan examples corrected.                                                 |
| Response: headers vs body envelope        | **Headers only.** Body is clean product data.                                                                 |
| Write: POST-only vs POST+PUT              | **POST-only with `operation` in body.** One endpoint per target.                                              |
| `fetch()` path: leading slash vs no slash | **No leading slash.** Path is appended to base URL.                                                           |
| `depends_on` default: `[]` vs required    | **Required for materialized/parameterized. Optional for virtual.** No default — omitting raises `ValueError`. |

---

## Resolution 10: Graceful Shutdown

```python
# On SIGTERM (Kubernetes pod termination)
await db.stop()
```

Shutdown sequence:

1. Stop accepting webhook deliveries
2. Wait for in-flight pipeline executions to complete (timeout: 30s)
3. Release coordination lock (leader yields to another worker)
4. Close source connections
5. Flush metrics
6. Return

If pipeline exceeds 30s timeout: abandon, log warning. Cache retains last successful data (atomic swap guarantees this — incomplete pipelines never write to cache).

---

## The Complete Design (Summary)

| Concern                 | Resolution                                                                   |
| ----------------------- | ---------------------------------------------------------------------------- |
| **Response format**     | HTTP headers for `_fabric` metadata. Clean body.                             |
| **Authentication**      | Inherits Nexus middleware. Per-product role requirements optional.           |
| **Rate limiting**       | Per-product, per-client. Cache cardinality limits for parameterized.         |
| **Pagination**          | `fetch()` = one page. `fetch_all()` = all pages. `fetch_pages()` = stream.   |
| **Multi-worker**        | Leader election (Redis or PG). Leader polls, all workers serve.              |
| **Multi-tenancy**       | `multi_tenant=True` on products. Tenant from request context.                |
| **Scheduled refresh**   | Cron expression on products. Runs on leader only.                            |
| **Credential rotation** | Env vars read per-request. OAuth2 auto-refresh.                              |
| **Graceful shutdown**   | Wait for in-flight, release lock, close connections, flush.                  |
| **Memory**              | Per-product cache size limits. `max_records` on `fetch_all()`. LRU eviction. |
