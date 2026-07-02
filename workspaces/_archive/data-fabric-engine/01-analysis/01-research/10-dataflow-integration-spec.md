# How DataFlow Becomes the Fabric — Precise Integration Specification

## The Answer: Yes, DataFlow Becomes the Fabric

DataFlow already has everything needed. The integration is surgical — no refactoring of existing code, only new code alongside existing abstractions.

### What DataFlow Already Has (exact code locations)

| Capability          | Where                                                        | How Fabric Uses It                                                      |
| ------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| Model registry      | `core/engine.py` — `self._models: Dict[str, Dict]`           | Fabric adds `self._sources` alongside it, same pattern                  |
| Express API         | `features/express.py` — `DataFlowExpress`                    | Product functions call `ctx.express.*` — same object as `db.express`    |
| Cache backend       | `cache/` — `InMemoryCache`, `RedisManager`, `auto_detection` | Fabric stores product cache using same backend, same protocol           |
| Cache invalidation  | `cache/invalidation.py` — `CacheInvalidator`                 | Fabric registers patterns: when source changes → invalidate products    |
| Dependency tracking | `core/engine.py` — `DerivedModelEngine` (TSG-100)            | Fabric extends this for product→source dependency graph                 |
| Health check        | `adapters/base_adapter.py` — `async health_check()`          | Already on `BaseAdapter`. New source adapters implement the same method |
| Node generation     | `core/nodes.py` — `NodeGenerator`                            | NOT used by fabric — products are not nodes, they are a new concept     |

### What Fabric Adds (new internal registries)

```python
# In DataFlow.__init__, alongside existing registries:

# EXISTING
self._models: Dict[str, Dict[str, Any]] = {}          # @db.model registrations
self._registered_models: Dict[str, Type] = {}          # model_name → class
self._nodes: Dict[str, str] = {}                       # generated node names

# NEW — fabric registries (only populated when fabric features are used)
self._sources: Dict[str, SourceRegistration] = {}      # db.source() registrations
self._products: Dict[str, ProductRegistration] = {}    # @db.product() registrations
self._fabric: Optional[FabricRuntime] = None           # The runtime (started by db.start())
```

### The `db.source()` Method — Added to DataFlow Class

```python
def source(self, name: str, config: BaseSourceConfig) -> None:
    """Register an external data source.

    This is the fabric equivalent of @db.model — but for data you don't own.
    @db.model = you own the table, DataFlow manages schema/migrations.
    db.source() = data lives elsewhere, DataFlow manages connection/caching.

    Validates immediately:
    - Env var references exist
    - URL format is valid
    - Name is unique (not already a model name or source name)

    Does NOT connect. Connection happens at db.start().
    """
    # Validate name uniqueness across models AND sources
    if name in self._models:
        raise ValueError(
            f"'{name}' is already registered as a @db.model. "
            f"Source names must not conflict with model names."
        )
    if name in self._sources:
        raise ValueError(f"Source '{name}' already registered.")

    # Validate config (env vars, URL format)
    config.validate()  # Raises EnvironmentError or ValueError

    # Store registration
    self._sources[name] = SourceRegistration(
        name=name,
        config=config,
        adapter=None,       # Created at db.start()
        state="registered",  # registered → connecting → active → paused → error
    )
```

### The `@db.product()` Decorator — Added to DataFlow Class

```python
def product(
    self,
    name: str,
    mode: Literal["materialized", "parameterized", "virtual"] = "materialized",
    depends_on: List[str] = None,  # REQUIRED for materialized/parameterized
    staleness: StalenessPolicy = None,
    schedule: Optional[str] = None,
    multi_tenant: bool = False,
    auth: Optional[Dict] = None,
    rate_limit: Optional[RateLimit] = None,
    write_debounce: Optional[timedelta] = None,
):
    """Decorator to register a data product.

    A product is a materialized view over sources. The decorated function
    receives a FabricContext and returns the data the frontend needs.
    """
    if mode in ("materialized", "parameterized") and not depends_on:
        raise ValueError(
            f"Product '{name}' requires depends_on for mode '{mode}'. "
            f"List the model names and source names this product reads from."
        )

    # Validate depends_on references exist
    if depends_on:
        for dep in depends_on:
            if dep not in self._models and dep not in self._sources:
                raise ValueError(
                    f"Product '{name}' depends_on '{dep}' which is not a "
                    f"registered @db.model or db.source()."
                )

    def decorator(fn: Callable) -> Callable:
        self._products[name] = ProductRegistration(
            name=name,
            mode=mode,
            depends_on=depends_on or [],
            staleness=staleness or StalenessPolicy(),
            schedule=schedule,
            multi_tenant=multi_tenant,
            auth=auth,
            rate_limit=rate_limit or RateLimit(),
            write_debounce=write_debounce or timedelta(seconds=1),
            fn=fn,
        )
        return fn
    return decorator
```

