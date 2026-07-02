# DataFlow Fabric API Specification (DX Red Team Resolved)

## Resolved Decisions

| #   | Gap                                            | Resolution                                                                                                     |
| --- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1   | `@db.model` vs `db.source()` for read-only DBs | Add `DatabaseSource` — `db.source("reporting", DatabaseSource("postgresql://readonly/..."))`                   |
| 2   | `ctx` (FabricContext) undefined                | Fully specified below                                                                                          |
| 3   | `db.start()` failure modes                     | Fail-fast by default, configurable `fail_fast=False` for skip-and-warn                                         |
| 4   | Testing story absent                           | `FabricContext.for_testing()` + `MockSource` adapter                                                           |
| 5   | Express API for sources: contradicted          | **Express is database-only.** Sources accessed via `ctx.source()`. No ambiguity.                               |
| 6   | Nexus integration mechanism                    | Fabric creates a `Nexus` handler set. Developer either passes existing Nexus or fabric creates one internally  |
| 7   | Dependency tracking                            | **Static declaration** via `depends_on=` parameter. Runtime verification warns on undeclared access            |
| 8   | Auth config: dicts vs typed objects            | **Typed objects only.** `BearerAuth(...)`, `ApiKeyAuth(...)`, `OAuth2Auth(...)`                                |
| 9   | Error surface timing                           | Env vars validated at `db.source()`. Connectivity validated at `db.start()`. Format errors at pipeline runtime |
| 10  | Hot reload                                     | `db.stop()` + `db.start()` for clean restart. `dev_mode=True` skips pre-warming                                |

---

## The Three New Concepts (Definitive)

### Concept 1: `db.source()` — Register an external data source

```python
db.source(name: str, config: BaseSourceConfig) -> None
```

Called after `DataFlow()` initialization. Registers a named source.
Validates immediately: checks env vars exist, validates URL format.
Does NOT connect — connection happens at `db.start()`.

**Source types:**

```python
from dataflow.fabric import (
    RestSource,       # REST/GraphQL APIs
    FileSource,       # Local files (JSON, YAML, CSV, Excel)
    CloudSource,      # S3, GCS, Azure Blob, Dropbox, SharePoint
    DatabaseSource,   # External/read-only databases
    StreamSource,     # Kafka, WebSocket, SSE
)

from dataflow.fabric.auth import (
    BearerAuth,       # Authorization: Bearer <token>
    ApiKeyAuth,       # X-Api-Key header or query param
    OAuth2Auth,       # OAuth2 client credentials flow
    BasicAuth,        # Username/password
)
```

**Examples:**

```python
# REST API
db.source("crm", RestSource(
    url=os.environ["CRM_API_URL"],
    auth=BearerAuth(token_env="CRM_TOKEN"),
    poll_interval=300,
    endpoints={
        "contacts": "/v1/contacts",
        "deals": "/v1/deals",
    },
))

# Local file (watched for changes)
db.source("config", FileSource(
    path="./config/settings.yaml",
    watch=True,
))

# Excel spreadsheet
db.source("hr", FileSource(
    path="/shared/hr/employees.xlsx",
    watch=True,
    parser="excel",  # auto-detected from extension, but explicit is fine
))

# Cloud storage
db.source("documents", CloudSource(
    bucket=os.environ["DOCS_BUCKET"],
    provider="s3",   # or "gcs", "azure", "dropbox", "sharepoint"
    prefix="reports/",
))

# External database (read-only, no @db.model, no migrations)
db.source("reporting", DatabaseSource(
    url=os.environ["REPORTING_DB_URL"],
    tables=["sales", "inventory", "returns"],  # optional: specify which tables
    read_only=True,
))

# Kafka stream
db.source("events", StreamSource(
    broker=os.environ["KAFKA_BROKER"],
    topic="user-events",
    group_id="fabric-consumer",
))
```

**Validation at `db.source()` time:**

