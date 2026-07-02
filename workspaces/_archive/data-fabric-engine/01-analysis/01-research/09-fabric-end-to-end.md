# The Fabric End-to-End: Anchored on Needs

Previous documents described components. This document describes what HAPPENS — the complete lifecycle of data through the fabric, anchored on what each person needs at each moment.

---

## What Is the Fabric, Actually?

The fabric is not a library you call. It is a **runtime system** that runs alongside your application. When you call `db.start()`, you are starting:

- **Background workers** that watch sources for changes
- **Pipelines** that fetch, transform, and cache data when changes are detected
- **A serving layer** that responds to FE requests from cache
- **A monitoring surface** that reports what's happening inside

Think of it like a database engine. You don't call PostgreSQL function-by-function. You configure it, start it, and it runs — handling queries, managing connections, maintaining indexes. The fabric does the same thing for your multi-source data.

---

## The Data Lifecycle

```
┌─────────┐     ┌──────────┐     ┌───────────┐     ┌─────────┐     ┌──────────┐
│  SOURCE  │────→│  INGEST  │────→│ TRANSFORM │────→│  CACHE  │────→│  SERVE   │
│          │     │          │     │           │     │         │     │          │
│ CRM API  │     │ Detect   │     │ Normalize │     │ Atomic  │     │ GET /fab │
│ Database │     │ change,  │     │ Enrich    │     │ swap on │     │ Headers  │
│ File     │     │ fetch    │     │ Validate  │     │ success │     │ Fresh?   │
│ Cloud    │     │ if new   │     │ Aggregate │     │ only    │     │ Stale?   │
└─────────┘     └──────────┘     └───────────┘     └─────────┘     └──────────┘
      ↑                                                                  │
      │              ┌────────────┐                                      │
      └──────────────│   WRITE    │←─────────────────────────────────────┘
                     │ pass-thru  │
                     └────────────┘
                           ↕
                     ┌────────────┐
                     │  OBSERVE   │
                     │            │
                     │ Health     │
                     │ Metrics    │
                     │ Traces     │
                     │ Alerts     │
                     └────────────┘
```

Each stage below answers: **what need does it serve, what happens, and what does the developer see?**

---

## Stage 1: Sources — "Where is my data?"

### The Need

A developer has data in multiple places. A CRM, a PostgreSQL database, an Excel file the finance team maintains on SharePoint, an internal REST API. They need all of it, combined, in their application.

### What the Developer Does

```python
db = DataFlow(os.environ["DATABASE_URL"])

# Own database — I control the schema
@db.model
class Customer:
    id: str
    name: str
    plan: str
    mrr: float

# CRM — I read from it, it has its own schema
db.source("crm", RestSource(
    url=os.environ["CRM_API_URL"],
    auth=BearerAuth(token_env="CRM_TOKEN"),
    endpoints={
        "contacts": "/api/v1/contacts",
        "deals": "/api/v1/deals",
    },
))

# Finance spreadsheet on SharePoint — updated weekly by finance team
db.source("finance", CloudSource(
    bucket=os.environ["SHAREPOINT_SITE"],
    provider="sharepoint",
    path="Shared Documents/Finance/revenue.xlsx",
))

# Internal billing API
db.source("billing", RestSource(
    url=os.environ["BILLING_API_URL"],
    auth=ApiKeyAuth(key_env="BILLING_KEY", header="X-Api-Key"),
    endpoints={
        "invoices": "/v2/invoices",
        "usage": "/v2/usage",
    },
))
```

### What the Developer Needs to Know

**"When does the fabric check each source for changes?"**

Every source has a **change detection strategy** — how the fabric knows something changed without fetching everything. The developer sets the rhythm:

```python
# REST API: poll for changes using HTTP caching headers
db.source("crm", RestSource(
    ...
    poll_interval=300,          # Check every 5 minutes
    # Fabric sends If-None-Match with stored ETag
    # If API returns 304 Not Modified → skip (no data transfer)
    # If API returns 200 → data changed, pipeline runs
))

# File: OS-level watch (instant notification on save)
db.source("finance", CloudSource(
    ...
    # SharePoint: poll metadata endpoint for LastModified
    poll_interval=600,          # Check every 10 minutes (file changes rarely)
))

# Database: lightweight change probe
# Fabric runs: SELECT MAX(updated_at) FROM customers
# If timestamp hasn't changed → skip
# poll_interval defaults to 60s for databases
```

