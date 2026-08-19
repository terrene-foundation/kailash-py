---
name: dataflow-fabric-engine
description: "Data Fabric Engine for external sources and derived products. Use when asking about 'fabric engine', 'data fabric', 'external sources', 'data products', 'db.source', 'db.product', 'db.start', 'REST source', 'polling', 'webhooks', 'MockSource', 'FabricContext', or 'fabric serving'."
---

# Data Fabric Engine -- External Sources & Derived Products

Extends DataFlow from "zero-config database operations" to "zero-config data operations" by adding external source adapters, derived data products, and an auto-refresh runtime with observability.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-express`](dataflow-express.md), [`dataflow-events`](dataflow-events.md), [`dataflow-quickstart`](dataflow-quickstart.md)
> Related Subagents: `dataflow-specialist` (framework guidance)

## Quick Reference

| Concept                | API                                   | Purpose                                             |
| ---------------------- | ------------------------------------- | --------------------------------------------------- |
| Register external data | `db.source(name, config)`             | REST, File, Cloud, DB, Stream adapters              |
| Define derived product | `@db.product(name, depends_on=[...])` | Materialized, Parameterized, Virtual modes          |
| Start fabric runtime   | `fabric = await db.start(...)`        | Auto-endpoints, polling, serving, pre-warming       |
| Stop fabric runtime    | `await db.stop()`                     | Graceful shutdown (drain pipelines, release leader) |

## Quick Start

Complete working example using MockSource (runs with just `pip install kailash-dataflow` and SQLite):

```python
import asyncio
from dataflow import DataFlow
from dataflow.fabric.testing import MockSource

db = DataFlow("sqlite:///app.db")

# 1. Define a local model
@db.model
class Task:
    title: str
    status: str
    assignee: str

# 2. Register an external source (MockSource for dev, RestSourceConfig for prod)
todo_source = MockSource(
    name="todos",
    data={"": {"items": [{"id": 1, "title": "Ship v1", "done": True}]}},
)
db.source("todos", todo_source)

# 3. Define a data product that combines local + external data
@db.product("dashboard", depends_on=["Task", "todos"])
async def build_dashboard(ctx):
    tasks = await ctx.express.list("Task")
    todos_payload = await ctx.source("todos").read()
    todo_items = todos_payload.get("items", [])
    open_tasks = [t for t in tasks if t.get("status") != "done"]
    return {
        "local_tasks_total": len(tasks),
        "local_tasks_open": len(open_tasks),
        "external_todos_total": len(todo_items),
    }

async def main():
    await db.express.create("Task", {"title": "Login", "status": "open", "assignee": "Alice"})

    # 4. Start the fabric runtime
    fabric = await db.start(dev_mode=True)

    # Inspect status
    status = fabric.status()
    info = fabric.product_info("dashboard")

    # Graceful shutdown
    await db.stop()

asyncio.run(main())
```

**Production source** (swap MockSource for a real config):

```python
from dataflow.fabric import RestSourceConfig, BearerAuth

