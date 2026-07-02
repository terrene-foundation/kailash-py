# Fabric on DataFlow Layers — The Precise Mapping

## DataFlow's Existing Layer Stack

```
Layer 9: Gateway          DataFlowGateway — multi-channel (API/CLI/MCP) via Nexus
Layer 8: Engine Wrapper   DataFlowEngine — builder pattern, validation, classification
Layer 7: Express API      DataFlowExpress — direct node invocation, 23x faster CRUD
Layer 6: Core Engine      DataFlow class — @db.model decorator, orchestrates everything
Layer 5: Node Generation  NodeGenerator — creates UserCreateNode, UserReadNode, etc. from models
Layer 4: Connection Mgmt  ConnectionManager + SchemaCache — pool lifecycle, schema metadata
Layer 3: Configuration    DataFlowConfig + DatabaseConfig — pool sizing, env detection
Layer 2: DB Adapters      PostgreSQLAdapter, MySQLAdapter, SQLiteAdapter, MongoDBAdapter
Layer 1: Base Adapter     BaseAdapter → DatabaseAdapter (abstract contracts)
Layer 0: Raw Drivers      asyncpg, aiosqlite, aiomysql, pymongo
```

Each layer calls only the layer below it. Developer touches Layer 6-9.

---

## Where Fabric Concepts Land — Layer by Layer

### Layer 1: BaseAdapter — EXTEND with BaseSourceAdapter

**Today**: `BaseAdapter` → `DatabaseAdapter` → concrete DB adapters.

**With fabric**: `BaseAdapter` → `BaseSourceAdapter` → concrete source adapters.

```
BaseAdapter (existing, unchanged)
├── DatabaseAdapter (existing, unchanged)
│   ├── PostgreSQLAdapter
│   ├── MySQLAdapter
│   ├── SQLiteAdapter
│   └── MongoDBAdapter
│
└── BaseSourceAdapter (NEW — parallel to DatabaseAdapter)
    ├── RestSourceAdapter      — HTTP APIs (Salesforce, Stripe, HubSpot)
    ├── FileSourceAdapter      — local files (JSON, YAML, CSV, Excel)
    ├── CloudSourceAdapter     — S3, GCS, Azure Blob, SharePoint
    ├── DatabaseSourceAdapter  — external/read-only databases
    └── StreamSourceAdapter    — Kafka, WebSocket, SSE
```

**What BaseSourceAdapter adds over BaseAdapter**:

| Method                   | BaseAdapter has it? | BaseSourceAdapter adds? | Purpose                                   |
| ------------------------ | ------------------- | ----------------------- | ----------------------------------------- |
| `connect()`              | YES                 | inherited               | Establish connection                      |
| `disconnect()`           | YES                 | inherited               | Close connection                          |
| `health_check()`         | YES                 | inherited               | Check if source is alive                  |
| `supports_feature()`     | YES                 | inherited               | Feature detection                         |
| `detect_change()`        | NO                  | **YES**                 | Cheap change detection (ETag, mtime, MAX) |
| `fetch(path, params)`    | NO                  | **YES**                 | Get data from source                      |
| `fetch_all(path)`        | NO                  | **YES**                 | Auto-paginate all pages                   |
| `fetch_pages(path)`      | NO                  | **YES**                 | Stream pages (async iterator)             |
| `write(path, data)`      | NO                  | **YES**                 | Write data to source                      |
| `last_successful_data()` | NO                  | **YES**                 | Graceful degradation on failure           |

**Key**: `DatabaseAdapter` has `execute_query()` and `get_table_schema()`. `BaseSourceAdapter` has `detect_change()` and `fetch()`. They are parallel specializations of `BaseAdapter`, not competing — database models use `DatabaseAdapter`, external sources use `BaseSourceAdapter`.

---

### Layer 2: Concrete Adapters — ADD 5 new adapters

Each new adapter implements `BaseSourceAdapter`:

