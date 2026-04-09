# Runtime Safety Defaults ("Pit of Success")

APIs where the default behavior is safe and the developer has to opt-in to dangerous operations. The safe path is the shortest path.

## Principles

1. **Safe by default, dangerous by opt-in** — the zero-argument version of any method does the safe thing
2. **Dangerous operations are visually distinct** — the function name, flag name, or type name makes code review trivial
3. **Progressive disclosure** — simple operations stay simple; complexity is opt-in, not mandatory

## Patterns

### 1. Input Validation at API Boundaries

**Status in kailash-py**: ABSENT at express.\* level. Calls accept `Any` and propagate junk 5 layers deep before failing.

**Status in kailash-rs**: PARTIAL. Core types validate; bindings do not.

**The problem**: `db.express.create("User", {"nme": "Alice"})` — typo in field name — succeeds silently. The misspelled field is discarded by DataFlow, the row is created with `name=NULL`, and the caller sees a 200 response. The bug surfaces days later when a report shows blank names.

**The fix**: Validate field names against the model schema at the express layer before delegating.

```python
# DO — validate at the boundary
async def create(self, model_name: str, data: dict) -> ModelResult:
    schema = self._get_schema(model_name)
    unknown_fields = set(data.keys()) - schema.field_names
    if unknown_fields:
        raise FieldValidationError(
            f"Unknown fields for {model_name}: {unknown_fields}. "
            f"Valid fields: {schema.field_names}"
        )
    return await self._engine.create(model_name, data)

# DO NOT — pass through silently
async def create(self, model_name: str, data: dict) -> ModelResult:
    return await self._engine.create(model_name, data)
    # typos in field names are silently discarded
```

**Industry precedent**: Django ORM raises `FieldError` on unknown field names. SQLAlchemy raises `InvalidRequestError`. Stripe returns a 400 with "unknown parameter: nme."

**Scope**: All `express.*` methods (create, update, read, list, delete), Nexus handler input parsing, Kaizen agent.run() input validation.

### 2. `unsafe_raw()` as the Sole Raw SQL Escape Hatch

**Status**: ABSENT in both SDKs. Raw SQL is available through multiple entry points with no naming convention.

**The problem**: Raw SQL bypasses DataFlow's access controls, audit logging, tenant isolation, and dialect portability. A security audit must grep the entire codebase for string interpolation near database calls — an O(codebase) operation.

**The fix**: A single, grep-able entry point.

```python
# DO — one entry point, grep-able name
result = await db.unsafe_raw(
    "SELECT * FROM users WHERE legacy_column LIKE %s",
    params=["%pattern%"],
    reason="legacy migration — tracked in #456",
)
# rg "unsafe_raw" src/  ← finds every raw SQL site in 1 command

# DO NOT — multiple entry points
result = await db.execute("SELECT ...")        # raw SQL via execute
result = await db.session.execute(text("...")) # raw SQL via session
result = await conn.fetch("SELECT ...")        # raw SQL via connection
# Security audit must check execute, session.execute, fetch, run, etc.
```

```rust
// Rust equivalent
let rows = db.unsafe_raw(
    "SELECT * FROM users WHERE legacy = $1",
    &[&pattern],
    UnsafeReason::LegacyMigration { issue: 456 },
).await?;
```

**Industry precedent**: Django's `raw()` is the sole raw SQL entry point — visually distinct from `objects.filter()`. Go's `database/sql` separates `Query()` (parameterized) from `Exec()` (raw). Rails has `find_by_sql()` — name signals "you're leaving the ORM."

**The key**: The word "unsafe" in the function name is the primitive. It makes raw SQL:

- Grep-able in security audits
- Visually distinct in code review
- Intentional (requires a `reason` parameter documenting why)

### 3. Pool Exhaustion Circuit Breaker

**Status**: ABSENT in both SDKs. Connection pools silently queue when exhausted.

**The problem**: Under load, connection pool fills up. New requests silently queue. Response times degrade from 200ms to 30s. No log, no metric, no error — just a slow death. The first signal is users complaining.

**The fix**: Structured warnings at thresholds, typed error at capacity.

```python
# DO — warn early, fail loud
class PoolConfig:
    max_connections: int = 20
    warn_threshold: float = 0.8          # emit WARN at 80%
    queue_timeout: float = 5.0           # seconds before PoolExhaustedError

# When pool hits 80%:
# logger.warning("pool.high_utilization", used=16, max=20, pct=0.80)

# When pool hits 100% + timeout:
# raise PoolExhaustedError(
#     "Connection pool exhausted: 20/20 in use, waited 5.0s. "
#     "Consider increasing pool_size or optimizing query duration."
# )

# DO NOT — silent queue
pool = create_pool(max_connections=20)
# At 100%: silently waits indefinitely. No log. No error.
# User sees: "the app is slow" with zero diagnostic signal.
```

