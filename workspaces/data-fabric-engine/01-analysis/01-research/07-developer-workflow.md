# Developer Workflow: How DataFlow Becomes a Fabric

## The Question

Not "what components does it have" — but "what does a developer DO, step by step, from new project to frontend consuming cached data from multiple sources?"

---

## Today: DataFlow Without Fabric

### Step 1: Install and initialize

```python
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/myapp", cache_enabled=True)
```

### Step 2: Define your data models

```python
@db.model
class User:
    id: str
    name: str
    email: str
    active: bool

@db.model
class Order:
    id: str
    user_id: str
    total: float
    status: str
```

DataFlow auto-generates CRUD nodes, runs migrations, sets up caching.

### Step 3: Use Express API for CRUD

```python
# Create
user = await db.express.create("User", {"id": "u1", "name": "Alice", "email": "alice@co.com", "active": True})

# Read (from cache if available)
user = await db.express.read("User", "u1")

# List with filters
active_users = await db.express.list("User", filter={"active": True}, limit=50)

# Update (auto-invalidates cache)
await db.express.update("User", "u1", {"name": "Alice Smith"})

# Count
count = await db.express.count("User", filter={"active": True})
```

### Step 4: Build API endpoints manually

```python
from nexus import Nexus

app = Nexus("MyApp")

@app.handler("get_dashboard")
async def get_dashboard(tenant_id: str) -> dict:
    # Developer writes this by hand
    users = await db.express.list("User", filter={"active": True})
    orders = await db.express.list("Order", filter={"status": "pending"})

    # Developer manually composes response
    return {
        "active_users": len(users),
        "pending_orders": len(orders),
        "total_revenue": sum(o["total"] for o in orders),
    }

@app.handler("list_users")
async def list_users(tenant_id: str, page: int = 1, limit: int = 50) -> dict:
    users = await db.express.list("User", limit=limit, offset=(page-1)*limit)
    count = await db.express.count("User")
    return {"data": users, "total": count, "page": page}
```

### Step 5: Add external data sources — THIS IS WHERE IT FALLS APART

```python
import httpx
import json

# Developer writes custom API client
async def get_crm_contacts():
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.salesforce.com/v1/contacts",
            headers={"Authorization": f"Bearer {os.environ['SF_TOKEN']}"},
        )
        resp.raise_for_status()
        return resp.json()

# Developer writes another custom client
def read_hr_spreadsheet():
    import openpyxl
    wb = openpyxl.load_workbook("/shared/hr/employees.xlsx")
    ws = wb.active
    return [dict(zip([c.value for c in ws[1]], [c.value for c in row])) for row in ws.iter_rows(min_row=2)]

# Developer writes caching manually
_crm_cache = None
_crm_cache_time = None

async def get_crm_contacts_cached():
    global _crm_cache, _crm_cache_time
    if _crm_cache and (time.time() - _crm_cache_time) < 300:
        return _crm_cache
    _crm_cache = await get_crm_contacts()
    _crm_cache_time = time.time()
    return _crm_cache

# Developer updates the handler to combine sources
@app.handler("get_dashboard")
async def get_dashboard(tenant_id: str) -> dict:
    users = await db.express.list("User", filter={"active": True})
    orders = await db.express.list("Order", filter={"status": "pending"})
    contacts = await get_crm_contacts_cached()  # Manual caching
    hr = read_hr_spreadsheet()                   # No caching at all

    return {
        "active_users": len(users),
        "pending_orders": len(orders),
        "total_revenue": sum(o["total"] for o in orders),
        "crm_contacts": len(contacts),
        "employee_count": len(hr),
    }
```

### What's Wrong With This

1. **Two completely different data access patterns** — Express API for database, custom code for everything else
2. **Manual caching** — TTL-based `_crm_cache` with global variables. Error-prone. No invalidation on failure.
3. **No caching at all** for the Excel file — reads disk on every request
4. **No error handling** — if Salesforce API is down, the entire dashboard fails
5. **No pre-warming** — first request after deploy is slow for all sources
6. **Handler couples FE to source details** — FE team needs to know which handler returns which data shape
7. **Every new source = more custom code** — adding Stripe, Slack, S3 means more manual integrations
8. **Cache is wrong** — 5 minutes TTL means 5 minutes of potentially stale data, then a slow refetch

**This is Aether's exact problem.** 24 custom adapters, 5,753 LOC of adapter code, zero backend caching, 30s stale time on FE.

---

## Tomorrow: DataFlow With Fabric

### Step 1: Install and initialize (SAME)

```python
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/myapp", cache_enabled=True)
```