**RestSourceAdapter**:

- `connect()` → create `httpx.AsyncClient` with auth, base URL, timeouts
- `detect_change()` → `HEAD` or conditional `GET` with `If-None-Match` → 304 = no change
- `fetch(path)` → `GET {base_url}/{path}` → parse JSON response
- `fetch_all(path)` → auto-paginate (follow `next` links, increment offset, etc.)
- `write(path, data)` → `POST {base_url}/{path}` with JSON body
- Handles: Bearer, API key, OAuth2, Basic auth via typed auth objects
- Has: circuit breaker (configurable threshold), retry with backoff

**FileSourceAdapter**:

- `connect()` → verify path exists, start watchdog observer (daemon thread)
- `detect_change()` → `os.stat(path).st_mtime` comparison (sub-ms)
- `fetch()` → read file, parse based on extension (.json, .yaml, .csv, .xlsx)
- `write(path, data)` → write file
- Watchdog callback bridges to async via `asyncio.run_coroutine_threadsafe()`

**CloudSourceAdapter**:

- `connect()` → create cloud client (boto3 for S3, gcs client for GCS)
- `detect_change()` → `ListObjectsV2` metadata (LastModified, ETag) comparison
- `fetch(path)` → `GetObject` → parse content
- `write(path, data)` → `PutObject`

**DatabaseSourceAdapter** (for external/read-only DBs):

- `connect()` → create connection pool via existing `DatabaseAdapter`
- `detect_change()` → `SELECT MAX(updated_at) FROM table` or change counter
- `fetch(path)` → `SELECT * FROM {path}` (path = table name)
- No `write()` if `read_only=True`
- Reuses existing DataFlow adapter infrastructure — NOT a reimplementation

**StreamSourceAdapter**:

- `connect()` → create Kafka consumer / WebSocket connection
- `detect_change()` → always True (stream is continuous)
- `fetch()` → consume messages from topic/stream
- `write()` → produce messages to topic

---

### Layer 3: Configuration — ADD source configs alongside database config

**Today**: `DataFlowConfig` has `DatabaseConfig`.

**With fabric**: `DataFlowConfig` gains source configurations.

```python
# Source config objects (new, parallel to DatabaseConfig)
class RestSourceConfig(BaseSourceConfig):
    url: str
    auth: AuthConfig              # BearerAuth | ApiKeyAuth | OAuth2Auth | BasicAuth
    poll_interval: int = 300      # seconds between change detection checks
    endpoints: Dict[str, str]     # named paths: {"contacts": "/v1/contacts"}
    webhook: Optional[WebhookConfig]
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    timeout: float = 10.0

class FileSourceConfig(BaseSourceConfig):
    path: str
    watch: bool = True            # use watchdog for instant change detection
    parser: str = "auto"          # auto-detect from extension, or "json"/"yaml"/"csv"/"excel"

class CloudSourceConfig(BaseSourceConfig):
    bucket: str
    provider: str                 # "s3" | "gcs" | "azure" | "sharepoint"
    prefix: str = ""
    poll_interval: int = 600

class DatabaseSourceConfig(BaseSourceConfig):
    url: str                      # connection string
    tables: List[str] = []        # optional table whitelist
    read_only: bool = True        # default: read-only (no migrations, no writes)
    poll_interval: int = 60

class StreamSourceConfig(BaseSourceConfig):
    broker: str
    topic: str
    group_id: str
```

These configs validate eagerly at `db.source()` time — env vars, URL format, required fields.

---

### Layer 5: Node Generation — NO CHANGE (fabric does NOT use nodes)

Products are NOT nodes. This is a critical distinction.

**Nodes** are Kailash SDK primitives — they have typed parameters, execute a single operation, and connect in workflows. DataFlow generates them from `@db.model` for CRUD operations.