```rust
// Rust equivalent
#[derive(thiserror::Error, Debug)]
#[error("connection pool exhausted: {used}/{max} in use, waited {waited:?}")]
pub struct PoolExhaustedError {
    pub used: u32,
    pub max: u32,
    pub waited: Duration,
}
```

**Industry precedent**: HikariCP (Java) WARNs at configurable threshold and rejects with `SQLTransientConnectionException` at capacity. pgBouncer logs pool state at INFO level every 60 seconds. Envoy hard-rejects at `max_connections` with a 503.

**Scope**: DataFlow connection pool, Kaizen LLM client pool, Nexus request handler pool.

### 4. UNSET Sentinels for Optional Parameters

**Status in kailash-py**: SPARSE (18 files). Most APIs use `None` to mean both "not provided" and "clear the value."

**The problem**: `db.express.update("User", id, {"tenant_id": None})` — does this mean "clear the tenant" or "don't change the tenant"? The answer depends on which DataFlow adapter is in use. Silent behavior difference.

**The fix**: Module-level sentinel distinguishes the two cases.

```python
# DO — unambiguous
_UNSET = object()

async def update(self, model: str, id: str, data: dict, tenant_id=_UNSET):
    if tenant_id is _UNSET:
        pass  # don't touch tenant_id
    elif tenant_id is None:
        data["tenant_id"] = None  # explicitly clear
    else:
        data["tenant_id"] = tenant_id  # set to value

# DO NOT — ambiguous None
async def update(self, model: str, id: str, data: dict, tenant_id=None):
    if tenant_id is not None:
        data["tenant_id"] = tenant_id
    # None means... don't change? Clear? Depends on the adapter.
```

**Industry precedent**: attrs uses `NOTHING` sentinel. pydantic uses `PydanticUndefined`. dataclasses uses `MISSING`. All for the same reason: `None` is a valid value, not a valid default.

**Scope**: All optional parameters where `None` is a valid user-supplied value: `tenant_id`, `timeout`, `retry_count`, `cache_ttl`.

### 5. Mandatory Context Managers for Resources

**Status**: PARTIAL in both SDKs. Context managers exist but raw access is also available.

**The problem**: `conn = await db.get_connection()` — if the function returns early or raises before `conn.close()`, the connection leaks. Multiply by 1000 requests and the pool is exhausted.

**The fix**: Hide raw access behind private APIs. The public API only offers context-managed access.

```python
# DO — only context-managed access is public
class DataFlow:
    async def connection(self) -> AsyncContextManager[Connection]:
        """Acquire a connection. Released automatically on exit."""
        conn = await self._pool.acquire()
        try:
            yield conn
        finally:
            await self._pool.release(conn)

    async def transaction(self) -> AsyncContextManager[Transaction]:
        """Start a transaction. Rolled back on exception, committed on success."""
        async with self.connection() as conn:
            txn = await conn.begin()
            try:
                yield txn
                await txn.commit()
            except:
                await txn.rollback()
                raise

# Usage — leak-proof
async with db.transaction() as txn:
    await txn.execute(...)
# Connection and transaction cleaned up in ALL code paths

# DO NOT — raw connection access
conn = await db.get_connection()  # public method, no context manager
await conn.execute(...)
# If exception here → connection leaked
await conn.close()  # developer must remember this
```

```rust
// Rust RAII equivalent — Drop handles cleanup
pub struct ConnectionGuard {
    conn: Connection,
    pool: Arc<Pool>,
}

impl Drop for ConnectionGuard {
    fn drop(&mut self) {
        self.pool.release(&mut self.conn);
    }
}
// Cannot leak — Drop runs in ALL code paths (return, panic, scope exit)
```

**Industry precedent**: Go's `database/sql` encourages `defer rows.Close()` but doesn't enforce it — resource leaks are Go's #1 database bug class. Python's SQLAlchemy 2.0 made `Session` a context manager by default. Rust's ownership model makes this automatic.

## Priority Ranking

| Rank | Pattern                            | SDK    | Effort     | Safety impact                              |
| ---- | ---------------------------------- | ------ | ---------- | ------------------------------------------ |
| 1    | Input validation at API boundaries | py, rs | 2 sessions | Prevents silent data corruption from typos |
| 2    | `unsafe_raw()` escape hatch        | py, rs | 1 session  | Makes security audits O(1 grep)            |
| 3    | Pool exhaustion circuit breaker    | py, rs | 1 session  | Prevents silent degradation under load     |
| 4    | UNSET sentinels                    | py     | 1 session  | Eliminates None ambiguity                  |
| 5    | Mandatory context managers         | py, rs | 2 sessions | Eliminates resource leaks                  |