**"What if a source pushes data TO the fabric instead of the fabric polling?"**

Sources can push changes via webhooks:

```python
db.source("crm", RestSource(
    ...
    webhook=WebhookConfig(
        path="/webhooks/crm",     # Fabric listens here
        secret_env="CRM_WEBHOOK_SECRET",
        events=["contact.created", "contact.updated", "deal.closed"],
    ),
    poll_interval=3600,           # Polling as fallback only (every hour)
))
```

When the CRM sends a webhook:

1. Fabric receives POST at `/webhooks/crm`
2. Validates signature using shared secret
3. Immediately triggers pipeline for all products that `depends_on=["crm"]`
4. No waiting for next poll cycle

**Push + pull is the right default.** Webhooks for instant updates when the source supports them. Polling as fallback for everything else. File watch for local files (instant, no polling needed).

---

## Stage 2: Ingest — "Get the data, but only when it changed"

### The Need

The developer does NOT want to fetch everything on every check. If the CRM has 50,000 contacts and only 3 changed since last check, the fabric should fetch only those 3.

### What Happens

The pipeline runs in three phases:

```
Phase 1: DETECT — Did anything change?
  REST: Send If-None-Match with stored ETag → 304 means no change
  File: watchdog event → file modified timestamp changed
  Cloud: ListObjects → compare ETags/LastModified of objects
  Database: SELECT MAX(updated_at) → compare with stored timestamp

Phase 2: FETCH — Get what changed
  REST: GET /contacts?updated_since=<last_sync_time> (if API supports it)
        or GET /contacts (full fetch if no incremental endpoint)
  File: Read file content
  Cloud: GetObject for objects whose metadata changed
  Database: SELECT * FROM customers WHERE updated_at > <last_sync_time>

Phase 3: DELIVER — Pass to product pipeline
  Raw data handed to product functions for transform + cache
```

### What the Developer Sees

The developer doesn't write any of this. It happens automatically based on the source type. But they CAN see it:

```python
# Check what the fabric is doing right now
status = db.fabric.status()

# Returns:
{
    "sources": {
        "crm": {
            "state": "active",
            "last_check": "2026-04-02T14:30:00Z",
            "last_change_detected": "2026-04-02T14:25:00Z",
            "checks_since_start": 48,
            "changes_detected": 3,
            "strategy": "etag_poll",
            "poll_interval": 300,
            "next_check_in": 127,       # seconds until next poll
            "health": "healthy",
            "circuit_breaker": "closed",
            "consecutive_failures": 0,
        },
        "finance": {
            "state": "active",
            "last_check": "2026-04-02T14:20:00Z",
            "last_change_detected": "2026-04-01T09:00:00Z",  # Yesterday
            "strategy": "metadata_poll",
            "health": "healthy",
        },
        "billing": {
            "state": "error",
            "last_check": "2026-04-02T14:28:00Z",
            "health": "unhealthy",
            "circuit_breaker": "open",   # Tripped after 3 failures
            "consecutive_failures": 5,
            "last_error": "ConnectionTimeout: billing API did not respond within 10s",
            "recovery_probe_in": 30,     # Circuit breaker will probe in 30s
        },
    },
}
```

---

## Stage 3: Transform — "Shape the data for what the frontend needs"

### The Need

Raw source data is never in the shape the frontend needs. The CRM returns contacts with field names like `FirstName`, `LastName`, `AccountId`. The database has `mrr` as a decimal. The finance spreadsheet has revenue in columns B through M. The frontend needs a dashboard with combined metrics.

### How Logic Is Written

Product functions ARE the transformation logic. They are plain Python async functions that receive a context and return the data shape the frontend needs:

