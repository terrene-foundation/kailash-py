---
name: dataflow-fabric-patterns
description: "Fabric runtime patterns including fabric-only mode, serving validation, batch caps, caching, startup timeouts, prewarm passthrough, and strict pool validation. Use when asking about 'fabric-only mode', '_fabric_only', 'get_cached_product', 'fabric startup timeout', 'prewarm', 'DATAFLOW_STRICT_POOL_VALIDATION', 'batch endpoint cap', 'serving validation', or 'fabric patterns'."
---

# DataFlow Fabric Patterns

Operational patterns for the Data Fabric Engine covering runtime behavior, validation, caching, and startup configuration.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `MEDIUM`
> Related Skills: [`dataflow-fabric-engine`](dataflow-fabric-engine.md), [`dataflow-express`](dataflow-express.md), [`dataflow-connection-config`](dataflow-connection-config.md)
> Related Subagents: `dataflow-specialist` (framework guidance)

## Fabric-Only Mode

When a DataFlow instance has registered sources (via `db.source()`) but no `@db.model` definitions, the fabric engine skips database initialization entirely. This enables pure data integration scenarios without requiring a database connection.

### Detection Pattern

The `_fabric_only` property on the DataFlow instance determines this mode:

```python
from dataflow import DataFlow

db = DataFlow()  # No connection string needed in fabric-only mode

# Register external sources only — no @db.model
db.source("crm", RestSourceConfig(url="https://api.example.com", ...))
db.source("analytics", RestSourceConfig(url="https://analytics.example.com", ...))

# db._fabric_only is True because:
#   - len(db._sources) > 0  (sources registered)
#   - len(db._models) == 0  (no models defined)

# db.start() skips db.initialize() entirely
fabric = await db.start()
```

### When fabric-only activates

| Sources registered | Models defined | `_fabric_only` | `db.initialize()` called |
| ------------------ | -------------- | -------------- | ------------------------ |
| Yes                | No             | `True`         | Skipped                  |
| Yes                | Yes            | `False`        | Called (normal mode)     |
| No                 | Yes            | `False`        | Called (normal mode)     |
| No                 | No             | N/A            | No-op (nothing to do)    |

### Use cases

- **API aggregation**: Combine multiple REST APIs into unified data products without a local database
- **Data gateway**: Proxy and transform external data with caching and circuit breakers
- **Health dashboard**: Monitor external service health without persisting state

```python
db = DataFlow()  # No connection string

db.source("service_a", RestSourceConfig(url="https://a.example.com", ...))
db.source("service_b", RestSourceConfig(url="https://b.example.com", ...))

@db.product("health", depends_on=["service_a", "service_b"])
async def health_check(ctx):
    a_status = await ctx.source("service_a").fetch("health")
    b_status = await ctx.source("service_b").fetch("health")
    return {"service_a": a_status, "service_b": b_status}

fabric = await db.start(dev_mode=True)  # No DB init, just sources + products
```

## Serving Parameter Validation

The fabric serving layer validates parameters for consumer and refresh endpoints at registration time, not at request time. This catches configuration errors early.

### Consumer schema validation

Parameterized products declare their parameters via function signature. The serving layer validates incoming query parameters against this schema:

```python
@db.product("filtered", mode="parameterized", depends_on=["Order"])
async def filtered_orders(ctx, status: str = "", limit: int = 50):
    return await ctx.express.list("Order", {"status": status}, limit=limit)

# GET /fabric/filtered?status=open&limit=10  -> valid
# GET /fabric/filtered?status=open&limit=abc -> 422: limit must be integer
# GET /fabric/filtered?unknown=x             -> 422: unknown parameter
```

### Refresh schema validation

Products with `schedule` or manual refresh endpoints validate that the refresh payload matches expected structure:

```python
# POST /fabric/filtered/_refresh with body {"force": true} -> valid
# POST /fabric/filtered/_refresh with body {"force": "yes"} -> 422: force must be boolean
```

## Batch Endpoint Product Count Cap

The batch endpoint (`GET /fabric/_batch?products=a,b,c`) enforces a maximum of **50 products** per request. Requests exceeding this cap receive a `400 Bad Request` response.

```python
# Valid: up to 50 products
# GET /fabric/_batch?products=p1,p2,...,p50  -> 200 OK

# Invalid: more than 50 products
# GET /fabric/_batch?products=p1,p2,...,p51  -> 400: Maximum 50 products per batch request
```

**Why 50**: Prevents a single batch request from monopolizing the event loop. Each product read involves cache lookup and potential staleness checks.

## FabricRuntime.get_cached_product()

Direct programmatic access to cached product data without going through HTTP endpoints:

