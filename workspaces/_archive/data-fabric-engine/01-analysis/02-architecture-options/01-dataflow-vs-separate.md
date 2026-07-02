# Architecture Decision: DataFlow Extension vs Separate Package

## The Question

Should the Data Fabric Engine be:

- **Option A**: An extension within `kailash-dataflow` (new module/feature set)
- **Option B**: A separate package `kailash-fabric` that wraps DataFlow + other engines
- **Option C**: A separate package that stands alone, reimplementing what it needs

## Analysis Criteria

| Criterion                | Weight | Description                                            |
| ------------------------ | ------ | ------------------------------------------------------ |
| **Conceptual fit**       | High   | Does the fabric concept belong in DataFlow's domain?   |
| **Dependency direction** | High   | Does fabric depend on DataFlow, or vice versa?         |
| **Scope creep risk**     | High   | Would adding fabric bloat DataFlow beyond its mission? |
| **Code reuse**           | Medium | How much existing DataFlow code does fabric use?       |
| **User mental model**    | Medium | Do users think of fabric as "database operations"?     |
| **Install footprint**    | Medium | Does bundling add unwanted dependencies?               |
| **Maintenance burden**   | Medium | Is it easier to maintain as one or two packages?       |

---

## Option A: Extend DataFlow

### What This Looks Like

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

# Existing DataFlow: database models
@db.model
class User:
    id: str
    name: str

# NEW: Fabric sources (non-database)
db.fabric.register_source("weather_api", RestSource(
    url="https://api.weather.com/v1/current",
    poll_interval=300,
    auth=BearerAuth(token=os.environ["WEATHER_API_KEY"]),
))

db.fabric.register_source("sales_excel", FileSource(
    path="/data/sales_q4.xlsx",
    watch=True,
))

# NEW: Fabric views (materialized from sources)
@db.fabric.view
class DashboardData:
    users: Query = Query("User", filter={"active": True})
    weather: Source = Source("weather_api")
    sales: Source = Source("sales_excel")

# Start fabric (pre-warms cache, starts source watchers)
await db.fabric.start()
```

### Assessment

| Criterion            | Score         | Reasoning                                                                                                                                            |
| -------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Conceptual fit       | **Poor**      | DataFlow is "zero-config database operations." Fabric is "unified data access across ALL sources." These are different domains                       |
| Dependency direction | **Wrong**     | Fabric depends on DataFlow (for DB sources), not the other way around. Putting fabric IN DataFlow creates a circular concept                         |
| Scope creep risk     | **High**      | DataFlow is already 250 files / 139K LOC. Adding source adapters, cache management, view materialization would add 50-100 files and blur its mission |
| Code reuse           | **Moderate**  | Fabric would reuse DataFlow's caching (memory/Redis), model system, and database adapters                                                            |
| User mental model    | **Confusing** | Users `pip install kailash-dataflow` to manage databases. Getting REST API adapters, Excel parsers, and file watchers is unexpected                  |
| Install footprint    | **Bad**       | Excel parsing (openpyxl), S3 (boto3), cloud storage dependencies would bloat DataFlow                                                                |
| Maintenance burden   | **Higher**    | Database adapter bugs and fabric source adapter bugs in the same package create noisy issue trackers                                                 |

### Verdict: **Not recommended**

DataFlow has a clear, focused mission: zero-config database operations. Fabric is fundamentally different — it unifies ALL data sources, not just databases. Putting fabric inside DataFlow would dilute DataFlow's identity and add unwanted dependencies.

---

## Option B: Separate Package Wrapping DataFlow (RECOMMENDED)

### What This Looks Like

```python
from kailash_fabric import Fabric, RestSource, FileSource, DbSource

fabric = Fabric()

# Register heterogeneous sources
fabric.source("users_db", DbSource("postgresql://...", model="User"))
fabric.source("weather", RestSource(
    url="https://api.weather.com/v1/current",
    poll_interval=300,
))
fabric.source("sales", FileSource("/data/sales_q4.xlsx", watch=True))

# Define data products (materialized views)
@fabric.product("dashboard")
async def dashboard_data(sources):
    users = await sources.users_db.list(filter={"active": True})
    weather = await sources.weather.fetch()
    sales = await sources.sales.read()
    return {"users": users, "weather": weather, "sales": sales}

# Start: pre-warms cache, starts watchers/pollers
await fabric.start()

