# AsyncPythonCodeNode Patterns

Full parity with PythonCodeNode since v0.9.30. Choose based on async needs — features are identical.

## Multi-Output (v0.9.30+)

All variables in code are automatically exported. Connect each output individually.

```python
workflow.add_node("AsyncPythonCodeNode", "async_processor", {
    "code": """
import asyncio

async def process_data(items):
    await asyncio.sleep(0.1)
    return [item * 2 for item in items]

data = [1, 2, 3, 4, 5]
processed_data = await process_data(data)
item_count = len(processed_data)
total_value = sum(processed_data)
average_value = total_value / item_count
    """
})

workflow.add_connection("async_processor", "processed_data", "next_node", "data")
workflow.add_connection("async_processor", "item_count", "next_node", "count")
workflow.add_connection("async_processor", "total_value", "next_node", "total")
```

**Legacy single-result pattern** still works — assign to `result`, access nested values with dot notation:

```python
workflow.add_connection("legacy", "result.data", "next", "input_data")
```

## Concurrent Processing

### asyncio.gather — Parallel Execution

```python
workflow.add_node("AsyncPythonCodeNode", "parallel_fetch", {
    "code": """
import asyncio

async def fetch_item(id):
    await asyncio.sleep(0.1)
    return {"id": id, "value": id * 10}

tasks = [fetch_item(id) for id in [1, 2, 3, 4, 5]]
results = await asyncio.gather(*tasks)
fetched_items = results
success_count = len([r for r in results if r is not None])
    """
})
```

### Semaphore — Concurrency Limiting

```python
workflow.add_node("AsyncPythonCodeNode", "controlled_concurrency", {
    "code": """
import asyncio

semaphore = asyncio.Semaphore(5)  # Max 5 concurrent

async def limited_fetch(id):
    async with semaphore:
        await asyncio.sleep(0.1)
        return {"id": id, "data": f"result_{id}"}

tasks = [limited_fetch(id) for id in range(100)]
results = await asyncio.gather(*tasks)
processed_count = len(results)
    """
})
```

### Error-Resilient Gather

Wrap each task in try/except so one failure does not cancel the batch:

```python
workflow.add_node("AsyncPythonCodeNode", "error_resilient", {
    "code": """
import asyncio

async def safe_fetch(id):
    try:
        await asyncio.sleep(0.1)
        if id % 3 == 0:
            raise ValueError(f"Invalid ID: {id}")
        return {"id": id, "status": "success"}
    except Exception as e:
        return {"id": id, "status": "error", "error": str(e)}

results = await asyncio.gather(*[safe_fetch(id) for id in range(10)])
successful_items = [r for r in results if r["status"] == "success"]
failed_items = [r for r in results if r["status"] == "error"]
    """
})
```

## Async I/O Patterns

### HTTP — aiohttp

```python
workflow.add_node("AsyncPythonCodeNode", "http_client", {
    "code": """
import aiohttp, asyncio

async def fetch_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

urls = ["https://api.example.com/users", "https://api.example.com/orders"]
api_responses = await asyncio.gather(*[fetch_url(u) for u in urls])
users_data = api_responses[0]
orders_data = api_responses[1]
    """
})
```

### Database — asyncpg

```python
workflow.add_node("AsyncPythonCodeNode", "db_query", {
    "code": """
import asyncpg, asyncio

conn = await asyncpg.connect(database_url)
try:
    users, orders, stats = await asyncio.gather(
        conn.fetch("SELECT * FROM users WHERE active = true"),
        conn.fetch("SELECT * FROM orders WHERE status = 'pending'"),
        conn.fetchrow("SELECT COUNT(*) as count FROM products")
    )
    active_users = [dict(u) for u in users]
    pending_orders = [dict(o) for o in orders]
    product_count = stats['count']
finally:
    await conn.close()
    """
})
```

### Files — aiofiles

```python
workflow.add_node("AsyncPythonCodeNode", "file_processor", {
    "code": """
import aiofiles, asyncio

async def read_file(fp):
    async with aiofiles.open(fp, mode='r') as f:
        return await f.read()

file_paths = ["/data/file1.txt", "/data/file2.txt", "/data/file3.txt"]
file_contents = await asyncio.gather(*[read_file(fp) for fp in file_paths])
combined_content = "\\n".join(file_contents)

async with aiofiles.open("/output/combined.txt", mode='w') as f:
    await f.write(combined_content)

files_read = len(file_contents)
total_chars = sum(len(c) for c in file_contents)
    """
})
```

## DataFlow Integration

Use multi-output to export variables from async nodes, then connect to DataFlow UpdateNode/QueryNode via `add_connection`. Pattern is identical to the multi-output example above — export `filter_data`, `verification_status`, etc. and wire each to the DataFlow node's input ports.

## Exception Handling (v0.9.29+)

All standard exceptions available: `NameError`, `AttributeError`, `ZeroDivisionError`, `StopIteration`, `AssertionError`, `ImportError`, `IOError`, `ArithmeticError`.

```python
workflow.add_node("AsyncPythonCodeNode", "error_handler", {
    "code": """
try:
    result = undefined_variable
except NameError as e:
    error_message = f"Variable not found: {e}"
    error_type = "NameError"
except AttributeError as e:
    error_message = f"Attribute error: {e}"
    error_type = "AttributeError"

error_occurred = 'error_message' in locals()
    """
})
```

## Template Resolution (v0.9.30+)

`${param}` syntax works in nested dicts/lists, resolving input variables at runtime:

```python
workflow.add_node("AsyncPythonCodeNode", "templated", {
    "code": """
filter_config = {
    "id": user_id,  # resolved from upstream
    "metadata": {"source": source_system, "timestamp": timestamp}
}
query_result = await query_data(filter_config)
matched_count = query_result["matched"]
    """
})
```

## When to Use

| Use AsyncPythonCodeNode                     | Use PythonCodeNode                     |
| ------------------------------------------- | -------------------------------------- |
| Database queries (asyncpg, aiomysql, motor) | CPU-bound (DataFrame, numpy, stats)    |
| HTTP requests (aiohttp, httpx)              | Synchronous/blocking I/O               |
| File I/O (aiofiles)                         | Simple logic, conditionals, transforms |
| WebSocket, Redis, message queues            | Data transformations, mappings         |
| Multiple concurrent operations              | Single-threaded calculations           |

## Common Pitfall: Blocking the Event Loop

Never use blocking calls inside AsyncPythonCodeNode. `time.sleep(5)` blocks the event loop — use `await asyncio.sleep(5)`. Same applies to sync HTTP and sync file I/O; always use async equivalents (aiohttp, aiofiles).

## Related Skills

- [pythoncode-best-practices](pythoncode-best-practices.md), [async-workflow-patterns](async-workflow-patterns.md), [runtime-execution](runtime-execution.md)
