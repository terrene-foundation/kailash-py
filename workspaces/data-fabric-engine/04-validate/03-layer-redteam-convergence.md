# Layer Mapping Red Team — Convergence

6 findings from layer stack review. All resolved.

## F1 (MAJOR): Layer 10 → Layer 2 skip (no connection manager for sources)

**Finding**: Database adapters get connection lifecycle via Layer 4 (ConnectionManager). Source adapters bypass this — FabricRuntime manages them directly.

**Resolution**: This is intentional and correct. Database connections need pooling (expensive, shared, limited). Source connections do NOT need pooling in the same way:

- REST: httpx.AsyncClient manages its own connection pool internally
- File: no connection — just a file handle
- Cloud: boto3/gcs clients manage their own connections
- Stream: single persistent connection per source

Creating a `SourceConnectionManager` at Layer 4 would be an empty abstraction. Document the skip explicitly: "Source adapters manage their own connection lifecycle because non-database connections do not share the same pooling constraints as database connections."

## F2 (Significant): Products not nodes — composability cost

**Finding**: Products cannot participate in WorkflowBuilder graphs, losing composability.

**Resolution**: Add `ProductInvokeNode` — a thin node wrapper around any product.

```python
# Auto-generated alongside product registration
class DashboardProductNode(Node):
    """Workflow node that invokes the 'dashboard' product and returns cached data."""

    async def execute(self, **params) -> Dict:
        return await self._fabric.get_cached_product("dashboard")
```

This node is generated at `@db.product()` time and registered in NodeRegistry. It reads from cache (not re-executing the product function). This gives composability: a workflow can read a product's cached result as a step.

## F3 (Confirmed clean): BaseAdapter has no SQL leakage

No action needed. `execute_query()` is on `DatabaseAdapter`, not `BaseAdapter`.

## F4 (CRITICAL): Pipeline snapshot inconsistency

**Finding**: Two Express calls within a product function can see different database states if a concurrent write happens between them.

**Resolution**: Product functions execute within a pipeline-scoped read context that deduplicates and snapshots Express queries.

```python
class PipelineContext(FabricContext):
    """FabricContext with pipeline-scoped read cache."""

    def __init__(self, express, sources, ...):
        self._read_cache: Dict[str, Any] = {}  # query signature → result

    @property
    def express(self) -> PipelineScopedExpress:
        """Express wrapper that caches reads within this pipeline run."""
        return PipelineScopedExpress(self._express, self._read_cache)

class PipelineScopedExpress:
    """Wraps DataFlowExpress. Caches reads within a single pipeline execution."""

    async def list(self, model, filter=None, **kwargs):
        key = f"list:{model}:{json.dumps(filter, sort_keys=True)}"
        if key not in self._read_cache:
            self._read_cache[key] = await self._express.list(model, filter=filter, **kwargs)
        return self._read_cache[key]
```

This ensures: if a product calls `ctx.express.list("User")` twice, the second call returns the same result. Queries are deduplicated within a pipeline run, not across runs.

## F5 (MAJOR): Background pipelines compete for DB pool

**Finding**: Pipeline tasks use the same connection pool as request-response. Under load, pipeline refreshes starve user requests.

**Resolution**: Reserve pool capacity for pipelines via `pipeline_pool_fraction`.

```python
# Pool sizing accounts for pipeline connections
total_pool = DatabaseConfig.get_pool_size(environment)
request_pool = int(total_pool * 0.8)   # 80% for user requests
pipeline_pool = int(total_pool * 0.2)  # 20% reserved for pipeline tasks

# PipelineExecutor uses a separate semaphore that limits DB-hitting pipelines
# to pipeline_pool concurrent connections
self._db_semaphore = asyncio.Semaphore(pipeline_pool)
```

The existing pool is shared (no partition at the adapter level), but the pipeline executor limits its own concurrency to stay within its budget. This is the same pattern as DataFlow's `LightweightPool` — a soft partition via application-level semaphore.

## F6 (MAJOR): Event bus gap — bulk_update/bulk_upsert don't exist in Express

**Finding**: Express has no `bulk_update` or `bulk_upsert` methods. Events for these operations never fire.

**Resolution**: Accept the gap for now. Document it explicitly.

- `bulk_update` and `bulk_upsert` exist as workflow nodes (Layer 5) but not as Express methods (Layer 7)
- Fabric change detection via event bus covers: `create`, `update`, `delete`, `upsert`, `bulk_create`, `bulk_delete` (6 of 8)
- For `bulk_update`/`bulk_upsert` via workflows, the fabric relies on poll-based change detection (`MAX(updated_at)`) as fallback — these changes will be detected on the next poll cycle, not instantly
- If Express gains `bulk_update`/`bulk_upsert` in the future, the event bus subscription already covers them (the subscription pattern matches any `model.*` event)
