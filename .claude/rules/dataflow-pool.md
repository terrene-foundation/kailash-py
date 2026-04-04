---
paths:
  - "**/dataflow/**"
---

# DataFlow Pool Configuration Rules

### 1. Single Source of Truth for Pool Size

Pool size MUST be resolved through `DatabaseConfig.get_pool_size()`. No hardcoded defaults elsewhere.

```python
# ✅
pool_size = config.database.get_pool_size(config.environment)

# ❌ Competing defaults
pool_size = kwargs.get("pool_size", 10)
pool_size = int(os.environ.get("DATAFLOW_POOL_SIZE", "10"))
```

**Why**: Five competing defaults (10, 20, 25, 30, `cpu_count * 4`) caused the pool exhaustion crisis.

### 2. Validate Pool Config at Startup

When connecting to PostgreSQL, `validate_pool_config()` logs whether pool will exhaust `max_connections`. Runs in `DataFlow.__init__` automatically.

### 3. No Deceptive Configuration

Config flags MUST have backing implementation. A flag set to `True` with no consumer is a stub (`zero-tolerance.md` Rule 2).

### 4. Bounded max_overflow

```python
# ✅
max_overflow = max(2, pool_size // 2)

# ❌ Triples connection footprint
max_overflow = pool_size * 2
```

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

**Why**: Five independent runtimes per DataFlow instance consumed 28-64 connections each.

## MUST NOT

- No new pool size defaults — consolidate with existing parameters before adding