### The `db.start()` Method — Added to DataFlow Class

```python
async def start(
    self,
    nexus: Optional[Any] = None,
    fail_fast: bool = True,
    dev_mode: bool = False,
    coordination: Optional[str] = None,  # "redis" | "postgresql" | None (auto)
    host: str = "127.0.0.1",
    port: int = 8000,
    enable_writes: bool = False,
    tenant_extractor: Optional[Callable] = None,
) -> None:
    """Start the fabric runtime.

    This does six things in order:
    1. Initialize DataFlow (ensure DB connected, migrations run)
    2. Connect to all registered sources
    3. Elect leader (multi-worker coordination)
    4. Pre-warm all materialized products (leader only)
    5. Start change detection watchers/pollers (leader only)
    6. Register fabric endpoints (all workers)

    Without db.start(): Express API works normally. Products are NOT accessible.
    """
    # 1. Ensure DataFlow itself is initialized
    await self.initialize()

    # 2-6: Create and start the fabric runtime
    self._fabric = FabricRuntime(
        dataflow=self,
        sources=self._sources,
        products=self._products,
        nexus=nexus,
        fail_fast=fail_fast,
        dev_mode=dev_mode,
        coordination=coordination,
        host=host,
        port=port,
        enable_writes=enable_writes,
        tenant_extractor=tenant_extractor,
    )
    await self._fabric.start()
```

### How Express Writes Trigger Product Refresh

The key integration point: when `db.express.create("User", {...})` runs, the fabric needs to know so it can refresh products that `depends_on=["User"]`.

```python
# In DataFlowExpress._execute_write() — AFTER the write succeeds:

async def _post_write_hook(self, model: str, operation: str, data: Dict) -> None:
    """Notify fabric of data changes."""
    if self._db._fabric and self._db._fabric.running:
        await self._db._fabric.notify_change(
            source_name=model,    # Model names are treated as source names
            operation=operation,   # "create", "update", "delete"
            data=data,
        )
        # FabricRuntime.notify_change() triggers debounced pipeline refresh
        # for all products where model is in depends_on
```

This is ~10 lines added to ExpressDataFlow. No changes to Express API signatures.

### Source Adapter Protocol — BaseSourceAdapter

New abstract class alongside existing `BaseAdapter` and `DatabaseAdapter`:

```python
class BaseSourceAdapter(ABC):
    """Base class for non-database source adapters.

    Existing hierarchy:
      BaseAdapter → DatabaseAdapter → PostgreSQLAdapter, MySQLAdapter, ...

    New hierarchy:
      BaseAdapter → BaseSourceAdapter → RestSourceAdapter, FileSourceAdapter, ...

    BaseSourceAdapter adds methods specific to fabric source management:
    change detection, fetch, and write. DatabaseAdapter already has these
    as SQL operations; BaseSourceAdapter provides them for non-DB sources.
    """

    def __init__(self, config: BaseSourceConfig):
        super().__init__(connection_string=str(config.url) if hasattr(config, 'url') else "")
        self.config = config
        self._state: str = "registered"  # registered → connecting → active → paused → error
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker.failure_threshold,
            probe_interval=config.circuit_breaker.probe_interval,
        )
        self._last_change_detected: Optional[datetime] = None
        self._last_successful_data: Dict[str, Any] = {}

    @property
    def adapter_type(self) -> str:
        return "source"

    # --- Change Detection ---

    @abstractmethod
    async def detect_change(self) -> bool:
        """Check if the source data has changed since last check.

        Must be CHEAP — no full data fetch. Use:
        - REST: ETag/Last-Modified conditional request
        - File: stat() for mtime
        - Cloud: ListObjects metadata
        - Database: MAX(updated_at) query

        Returns True if data changed, False if unchanged.
        """

    # --- Data Fetch ---

    @abstractmethod
    async def fetch(self, path: str = "", params: Optional[Dict] = None) -> Any:
        """Fetch data from the source.

        path: Resource path within the source (e.g., "contacts", "deals")
        params: Query parameters (e.g., {"status": "active", "limit": 100})
        Returns: Parsed response data (dict, list, or raw content)
        """

    async def fetch_all(
        self, path: str = "", page_size: int = 100, max_records: int = 100_000
    ) -> List[Any]:
        """Fetch all pages from a paginated source.

        Default implementation calls fetch() in a loop using source-specific
        pagination. Subclasses override for source-specific pagination patterns.
        """

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        """Stream pages from a paginated source. Memory-efficient."""

    async def read(self) -> Any:
        """Read the entire source content. Alias for fetch("")."""
        return await self.fetch()

    async def list(self, prefix: str = "", limit: int = 100) -> List[Any]:
        """List items from the source."""
        return await self.fetch(prefix, params={"limit": limit})

    # --- Write ---

    async def write(self, path: str, data: Any) -> Any:
        """Write data to the source. Optional — not all sources support writes."""
        raise NotImplementedError(f"Source {self.adapter_type} does not support writes")

    # --- Stale Data Access ---

    def last_successful_data(self, path: str = "") -> Optional[Any]:
        """Return the last successfully fetched data for a path.
        Used by product functions for graceful degradation when source is down.
        """
        return self._last_successful_data.get(path)

    # --- State ---

    @property
    def state(self) -> str:
        return self._state

    @property
    def healthy(self) -> bool:
        return self._state == "active" and self._circuit_breaker.state == "closed"

    @property
    def last_change_detected(self) -> Optional[datetime]:
        return self._last_change_detected
```