- Env var references checked immediately → `EnvironmentError` if missing
- URL format validated → `ValueError` if malformed
- Required fields checked → `TypeError` if missing
- Source name uniqueness checked → `ValueError` if duplicate

**Does NOT:**

- Connect to the source
- Fetch any data
- Start any watchers

### Concept 2: `@db.product()` — Define a data product

```python
@db.product(
    name: str,
    mode: Literal["materialized", "parameterized", "virtual"] = "materialized",
    depends_on: list[str] = [],        # REQUIRED for materialized/parameterized
    staleness: StalenessPolicy = StalenessPolicy(),
)
```

**`depends_on` is required** (static declaration). Lists model names and source names this product reads from. Fabric uses this to know which products to refresh when a source changes.

```python
@db.product("dashboard",
    mode="materialized",
    depends_on=["User", "Order", "crm"],     # ← explicit
    staleness=StalenessPolicy(
        max_age=timedelta(hours=1),
        on_stale="serve_with_warning",
        on_source_error="keep_cache",
    ),
)
async def dashboard(ctx: FabricContext) -> dict:
    users = await ctx.express.list("User", filter={"active": True})
    orders = await ctx.express.list("Order", filter={"status": "pending"})
    contacts = await ctx.source("crm").fetch("contacts")
    return {
        "active_users": len(users),
        "pending_orders": len(orders),
        "crm_contacts": len(contacts),
    }
```

**Runtime verification**: If the product function accesses a source NOT in `depends_on`, fabric logs a warning: `"Product 'dashboard' accessed source 'hr' not declared in depends_on. Add 'hr' to depends_on to enable automatic refresh."`

**Parameterized products** — parameters come from query string:

```python
@db.product("users",
    mode="parameterized",
    depends_on=["User"],
)
async def users(ctx: FabricContext, filter: dict = None, page: int = 1, limit: int = 50) -> dict:
    offset = (page - 1) * limit
    users = await ctx.express.list("User", filter=filter, limit=limit, offset=offset)
    count = await ctx.express.count("User", filter=filter)
    return {"data": users, "total": count, "page": page, "limit": limit}
```

Served as: `GET /fabric/users?filter={"active":true}&page=2&limit=20`
Cache key: `fabric:users:filter={"active":true}:page=2:limit=20`

**Virtual products** — no cache, pass-through:

```python
@db.product("live_docs",
    mode="virtual",
    depends_on=["documents"],
)
async def live_docs(ctx: FabricContext, prefix: str = "") -> list:
    return await ctx.source("documents").list(prefix=prefix)
```

### Concept 3: `await db.start()` — Start the fabric

```python
await db.start(
    fail_fast: bool = True,        # Raise on any source health check failure
    dev_mode: bool = False,        # Skip pre-warming for fast restart
    nexus: Optional[Nexus] = None, # Attach to existing Nexus, or create internal
)
```

**What happens, in order:**

```
1. Connect to all registered sources (parallel)
   → Success: source state → "active"
   → Failure + fail_fast=True: raise FabricStartupError(source_name, error)
   → Failure + fail_fast=False: source state → "error", log warning, continue

2. Health check each active source
   → REST: HEAD request to base URL
   → File: check path exists and is readable
   → Cloud: list bucket (1 item)
   → Database: SELECT 1

3. Pre-warm all materialized products (unless dev_mode=True)
   → Execute each product function
   → Write result to cache
   → Track dependency graph for runtime verification
   → Stagger: max 3 concurrent product warmings
   → Failure: log error, mark product as "cold" (first access blocks)

4. Start change detection for each active source
   → REST: start poll timer (poll_interval)
   → File: start watchdog observer
   → Cloud: start metadata poll timer
   → Database: start MAX(updated_at) poll timer
   → Stream: start consumer

5. Register fabric endpoints
   → If nexus provided: attach handlers to existing Nexus
   → If nexus not provided: create internal Nexus (no explicit Nexus needed)
   → For each product: register GET /fabric/{product_name}
   → For each writable source: register POST /fabric/{source_name}/write

6. Return → fabric is ready
```

