# DataFlow Fabric — Architecture Plan (Final)

## One-Line Summary

DataFlow evolves from "zero-config database operations" to "zero-config data operations" — databases, APIs, files, cloud, anything — with pipeline-driven cache that eliminates TTL and ensures users never see stale data.

---

## Core Principle

**DataFlow IS the fabric.** No separate package. No extension. DataFlow's existing abstractions (BaseAdapter, Express API, cache invalidation) are already source-agnostic. The evolution adds non-database adapters, source registration, data products, and pipeline-driven caching.

100% backward compatible. All existing `@db.model` code works unchanged.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Frontend                                  │
│   GET /fabric/<product>  →  always cached                    │
│   POST /fabric/<product>/write  →  pass-through + refresh    │
│   Headers: X-Fabric-Freshness, X-Fabric-Source               │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                  Serving Layer (Nexus)                        │
│  Auto-generated REST endpoints per data product              │
│  Materialized: instant from cache                            │
│  Parameterized: cached per query combo                       │
│  Virtual: pass-through to source                             │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                  Cache Layer (DataFlow cache)                 │
│  Pipeline-driven: updated on source change, NOT on TTL       │
│  Atomic swap: cache updated only on pipeline success         │
│  Content hash: skip write if data unchanged                  │
│  Pre-warming: all products cached before first request       │
│  Staleness policy: per-product max_age + degradation mode    │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                  Pipeline Layer                               │
│  1. Cheap change detection per source type                   │
│     DB: MAX(updated_at) │ REST: ETag │ File: watch │ Cloud: metadata│
│  2. Fetch from source (only if changed)                      │
│  3. Transform hooks (optional, user-defined)                 │
│  4. Content hash vs cache (skip if identical)                │
│  5. Atomic swap to cache                                     │
│  Circuit breaker │ Backpressure │ Distributed lock            │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                  Source Layer                                  │
│  @db.model     → Database table (existing, unchanged)        │
│  @db.source()  → External source (REST, File, Cloud, Excel)  │
│                                                              │
│  Adapters:                                                   │
│  DatabaseAdapter (existing) │ RestAdapter │ FileAdapter       │
│  CloudAdapter │ ExcelAdapter │ StreamAdapter (Kafka/WS)       │
│                                                              │
│  Each source: state machine, health check, circuit breaker    │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Product Modes

| Mode              | Dataset Size     | Cache           | Query Support       | Use Case                      |
| ----------------- | ---------------- | --------------- | ------------------- | ----------------------------- |
| **Materialized**  | <10K records     | Full in cache   | FE gets all         | Dashboards, config, summaries |
| **Parameterized** | 10K-1M records   | Per-query-combo | Filters, pagination | User lists, search, reports   |
| **Virtual**       | >1M or real-time | Pass-through    | Full push-down      | Analytics, live metrics       |

---

## Target Audience

**Anyone pulling 2+ data sources.** This is not enterprise-only.

Every SME today runs 2+ systems:

- CRM (Salesforce, HubSpot)
- ERP (SAP, NetSuite)
- HRMS (BambooHR, Workday)
- Local files (Excel, CSV)
- Shared drives (Dropbox, SharePoint, Google Drive)
- Databases (PostgreSQL, MySQL, MongoDB)
- APIs (Stripe, SendGrid, custom)

The moment you pull from 2 sources, you have:

- Two different connection patterns
- Two different error handling strategies
- Two different caching approaches
- Two different data formats to normalize
- Frontend code coupling to both

DataFlow fabric eliminates all of this. Register sources, define products, start. Frontend reads from cache. Done.

---

## Developer Experience

```python
from dataflow import DataFlow
from dataflow.fabric import RestSource, FileSource, CloudSource, StalenessPolicy

db = DataFlow("postgresql://...")

# Existing: database models (unchanged)
@db.model
class User:
    id: str
    name: str
    email: str
    active: bool

# NEW: register external sources
db.source("crm", RestSource(
    url=os.environ["CRM_API_URL"],
    auth={"type": "bearer", "token_env": "CRM_TOKEN"},
    poll_interval=300,
))

db.source("hr_file", FileSource(
    path="/shared/hr/employees.xlsx",
    watch=True,
))

db.source("documents", CloudSource(
    bucket=os.environ["DOCS_BUCKET"],
    provider="s3",
))

# NEW: define data products
@db.product("dashboard", mode="materialized", staleness=StalenessPolicy(
    max_age=timedelta(hours=1),
    on_stale="serve_with_warning",
    on_source_error="keep_cache",
))
async def dashboard(ctx):
    users = await ctx.express.list("User", filter={"active": True})
    contacts = await ctx.source("crm").fetch("/contacts")
    hr = await ctx.source("hr_file").read()
    return {
        "employee_count": len(users),
        "crm_contacts": contacts,
        "hr_summary": hr,
    }

@db.product("users", mode="parameterized")
async def users(ctx, filter=None, page=1, limit=50):
    return await ctx.express.list("User", filter=filter, page=page, limit=limit)

# Start: pre-warms cache, starts source watchers
await db.start()

# Write through fabric (triggers product refresh)
await db.fabric.write("crm", "create", {"name": "New Contact", ...})
```

---

## Source Types