**Products** are fabric-level compositions — they are async functions that call multiple sources and return a combined result. They do not register in `NodeRegistry`, do not have `NodeParameter` definitions, and do not participate in `WorkflowBuilder` graphs.

```
@db.model → generates UserCreateNode, UserReadNode, etc. (Layer 5 nodes)
@db.product → registers a product function in _products registry (NOT a node)
```

**Why products are not nodes**: A node is a single-operation unit. A product calls multiple sources, transforms data, handles errors, and composes results. Making it a node would force it into node constraints (single input/output, typed parameters) that don't fit.

**Where products live**: In a new registry (`self._products`) at Layer 6, parallel to `self._models`.

---

### Layer 6: Core Engine — ADD source/product registries and start/stop lifecycle

**Today**, `DataFlow.__init__` creates:

```python
self._models: Dict[str, Dict]         # populated by @db.model
self._registered_models: Dict[str, Type]
self._model_fields: Dict[str, Dict]
self._nodes: Dict[str, str]           # populated by NodeGenerator
```

**With fabric**, `DataFlow.__init__` also creates:

```python
self._sources: Dict[str, SourceRegistration] = {}    # populated by db.source()
self._products: Dict[str, ProductRegistration] = {}  # populated by @db.product()
self._fabric: Optional[FabricRuntime] = None         # created by db.start()
```

**Today**, `DataFlow` has these lifecycle methods:

```python
db = DataFlow(url)          # sync: parse URL, create adapter, set up config
@db.model                   # sync: register model, generate nodes
await db.initialize()       # async: connect to DB, run migrations, warm schema
```

**With fabric**, `DataFlow` gains:

```python
db.source(name, config)     # sync: register source, validate config
@db.product(name, ...)      # sync: register product, validate depends_on
await db.start(...)         # async: initialize() + connect sources + start fabric runtime
await db.stop()             # async: drain pipelines + release locks + disconnect sources
```

**`db.start()` supersedes `db.initialize()`**: It calls `initialize()` first (for database setup), then adds fabric lifecycle on top. If you never call `db.source()` or `@db.product()`, `db.start()` effectively just calls `initialize()` — backward compatible.

**The relationship between registries**:

```
db.source("crm", RestSource(...))
  → self._sources["crm"] = SourceRegistration(config=RestSource(...), adapter=None, state="registered")

@db.model class User: ...
  → self._models["User"] = {class: User, fields: {...}, ...}
  → self._nodes["UserCreateNode"] = generated node

@db.product("dashboard", depends_on=["User", "crm"])
  → self._products["dashboard"] = ProductRegistration(fn=dashboard, depends_on=["User", "crm"])
  → Validates: "User" is in self._models, "crm" is in self._sources
```

---

### Layer 7: Express API — UNCHANGED (fabric uses it, doesn't modify it)

Express API stays database-only. Inside product functions, `ctx.express` IS `db.express` — the same object.

```python
@db.product("dashboard", depends_on=["User", "crm"])
async def dashboard(ctx):
    # ctx.express IS db.express — calls Layer 7 directly
    users = await ctx.express.list("User", filter={"active": True})

    # ctx.source("crm") returns a SourceHandle wrapping the RestSourceAdapter at Layer 2
    contacts = await ctx.source("crm").fetch("contacts")

    return {"users": users, "contacts": contacts}
```

**Where each call goes**:

- `ctx.express.list("User")` → Layer 7 (Express) → Layer 5 (UserListNode) → Layer 2 (PostgreSQLAdapter) → Layer 0 (asyncpg)
- `ctx.source("crm").fetch("contacts")` → Layer 2 (RestSourceAdapter) → httpx → CRM API

Express handles databases. SourceHandle handles everything else. Both are available in the product function via `ctx`.

---

### Layer 8: DataFlowEngine — UNCHANGED (optional, works with fabric)

The builder pattern gains `.source()` and `.fabric()` methods, but the engine wrapper itself is unchanged:

```python
engine = await DataFlowEngine.builder("postgresql://...")
    .source("crm", RestSource(...))   # NEW — registers source
    .fabric(host="0.0.0.0", port=8000)  # NEW — configures fabric runtime
    .validate_on_write(True)           # existing
    .build()                           # existing — now also starts fabric if configured
```

---

### Layer 9: Gateway — REPLACED by fabric serving for product endpoints

**Today**: `DataFlowGateway` creates Nexus endpoints for workflow-based bulk operations.

**With fabric**: Fabric serving layer creates Nexus endpoints for products. They serve the same purpose (expose DataFlow via HTTP) but with different abstractions:

```
Gateway endpoints (existing, still available):
  POST /dataflow/User/bulk_create   → BulkCreateNode workflow
  GET  /dataflow/health             → HealthMonitor

Fabric endpoints (new, auto-generated):
  GET  /fabric/dashboard            → cached product data (headers: X-Fabric-Freshness)
  GET  /fabric/users?page=2         → parameterized product
  POST /fabric/User/write           → write pass-through + product refresh
  GET  /fabric/_health              → source + product + cache health
  GET  /fabric/_trace/dashboard     → pipeline execution traces
  GET  /fabric/_events              → SSE stream for real-time updates
  GET  /fabric/_batch?products=a,b  → batch product read (single Redis MGET)
```

Gateway and fabric endpoints can coexist on the same Nexus instance.

---

### Layer 10 (NEW): FabricRuntime — the background system

This is the only genuinely new layer. It sits on top of everything else and runs after `db.start()`.

```
Layer 10: FabricRuntime (NEW)
  ├── LeaderElector        — Redis SETNX / PG advisory lock, 10s heartbeat
  ├── SourceManager        — manages BaseSourceAdapter instances (Layer 2)
  ├── ChangeDetector       — poll loops calling adapter.detect_change() (Layer 2)
  ├── WebhookReceiver      — HTTP endpoints for push-based sources
  ├── PipelineExecutor     — runs product functions, writes to cache
  │   ├── Uses: ctx.express (Layer 7) for database access
  │   ├── Uses: SourceHandle → BaseSourceAdapter (Layer 2) for source access
  │   └── Uses: Redis Lua script for atomic cache write
  ├── CacheManager         — product-level cache using DataFlow's cache backend
  ├── Scheduler            — cron-based product refresh
  ├── SSEBroadcaster       — Server-Sent Events to connected FE clients
  └── HealthReporter       — extends DataFlow HealthMonitor (Layer 8)
```

**What FabricRuntime depends on (downward only)**:

- Layer 7 (Express) — product functions call `ctx.express.*`
- Layer 6 (DataFlow) — source/product registries, event bus for write notifications
- Layer 2 (Adapters) — source adapters for `detect_change()` and `fetch()`
- Layer 3 (Config) — source configs, circuit breaker configs
- DataFlow cache subsystem — `InMemoryCache` or `RedisCacheManager`

---

## The Complete Stack After Fabric

```
Layer 10: FabricRuntime     Background tasks: poll, watch, pipeline, schedule, SSE, health
Layer  9: Gateway           Multi-channel Nexus (existing) + fabric auto-generated endpoints
Layer  8: DataFlowEngine    Builder + validation + classification (existing, unchanged)
Layer  7: Express API       Direct CRUD, 23x faster (existing, unchanged)
Layer  6: DataFlow Core     @db.model + db.source() + @db.product() + db.start()
Layer  5: Node Generation   UserCreateNode, etc. (existing, unchanged — products are NOT nodes)
Layer  4: Connection Mgmt   Pool lifecycle + schema cache (existing, unchanged)
Layer  3: Configuration     DatabaseConfig + source configs (RestSourceConfig, etc.)
Layer  2: Adapters          DatabaseAdapter (existing) + BaseSourceAdapter (new, parallel)
Layer  1: Base Adapter      BaseAdapter (existing, unchanged — both hierarchies inherit from it)
Layer  0: Raw Drivers       asyncpg, aiosqlite + httpx, watchdog, boto3 (new driver deps)
```