**Without `db.start()`:**

- Express API works normally (backward compatible)
- `@db.model` works normally (backward compatible)
- Products are NOT accessible (no endpoints, no cache, no watchers)
- Sources are registered but NOT connected

---

## FabricContext — The Complete Interface

```python
class FabricContext:
    """Runtime context passed to product functions.

    Provides access to database models (via Express API) and
    registered sources. Used only inside @db.product functions.
    """

    # Database access (same as db.express — exact same object)
    express: DataFlowExpress

    # Source access
    def source(self, name: str) -> SourceHandle:
        """Get a handle to a registered source.

        Raises:
            KeyError: if source name not registered
        """

    # Product access (read cached result of another product)
    async def product(self, name: str) -> Any:
        """Read the cached result of another product.

        Returns the cached value if available, or executes
        the product function if not cached.

        Raises:
            KeyError: if product name not registered
        """
```

### SourceHandle — What You Get From `ctx.source("name")`

```python
class SourceHandle:
    """Handle to a registered source. Methods vary by source type."""

    # Universal methods (all source types)
    async def fetch(self, path: str = "") -> Any:
        """Fetch data from the source.
        REST: GET {url}/{path}
        File: read file content
        Cloud: get object at path
        Database: SELECT * FROM {path}
        """

    async def read(self) -> Any:
        """Read the entire source content.
        Alias for fetch("") for sources with a single resource.
        """

    async def list(self, prefix: str = "", limit: int = 100) -> list:
        """List items from the source.
        REST: GET {url}/{path} with pagination
        File: list directory entries
        Cloud: list objects with prefix
        Database: SELECT * with LIMIT
        """

    # Write methods (source-specific)
    async def write(self, path: str, data: Any) -> Any:
        """Write data to the source.
        REST: POST {url}/{path} with data
        File: write file content
        Cloud: put object at path
        Database: INSERT/UPDATE
        """

    # Metadata
    @property
    def name(self) -> str: ...

    @property
    def source_type(self) -> str: ...  # "rest", "file", "cloud", "database", "stream"

    @property
    def healthy(self) -> bool: ...

    @property
    def last_change_detected(self) -> Optional[datetime]: ...
```

---

## Testing Contract

### Tier 1: Unit Tests (product functions in isolation)

```python
from dataflow.fabric.testing import FabricContext

# Create test context with pre-loaded data
ctx = FabricContext.for_testing(
    express_data={
        "User": [
            {"id": "u1", "name": "Alice", "active": True},
            {"id": "u2", "name": "Bob", "active": False},
        ],
    },
    source_data={
        "crm": {"contacts": [{"id": "c1", "name": "Corp A"}]},
        "config": {"theme": "dark", "timezone": "UTC"},
    },
)

# Test product function directly — no database, no network
result = await dashboard(ctx)
assert result["active_users"] == 1
assert result["crm_contacts"] == 1
```

### Tier 2: Integration Tests (real DB, mock external sources)

```python
from dataflow.fabric.testing import MockSource

db = DataFlow("postgresql://test_db", tdd_mode=True)

@db.model
class User:
    id: str
    name: str
    active: bool

# Real database, mock external source
db.source("crm", MockSource(data={"contacts": [...]}))

await db.start(dev_mode=True)  # Skip pre-warming
result = await dashboard(db.fabric.context())
```

### Tier 3: E2E Tests (real everything)

```python
# Full stack with real sources
db = DataFlow(os.environ["TEST_DATABASE_URL"])
db.source("crm", RestSource(url=os.environ["TEST_CRM_URL"], ...))
await db.start()

# Hit the actual endpoint
response = httpx.get("http://localhost:8000/fabric/dashboard")
assert response.status_code == 200
```

---

## Error Surface Timeline