### Source State Machine

```
                  db.source()           db.start()           health check OK
  ┌─────────────┐          ┌──────────────┐          ┌──────────┐
  │  registered  │─────────→│  connecting  │─────────→│  active  │
  └─────────────┘          └──────────────┘          └──────────┘
                                   │                       │
                          connect fails              3 failures
                                   │                  (circuit open)
                                   ▼                       ▼
                            ┌──────────┐            ┌──────────┐
                            │  error   │←───────────│  paused  │
                            └──────────┘            └──────────┘
                                   │                       ↑
                            retry succeeds          probe succeeds
                                   │                       │
                                   └──────────────→ active ─┘
```

Transitions:
| From | To | Trigger |
|------|-----|---------|
| registered | connecting | `db.start()` called |
| connecting | active | `adapter.connect()` + `adapter.health_check()` succeed |
| connecting | error | `adapter.connect()` fails (and `fail_fast=True` → raise) |
| active | paused | Circuit breaker opens (3 consecutive failures) |
| paused | active | Circuit breaker probe succeeds |
| paused | error | Circuit breaker probe fails N times (configurable) |
| error | connecting | Manual `db.fabric.reconnect("source_name")` |

---

## DataFlowEngine Builder Integration

```python
class DataFlowEngineBuilder:
    # EXISTING methods (unchanged)
    def validation(self, layer) -> DataFlowEngineBuilder: ...
    def classification_policy(self, policy) -> DataFlowEngineBuilder: ...
    def slow_query_threshold(self, seconds) -> DataFlowEngineBuilder: ...
    def validate_on_write(self, enabled) -> DataFlowEngineBuilder: ...
    def config(self, **kwargs) -> DataFlowEngineBuilder: ...

    # NEW — fabric configuration methods
    def source(self, name: str, config: BaseSourceConfig) -> DataFlowEngineBuilder:
        """Register a source via builder. Same as db.source() but chainable."""
        self._sources[name] = config
        return self

    def fabric(self, **kwargs) -> DataFlowEngineBuilder:
        """Configure fabric runtime parameters."""
        self._fabric_config = kwargs  # host, port, coordination, etc.
        return self

    async def build(self) -> DataFlowEngine:
        """Build engine. Sources registered via .source() are added to the DataFlow instance."""
        dataflow = DataFlow(self._database_url, **self._dataflow_kwargs)
        for name, config in self._sources.items():
            dataflow.source(name, config)
        # ... existing build logic ...
        return engine
```

---

## Backward Compatibility Guarantee

Every change is ADDITIVE. No existing method, parameter, or behavior changes.

| Existing Code                                | Still Works? | How?                                                                 |
| -------------------------------------------- | ------------ | -------------------------------------------------------------------- |
| `db = DataFlow("pg://...")`                  | YES          | `_sources`, `_products`, `_fabric` default to empty/None             |
| `@db.model class User: ...`                  | YES          | Model registry unchanged                                             |
| `await db.express.create("User", {...})`     | YES          | Express API unchanged. Post-write hook is no-op if `_fabric` is None |
| `db.express_sync.read("User", "u1")`         | YES          | Sync express unchanged                                               |
| `DataFlowEngine.builder("pg://...").build()` | YES          | Builder unchanged. New methods are additive                          |
| `DataFlowGateway(...)`                       | YES          | Gateway unchanged. Does not interact with fabric                     |
| Cache configuration                          | YES          | Fabric uses same cache backend. No conflicts                         |

**The test**: Every existing DataFlow test suite passes unchanged after fabric code is added.
