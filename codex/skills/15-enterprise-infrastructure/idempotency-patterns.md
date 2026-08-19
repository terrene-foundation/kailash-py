# Idempotency Patterns

You are an expert in Kailash idempotency patterns for exactly-once workflow execution. Guide users through the IdempotentExecutor, the claim-execute-store pattern, atomic claims, release-on-failure, and TTL expiry.

> For full implementation details, see `docs/enterprise-infrastructure/04-idempotency.md` and the source at `kailash/infrastructure/idempotency.py` and `kailash/infrastructure/idempotency_store.py`.

## IdempotentExecutor Overview

The `IdempotentExecutor` wraps any runtime's `execute` method to provide exactly-once semantics. Before executing a workflow, it checks if the idempotency key has already been used. If so, it returns the cached result. If not, it claims the key, executes, and stores the result.

### Setup

```python
from kailash.infrastructure.factory import StoreFactory
from kailash.infrastructure.idempotency import IdempotentExecutor

factory = StoreFactory.get_default()
await factory.initialize()

idem_store = await factory.create_idempotency_store()
# idem_store is None at Level 0 (no database)
# idem_store is DBIdempotencyStore at Level 1+

if idem_store is not None:
    executor = IdempotentExecutor(idem_store, ttl_seconds=3600)
```

### Usage

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {"code": "result = {'total': 42}"})
built = workflow.build()

runtime = LocalRuntime()

# First call: executes the workflow
results, run_id = await executor.execute(
    runtime, built, parameters={},
    idempotency_key="order-12345-payment"
)

# Second call with same key: returns cached result (no re-execution)
results2, run_id2 = await executor.execute(
    runtime, built, parameters={},
    idempotency_key="order-12345-payment"
)
assert results == results2
assert run_id == run_id2

# No key: pass-through (no idempotency)
results3, run_id3 = await executor.execute(
    runtime, built, parameters={},
    idempotency_key=None
)
```

## Claim-Execute-Store Pattern

The IdempotentExecutor follows a strict three-phase protocol:

```
1. CHECK  → Get cached result for key. If found, return it.
2. CLAIM  → Atomically insert placeholder row (INSERT IGNORE + verify)
3. EXECUTE → Run the workflow
4. STORE  → Update the placeholder with actual results
   (on failure: RELEASE the claim so the key can be retried)
```

### Phase 1: Check Cache

```python
# From IdempotentExecutor.execute()
cached = await self._store.get(idempotency_key)
if cached is not None:
    # Cache hit -- return stored result without re-executing
    cached_data = json.loads(cached["response_data"])
    return cached_data.get("results", {}), cached_data.get("run_id", "")
```

### Phase 2: Atomic Claim

The claim uses INSERT IGNORE inside a transaction to prevent TOCTOU races:

```python
# From DBIdempotencyStore.try_claim()
async with self._conn.transaction() as tx:
    # INSERT IGNORE: succeeds only if key doesn't exist
    await tx.execute(sql, key, fingerprint, "{}", 0, "{}", created_at, expires_at)

    # Verify the claim by checking if OUR fingerprint is stored
    row = await tx.fetchone(
        f"SELECT fingerprint FROM {self.TABLE_NAME} WHERE idempotency_key = ?",
        key,
    )

# If row.fingerprint matches ours, we claimed it
if row is not None and row["fingerprint"] == fingerprint:
    return True   # Claim succeeded
return False      # Another worker already claimed this key
```

**Key insight**: The INSERT IGNORE + fingerprint verification in a single transaction eliminates the TOCTOU race that was found during red team validation (C3 in the red team report). No separate SELECT-before-INSERT check.

### Phase 3: Execute and Store

```python
# Execute the workflow
try:
    results, run_id = runtime.execute(workflow, parameters=parameters or {})
except Exception:
    # Release claim on failure -- allows retry with same key
    await self._store.release_claim(idempotency_key)
    raise