| Source                                          | Adapter                      | Change Detection             | Write Support  |
| ----------------------------------------------- | ---------------------------- | ---------------------------- | -------------- |
| PostgreSQL, MySQL, SQLite, MongoDB              | `DatabaseAdapter` (existing) | `MAX(updated_at)` poll       | Express API    |
| REST APIs (Salesforce, HubSpot, Stripe, custom) | `RestAdapter`                | ETag / Last-Modified headers | POST/PUT/PATCH |
| Local files (JSON, YAML, CSV)                   | `FileAdapter`                | watchdog file events         | File write     |
| Excel spreadsheets                              | `ExcelAdapter`               | watchdog + sheet hash        | Sheet write    |
| Cloud storage (S3, GCS, Azure Blob)             | `CloudAdapter`               | ListObjects metadata         | PutObject      |
| Shared drives (Dropbox, SharePoint, OneDrive)   | `CloudAdapter`               | API metadata polling         | Upload API     |
| Streaming (Kafka, WebSocket, SSE)               | `StreamAdapter`              | Continuous consumption       | Produce        |
| GraphQL APIs                                    | `RestAdapter` subclass       | Poll + response hash         | Mutations      |
| Email (IMAP, MS Graph)                          | `RestAdapter` subclass       | Poll + message count         | Send           |
| Chat (Slack, Teams, Discord)                    | `RestAdapter` + WebSocket    | WebSocket events             | Post message   |

---

## Package Structure

```
packages/kailash-dataflow/
├── src/dataflow/
│   ├── core/              # Existing — unchanged
│   ├── cache/             # Existing — publishes CacheProtocol
│   ├── adapters/          # Existing DB adapters + NEW source adapters
│   │   ├── base.py        # BaseAdapter (existing, unchanged)
│   │   ├── base_adapter.py
│   │   ├── postgresql.py  # Existing
│   │   ├── mysql.py       # Existing
│   │   ├── sqlite.py      # Existing
│   │   ├── mongodb.py     # Existing
│   │   ├── rest.py        # NEW — REST API adapter
│   │   ├── file.py        # NEW — File system adapter
│   │   ├── cloud.py       # NEW — S3/GCS/Azure adapter
│   │   ├── excel.py       # NEW — Excel/CSV adapter
│   │   └── stream.py      # NEW — Kafka/WebSocket adapter
│   ├── features/          # Existing — unchanged
│   └── fabric/            # NEW — fabric engine
│       ├── __init__.py
│       ├── engine.py      # FabricEngine orchestrator
│       ├── sources.py     # Source registration + management
│       ├── products.py    # @db.product decorator + registry
│       ├── pipeline.py    # Pipeline runner + change detection
│       ├── serving.py     # Nexus endpoint generation
│       ├── warming.py     # Pre-warming orchestrator
│       ├── staleness.py   # Staleness policy
│       ├── circuit.py     # Circuit breaker per source
│       ├── backpressure.py # Adaptive batch sizing
│       └── health.py      # Source health monitoring
├── pyproject.toml          # Optional extras for source deps
└── tests/fabric/           # Full test coverage
```

### Optional Extras

```toml
[project.optional-dependencies]
fabric = ["httpx>=0.27", "watchdog>=4.0"]
cloud = ["boto3>=1.35", "google-cloud-storage>=2.18"]
excel = ["openpyxl>=3.1"]
streaming = ["aiokafka>=0.11", "websockets>=13.0"]
fabric-all = ["kailash-dataflow[fabric,cloud,excel,streaming]"]
```

---

## Estimated Effort (Full Scope, No Phasing)

| Component                                          | Files   | LOC              | Tests LOC        |
| -------------------------------------------------- | ------- | ---------------- | ---------------- |
| Source adapters (REST, File, Cloud, Excel, Stream) | 5       | 2,000-3,000      | 1,500-2,000      |
| Fabric engine + orchestrator                       | 1       | 800-1,200        | 500-800          |
| Products (decorator, registry, modes)              | 1       | 500-700          | 400-600          |
| Pipeline (runner, change detection)                | 1       | 800-1,200        | 600-800          |
| Cache extensions (atomic swap, warming, staleness) | 3       | 800-1,200        | 500-700          |
| Serving (Nexus integration)                        | 1       | 400-600          | 300-400          |
| Circuit breaker + backpressure + health            | 3       | 600-900          | 400-600          |
| Write pass-through                                 | 1       | 300-500          | 200-300          |
| DataFlow core changes (source registration)        | 2       | 300-500          | 200-300          |
| **Total**                                          | **~18** | **~6,500-9,800** | **~4,600-6,500** |

**Autonomous execution**: 3-4 sessions for implementation + 1 session for red team validation.

---

## Key Design Constraints

1. **100% backward compatible** — all existing `@db.model` code works unchanged
2. **Secrets from `.env`** — all source credentials via `os.environ`, per env-models rule
3. **Cache updated on pipeline success only** — never partial, never failed data
4. **FE reads from cache only** — source fetches in background pipelines
5. **Products are async functions** — `async def` with `FabricContext`
6. **Cheap change detection first** — content hash is secondary, after cheap indicator
7. **Staleness policy per product** — configurable max_age, degradation behavior
8. **Multi-worker safe** — distributed lock for pipeline scheduling