### Step 2: Define your data models (SAME)

```python
@db.model
class User:
    id: str
    name: str
    email: str
    active: bool

@db.model
class Order:
    id: str
    user_id: str
    total: float
    status: str
```

### Step 3: Register external sources (NEW — replaces custom code)

```python
from dataflow.fabric import RestSource, FileSource, CloudSource

# CRM — was: 50+ lines of custom httpx client + manual caching
db.source("crm", RestSource(
    url=os.environ["CRM_API_URL"],
    auth={"type": "bearer", "token_env": "CRM_TOKEN"},
    poll_interval=300,  # Check for changes every 5 min
))

# HR spreadsheet — was: 20+ lines of openpyxl code with no caching
db.source("hr", FileSource(
    path="/shared/hr/employees.xlsx",
    watch=True,  # OS-level file watch — instant refresh on save
))

# Documents — was: 30+ lines of boto3 code
db.source("docs", CloudSource(
    bucket=os.environ["DOCS_BUCKET"],
    provider="s3",
))
```

**What happened**: Three source registrations replaced 100+ lines of custom integration code. Each source gets automatic:

- Connection management with circuit breaker
- Change detection (ETag for REST, file watch for local, metadata for cloud)
- Health monitoring
- State machine lifecycle (configured → active → paused → error)

### Step 4: Define data products (NEW — replaces manual handlers)

```python
from dataflow.fabric import StalenessPolicy
from datetime import timedelta

@db.product("dashboard", mode="materialized", staleness=StalenessPolicy(
    max_age=timedelta(hours=1),
    on_stale="serve_with_warning",
    on_source_error="keep_cache",
))
async def dashboard(ctx):
    """Dashboard summary — combines database + CRM + HR data."""
    users = await ctx.express.list("User", filter={"active": True})
    orders = await ctx.express.list("Order", filter={"status": "pending"})
    contacts = await ctx.source("crm").fetch("/contacts")
    hr = await ctx.source("hr").read()

    return {
        "active_users": len(users),
        "pending_orders": len(orders),
        "total_revenue": sum(o["total"] for o in orders),
        "crm_contacts": len(contacts),
        "employee_count": len(hr),
    }

@db.product("users", mode="parameterized")
async def users_product(ctx, filter=None, page=1, limit=50):
    """User list with CRM enrichment."""
    users = await ctx.express.list("User", filter=filter, limit=limit, offset=(page-1)*limit)
    count = await ctx.express.count("User", filter=filter)
    return {"data": users, "total": count, "page": page}

@db.product("documents", mode="virtual")
async def documents_product(ctx, prefix=None):
    """Documents from S3 — pass-through, not cached."""
    return await ctx.source("docs").list(prefix=prefix)
```

**What happened**: Data products define WHAT data the FE needs. The fabric handles:

- When to re-materialize (when any source changes)
- Where to cache (Redis or memory)
- How to serve (auto-generated endpoints)
- What to do on failure (staleness policy)

### Step 5: Start the fabric (NEW)

```python
await db.start()
```

**What happens on `db.start()`:**

1. Connects to all registered sources
2. Runs health checks on each source
3. Pre-warms ALL materialized products — fetches data, runs product functions, populates cache
4. Starts change detection watchers/pollers for each source
5. Registers auto-generated endpoints with Nexus

**After `db.start()` returns:**

- Every materialized product is in cache and ready
- Every source has an active watcher/poller
- Nexus endpoints are live
- **The first FE request gets instant data — no loading spinner**

### Step 6: FE consumes from auto-generated endpoints (NEW)

```
GET /fabric/dashboard          → cached dashboard (sub-ms response)
GET /fabric/users?page=2       → cached user list (cached per query combo)
GET /fabric/documents?prefix=reports/  → pass-through to S3

Response headers:
  X-Fabric-Freshness: 2026-04-02T14:30:00Z
  X-Fabric-Source: cache
  X-Fabric-Product: dashboard
```

FE code:

```typescript
// Before: 31 hook files, 3,835 LOC, custom per handler
export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get("/fabric/dashboard"),
    staleTime: Infinity, // Cache is always correct — fabric manages freshness
  });
}
```

**`staleTime: Infinity`** — the FE never refetches on its own. The fabric manages freshness via pipeline. When the fabric updates cache, the FE can either:

- Poll `/fabric/dashboard` periodically (simple)
- Subscribe via WebSocket for push updates (real-time)
- Just use `staleTime: 60000` as a safety net (practical)

### Step 7: Writes go through fabric (NEW)

