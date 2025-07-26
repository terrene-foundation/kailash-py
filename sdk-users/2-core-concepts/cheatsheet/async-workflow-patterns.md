# AsyncWorkflowBuilder Cheatsheet

## Basic Async Workflow (200 tokens)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.workflow import AsyncWorkflowBuilder

workflow = (
    AsyncWorkflowBuilder("my_async_workflow")
    .add_async_code("fetch", "result = {'data': await fetch_data()}")
    .add_async_code("process", "result = await process(input_data)")
    .add_connection("fetch", "data", "process", "input_data")
    .build()
)
```

## Parallel Processing (250 tokens)
```python
workflow = (
    AsyncWorkflowBuilder("parallel_processor")
    .add_parallel_map(
        "process_items",
        """
async def process_item(item):
    await asyncio.sleep(0.1)
    return item * 2
""",
        max_workers=10,
        batch_size=50
    )
    .build()
)
```

## Resource Management (300 tokens)
```python
workflow = (
    AsyncWorkflowBuilder("data_pipeline")
    .with_database("db", host="localhost", database="mydb")
    .with_http_client("api", base_url="https://api.example.com")
    .with_cache("cache", backend="redis")
    .add_async_code(
        "fetch_and_cache",
        """
db = await get_resource("db")
api = await get_resource("api")
cache = await get_resource("cache")

data = await db.fetch("SELECT * FROM users")
enriched = await api.get("/enrich", params={"ids": [d['id'] for d in data]})
await cache.setex("users", 300, json.dumps(enriched))
result = {"users": enriched}
"""
    )
    .build()
)
```

## Retry Pattern (200 tokens)
```python
from kailash.workflow import AsyncPatterns

AsyncPatterns.retry_with_backoff(
    builder,
    "api_call",
    """
response = await http.get("/flaky-endpoint")
result = await response.json()
""",
    max_retries=5,
    initial_backoff=1.0
)
```

## Rate Limiting (200 tokens)
```python
AsyncPatterns.rate_limited(
    builder,
    "bulk_api",
    """
results = []
for item in items:
    response = await http.post("/api", json=item)
    results.append(await response.json())
result = {"processed": results}
""",
    requests_per_second=10
)
```

## Circuit Breaker (250 tokens)
```python
AsyncPatterns.circuit_breaker(
    builder,
    "external_service",
    """
response = await unreliable_api.get("/data")
if response.status != 200:
    raise Exception(f"API error: {response.status}")
result = await response.json()
""",
    failure_threshold=5,
    reset_timeout=60
)
```

## Cache-Aside Pattern (300 tokens)
```python
AsyncPatterns.cache_aside(
    builder,
    "cache_check",
    "db_fetch",
    "cache_store",
    """
# Database fetch operation
db = await get_resource("db")
data = await db.fetchrow("SELECT * FROM expensive_query WHERE id = $1", item_id)
result = dict(data) if data else None
""",
    cache_resource="redis",
    cache_key_template="query:{item_id}",
    ttl_seconds=300
)
```

## Timeout with Fallback (250 tokens)
```python
AsyncPatterns.timeout_with_fallback(
    builder,
    "primary",
    "fallback",
    """
# Primary operation (might be slow)
result = await slow_external_service()
""",
    """
# Fallback operation (fast)
result = {"data": "cached_default", "fallback": True}
""",
    timeout_seconds=5.0
)
```

## Complete Example (400 tokens)
```python
from kailash.workflow import AsyncWorkflowBuilder, AsyncPatterns
from kailash.runtime.async_local import AsyncLocalRuntime

# Build complete async workflow
workflow = (
    AsyncWorkflowBuilder("production_pipeline")
    .with_database("db", host="localhost")
    .with_http_client("api")
    .with_cache("redis")

    # Fetch with connection pool
    .add_async_code("fetch", """
db = await get_resource("db")
async with db.acquire() as conn:
    data = await conn.fetch("SELECT * FROM items WHERE status = 'pending'")
result = {"items": [dict(row) for row in data]}
""")

    # Process in parallel with rate limiting
    .add_parallel_map("process", """
async def process_item(item):
    api = await get_resource("api")
    response = await api.post("/process", json=item)
    return await response.json()
""", max_workers=20)

    # Store results
    .add_async_code("store", """
db = await get_resource("db")
cache = await get_resource("redis")

# Batch insert
async with db.acquire() as conn:
    await conn.executemany(
        "INSERT INTO results (id, data) VALUES ($1, $2)",
        [(r['id'], json.dumps(r)) for r in results]
    )

# Cache summary
await cache.setex("latest_results", 3600, json.dumps({
    "count": len(results),
    "timestamp": time.time()
}))

result = {"stored": len(results)}
""")

    .add_connection("fetch", "items", "process", "items")
    .add_connection("process", "results", "store", "results")
    .build()
)

# Execute
runtime = AsyncLocalRuntime()
result = await runtime.execute_workflow_async(workflow, {})
```