```python
@db.product("revenue_dashboard",
    depends_on=["Customer", "crm", "finance", "billing"],
    staleness=StalenessPolicy(max_age=timedelta(hours=2)),
)
async def revenue_dashboard(ctx: FabricContext) -> dict:
    """
    This function runs:
    - On startup (pre-warming)
    - Whenever ANY dependency changes (Customer table, CRM, finance file, billing API)
    - The result is cached and served to all FE requests
    """

    # 1. FETCH from each source
    customers = await ctx.express.list("Customer", filter={"plan": {"$ne": "free"}})
    crm_deals = await ctx.source("crm").fetch("deals", params={"status": "won"})
    finance_data = await ctx.source("finance").read()  # Reads the Excel file
    invoices = await ctx.source("billing").fetch("invoices", params={"status": "paid"})

    # 2. NORMALIZE — each source has different shapes
    #    This is where the developer writes their business logic
    total_mrr = sum(c["mrr"] for c in customers)

    deals_by_month = {}
    for deal in crm_deals:
        month = deal["CloseDate"][:7]  # "2026-04" from "2026-04-15"
        deals_by_month.setdefault(month, []).append({
            "name": deal["Name"],
            "amount": deal["Amount"],
            "account": deal["AccountName"],
        })

    # Parse Excel: finance team puts monthly revenue in row 2, columns B-M
    monthly_revenue = []
    for row in finance_data:
        if row.get("metric") == "revenue":
            for month_col in ["jan", "feb", "mar", "apr", "may", "jun",
                              "jul", "aug", "sep", "oct", "nov", "dec"]:
                if row.get(month_col):
                    monthly_revenue.append({
                        "month": month_col,
                        "revenue": float(row[month_col]),
                    })

    outstanding = sum(inv["amount"] for inv in invoices if inv["status"] == "pending")

    # 3. COMPOSE — return the shape the FE needs
    return {
        "total_mrr": total_mrr,
        "paying_customers": len(customers),
        "deals_closed_this_month": len(deals_by_month.get("2026-04", [])),
        "recent_deals": deals_by_month.get("2026-04", [])[:10],
        "monthly_revenue": monthly_revenue,
        "outstanding_invoices": outstanding,
        "last_updated": datetime.utcnow().isoformat(),
    }
```

### The Key Insight About Logic

**The product function IS the business logic layer.** It replaces:

- Backend API handlers that compose data
- Custom data transformation code
- Manual cache management code
- Data aggregation logic scattered across services

It is NOT:

- A database query (Express handles that)
- A source connector (adapters handle that)
- A cache manager (fabric handles that)
- An HTTP endpoint (Nexus handles that)

The product function is ONLY: **"given data from sources, what should the frontend see?"**

### Handling Partial Source Failures Inside Products

What if one source is down but others work? The developer decides:

```python
@db.product("dashboard",
    depends_on=["Customer", "crm", "billing"],
    staleness=StalenessPolicy(
        on_source_error="keep_cache",  # Keep serving old data if source fails
    ),
)
async def dashboard(ctx: FabricContext) -> dict:
    # Always available — it's your own database
    customers = await ctx.express.list("Customer")

    # CRM might be down — handle gracefully
    try:
        deals = await ctx.source("crm").fetch("deals")
    except SourceUnavailableError:
        # Use last known data from cache, or empty
        deals = ctx.source("crm").last_successful_data("deals") or []

    # Billing might be down
    try:
        invoices = await ctx.source("billing").fetch("invoices")
    except SourceUnavailableError:
        invoices = ctx.source("billing").last_successful_data("invoices") or []

    return {
        "customers": len(customers),
        "deals": len(deals),
        "invoices": len(invoices),
        "degraded": not ctx.source("crm").healthy or not ctx.source("billing").healthy,
        "degraded_sources": [
            s for s in ["crm", "billing"] if not ctx.source(s).healthy
        ],
    }
```

The product function can report its own health state in the response. The frontend can then show "Some data may be outdated" when `degraded: true`.

---

## Stage 4: Cache — "Store it so nobody waits"

### The Need

The frontend should never wait for a source to respond. Every request should get instant data. The cache is the answer, but the cache must be CORRECT — not just fast.

### How Caching Works

When a product function returns successfully:

```
1. Content hash: SHA-256 of the serialized return value
2. Compare: is the hash different from what's in cache?
   → Same: skip write (nothing changed, save the Redis roundtrip)
   → Different: atomic swap — replace old cache entry with new one
3. Metadata: store alongside the cached data
   {
     "product": "revenue_dashboard",
     "cached_at": "2026-04-02T14:30:00Z",
     "pipeline_duration_ms": 847,
     "sources_used": ["Customer", "crm", "finance", "billing"],
     "source_states": {
       "Customer": {"healthy": true, "last_change": "2026-04-02T14:25:00Z"},
       "crm": {"healthy": true, "last_change": "2026-04-02T14:20:00Z"},
       "finance": {"healthy": true, "last_change": "2026-04-01T09:00:00Z"},
       "billing": {"healthy": false, "used_stale_data": true},
     },
     "content_hash": "a1b2c3...",
   }
```