```python
fabric = await db.start()

# Read cached product data directly (no HTTP round-trip)
dashboard = fabric.get_cached_product("dashboard")
# Returns: {"local_tasks_total": 5, "local_tasks_open": 2, ...}

# Returns None if product has not been computed yet
result = fabric.get_cached_product("nonexistent")
# Returns: None

# For parameterized products, pass the parameter key
user_data = fabric.get_cached_product("user_orders", params={"user_id": "u123"})
```

**When to use**: Inside application code that already has a reference to the `FabricRuntime` instance. Avoids HTTP overhead for co-located product consumers.

## FabricRuntime.start() Timeout on db.initialize()

When the fabric engine is not in fabric-only mode, `db.start()` wraps the `db.initialize()` call in a **30-second timeout** via `asyncio.wait_for()`. If database initialization exceeds this timeout, an `asyncio.TimeoutError` is raised.

```python
# Internal behavior (simplified):
async def start(self, **kwargs):
    if not self._fabric_only:
        try:
            await asyncio.wait_for(self.db.initialize(), timeout=30.0)
        except asyncio.TimeoutError:
            raise TimeoutError(
                "Database initialization timed out after 30s. "
                "Check connection string and database availability."
            )
    # ... continue with source connections and product warming
```

**Common causes of timeout**:

- Database server unreachable (wrong host/port)
- Network firewall blocking the connection
- Database under heavy load during migration
- DNS resolution failure

**Workaround for slow migrations**: If you need more time for initial schema creation, call `await db.initialize()` separately before `db.start()`:

```python
await db.initialize()  # No timeout — waits as long as needed
fabric = await db.start()  # Skips initialize since already done
```

## DataFlow.start(prewarm=True) Parameter Passthrough

The `prewarm` parameter on `db.start()` controls whether materialized products are computed at startup:

```python
# Default: prewarm all materialized products at startup
fabric = await db.start(prewarm=True)

# Skip prewarming — products computed on first request
fabric = await db.start(prewarm=False)

# dev_mode implies prewarm=False
fabric = await db.start(dev_mode=True)  # Equivalent to prewarm=False
```

**Prewarm behavior**:

- `prewarm=True` (default): All materialized products are computed sequentially during startup. Startup is slower but first requests are fast.
- `prewarm=False`: No products computed at startup. First request to each product triggers computation (cache-miss penalty).
- `dev_mode=True`: Overrides `prewarm` to `False` regardless of explicit setting.

**Passthrough**: The `prewarm` flag is passed through from `DataFlow.start()` to `FabricRuntime.start()` without modification. Any custom FabricRuntime subclass receives the same parameter.

## Strict Pool Validation via DATAFLOW_STRICT_POOL_VALIDATION

Set the `DATAFLOW_STRICT_POOL_VALIDATION` environment variable to enable strict connection pool validation. When enabled, DataFlow validates pool configuration at initialization and raises errors for misconfigured pools instead of silently adjusting values.

```bash
# Enable strict pool validation
export DATAFLOW_STRICT_POOL_VALIDATION=1
```

### What strict validation checks

| Check                        | Default behavior (non-strict) | Strict behavior                   |
| ---------------------------- | ----------------------------- | --------------------------------- |
| `pool_size` < 1              | Silently set to 1             | Raises `ValueError`               |
| `max_overflow` < 0           | Silently set to 0             | Raises `ValueError`               |
| `pool_size` > `max_overflow` | Silently adjusts overflow     | Raises `ValueError`               |
| `pool_timeout` < 1           | Silently set to 1             | Raises `ValueError`               |
| SQLite with `pool_size` > 1  | Silently set to 1             | Raises `ValueError` with WAL hint |

### When to enable

- **CI/CD pipelines**: Catch pool misconfigurations before deployment
- **Production**: Prevent silent degradation from misconfigured pools
- **Development**: Optional, but useful when tuning pool parameters

```python
import os
os.environ["DATAFLOW_STRICT_POOL_VALIDATION"] = "1"

from dataflow import DataFlow

# This now raises ValueError instead of silently adjusting
db = DataFlow("sqlite:///app.db", pool_size=10)  # ValueError: SQLite pool_size must be 1
```

## Critical Rules

- **Fabric-only mode** is automatic — do not force `_fabric_only` manually
- **Batch cap of 50** is server-enforced — client-side splitting is the caller's responsibility
- **30s init timeout** applies only when `_fabric_only` is `False` — pure fabric mode skips initialization entirely
- **Strict pool validation** is opt-in via environment variable — it is not enabled by default
- **Prewarm** only affects materialized products — parameterized and virtual products are always computed on-demand
