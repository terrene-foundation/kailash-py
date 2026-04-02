# DataFlow IS the Fabric — Revised Architecture

## The Insight

The red team recommended "DataFlow extension" (`kailash-dataflow[fabric]`). The user asked a deeper question: **what is the difference between DataFlow and a fabric?**

After reading DataFlow's core abstractions, the answer is: **there is no fundamental difference.** DataFlow is already a data fabric — but currently limited to database sources. The architecture doesn't need extension; it needs **generalization**.

## Evidence from DataFlow's Own Code

### BaseAdapter is source-agnostic

```python
class BaseAdapter(ABC):
    """Minimal base interface for all DataFlow adapters."""
    # No SQL. No schema. No queries.
    # Just: connect(), disconnect(), supports_feature()
    # Subtypes: DatabaseAdapter, DocumentAdapter, VectorAdapter,
    #           GraphAdapter, KeyValueAdapter
```

Nothing prevents adding `RestAPIAdapter(BaseAdapter)`, `FileAdapter(BaseAdapter)`, `CloudAdapter(BaseAdapter)`.

### Express API dispatches on strings and dicts

```python
await db.express.create("User", {"id": "u1", "name": "Alice"})
await db.express.read("User", "u1")
await db.express.list("User", filter={"active": True})
```

The model name is a string. The data is a dict. This works for ANY source — `db.express.read("WeatherAPI", "current")` would route to a REST adapter just as naturally.

### Cache invalidation is semantic

```python
@dataclass
class InvalidationPattern:
    model: str        # "User", "WeatherAPI", "ConfigFile" — any string
    operation: str    # "create", "update", "delete", "refresh" — any string
    invalidates: List[str]  # Cache key patterns to clear
```

No database concepts. Purely model + operation → cache keys.

### The only database-specific parts

1. **Constructor**: `DataFlow(database_url="postgresql://...")` — takes a single DB URL
2. **Auto-migration**: Assumes relational schema, runs ALTER TABLE
3. **Node generator**: Generates SQL-specific CRUD nodes from `@db.model`

These three are the ONLY things that need generalization. Everything else (cache, express, invalidation, multi-tenancy, audit logging) already works for any source.

---

## What DataFlow Becomes

### Current Identity

> "Zero-config database operations"

### New Identity

> "Zero-config data operations — databases, APIs, files, cloud, anything"

This is not scope creep — it is the natural evolution. DataFlow already abstracts away database differences (PostgreSQL vs MySQL vs SQLite vs MongoDB). Extending to REST APIs and files is the same abstraction at a wider scope.

### The Conceptual Model

```
┌─────────────────────────────────────────────────────────────┐
│                     DataFlow Engine                          │
│                                                              │
│  @db.model          — register a database table as source    │
│  @db.source          — register ANY external source          │
│  @db.product         — define materialized view over sources │
│                                                              │
│  db.express.read()  — read from any source (cached)          │
│  db.express.list()  — list from any source (cached)          │
│  db.express.create() — write to any source                   │
│                                                              │
│  Pipeline-driven cache: updated on source change, not TTL    │
│  Pre-warming: all products cached before first request       │
│  Auto-endpoints: Nexus integration for serving               │
└─────────────────────────────────────────────────────────────┘
```

### What `@db.model` vs `@db.source` vs `@db.product` Mean

```python
db = DataFlow("postgresql://...")  # Primary database (existing)

# @db.model — you OWN this data (existing, unchanged)
@db.model
class User:
    id: str
    name: str
    email: str

# @db.source — data from ELSEWHERE (new)
# DataFlow manages the connection, polling, caching, health
db.source("crm", RestSource(
    url="https://api.salesforce.com/v1",
    auth=BearerAuth(token_env="SALESFORCE_TOKEN"),
    poll_interval=300,
))

db.source("hr_data", FileSource(
    path="/shared/hr/employees.xlsx",
    watch=True,
))

db.source("documents", CloudSource(
    bucket="company-docs",
    provider="s3",
    credentials_env="AWS_CREDENTIALS",
))

# @db.product — materialized view over any combination (new)
# Pipeline-driven: re-materialized when sources change
# Cached: FE reads from cache, never from source
@db.product("employee_dashboard")
async def employee_dashboard(ctx):
    users = await ctx.express.list("User", filter={"active": True})
    crm = await ctx.source("crm").fetch("/contacts")
    hr = await ctx.source("hr_data").read()
    return {
        "employees": users,
        "crm_contacts": crm,
        "hr_records": hr,
    }
```