### What Does NOT Get Cached

- **Virtual products** — pass-through, no cache
- **Failed pipeline runs** — old cache is kept, failure is logged
- **Identical data** — content hash match means skip the write

### Cache Eviction

- **Memory cache**: LRU eviction when memory limit reached. Evicted products become "cold" — next request triggers pipeline.
- **Redis cache**: No eviction by the fabric. Redis memory management applies. Products have optional TTL as a safety net (default: none — pipeline-driven freshness replaces TTL).

---

## Stage 5: Serve — "Give it to the frontend"

### The Need

The FE developer needs ONE interface to get data. They don't want to know which sources exist, how caching works, or what pipelines run. They want: call an endpoint, get data, show it to users.

### What the FE Developer Gets

**Every product becomes a REST endpoint automatically.**

```
GET /fabric/revenue_dashboard
```

Response:

```json
{
  "data": {
    "total_mrr": 125000,
    "paying_customers": 342,
    "deals_closed_this_month": 7,
    "recent_deals": [...],
    "monthly_revenue": [...],
    "outstanding_invoices": 14500,
    "last_updated": "2026-04-02T14:30:00Z",
    "degraded": false,
    "degraded_sources": []
  },
  "_fabric": {
    "product": "revenue_dashboard",
    "cached_at": "2026-04-02T14:30:00Z",
    "freshness": "fresh",
    "age_seconds": 127,
    "mode": "materialized",
    "pipeline_duration_ms": 847
  }
}
```

The `_fabric` metadata tells the FE everything it needs:

- **`freshness`**: `"fresh"` | `"stale"` | `"cold"` — is this data current?
- **`age_seconds`**: how old is this cached result?
- **`cached_at`**: when was this data produced?
- **`pipeline_duration_ms`**: how long did the last refresh take?

### Parameterized Products — Query Parameters

```
GET /fabric/customers?plan=enterprise&page=2&limit=20
```

The parameters map to the product function's arguments:

```python
@db.product("customers", mode="parameterized", depends_on=["Customer", "crm"])
async def customers(ctx, plan: str = None, page: int = 1, limit: int = 50):
    filters = {}
    if plan:
        filters["plan"] = plan

    offset = (page - 1) * limit
    customers = await ctx.express.list("Customer", filter=filters, limit=limit, offset=offset)
    count = await ctx.express.count("Customer", filter=filters)

    # Enrich with CRM data
    for c in customers:
        crm_contact = await ctx.source("crm").fetch(f"contacts/{c['id']}")
        if crm_contact:
            c["crm_stage"] = crm_contact.get("Stage", "unknown")

    return {"data": customers, "total": count, "page": page, "limit": limit}
```

Cache key includes parameters: `fabric:customers:plan=enterprise:page=2:limit=20`
Each unique parameter combination is cached independently.

### Error Responses

```
GET /fabric/revenue_dashboard  (when product is cold — not in cache)
```

Response (202 Accepted):

```json
{
  "data": null,
  "_fabric": {
    "product": "revenue_dashboard",
    "freshness": "cold",
    "status": "warming",
    "retry_after_seconds": 5
  }
}
```

FE knows to retry in 5 seconds. On retry, data is available.

```
GET /fabric/revenue_dashboard  (when product is stale beyond max_age)
```

Response (200 with stale indicator):

```json
{
  "data": { ... },
  "_fabric": {
    "freshness": "stale",
    "age_seconds": 7800,
    "max_age_seconds": 7200,
    "stale_reason": "source 'billing' has been unhealthy for 2h 10m"
  }
}
```

### How the FE Consumes This

