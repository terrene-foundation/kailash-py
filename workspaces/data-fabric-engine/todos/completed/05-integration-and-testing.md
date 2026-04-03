# Milestone 5: Integration, Builder, Testing & Packaging

---

## TODO-26: Wire DataFlowEngine builder for fabric

**Layer**: 8
**File**: `packages/kailash-dataflow/src/dataflow/engine.py`

Add builder methods (doc 13, lines 258-264):
- `.source(name, config) -> DataFlowEngineBuilder` — chainable source registration
- `.fabric(**kwargs) -> DataFlowEngineBuilder` — configure fabric runtime params

Builder stores configs and applies at `build()` time by calling `dataflow.source()` for each registered source.

**Test**: Tier 1 — test builder chain, verify sources registered after build.

---

## TODO-27: Build MockSource for testing

**Layer**: testing
**File**: `packages/kailash-dataflow/src/dataflow/fabric/testing.py`

Implement `MockSource(BaseSourceAdapter)` (doc 08, lines 349-364):
- Accepts pre-loaded `data` dict at construction
- `detect_change()` → configurable (default False)
- `fetch()` → return pre-loaded data
- No real connections, no network

For Tier 1/2 testing where developers test product functions without external sources.

**Test**: Tier 1 — test MockSource returns configured data.

---

## TODO-28: Build Cron scheduler for scheduled products

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/scheduler.py`

Implement cron-based product refresh (doc 04, lines 222-249):
- Parse cron expression (use `croniter` library)
- Supervised background task on leader worker only
- On trigger: enqueue product pipeline execution (same as source-change trigger)

Products refresh on BOTH source change AND schedule — whichever comes first.

**Test**: Tier 1 — test cron parsing. Tier 2 — test scheduled execution triggers pipeline.

---

## TODO-29: Build multi-tenancy support

**Layer**: 6-10
**Files**: multiple

Multi-tenant cache isolation (doc 04, lines 186-218):
- Products with `multi_tenant=True` get per-tenant cache keys: `fabric:{tenant_id}:{product}`
- `tenant_extractor` lambda on `db.start()` extracts tenant from request
- `ctx.tenant_id` available in product functions
- `multi_tenant=True` without `tenant_extractor` raises error at `db.start()` (fail-closed)
- Pre-warming: accept `tenant_ids: list[str]` or query from DB

**Test**: Tier 2 — test tenant isolation in cache. Two tenants see different data for same product.

---

## TODO-30: Update pyproject.toml with fabric extras

**Layer**: packaging
**File**: `packages/kailash-dataflow/pyproject.toml`

Add optional dependency groups (doc 01-arch-plan, lines 223-230):

```toml
[project.optional-dependencies]
fabric = ["httpx>=0.27", "watchdog>=4.0", "msgpack>=1.0"]
cloud = ["boto3>=1.35", "google-cloud-storage>=2.18"]
excel = ["openpyxl>=3.1"]
streaming = ["aiokafka>=0.11", "websockets>=13.0"]
fabric-all = ["kailash-dataflow[fabric,cloud,excel,streaming]"]
```

Fabric core requires httpx (REST), watchdog (file watch), msgpack (serialization).
Cloud, Excel, streaming are optional extras.

**Test**: Verify `pip install kailash-dataflow[fabric]` works. Verify lazy imports for optional deps.

---

## TODO-31: Build comprehensive Tier 2 integration test suite

**Layer**: testing
**File**: `packages/kailash-dataflow/tests/fabric/`

End-to-end integration tests with real infrastructure:

- Test 1: Register 3 sources (DB model, REST mock server, temp file) → define 1 materialized product → `db.start()` → verify pre-warming → GET endpoint → verify headers + data
- Test 2: Modify file → verify change detected → pipeline runs → cache updated → GET returns new data
- Test 3: Write via Express → verify event fires → product refresh → cache updated
- Test 4: Source goes down → circuit breaker opens → product serves stale with degraded flag → source recovers → fresh data
- Test 5: Multiple parameterized requests → verify cache per parameter combo → verify cardinality limit
- Test 6: `db.stop()` → verify graceful shutdown (pipelines drain, locks released)
- Test 7: Two workers → leader election → only leader polls → follower serves from cache

**No mocking** in Tier 2. Use: SQLite in-memory (DB), local HTTP test server (REST), temp files (file), real Redis.

---

## TODO-32: Build reference application

**Layer**: examples
**File**: `packages/kailash-dataflow/examples/fabric_reference/`

Clean-room minimal app (doc 11-aether-as-reference):

```python
db = DataFlow("sqlite:///app.db")

@db.model
class Task:
    id: str
    title: str
    status: str

db.source("todos", RestSource(url="https://jsonplaceholder.typicode.com", endpoints={"items": "/todos"}, poll_interval=60))
db.source("config", FileSource(path="./config.yaml", watch=True))

@db.product("dashboard", depends_on=["Task", "todos", "config"])
async def dashboard(ctx):
    tasks = await ctx.express.list("Task")
    todos = await ctx.source("todos").fetch("items")
    config = await ctx.source("config").read()
    return {"my_tasks": len(tasks), "api_todos": len(todos), "theme": config.get("theme", "light")}

await db.start(dev_mode=True)
```

Runs with: `pip install kailash-dataflow[fabric]` + SQLite + no external credentials.

---

## TODO-33: Update DataFlow README.md and documentation

**Layer**: documentation
**Files**: `packages/kailash-dataflow/README.md`, `docs/`

Update DataFlow identity from "zero-config database operations" to "zero-config data operations."

Document:
- New concepts: `db.source()`, `@db.product()`, `db.start()`
- Three product modes with examples
- Source types with configuration examples
- Observability endpoints
- Migration guide for existing users (all existing code unchanged)

Update `CHANGELOG.md` with fabric feature addition.