```python
# Write to database source
await db.fabric.write("User", "create", {"id": "u2", "name": "Bob", ...})
# → Creates user via Express API
# → Triggers refresh of all products that depend on User model
# → Cache updated atomically

# Write to CRM source
await db.fabric.write("crm", "create", {"name": "New Contact", ...})
# → POSTs to CRM API
# → Triggers refresh of all products that depend on "crm" source
# → Cache updated atomically
```

---

## Side-by-Side Comparison

| Step                 | Without Fabric                                                  | With Fabric                                       |
| -------------------- | --------------------------------------------------------------- | ------------------------------------------------- |
| **Initialize**       | `DataFlow(url)`                                                 | `DataFlow(url)` — same                            |
| **DB models**        | `@db.model`                                                     | `@db.model` — same                                |
| **External sources** | 50-100 LOC per source (httpx, boto3, openpyxl) + manual caching | `db.source("name", RestSource(...))` — 5-10 lines |
| **Data composition** | Manual handler code combining sources                           | `@db.product("name")` function                    |
| **Caching**          | Manual TTL globals, or no caching                               | Automatic pipeline-driven cache                   |
| **Pre-warming**      | None — first request is cold                                    | `await db.start()` warms everything               |
| **API endpoints**    | Manual Nexus handler per data shape                             | Auto-generated from products                      |
| **Error handling**   | Manual try/except per source                                    | Circuit breaker + staleness policy                |
| **FE consumption**   | Custom hook per handler                                         | Generic hook per product                          |
| **Cache freshness**  | TTL-based (stale data for N seconds)                            | Pipeline-driven (always current)                  |

---

## What Changes in the Developer's Mental Model

### Before: "I write code to fetch data, cache it, and serve it"

```
Developer thinks about:
- How to connect to each source (different for each)
- How to cache results (TTL? Redis? memory? globals?)
- How to compose responses (manual joins in handlers)
- How to handle errors (try/except per source)
- How to invalidate cache (manually, or just wait for TTL)
- How to write API endpoints (one handler per data shape)
```

### After: "I declare what I need, DataFlow handles the rest"

```
Developer thinks about:
- What sources exist (register once)
- What data the FE needs (define products)
- What freshness is acceptable (staleness policy)

Developer does NOT think about:
- How to connect (adapter handles it)
- How to cache (pipeline handles it)
- When to refresh (change detection handles it)
- How to serve (auto-generated endpoints)
- What to do on failure (circuit breaker + staleness policy)
```

**The mental model shift**: from **imperative** ("fetch this, cache it, serve it") to **declarative** ("I need this data, from these sources, this fresh").

---

## The Three New Concepts

A developer learns three new things. Everything else is existing DataFlow:

### 1. `db.source()` — Register an external data source

```python
db.source("name", SourceConfig(...))
```

"I have data at this URL / path / bucket. DataFlow, manage it for me."

### 2. `@db.product()` — Define a data product

```python
@db.product("name", mode="materialized")
async def product_fn(ctx):
    ...
    return data
```

"When the FE asks for 'name', give them this data composed from these sources."

### 3. `await db.start()` — Start the fabric

```python
await db.start()
```

"Pre-warm everything, start watching for changes, serve endpoints."

That's it. Three new concepts. Everything else (`@db.model`, `db.express`, caching, Nexus) is unchanged.

---

## Complete Minimal Example

```python
from dataflow import DataFlow
from dataflow.fabric import RestSource, FileSource, StalenessPolicy
from datetime import timedelta
import os

# 1. Initialize (existing)
db = DataFlow(os.environ["DATABASE_URL"])

# 2. Define models (existing)
@db.model
class User:
    id: str
    name: str
    email: str
    active: bool

# 3. Register sources (new)
db.source("crm", RestSource(
    url=os.environ["CRM_API_URL"],
    auth={"type": "bearer", "token_env": "CRM_TOKEN"},
    poll_interval=300,
))

db.source("config", FileSource(
    path="./config/settings.yaml",
    watch=True,
))

# 4. Define products (new)
@db.product("dashboard", mode="materialized")
async def dashboard(ctx):
    users = await ctx.express.list("User", filter={"active": True})
    contacts = await ctx.source("crm").fetch("/contacts")
    config = await ctx.source("config").read()
    return {
        "user_count": len(users),
        "contact_count": len(contacts),
        "settings": config,
    }

# 5. Start (new)
await db.start()

# That's it.
# GET /fabric/dashboard → instant cached data
# Cache refreshes when User table changes, CRM returns new ETag, or config file is saved
# FE never waits. Cache is always correct.
```
