# DataFlow Pool Configuration Rules

## Scope

These rules apply when editing `packages/kailash-dataflow/**` files.

## MUST Rules

### 1. Single Source of Truth for Pool Size

Pool size MUST be resolved through exactly one code path: `DatabaseConfig.get_pool_size()`.

No hardcoded pool size defaults outside this method. Any code that needs a pool size MUST call the config object's method. If the config object does not have a value, that is a config bug — not a reason to invent a local default.

**Why**: Five competing defaults (10, 20, 25, 30, `cpu_count * 4`) caused the pool exhaustion crisis. Every new default creates convention drift.

**How to apply**: Before adding `pool_size=N` anywhere, check if `get_pool_size()` is being called. If not, wire it up rather than hardcoding.

### 2. No Hardcoded Numeric Pool Defaults

MUST NOT add `pool_size=N` as a default in constructors, env var fallbacks, or adapter base classes. All defaults flow through `get_pool_size()`.

```python
# DO:
pool_size = config.database.get_pool_size(config.environment)

# DO NOT:
pool_size = kwargs.get("pool_size", 10)  # Competing default!
pool_size = int(os.environ.get("DATAFLOW_POOL_SIZE", "10"))  # Ghost code!
```

### 3. Validate Pool Config at Startup

When connecting to PostgreSQL, MUST call `validate_pool_config()` to log whether the configured pool will exhaust `max_connections`. This runs in `DataFlow.__init__` automatically.

### 4. No Deceptive Configuration

Config fields that suggest a feature exists MUST have a backing implementation. A config flag set to `True` by default with no consumer is functionally a stub and violates `no-stubs.md` Rule 4.

**Why**: `MonitoringConfig.alert_on_connection_exhaustion=True` with no backing code led users to believe they had exhaustion protection when they didn't.

### 5. Bounded max_overflow

MUST NOT compute `max_overflow = pool_size * 2`. This triples the connection footprint. Use `max(2, pool_size // 2)` instead.

```python
# DO:
max_overflow = max(2, pool_size // 2)

# DO NOT:
max_overflow = pool_size * 2  # Triples connection footprint!
```

### 6. No Orphan Runtimes

DataFlow subsystem classes MUST accept an optional `runtime` parameter. If provided, call `runtime.acquire()` and store. If `None`, create own runtime. All classes MUST implement `close()` that calls `self.runtime.release()`.

```python
# DO:
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
            self.runtime = None

# DO NOT:
class SubsystemClass:
    def __init__(self, ...):
        self.runtime = LocalRuntime()  # Orphan — no close(), no sharing
```

**Why**: Five independent runtimes per DataFlow instance caused the connection pool exhaustion crisis of #71. Each runtime opens 7-16 connections; without sharing, a single `DataFlow(auto_migrate=True)` consumed 28-64 connections.

**Enforced by**: `validate-workflow.js` emits WARNING on unmanaged `LocalRuntime()` or `AsyncLocalRuntime()` construction.

## MUST NOT Rules

### 1. No New Pool Size Defaults

When adding a new config parameter, search for existing parameters with similar names or purposes. Consolidate before adding. The pool default drift incident (five competing defaults) is the canonical example of what happens when this rule is violated.

## Cross-References

- `01-analysis/01-codebase-defects.md` — DEFECT-A (five competing defaults)
- `01-analysis/04-cross-sdk-alignment.md` — kailash-rs uses same auto-scaling formula
- `dataflow/core/pool_utils.py` — probe and worker detection
- `dataflow/core/pool_validator.py` — startup validation
- `dataflow/core/pool_monitor.py` — utilization monitor + leak detection