db.source("crm", RestSourceConfig(
    url="https://api.example.com",
    auth=BearerAuth(token_env="CRM_API_TOKEN"),
    poll_interval=60,
    endpoints={"deals": "/v2/deals", "contacts": "/v2/contacts"},
))
```

## Source Types

| Type          | Config Class           | Key Parameters                                              | Install Extra |
| ------------- | ---------------------- | ----------------------------------------------------------- | ------------- |
| REST API      | `RestSourceConfig`     | `url`, `auth`, `endpoints`, `webhook`, `timeout`, `headers` | `fabric`      |
| Local File    | `FileSourceConfig`     | `path`, `watch`, `parser` ("json"/"csv"/"yaml"/"xlsx"/auto) | `fabric`      |
| Cloud Storage | `CloudSourceConfig`    | `bucket`, `provider` ("s3"/"gcs"/"azure"), `prefix`         | `cloud`       |
| External DB   | `DatabaseSourceConfig` | `url`, `tables`, `read_only`                                | base          |
| Stream        | `StreamSourceConfig`   | `broker`, `topic`, `group_id`                               | `streaming`   |

All source configs inherit from `BaseSourceConfig` which provides:

- `poll_interval: float = 60.0` -- seconds between change detection polls
- `circuit_breaker: CircuitBreakerConfig` -- failure threshold (default 3), probe interval (30s)
- `staleness: StalenessPolicy` -- max age, on-stale behavior, on-source-error behavior

### Auth Types

| Auth                      | Config Class | Key Parameters                                              |
| ------------------------- | ------------ | ----------------------------------------------------------- |
| Bearer token              | `BearerAuth` | `token_env` (env var name, read per-request)                |
| API key                   | `ApiKeyAuth` | `key_env`, `header` (default `"X-API-Key"`)                 |
| OAuth2 client credentials | `OAuth2Auth` | `client_id_env`, `client_secret_env`, `token_url`, `scopes` |
| HTTP Basic                | `BasicAuth`  | `username_env`, `password_env`                              |

Secrets are **never stored** -- only env var names are kept, values are read per-request.

## Product Modes

| Mode                       | Behavior                                                             | Use When                            |
| -------------------------- | -------------------------------------------------------------------- | ----------------------------------- |
| `"materialized"` (default) | Pre-computed at startup, cached, auto-refreshed on dependency change | Dashboards, aggregations, reports   |
| `"parameterized"`          | On-demand with query parameters, result cached per parameter combo   | Filtered views, search results      |
| `"virtual"`                | No cache, re-computed on every request                               | Real-time data, user-specific views |

### Materialized Product

```python
@db.product("summary", depends_on=["Order", "crm"])
async def summary(ctx):
    orders = await ctx.express.list("Order")
    deals = await ctx.source("crm").fetch("deals")
    return {"total_orders": len(orders), "total_deals": len(deals)}
```

### Parameterized Product

```python
@db.product("user_orders", mode="parameterized", depends_on=["Order"])
async def user_orders(ctx, user_id: str = "", limit: int = 50):
    return await ctx.express.list("Order", {"user_id": user_id}, limit=limit)
```

### Virtual Product

```python
@db.product("live_status", mode="virtual", depends_on=["crm"])
async def live_status(ctx):
    return await ctx.source("crm").fetch("status")
```

### Product-to-Product Dependencies

Products can depend on other products. Use `ctx.product(name)` to read a cached upstream product:

```python
@db.product("enriched", depends_on=["summary", "crm"])
async def enriched(ctx):
    base = ctx.product("summary")  # Reads cached result of "summary"
    extra = await ctx.source("crm").fetch("metadata")
    return {**base, "metadata": extra}
```

### Advanced Product Options

```python
from datetime import timedelta
from dataflow.fabric import StalenessPolicy, RateLimit

@db.product(
    "analytics",
    depends_on=["Order"],
    staleness=StalenessPolicy(max_age=timedelta(minutes=10), on_stale="serve"),
    schedule="*/15 * * * *",           # Cron refresh every 15 min (requires croniter)
    multi_tenant=True,                  # Cache partitioned per tenant
    auth={"roles": ["admin", "analyst"]},
    rate_limit=RateLimit(max_requests=200, max_unique_params=100),
    write_debounce=timedelta(seconds=5),
    cache_miss="async_202",            # Return 202 + Retry-After on cold cache
)
async def analytics(ctx):
    ...