# Serve: auto-generates endpoints for data products
# GET /fabric/dashboard → returns cached dashboard_data
# Integrates with Nexus for multi-channel exposure
```

### Assessment

| Criterion            | Score           | Reasoning                                                                                |
| -------------------- | --------------- | ---------------------------------------------------------------------------------------- |
| Conceptual fit       | **Excellent**   | Fabric is a new concept — a new package is the right home                                |
| Dependency direction | **Correct**     | `kailash-fabric` depends on `kailash-dataflow` for DB sources. Clean, one-way dependency |
| Scope creep risk     | **None**        | DataFlow stays focused. Fabric has its own scope                                         |
| Code reuse           | **High**        | Fabric imports DataFlow for DB operations, Nexus for endpoint serving                    |
| User mental model    | **Clear**       | `pip install kailash-fabric` = data fabric. Users opt in when they need it               |
| Install footprint    | **Right**       | Source-specific deps are optional extras: `kailash-fabric[s3]`, `kailash-fabric[excel]`  |
| Maintenance burden   | **Appropriate** | Separate issue tracking, separate release cadence                                        |

### Dependency Graph

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ kailash-fabric│────→│kailash-dataflow│────→│   kailash     │
│               │     │               │     │  (core SDK)   │
│  Sources      │     │  Models       │     │  Workflow     │
│  Views        │     │  Express API  │     │  Runtime      │
│  Cache        │     │  Caching      │     │  Nodes        │
│  Endpoints    │     │  Adapters     │     │               │
└───────┬───────┘     └───────────────┘     └───────────────┘
        │
        ├────→ kailash-nexus (for endpoint serving)
        │
        └────→ Optional: boto3, openpyxl, httpx, etc.
```

### Verdict: **Recommended**

This is the clean architectural choice. Fabric is a higher-level abstraction that composes DataFlow (for DB), Nexus (for serving), and custom source adapters into a unified data access layer.

---

## Option C: Standalone Package (reimplements)

### Assessment

Would reimplement caching, database access, and endpoint serving that already exist in DataFlow and Nexus. Violates the Kailash framework-first directive. **Not recommended.**

---

## Recommendation: Option B — `kailash-fabric` as Separate Package

### Package Design

```
kailash-fabric/
├── src/fabric/
│   ├── engine.py           # FabricEngine — main orchestrator
│   ├── sources/            # Source adapters
│   │   ├── base.py         # BaseSource protocol
│   │   ├── db.py           # DataFlow-backed database source
│   │   ├── rest.py         # REST API source (poll/webhook)
│   │   ├── file.py         # File system source (watch/poll)
│   │   ├── excel.py        # Excel/CSV source
│   │   ├── cloud.py        # S3/GCS/Azure Blob source
│   │   └── stream.py       # WebSocket/SSE/Kafka source
│   ├── products/           # Data product definitions
│   │   ├── base.py         # BaseProduct protocol
│   │   ├── view.py         # Materialized view product
│   │   └── composite.py    # Multi-source composite product
│   ├── cache/              # Cache management
│   │   ├── manager.py      # Cache manager (wraps DataFlow cache)
│   │   ├── warming.py      # Pre-warming logic
│   │   └── invalidation.py # Event-driven invalidation
│   ├── pipeline/           # Data pipeline
│   │   ├── runner.py       # Async pipeline runner
│   │   ├── backpressure.py # Backpressure controller
│   │   └── circuit.py      # Circuit breaker
│   ├── serving/            # Endpoint generation
│   │   ├── endpoints.py    # Auto-generated REST endpoints
│   │   └── nexus.py        # Nexus integration
│   └── observability/      # Metrics, health, lineage
│       ├── metrics.py      # Source/cache/pipeline metrics
│       └── health.py       # Source health checking
├── pyproject.toml
└── tests/
```

### Install Options

```bash
pip install kailash-fabric                    # Core + DB + file sources
pip install kailash-fabric[cloud]             # + S3, GCS, Azure Blob
pip install kailash-fabric[excel]             # + Excel/CSV parsing
pip install kailash-fabric[streaming]         # + Kafka, WebSocket, SSE
pip install kailash-fabric[all]               # Everything
```

### Integration with Existing Kailash Packages

| Package              | Role in Fabric                                    |
| -------------------- | ------------------------------------------------- |
| `kailash` (Core SDK) | Workflow runtime for complex pipelines            |
| `kailash-dataflow`   | Database source adapter, caching infrastructure   |
| `kailash-nexus`      | Multi-channel endpoint serving (REST + CLI + MCP) |
| `kailash-kaizen`     | Optional: AI-powered data enrichment agents       |
| `kailash-pact`       | Optional: governance envelopes for data access    |