```typescript
// Generic fabric hook — works for ANY product
function useFabricProduct<T>(productName: string, params?: Record<string, any>) {
  return useQuery<FabricResponse<T>>({
    queryKey: ["fabric", productName, params],
    queryFn: () => api.get(`/fabric/${productName}`, params),

    // Fabric manages freshness — FE trusts it
    staleTime: 60_000,         // Re-check every 60s as safety net

    // Show stale data while refetching
    placeholderData: keepPreviousData,

    // Handle fabric-specific response
    select: (response) => ({
      data: response.data,
      isFresh: response._fabric.freshness === "fresh",
      isStale: response._fabric.freshness === "stale",
      isCold: response._fabric.freshness === "cold",
      cachedAt: response._fabric.cached_at,
      degradedSources: response.data?.degraded_sources || [],
    }),
  });
}

// Usage in components
function RevenueDashboard() {
  const { data, isFresh, isStale, degradedSources } = useFabricProduct("revenue_dashboard");

  return (
    <div>
      {isStale && <Banner>Some data may be outdated</Banner>}
      {degradedSources.length > 0 && (
        <Banner>Limited data: {degradedSources.join(", ")} unavailable</Banner>
      )}
      <MRRCard value={data.total_mrr} />
      <DealsTable deals={data.recent_deals} />
    </div>
  );
}
```

ONE hook for ALL products. The FE developer never writes custom data fetching logic per endpoint.

---

## Stage 6: Write — "Send data back through the fabric"

### The Need

The FE also needs to CREATE and UPDATE data. If reads go through the fabric, writes should too — otherwise the developer maintains two data access patterns.

### How Writes Work

```
FE: POST /fabric/Customer/write
Body: { "operation": "create", "data": { "name": "Acme Corp", "plan": "enterprise", "mrr": 5000 } }

Fabric:
  1. Validates the request (source exists, operation supported)
  2. Routes to the correct adapter:
     - "Customer" is a @db.model → Express API create
     - "crm" would be a source → REST adapter POST
  3. Executes the write
  4. On success: triggers async refresh of ALL products with "Customer" in depends_on
  5. Returns write result to FE immediately
  6. In background: pipeline runs, cache updated with new data
```

Response:

```json
{
  "result": {
    "id": "cust-789",
    "name": "Acme Corp",
    "plan": "enterprise",
    "mrr": 5000
  },
  "_fabric": {
    "write_target": "Customer",
    "operation": "create",
    "products_refreshing": ["revenue_dashboard", "customers"],
    "refresh_triggered_at": "2026-04-02T14:31:00Z"
  }
}
```

The FE knows:

- The write succeeded
- Two products are being refreshed in the background
- Next GET to those products will have the new data (usually within seconds)

### FE Write Hook

```typescript
function useFabricWrite(target: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { operation: string; data: any }) =>
      api.post(`/fabric/${target}/write`, payload),

    onSuccess: (response) => {
      // Invalidate the products that depend on this target
      for (const product of response._fabric.products_refreshing) {
        queryClient.invalidateQueries({ queryKey: ["fabric", product] });
      }
    },
  });
}

// Usage
function CreateCustomerForm() {
  const createCustomer = useFabricWrite("Customer");

  const handleSubmit = (formData) => {
    createCustomer.mutate({ operation: "create", data: formData });
  };
}
```

---

## Stage 7: Observe — "What's happening inside?"

### The Need

The developer (and later, ops) needs to know:

- Are all sources healthy?
- Are products being refreshed?
- How fresh is the data?
- What went wrong and when?

### The Monitoring Surface

**1. Health Endpoint**

```
GET /fabric/_health
```

```json
{
  "status": "degraded",
  "uptime_seconds": 86400,
  "sources": {
    "crm": {
      "health": "healthy",
      "latency_ms": 230,
      "last_success": "2026-04-02T14:30:00Z"
    },
    "finance": {
      "health": "healthy",
      "latency_ms": 1200,
      "last_success": "2026-04-02T14:20:00Z"
    },
    "billing": {
      "health": "unhealthy",
      "circuit_breaker": "open",
      "last_error": "ConnectionTimeout",
      "down_since": "2026-04-02T12:20:00Z"
    }
  },
  "products": {
    "revenue_dashboard": {
      "freshness": "stale",
      "age_seconds": 7800,
      "last_refresh": "2026-04-02T12:15:00Z",
      "refresh_count": 48
    },
    "customers": {
      "freshness": "fresh",
      "age_seconds": 120,
      "last_refresh": "2026-04-02T14:28:00Z",
      "refresh_count": 720
    }
  },
  "cache": {
    "backend": "redis",
    "hit_rate": 0.94,
    "entries": 847,
    "memory_mb": 12.4
  },
  "pipelines": {
    "total_runs": 1200,
    "successful": 1150,
    "failed": 50,
    "avg_duration_ms": 340
  }
}
```