```

`cache_miss` strategies: `"timeout"` (default, wait for computation), `"async_202"` (return HTTP 202 immediately), `"inline"` (compute synchronously).

## FabricContext API

Product functions receive a `FabricContext` (or `PipelineContext` during pipeline execution, which adds read deduplication for snapshot consistency).

| Method / Property   | Returns                                        | Purpose                                                                       |
| ------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------- |
| `ctx.express`       | `DataFlowExpress` (or `PipelineScopedExpress`) | Model CRUD (`list`, `read`, `create`, `update`, `delete`, `count`)            |
| `ctx.source(name)`  | `SourceHandle`                                 | External source access (`fetch`, `read`, `fetch_all`, `fetch_pages`, `write`) |
| `ctx.product(name)` | `Any`                                          | Read cached result of another product                                         |
| `ctx.tenant_id`     | `Optional[str]`                                | Current tenant for multi-tenant products                                      |

### SourceHandle Methods

| Method                 | Signature                                               | Purpose                                             |
| ---------------------- | ------------------------------------------------------- | --------------------------------------------------- |
| `fetch`                | `(path="", params=None) -> Any`                         | Fetch single endpoint (circuit-breaker protected)   |
| `read`                 | `() -> Any`                                             | Alias for `fetch("")`                               |
| `fetch_all`            | `(path="", page_size=100, max_records=100_000) -> List` | Auto-paginate with memory guard                     |
| `fetch_pages`          | `(path="", page_size=100) -> AsyncIterator[List]`       | Stream pages as async iterator                      |
| `write`                | `(path, data) -> Any`                                   | Write data to source                                |
| `last_successful_data` | `(path="") -> Optional[Any]`                            | Last known good data for graceful degradation       |
| `healthy`              | property                                                | Whether source is active and circuit breaker closed |

## `db.start()` Parameters

| Parameter          | Type                 | Default       | Purpose                                                                                    |
| ------------------ | -------------------- | ------------- | ------------------------------------------------------------------------------------------ |
| `fail_fast`        | `bool`               | `True`        | Raise on source connection failure (False: skip unhealthy)                                 |
| `dev_mode`         | `bool`               | `False`       | Skip pre-warming, in-memory cache, reduced poll intervals                                  |
| `nexus`            | `Optional[Nexus]`    | `None`        | Existing Nexus instance to attach endpoints to                                             |
| `coordination`     | `Optional[str]`      | `None`        | `"redis"` or `"postgresql"` (auto-detects if None)                                         |
| `host`             | `str`                | `"127.0.0.1"` | Bind address for internal server (if no nexus)                                             |
| `port`             | `int`                | `8000`        | Port for internal server                                                                   |
| `enable_writes`    | `bool`               | `False`       | Enable write pass-through endpoints (`POST /fabric/{target}/write`)                        |
| `tenant_extractor` | `Optional[Callable]` | `None`        | Lambda to extract tenant_id from request (required if any product has `multi_tenant=True`) |

Returns a `FabricRuntime` instance with `.status()`, `.product_info(name)`, `.source_health(name)`, `.is_leader`.

### Startup Sequence

1. Initialize DataFlow (ensure DB connected)
2. Connect all registered sources (parallel)
3. Elect leader (Redis or PostgreSQL coordination)
4. Pre-warm all materialized products (leader only, skipped in `dev_mode`)
5. Start change detection poll loops (leader only)
6. Register fabric endpoints (all workers)

### Shutdown (`await db.stop()`)

1. Stop accepting webhook deliveries
2. Wait for in-flight pipelines (30s timeout)
3. Cancel all supervised tasks
4. Release leader lock
5. Disconnect sources
6. Flush metrics

## Webhook Configuration

Push-based change detection for sources that support webhooks:

```python
from dataflow.fabric import RestSourceConfig, BearerAuth, WebhookConfig

db.source("github", RestSourceConfig(
    url="https://api.github.com",
    auth=BearerAuth(token_env="GITHUB_TOKEN"),
    webhook=WebhookConfig(
        path="/webhooks/github",
        secret_env="GITHUB_WEBHOOK_SECRET",
        events=("push", "pull_request"),
    ),
))
```

Webhook validation: HMAC-SHA256 signature (`X-Webhook-Signature` header, constant-time comparison), timestamp rejection (>5 minutes stale), nonce deduplication (Redis in production, in-memory in dev mode).

## Testing with MockSource

`MockSource` provides a fully controllable adapter for tests without real connections:

```python
from dataflow.fabric.testing import MockSource

source = MockSource("crm", data={
    "deals": [{"id": 1, "amount": 1000}],
    "contacts": [{"id": 1, "name": "Alice"}],
    "": {"status": "ok"},  # Default path
})

await source.connect()

# Fetch by path
deals = await source.fetch("deals")
assert deals == [{"id": 1, "amount": 1000}]

# Default path
status = await source.fetch()
assert status == {"status": "ok"}

# Simulate source changes
source.trigger_change()
assert await source.detect_change() is True   # One-shot: resets after read
assert await source.detect_change() is False

# Update data at runtime
source.set_data("deals", [{"id": 1, "amount": 2000}])
```

### Testing Product Functions in Isolation

Use `FabricContext.for_testing()` to test product logic without a database or sources:

```python
from dataflow.fabric.context import FabricContext