---

## What Changes in DataFlow

### Minimal Core Changes

| Component                  | Change                                                               | Effort |
| -------------------------- | -------------------------------------------------------------------- | ------ |
| `DataFlow.__init__`        | Add `sources: Dict[str, BaseSource]` parameter                       | Small  |
| `BaseAdapter`              | Add new subclasses: `RestAdapter`, `FileAdapter`, `CloudAdapter`     | Medium |
| `DataFlowEngine.builder()` | Add `.source(name, config)` method                                   | Small  |
| `Express API`              | Route to correct adapter based on model/source registry              | Small  |
| Auto-migration             | Skip for non-database sources (already has `migration_enabled` flag) | None   |

### New Components (Added, Not Changed)

| Component                      | Purpose                                               | LOC Est. |
| ------------------------------ | ----------------------------------------------------- | -------- |
| `adapters/rest.py`             | REST API adapter                                      | 500-800  |
| `adapters/file.py`             | File system adapter                                   | 300-500  |
| `adapters/cloud.py`            | S3/GCS/Azure adapter                                  | 400-600  |
| `adapters/excel.py`            | Excel/CSV adapter                                     | 300-400  |
| `fabric/engine.py`             | Fabric orchestrator (products, pipeline, pre-warming) | 800-1200 |
| `fabric/products.py`           | Product definitions + registry                        | 500-700  |
| `fabric/pipeline.py`           | Pipeline runner + change detection                    | 800-1200 |
| `fabric/serving.py`            | Nexus endpoint generation                             | 400-600  |
| `fabric/warming.py`            | Pre-warming orchestrator                              | 300-400  |
| `fabric/staleness.py`          | Staleness policy                                      | 200-300  |
| `pipeline/change_detection.py` | Cheap change detection strategies                     | 400-600  |
| `pipeline/circuit_breaker.py`  | Circuit breaker per source                            | 300-400  |
| `pipeline/backpressure.py`     | Adaptive batch sizing                                 | 200-300  |

**Total new code**: ~5,000-7,500 LOC
**Total new tests**: ~4,000-6,000 LOC

### What Does NOT Change

- `@db.model` and all database operations — 100% backward compatible
- Express API surface — same methods, same signatures
- Cache infrastructure — same backends, same protocols
- Multi-tenancy, audit logging, classification — unchanged
- Migration system — unchanged (skipped for non-DB sources)
- All existing adapters — unchanged

---

## Why This Is Better Than Separate Package

| Concern            | Separate Package                                     | DataFlow Evolution                                       |
| ------------------ | ---------------------------------------------------- | -------------------------------------------------------- |
| **User discovery** | "I need kailash-fabric AND kailash-dataflow"         | "I already use DataFlow, it now supports APIs and files" |
| **API surface**    | Two APIs to learn                                    | Same `db.express` API for everything                     |
| **Dependency**     | Fabric wraps DataFlow — hidden coupling              | No wrapping — one engine                                 |
| **Cache**          | Two cache layers interacting                         | One cache layer, one protocol                            |
| **Version matrix** | Three packages to keep compatible                    | One package                                              |
| **Mental model**   | "DataFlow for databases, Fabric for everything else" | "DataFlow for data"                                      |
| **Identity**       | Two things that overlap                              | One thing with a clear mission                           |

---

## The Answer to "What Is the Difference?"

There is no difference. A data fabric is: unified access to heterogeneous sources with intelligent caching and serving. DataFlow already does this for databases. The evolution is removing the "database" constraint and letting it do it for ALL sources.

**DataFlow = Data Fabric.**
**`@db.model` = register a database source.**
**`@db.source` = register any source.**
**`@db.product` = define a materialized view over sources.**
**Express API = read/write any source.**
**Cache = pipeline-driven, not TTL-driven.**