---

## How a Piece of Data Actually Flows

### Database data (unchanged from today):

```
@db.model class User → NodeGenerator → UserListNode
                                          ↓
await db.express.list("User")  →  UserListNode.execute()
                                          ↓
                                  PostgreSQLAdapter.execute_query()
                                          ↓
                                  asyncpg → PostgreSQL → rows
                                          ↓
                                  Express cache (optional) → developer
```

### External source data (new):

```
db.source("crm", RestSource(...))  →  SourceRegistration stored

await db.start()  →  RestSourceAdapter.connect()  →  httpx client created
                  →  Poll loop started (Layer 10)
                  →  Pre-warm: product function runs → fetch → cache

Change detected by poll loop:
  RestSourceAdapter.detect_change()  →  HEAD request → 304 or 200?
  If 200 (changed):
    PipelineExecutor.enqueue("dashboard")  →  debounce  →  execute
      → product function runs:
          ctx.express.list("User")          → Layer 7 → Layer 2 → asyncpg
          ctx.source("crm").fetch("deals")  → Layer 2 → httpx → CRM API
          return combined result
      → content hash compare → Lua atomic write to Redis
      → SSE broadcast: "product_updated: dashboard"

FE request:
  GET /fabric/dashboard
    → Redis GET fabric:data:dashboard → msgpack deserialize → JSON response
    → Headers: X-Fabric-Freshness: fresh, X-Fabric-Age: 42
    → Duration: <5ms (cache read, no computation)
```

### Write through fabric (new):

```
POST /fabric/User/write  {operation: "create", data: {name: "Alice"}}
    → db.express.create("User", data)           (Layer 7)
    → UserCreateNode.execute()                   (Layer 5)
    → PostgreSQLAdapter.execute_query(INSERT)     (Layer 2)
    → asyncpg → PostgreSQL                        (Layer 0)
    → DataFlowEventMixin emits "model.created"    (Layer 6)
    → FabricRuntime._on_model_write()             (Layer 10)
    → PipelineExecutor.enqueue("dashboard")       (Layer 10 — debounced)
    → product function re-runs → cache updated
    → Response: {result: {id: "u1", name: "Alice"}, headers: X-Fabric-Products-Refreshing: dashboard}
```

---

## Summary: What Each Layer Gains

| Layer | Today                          | With Fabric                                                                                     | What Changed                                    |
| ----- | ------------------------------ | ----------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| 0     | asyncpg, aiosqlite             | + httpx, watchdog, boto3, msgpack                                                               | New driver dependencies                         |
| 1     | BaseAdapter                    | Unchanged                                                                                       | Nothing                                         |
| 2     | DatabaseAdapter hierarchy      | + BaseSourceAdapter hierarchy                                                                   | Parallel adapter tree                           |
| 3     | DatabaseConfig                 | + source configs (RestSourceConfig, etc.)                                                       | New config types                                |
| 4     | ConnectionManager, SchemaCache | Unchanged                                                                                       | Nothing                                         |
| 5     | NodeGenerator                  | Unchanged                                                                                       | Nothing (products are NOT nodes)                |
| 6     | DataFlow class                 | + `_sources`, `_products`, `_fabric` registries; + `source()`, `product()`, `start()`, `stop()` | New registries and lifecycle methods            |
| 7     | DataFlowExpress                | Unchanged                                                                                       | Nothing (products USE express, don't change it) |
| 8     | DataFlowEngine                 | + `.source()`, `.fabric()` builder methods                                                      | Additive only                                   |
| 9     | DataFlowGateway                | + fabric auto-generated endpoints (coexist)                                                     | Additive only                                   |
| 10    | (new)                          | FabricRuntime                                                                                   | The background system                           |