ctx = FabricContext.for_testing(
    express_data={"Task": [{"id": "1", "status": "open"}, {"id": "2", "status": "done"}]},
    source_data={"crm": {"deals": [{"id": 1}]}},
    products_cache={"upstream": {"count": 42}},
)

# Call your product function directly
result = await build_dashboard(ctx)
assert result["local_tasks_total"] == 2
```

## Observability Endpoints

Auto-generated by the serving layer (all products get endpoints automatically):

| Endpoint                        | Method | Purpose                                              |
| ------------------------------- | ------ | ---------------------------------------------------- |
| `/fabric/{product}`             | GET    | Serve cached product data with fabric headers        |
| `/fabric/_batch?products=a,b,c` | GET    | Batch read multiple products                         |
| `/fabric/{target}/write`        | POST   | Write pass-through (requires `enable_writes=True`)   |
| `/fabric/_health`               | GET    | Overall fabric health (sources, products, pipelines) |
| `/fabric/_trace/{product}`      | GET    | Last 20 pipeline runs for a product                  |

### Fabric Response Headers

Product responses include metadata in HTTP headers (body is clean JSON):

| Header                 | Value                                                   |
| ---------------------- | ------------------------------------------------------- |
| `X-Fabric-Freshness`   | `"fresh"`, `"stale"`, or `"cold"`                       |
| `X-Fabric-Age`         | Cache age in seconds                                    |
| `X-Fabric-Cached-At`   | ISO-8601 timestamp of cache write                       |
| `X-Fabric-Pipeline-Ms` | Pipeline execution duration                             |
| `X-Fabric-Mode`        | Product mode (`materialized`/`parameterized`/`virtual`) |

### Prometheus Metrics

When `prometheus_client` is installed, the following metrics are registered (no-op otherwise):

| Metric                                               | Type      | Labels                 |
| ---------------------------------------------------- | --------- | ---------------------- |
| `fabric_source_health`                               | Gauge     | `source`               |
| `fabric_source_check_duration_seconds`               | Histogram | `source`               |
| `fabric_pipeline_duration_seconds`                   | Histogram | `product`              |
| `fabric_pipeline_runs_total`                         | Counter   | `product`, `status`    |
| `fabric_cache_hit_total` / `fabric_cache_miss_total` | Counter   | `product`              |
| `fabric_product_age_seconds`                         | Gauge     | `product`              |
| `fabric_request_duration_seconds`                    | Histogram | `product`              |
| `fabric_request_total`                               | Counter   | `product`, `freshness` |

## Security

- **SSRF protection**: `RestSourceConfig.url` validated to start with `http://` or `https://`
- **No secrets stored**: Auth configs store env var _names_, values read per-request
- **Webhook HMAC**: Constant-time `hmac.compare_digest()`, never `==`
- **Timestamp rejection**: Webhooks older than 5 minutes are rejected
- **Nonce deduplication**: Prevents webhook replay attacks (Redis in production, bounded in-memory in dev)
- **Filter allowlist**: Query filter operators restricted to `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`
- **Error sanitization**: Health/trace endpoints redact credentials and connection strings from error messages
- **NaN/Inf guard**: Webhook timestamps validated with `math.isfinite()` to prevent numeric bypass

## Optional Extras

| Extra        | Install                                    | Provides                                                                        |
| ------------ | ------------------------------------------ | ------------------------------------------------------------------------------- |
| `fabric`     | `pip install kailash-dataflow[fabric]`     | `httpx`, `watchdog`, `msgpack` (REST adapter, file watcher, fast serialization) |
| `cloud`      | `pip install kailash-dataflow[cloud]`      | `boto3`, `google-cloud-storage` (S3, GCS adapters)                              |
| `excel`      | `pip install kailash-dataflow[excel]`      | `openpyxl` (XLSX file parsing)                                                  |
| `streaming`  | `pip install kailash-dataflow[streaming]`  | `aiokafka`, `websockets` (Kafka, WebSocket adapters)                            |
| `fabric-all` | `pip install kailash-dataflow[fabric-all]` | All of the above combined                                                       |

For scheduled products, also install `croniter`: `pip install croniter`.
For Prometheus metrics: `pip install prometheus_client`.
