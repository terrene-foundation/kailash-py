---
priority: 10
scope: path-scoped
paths:
  - "**/dataflow/**"
---

# DataFlow Pool Configuration Rules


<!-- slot:neutral-body -->

> **Scope**: Application code MUST go through DataFlow's high-level API (`@db.model`, `db.express`) — see `framework-first.md` § Work-Domain Binding. The patterns here are for tuning the DataFlow connection pool itself, not for bypassing it.

### 1. Single Source of Truth for Pool Size

Pool size MUST be resolved through `DatabaseConfig.get_pool_size()`. No hardcoded defaults elsewhere.

```python
# ✅
pool_size = config.database.get_pool_size(config.environment)

# ❌ Competing defaults
pool_size = kwargs.get("pool_size", 10)
pool_size = int(os.environ.get("DATAFLOW_POOL_SIZE", "10"))
```

**Why:** Five competing defaults (10, 20, 25, 30, `cpu_count * 4`) caused the pool exhaustion crisis.

### 2. Validate Pool Config AND Reachability at Startup

When connecting to PostgreSQL, `validate_pool_config()` logs whether the pool will exhaust `max_connections`, AND a lightweight `SELECT 1` health check verifies the connection actually reaches the database. Both run in `DataFlow.__init__` automatically. A failed health check MUST log ERROR and prevent application startup, NOT silently degrade.

```python
# DO — fail-fast startup
df = DataFlow(os.environ["DATABASE_URL"])  # raises on unreachable DB, logs ERROR

# DO NOT — defer the check until first request
df = DataFlow(os.environ["DATABASE_URL"], lazy_connect=True)  # silent until first query
# ↑ first user request becomes the health check; production breaks for users, not for ops
```

**Why:** Without startup validation, pool exhaustion surfaces hours later under production load — too late for a config fix, early enough for an outage. Without reachability validation, a wrong connection string or expired credentials lets the application "start" successfully and then fail on the first real request, turning a config error into a user-facing outage. Pool math AND connection reachability MUST both be checked before the application accepts traffic.

### 3. No Deceptive Configuration

Config flags MUST have backing implementation. A flag set to `True` with no consumer is a stub (`zero-tolerance.md` Rule 2).

**Why:** A flag that appears configurable but does nothing misleads operators into thinking a feature is active when it isn't.

**Extended enforcement (DataFlow 2.0 Phase 5.11):** every attribute on the DataFlow / adapter / connection manager whose name ends in `_url`, `_backend`, `_client`, `_executor`, `_store`, or `_policy` MUST have at least one production call site that reads it. Set-but-never-read is the same failure mode as a deceptive flag — the orphan attribute implies a feature the framework never actually delivers.

```python
# DO — url is stored AND read
class RedisFabricCacheBackend:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url            # stored
        self._client = redis.asyncio.from_url(redis_url)  # read at init

    async def get(self, key):
        return await self._client.get(key)     # read on every operation

# DO NOT — url stored, never consumed
class PipelineExecutor:
    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url            # stored
        self._cache = {}                        # actually uses in-memory dict
    # Nothing ever reads self._redis_url; operators think they're using Redis
```

**Why:** The orphan-attribute pattern is the exact bug Phase 5.2 fixed in `PipelineExecutor` — `redis_url` was stored and logged at init but the executor used an in-memory dict internally. Operators believed the cache was Redis-backed for weeks. The fix requires every `_url` / `_backend` / `_client` to have a grep-able consumer.

**Audit protocol:** run `rg 'self\._(url|backend|client|executor|store|policy)\w*\s*=' .` and for each match, verify there's at least one `self._<attr>.` read in the same class OR a downstream passthrough to another class that consumes it.

### 4. Bounded max_overflow

```python
# ✅
max_overflow = max(2, pool_size // 2)

# ❌ Triples connection footprint
max_overflow = pool_size * 2
```

**Why:** Unbounded overflow silently triples the connection footprint and exhausts PostgreSQL `max_connections` under load.

### 5. No Orphan Runtimes

Subsystem classes MUST accept optional `runtime` parameter. If provided, `runtime.acquire()`. If None, create own. All MUST implement `close()` calling `runtime.release()`.

```python
# ✅
class SubsystemClass:
    def __init__(self, ..., runtime=None):
        if runtime is not None:
            self.runtime = runtime.acquire()
            self._owns_runtime = False
        else:
            self.runtime = LocalRuntime()
            self._owns_runtime = True

    def close(self):
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.release()

# ❌ Orphan — no close(), no sharing
class SubsystemClass:
    def __init__(self):
        self.runtime = LocalRuntime()
```

**Why:** Orphan runtimes leak connections on every subsystem instantiation — five independent runtimes per DataFlow instance consumed 28-64 connections each, exhausting the pool.

## MUST NOT

- No new pool size defaults — consolidate with existing parameters before adding

**Why:** Every additional default becomes another competing source of truth, recreating the exact pool exhaustion crisis these rules prevent.

<!-- /slot:neutral-body -->
