# Developer Journey: DataFlow Fabric

## Flow 1: New Project With Multiple Sources

```
Developer has: PostgreSQL database + Salesforce CRM + shared Excel file
Developer wants: Dashboard showing combined data, instant FE load

Step 1: pip install kailash-dataflow[fabric]
Step 2: db = DataFlow("postgresql://...")
Step 3: @db.model for database tables
Step 4: db.source("crm", RestSource(...))
Step 5: db.source("hr", FileSource(...))
Step 6: @db.product("dashboard") → compose data
Step 7: await db.start() → pre-warm + watch
Step 8: FE calls GET /fabric/dashboard → instant

Time: minutes, not days
LOC: ~50 lines total (models + sources + products)
```

## Flow 2: Adding a New Source to Existing Project

```
Developer has: Working project with 3 sources
Developer needs: Add Stripe billing data to dashboard

Step 1: db.source("billing", RestSource(url=os.environ["STRIPE_API_URL"], ...))
Step 2: Update @db.product("dashboard") to include billing data
Step 3: Restart → fabric pre-warms the new source
Step 4: FE unchanged — same endpoint, now includes billing data

Time: 5 minutes
LOC: +10 lines (source registration + product update)
FE changes: zero
```

## Flow 3: Existing DataFlow Project Adopts Fabric

```
Developer has: DataFlow project with @db.model + Express API + manual Nexus handlers
Developer wants: Add external sources without rewriting everything

Step 1: pip install kailash-dataflow[fabric]  (adds fabric deps)
Step 2: Keep ALL existing @db.model code unchanged
Step 3: Keep ALL existing Express API code unchanged
Step 4: Add db.source() for external sources
Step 5: Add @db.product() for combined data views
Step 6: Add await db.start() to app startup
Step 7: Gradually migrate Nexus handlers to products

Existing code breaks: NOTHING
Migration: incremental, product by product
```

## Flow 4: FE Developer Consuming Fabric

```
FE developer has: React app with TanStack Query
FE developer needs: Data from multiple backend sources

Before:
  - useUsers() → GET /api/users         → custom hook, custom handler
  - useCRM() → GET /api/crm/contacts    → custom hook, custom handler
  - useHR() → GET /api/hr/employees     → custom hook, custom handler
  - useDashboard() → GET /api/dashboard  → custom hook, manual composition
  Total: 4 hooks, 4 handlers, 4 error paths, 4 cache strategies

After:
  - useDashboard() → GET /fabric/dashboard  → one hook, auto-generated
  - useUsers() → GET /fabric/users?page=1   → one hook, auto-generated
  Total: 2 hooks, 0 custom handlers, unified error handling, pipeline-driven cache

FE staleTime: Infinity (or 60s safety net)
FE never manages cache invalidation
FE never sees loading spinners for warm products
```

## Flow 5: Source Goes Down

```
Scenario: CRM API returns 500 errors

Pipeline detects: CRM source unhealthy
Circuit breaker: Opens after 3 failures
Cache: Keeps serving last successful data
Response header: X-Fabric-Freshness: 2026-04-02T13:00:00Z (1 hour ago)
Staleness policy: on_source_error="keep_cache"
FE: Shows data with optional "last updated 1 hour ago" indicator

When CRM recovers:
Circuit breaker: Closes after successful probe
Pipeline: Fetches fresh data
Cache: Atomic swap to fresh data
FE: Next request gets fresh data, no action needed
```

## Flow 6: Write Through Fabric

```
FE: POST /fabric/users/write { "name": "Bob", "email": "bob@co.com" }

Fabric:
  1. Routes write to "User" model via Express API
  2. Express creates record in PostgreSQL
  3. Fabric identifies products depending on User: ["dashboard", "users"]
  4. Triggers pipeline refresh for both products
  5. Cache updated atomically with new data
  6. Returns write result to FE

FE:
  - Receives write confirmation
  - Next GET /fabric/dashboard includes the new user
  - No manual cache invalidation needed
```