# Store the result
result_payload = {"results": results, "run_id": run_id}
await self._store.store_result(
    idempotency_key, result_payload, status_code=200, headers={}
)
```

## Release-on-Failure

If workflow execution fails, the claim is released by deleting the placeholder row. This allows the same idempotency key to be retried:

```python
# From DBIdempotencyStore.release_claim()
await self._conn.execute(
    f"DELETE FROM {self.TABLE_NAME} WHERE idempotency_key = ?", key
)
```

**Why delete instead of update?** A deleted row allows a clean INSERT IGNORE on retry. An updated row with a "failed" status would require additional check logic and could lead to stale claims blocking retries.

## TTL Expiry

Claims get a generous 5-minute TTL to allow processing time. Completed results use a configurable TTL (default: 1 hour).

### Claim TTL

```python
# From DBIdempotencyStore.try_claim()
expires_at = (now + timedelta(minutes=5)).isoformat()
```

### Result TTL

```python
# From DBIdempotencyStore.set()
expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
```

### Cleanup

```python
# Remove expired entries (run periodically)
await idem_store.cleanup()                         # Deletes entries with expires_at < now
await idem_store.cleanup(before="2026-03-17T00:00:00+00:00")  # Explicit cutoff
```

## Concurrent Worker Behavior

When two workers receive the same idempotency key simultaneously:

1. **Worker A** calls `try_claim("key-1", "fp-A")` -- succeeds (INSERT IGNORE wins)
2. **Worker B** calls `try_claim("key-1", "fp-B")` -- fails (row already exists with fp-A)
3. **Worker B** checks cache -- no result yet (Worker A still processing)
4. **Worker B** raises `RuntimeError` with message: "key is claimed by another worker"
5. **Worker A** completes and calls `store_result("key-1", ...)`
6. **Next request** with key-1 hits the cache and returns the stored result

## Table Schema

```sql
CREATE TABLE IF NOT EXISTS kailash_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    response_data TEXT NOT NULL,      -- JSON (empty "{}" during claim)
    status_code INTEGER NOT NULL,     -- 0 during claim, HTTP status after store
    headers TEXT DEFAULT '{}',        -- JSON
    created_at TEXT NOT NULL,         -- ISO-8601 UTC
    expires_at TEXT NOT NULL          -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires
    ON kailash_idempotency (expires_at);
```

## DBIdempotencyStore API Reference

| Method                                                                    | Purpose                                 | Returns      |
| ------------------------------------------------------------------------- | --------------------------------------- | ------------ |
| `initialize()`                                                            | Create table + indices                  | None         |
| `get(key)`                                                                | Lookup non-expired entry                | dict or None |
| `set(key, fingerprint, response_data, status_code, headers, ttl_seconds)` | Store entry (INSERT IGNORE)             | None         |
| `try_claim(key, fingerprint)`                                             | Atomic claim via INSERT IGNORE + verify | bool         |
| `store_result(key, response_data, status_code, headers)`                  | Update claimed entry with result        | None         |
| `release_claim(key)`                                                      | Delete claimed entry (allow retry)      | None         |
| `cleanup(before=None)`                                                    | Delete expired entries                  | None         |
| `close()`                                                                 | No-op (ConnectionManager is shared)     | None         |

## Anti-Patterns

### Never Use Check-Then-Act for Claims

```python
# WRONG: TOCTOU race -- another worker can claim between SELECT and INSERT
existing = await store.get(key)
if existing is None:
    await store.set(key, ...)

# CORRECT: Atomic claim via INSERT IGNORE + fingerprint verification
claimed = await store.try_claim(key, fingerprint)
```

### Never Forget to Release on Failure

```python
# WRONG: Claim is permanent if execution fails -- blocks all retries
claimed = await store.try_claim(key, fingerprint)
results, run_id = runtime.execute(workflow)  # May raise!
await store.store_result(key, ...)

# CORRECT: Release claim in except block
claimed = await store.try_claim(key, fingerprint)
try:
    results, run_id = runtime.execute(workflow)
except Exception:
    await store.release_claim(key)
    raise
await store.store_result(key, ...)
```

### Never Skip TTL on Claims

Claims without TTL can permanently block a key if the worker crashes between claim and store/release. The 5-minute default ensures stale claims expire and can be retried.

## When to Engage

- User asks about "idempotency", "exactly-once", "deduplication"
- User asks about "IdempotentExecutor", "idempotency key", "idempotent execution"
- User needs to prevent duplicate workflow executions
- User asks about "claim-execute-store", "try_claim", "release_claim"
- User asks about concurrent request handling