**2. Structured Logging**

Every pipeline run produces structured logs:

```
[2026-04-02T14:30:00Z] [fabric.pipeline] INFO  product=revenue_dashboard trigger=source_change source=crm
[2026-04-02T14:30:00Z] [fabric.source]   INFO  source=crm action=fetch endpoint=deals records=142 duration_ms=230
[2026-04-02T14:30:00Z] [fabric.source]   INFO  source=finance action=skip reason=no_change last_modified=2026-04-01T09:00:00Z
[2026-04-02T14:30:00Z] [fabric.source]   WARN  source=billing action=fetch_failed error=ConnectionTimeout circuit=open
[2026-04-02T14:30:01Z] [fabric.cache]    INFO  product=revenue_dashboard action=swap content_changed=true duration_ms=12
[2026-04-02T14:30:01Z] [fabric.pipeline] INFO  product=revenue_dashboard status=complete duration_ms=847 sources_used=4 sources_degraded=1
```

**3. Metrics (Prometheus-compatible)**

```
# Source health
fabric_source_health{source="crm"} 1
fabric_source_health{source="billing"} 0
fabric_source_check_duration_seconds{source="crm"} 0.23
fabric_source_consecutive_failures{source="billing"} 5

# Pipeline performance
fabric_pipeline_duration_seconds{product="revenue_dashboard"} 0.847
fabric_pipeline_runs_total{product="revenue_dashboard",status="success"} 48
fabric_pipeline_runs_total{product="revenue_dashboard",status="failure"} 2

# Cache
fabric_cache_hit_total{product="revenue_dashboard"} 12400
fabric_cache_miss_total{product="revenue_dashboard"} 48
fabric_product_age_seconds{product="revenue_dashboard"} 127

# Serving
fabric_request_duration_seconds{product="revenue_dashboard"} 0.001
fabric_request_total{product="revenue_dashboard",freshness="fresh"} 12300
fabric_request_total{product="revenue_dashboard",freshness="stale"} 100
```

**4. Pipeline Trace (Debugging)**

When something goes wrong, the developer needs to trace exactly what happened:

```
GET /fabric/_trace/revenue_dashboard
```

```json
{
  "product": "revenue_dashboard",
  "last_5_runs": [
    {
      "run_id": "run-847",
      "triggered_by": "source_change:crm",
      "started_at": "2026-04-02T14:30:00Z",
      "duration_ms": 847,
      "status": "success",
      "steps": [
        {
          "source": "Customer",
          "action": "express.list",
          "records": 342,
          "duration_ms": 45,
          "from_cache": false
        },
        {
          "source": "crm",
          "action": "fetch:deals",
          "records": 142,
          "duration_ms": 230,
          "status": "ok"
        },
        {
          "source": "finance",
          "action": "read",
          "records": 12,
          "duration_ms": 1200,
          "status": "ok"
        },
        {
          "source": "billing",
          "action": "fetch:invoices",
          "records": 0,
          "duration_ms": 0,
          "status": "unavailable",
          "used_stale": true
        }
      ],
      "cache_action": "swap",
      "content_changed": true
    },
    {
      "run_id": "run-846",
      "triggered_by": "poll_interval",
      "status": "skipped",
      "reason": "no_source_changes_detected"
    }
  ]
}
```

**5. In-Code Observation**

```python
# Programmatic access to fabric state (not just endpoints)
status = db.fabric.status()                           # Full system status
source_health = db.fabric.source_health("crm")        # Single source
product_info = db.fabric.product_info("revenue_dashboard")  # Single product
trace = db.fabric.last_trace("revenue_dashboard")     # Last pipeline trace
```

---

## Tying It All Together: The Complete Picture

### From Salesforce to Dashboard — Every Step