| Error                             | When             | What Developer Sees                                                                              |
| --------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------ |
| Missing env var in source config  | `db.source()`    | `EnvironmentError: Source 'crm' requires CRM_TOKEN but it is not set`                            |
| Malformed URL                     | `db.source()`    | `ValueError: Source 'crm' URL 'not-a-url' is not a valid URL`                                    |
| Duplicate source name             | `db.source()`    | `ValueError: Source 'crm' already registered`                                                    |
| Product depends_on unknown source | `@db.product()`  | `ValueError: Product 'dashboard' depends_on 'unknown' which is not a registered source or model` |
| Source unreachable                | `db.start()`     | `FabricStartupError: Source 'crm' health check failed: ConnectionError(...)`                     |
| Auth credentials wrong            | `db.start()`     | `FabricStartupError: Source 'crm' health check failed: 401 Unauthorized`                         |
| Pre-warming fails                 | `db.start()`     | Warning logged, product marked as "cold". First access triggers pipeline.                        |
| Source returns unexpected format  | Pipeline runtime | Warning logged, cache keeps old data, source marked for review                                   |
| Product function raises           | Pipeline runtime | Warning logged, cache keeps old data, error metric incremented                                   |

---

## Write Path — Definitive

```python
# Write through fabric to any source
await db.fabric.write(target: str, operation: str, data: dict) -> dict
```

**For database models** (target = model name):

```python
result = await db.fabric.write("User", "create", {"id": "u3", "name": "Charlie"})
# 1. Routes to db.express.create("User", data)
# 2. Express writes to database
# 3. Fabric identifies products with "User" in depends_on
# 4. Triggers async pipeline refresh for those products
# 5. Returns write result immediately (refresh is async)
```

**For external sources** (target = source name):

```python
result = await db.fabric.write("crm", "create", {"name": "New Contact", "email": "new@co.com"})
# 1. Routes to source("crm").write("/contacts", data)
# 2. REST adapter POSTs to CRM API
# 3. Fabric identifies products with "crm" in depends_on
# 4. Triggers async pipeline refresh for those products
# 5. Returns write result immediately (refresh is async)
```

**Auto-generated write endpoints:**

```
POST /fabric/User/write       → db.fabric.write("User", "create", body)
PUT  /fabric/User/write/{id}  → db.fabric.write("User", "update", {id, ...body})
POST /fabric/crm/write        → db.fabric.write("crm", "create", body)
```

---

## Nexus Integration — Definitive

**Option A: Fabric creates internal Nexus (zero-config)**

```python
db = DataFlow(os.environ["DATABASE_URL"])
# ... models, sources, products ...
await db.start()  # Creates internal Nexus, binds to 0.0.0.0:8000

# Endpoints available:
# GET  /fabric/dashboard
# GET  /fabric/users?page=1
# POST /fabric/User/write
```

**Option B: Attach to existing Nexus (controlled)**

```python
from nexus import Nexus

app = Nexus("MyApp")

# Developer's own handlers
@app.handler("custom_endpoint")
async def custom(): ...

db = DataFlow(os.environ["DATABASE_URL"])
# ... models, sources, products ...
await db.start(nexus=app)  # Attaches fabric handlers to existing Nexus

# Both custom and fabric endpoints available:
# GET  /custom_endpoint        (developer's handler)
# GET  /fabric/dashboard       (fabric auto-generated)
```

**DataFlowGateway**: Remains available for pure-database projects. Fabric serving replaces it when fabric is active. They do not coexist — `db.start()` with products supersedes `DataFlowGateway`.

---

## Development Mode

```python
# Fast restart during development
await db.start(dev_mode=True)
```

**What `dev_mode=True` changes:**

- Skips pre-warming (products start "cold" — first access triggers pipeline)
- Uses in-memory cache (no Redis required)
- Reduces poll intervals to minimum (5 seconds)
- Enables verbose logging for pipeline execution
- Does NOT skip source connection or health checks (developer needs to know if source is reachable)

**Clean restart:**

```python
await db.stop()   # Closes watchers, disconnects sources, clears in-memory cache
await db.start()  # Re-initializes everything

# With uvicorn --reload: db.stop() called on SIGTERM, db.start() on new process
```
