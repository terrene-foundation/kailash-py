# Idempotency Reference

Kailash provides two layers of idempotency to ensure exactly-once execution semantics:

1. **HTTP deduplication** -- `RequestDeduplicator` operates at the API gateway layer, deduplicating incoming HTTP requests by fingerprint or idempotency key.
2. **Execution-level idempotency** -- `IdempotentExecutor` wraps any runtime to cache workflow execution results by idempotency key.

Both layers require Level 1+ (a configured `KAILASH_DATABASE_URL`) for persistent deduplication. At Level 0, idempotency is not available.

## Layer 1: HTTP Request Deduplication

The `RequestDeduplicator` (in `kailash.middleware.gateway.deduplicator`) provides request-level deduplication at the API gateway:

- **Request fingerprinting**: SHA-256 of method + path + query + body
- **Idempotency key support**: Clients send `Idempotency-Key` header; the deduplicator validates that the same key always maps to the same request
- **LRU in-memory cache**: 1-hour TTL, 10,000 max entries by default

This layer catches duplicate HTTP requests before they reach the workflow engine.

## Layer 2: IdempotentExecutor

The `IdempotentExecutor` wraps any runtime's `execute()` method with persistent, database-backed idempotency. This is the primary mechanism for exactly-once workflow execution.

### How It Works

```
Client sends request with idempotency_key
           │
           ▼
   ┌──────────────────┐
   │ Check cache (GET) │
   └────────┬─────────┘
            │
      ┌─────┴─────┐
      │ Hit?       │
      │            │
     Yes          No
      │            │
      ▼            ▼
   Return      ┌──────────┐
   cached      │ Claim key │
   result      └─────┬────┘
                     │
               ┌─────┴─────┐
               │ Claimed?   │
               │            │
              Yes          No
               │            │
               ▼            ▼
          ┌──────────┐   Another worker
          │ Execute  │   owns this key
          │ workflow │   (wait or error)
          └─────┬────┘
                │
          ┌─────┴─────┐
          │            │
        Success     Failure
          │            │
          ▼            ▼
     Store result  Release claim
     (cached for   (key can be
      TTL period)   retried)
```

### The Claim-Execute-Store Pattern

1. **Check cache**: Look up the idempotency key in the `DBIdempotencyStore`. If found and not expired, return the cached result immediately.
2. **Claim the key**: Atomically insert a placeholder row with `status_code=0`. If the insert succeeds (no existing row), the key is claimed. If it fails, another worker already owns this key.
3. **Execute the workflow**: Run the workflow via the wrapped runtime.
4. **Store the result**: Update the placeholder row with the actual response data. The result is now cached for the TTL period.
5. **On failure**: Delete the placeholder row (`release_claim`), allowing a future request with the same key to retry.

### Usage

```python
import asyncio
from kailash import WorkflowBuilder, LocalRuntime
from kailash.infrastructure import StoreFactory, IdempotentExecutor

async def main():
    # Create the idempotency store (requires Level 1+)
    factory = StoreFactory(database_url="postgresql://user:pass@localhost:5432/kailash")
    idempotency_store = await factory.create_idempotency_store()

    # Wrap the runtime with idempotency
    executor = IdempotentExecutor(idempotency_store, ttl_seconds=3600)

    # Build a workflow
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "process", {
        "code": "output = data.upper()",
        "inputs": {"data": "str"},
        "output_type": "str",
    })
    wf = builder.build()

    runtime = LocalRuntime()

    # First call: executes the workflow, caches the result
    results, run_id = await executor.execute(
        runtime, wf,
        parameters={"process": {"data": "hello"}},
        idempotency_key="request-abc-123",
    )
    print(results)  # {"process": {"output": "HELLO"}}

    # Second call with same key: returns cached result, no re-execution
    results2, run_id2 = await executor.execute(
        runtime, wf,
        parameters={"process": {"data": "hello"}},
        idempotency_key="request-abc-123",
    )
    print(results2)  # {"process": {"output": "HELLO"}} -- same result, from cache

    await factory.close()

asyncio.run(main())
```

### Pass-Through Mode

If `idempotency_key` is `None`, the executor passes through to the runtime directly with no deduplication:

```python
# No idempotency key -- direct execution, no caching
results, run_id = await executor.execute(runtime, wf, parameters=params)
```

### TTL Configuration

The `ttl_seconds` parameter controls how long cached results are stored:

```python
# Cache results for 24 hours
executor = IdempotentExecutor(idempotency_store, ttl_seconds=86400)

# Cache results for 5 minutes (short-lived operations)
executor = IdempotentExecutor(idempotency_store, ttl_seconds=300)
```

After the TTL expires, the idempotency key becomes available for reuse. Expired entries are cleaned up by calling:

```python
await idempotency_store.cleanup()
```

### Failure Recovery

If the workflow execution raises an exception, the claim is **released** so the key can be retried:

```python
try:
    results, run_id = await executor.execute(
        runtime, wf,
        parameters=params,
        idempotency_key="request-xyz",
    )
except Exception as e:
    # The claim was released -- a retry with the same key will re-execute
    print(f"Execution failed: {e}")
```

This ensures that transient failures (network timeouts, temporary database issues) do not permanently consume an idempotency key.

### Concurrent Requests

When two workers receive the same idempotency key simultaneously:

1. Worker A claims the key (succeeds).
2. Worker B attempts to claim (fails -- key exists).
3. Worker B checks if a result is already available:
   - If yes (Worker A finished fast): returns the cached result.
   - If no (Worker A still processing): raises `RuntimeError` indicating the key is claimed by another worker.

The calling code should handle this case with a retry-after-delay pattern:

```python
import asyncio

async def execute_with_retry(executor, runtime, wf, params, key, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await executor.execute(
                runtime, wf, parameters=params, idempotency_key=key,
            )
        except RuntimeError as e:
            if "claimed by another worker" in str(e) and attempt < max_retries - 1:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            raise
```

## IdempotencyStore Direct Access

For advanced use cases, the `DBIdempotencyStore` can be used directly:

```python
from kailash.infrastructure import StoreFactory

factory = StoreFactory()
store = await factory.create_idempotency_store()

# Manual claim-store cycle
claimed = await store.try_claim("my-key", fingerprint="abc")
if claimed:
    try:
        result = do_work()
        await store.store_result("my-key", result, status_code=200, headers={})
    except Exception:
        await store.release_claim("my-key")
        raise

# Set an entry directly with TTL
await store.set(
    key="cached-key",
    fingerprint="def",
    response_data={"value": 42},
    status_code=200,
    headers={"Content-Type": "application/json"},
    ttl_seconds=3600,
)

# Get an entry (returns None if expired)
entry = await store.get("cached-key")

# Cleanup expired entries
await store.cleanup()
```