```
1. Developer registers CRM:
   db.source("crm", RestSource(url=..., webhook=WebhookConfig(path="/webhooks/crm")))

2. Developer writes product:
   @db.product("dashboard", depends_on=["Customer", "crm"])
   async def dashboard(ctx): ...

3. Developer starts fabric:
   await db.start()

4. Startup sequence:
   a. Connect to PostgreSQL (existing DataFlow)
   b. Connect to CRM API (health check: GET /api/v1/status → 200)
   c. Pre-warm: run dashboard product function
      - Express fetches Customers from PostgreSQL
      - RestAdapter fetches contacts from CRM
      - Product function transforms and returns dashboard data
      - Cache stores result in Redis
   d. Start CRM poll timer (every 5 min)
   e. Register webhook listener at /webhooks/crm
   f. Register GET /fabric/dashboard endpoint
   g. db.start() returns — fabric is ready

5. FE loads dashboard page:
   GET /fabric/dashboard → 200, data from cache, 1ms response
   _fabric.freshness = "fresh", age_seconds = 3

6. Sales rep creates deal in Salesforce:
   Salesforce fires webhook → POST /webhooks/crm
   Fabric validates signature, identifies source "crm"
   Fabric identifies products: ["dashboard"] depends_on crm
   Fabric runs dashboard pipeline:
     - Fetches fresh Customer data from PostgreSQL
     - Fetches fresh contacts/deals from CRM
     - Runs product function → new dashboard data
     - Content hash differs → atomic swap in cache
   Log: product=dashboard trigger=webhook source=crm duration_ms=450

7. FE next request (or after staleTime expires):
   GET /fabric/dashboard → 200, FRESH data including new deal
   User sees the new deal without doing anything

8. Billing API goes down:
   Poll fails 3 times → circuit breaker opens
   Log: source=billing circuit=open consecutive_failures=3
   Next pipeline run: billing source returns SourceUnavailableError
   Product function catches it, uses stale billing data
   Cache updated with degraded=true
   FE shows "Some data may be outdated" banner
   Health endpoint: status=degraded, billing=unhealthy

9. Billing API recovers:
   Circuit breaker probes after 30s → success
   Circuit breaker closes
   Next pipeline run: billing data fetched successfully
   Cache updated with degraded=false
   FE: banner disappears, fresh data everywhere
```

---

## Summary: What Each Person Does

### Backend Developer

| Task                         | How                                                               |
| ---------------------------- | ----------------------------------------------------------------- |
| Connect to a database        | `@db.model` (existing DataFlow)                                   |
| Connect to an API            | `db.source("name", RestSource(...))`                              |
| Connect to a file            | `db.source("name", FileSource(...))`                              |
| Write business logic         | `@db.product("name") async def fn(ctx): ...`                      |
| Handle source failures       | `try/except SourceUnavailableError` in product                    |
| Set freshness requirements   | `StalenessPolicy(max_age=..., on_source_error=...)`               |
| Accept webhooks from sources | `WebhookConfig(path=..., secret_env=...)`                         |
| Start everything             | `await db.start()`                                                |
| Check system health          | `db.fabric.status()` or `GET /fabric/_health`                     |
| Debug a pipeline             | `db.fabric.last_trace("product")` or `GET /fabric/_trace/product` |

### Frontend Developer

| Task                               | How                                                           |
| ---------------------------------- | ------------------------------------------------------------- |
| Get data                           | `GET /fabric/{product}`                                       |
| Get filtered/paginated data        | `GET /fabric/{product}?param=value&page=2`                    |
| Check data freshness               | Read `_fabric.freshness` from response                        |
| Show staleness indicator           | `if (response._fabric.freshness === "stale")`                 |
| Write data                         | `POST /fabric/{target}/write`                                 |
| Know what's refreshing after write | Read `_fabric.products_refreshing` from write response        |
| Generic data hook                  | `useFabricProduct("product_name", params)` — one hook for all |

### Operator

| Task                     | How                                                       |
| ------------------------ | --------------------------------------------------------- |
| Check overall health     | `GET /fabric/_health`                                     |
| Monitor source uptime    | `fabric_source_health` metric                             |
| Monitor data freshness   | `fabric_product_age_seconds` metric                       |
| Monitor cache efficiency | `fabric_cache_hit_total` / `fabric_cache_miss_total`      |
| Debug stale data         | `GET /fabric/_trace/{product}` — see last 5 pipeline runs |
| Alert on source failure  | Alert on `fabric_source_consecutive_failures > 3`         |
| Alert on stale product   | Alert on `fabric_product_age_seconds > max_age`           |
