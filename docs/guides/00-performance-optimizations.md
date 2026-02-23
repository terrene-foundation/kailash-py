# Phase 0 Performance Optimizations

Hot-path optimizations for workflow execution in LocalRuntime and AsyncLocalRuntime.
These changes reduce per-node overhead without changing any public API.

## What Changed

### Phase 0a: Quick Wins

**P0A-001 Module-level imports** — `DataTypeValidator` and resource manager error classes
(`CPULimitExceededError`, `ConnectionLimitExceededError`, `MemoryLimitExceededError`) are
imported once at module level in `local.py`, eliminating repeated `import` calls inside
per-node execution loops.

**P0A-002 Shared MetricsCollector** — A single `MetricsCollector()` instance is created once
per `_execute_workflow_async()` call and reused for all nodes in that execution. Previously
each node created its own collector.

**P0A-003 psutil opt-in** — Resource limit checks (`check_all_limits()`) are now gated behind
`enable_resource_limits=False` (default). The `psutil` syscalls only run when explicitly opted in:

```python
with LocalRuntime(enable_resource_limits=True) as runtime:
    results, run_id = runtime.execute(workflow.build())
```

**P0A-005 Cached node IDs** — `frozenset(workflow.graph.nodes())` is computed once before the
execution loop and passed to `_prepare_node_inputs()` via the `_node_ids` parameter, avoiding
repeated set construction per node.

### Phase 0b: Deduplication

**P0B-001 Remove VP#1** — `DataTypeValidator.validate_node_input()` was a near-noop (copies dict,
logs one warning) that ran before every `node.execute()` call. Removed from both the main execution
loop and `_execute_single_node()`. `Node.execute()` still performs authoritative validation via VP#3
(`validate_inputs`).

**P0B-004 Cache topological sort** — `Workflow.get_execution_order()` caches its result in
`_topo_cache`. Cache is invalidated when `add_node()` or `connect()` mutate the graph. Repeated
executions of the same workflow skip the `nx.topological_sort()` call entirely.

**P0B-005 Cache cycle edge classification** — `Workflow.separate_dag_and_cycle_edges()` caches
its result in `_dag_cycle_cache` with the same invalidation strategy as P0B-004.

### Phase 0c: networkx Hot-Path Removal

**P0C-001/002 Cached topo sort in runtimes** — All `nx.topological_sort(workflow.graph)` calls
in `local.py` (main execution, switch evaluation, fallback path) replaced with
`workflow.get_execution_order()` which returns the cached result.

**P0C-003 AsyncLocalRuntime** — Same replacement in `async_local.py`.

**P0C-004 Pure-Python BFS ancestors** — `nx.ancestors(workflow.graph, switch_id)` replaced with
an iterative BFS using `workflow.graph.predecessors()`. Avoids networkx function call overhead
for ancestor traversal.

**P0C-005 Removed imports** — `import networkx as nx` removed from `local.py` and `async_local.py`
since no `nx.*` calls remain in those files.

### Phase 0d: Deep Profiling Fixes

**P0D-001 MetricsCollector thread elimination** — `MetricsCollector` now accepts
`enable_resource_monitoring` parameter. When `enable_resource_limits=False` (default),
the collector skips psutil thread creation/join entirely. Previously, every `collector.collect()`
call spawned a background thread and blocked on `thread.join(timeout=1.0)`, adding ~2.2ms/node.
After: ~1.5us/node (1,467x faster).

**P0D-002 Cached allowed_types** — `sanitize_input()` in `security.py` previously performed
13+ lazy imports (pandas, numpy, torch, tensorflow, scipy, sklearn, xgboost, lightgbm,
matplotlib, plotly, statsmodels, PIL, spacy, networkx, prophet) on every call. Now uses
`_get_cached_allowed_types()` which computes the type list once at module level and returns
a copy on subsequent calls. Eliminates ~1.6ms/node from import machinery lookups.

**P0D-003 Immutable topo cache** — `Workflow._topo_cache` now stores a `tuple` instead of
a `list`. Prevents callers from accidentally corrupting the cache by mutating the returned
sequence. The `get_execution_order()` return type was updated to `tuple[str, ...] | list[str]`.

**P0D-004 Hoisted trust verification** — `_verify_node_trust` and `_get_effective_trust_context`
were called per-node even when trust verification is DISABLED (default). Now a `_trust_enabled`
flag and `_trust_context` are computed once before the execution loop. When DISABLED, the
entire per-node trust block is skipped.

**P0D-005 Lazy psutil import** — `import psutil` moved from module-level in `local.py` to
a lazy import inside `get_health_diagnostics()`. psutil is only used in this cold-path
diagnostic method, so the module-level import was unnecessary.

**P0D-006 Logging format optimization** — Hot-path log statements in `_execute_workflow_async`
changed from f-strings to `%s` lazy formatting. When the log level is above INFO, Python
skips string formatting entirely with `%s` style but always formats f-strings.

**P0D-007 Deferred monitoring storage** — `enable_monitoring=True` (default) previously created
a `TaskManager` with `FileSystemStorage` that performed 5 disk writes per node (create_task,
update_status(RUNNING), update_status(COMPLETED), update_metrics, save_run). This caused
**~132ms/node overhead** — a 3200x slowdown vs monitoring OFF. Now uses `DeferredStorageBackend`,
a pure in-memory storage backend during execution. All tracking data stays in memory with zero
I/O. `flush_to_filesystem()` persists CARE audit data after execution completes.
After: monitoring adds ~35us/node in-loop overhead (1.35x vs monitoring OFF).

**P0D-007b Batch file CARE persistence** — `flush_to_filesystem()` writes a single
`batch/{run_id}.json` file per run containing all CARE audit data (run metadata + all tasks
with metrics). This avoids the bloated `tasks/` directory (1M+ entries) where even
`mkdir(exist_ok=True)` took ~8ms due to directory entry scanning. Also skips the 4MB+
`index.json` read/write (a lookup optimization, not a CARE requirement). Total flush cost:
~0.5ms for a 20-node workflow (1 mkdir + 1 file write).

### Phase 0e: SQLite CARE Storage Backend

**P0E-001 SQLiteStorage rewrite** — `DatabaseStorage` was rewritten as an optimized
`SQLiteStorage` class (`src/kailash/tracking/storage/database.py`) with:

- WAL mode + `synchronous=NORMAL` + `busy_timeout=5000` for concurrent access
- Metrics inlined into the `tasks` table (eliminated the separate `metrics` table and JOIN)
- `audit_events` table for `RuntimeAuditGenerator` EATP event persistence
- CHECK constraints on status columns for data integrity
- `executemany()` batch insert via `save_tasks_batch()` for O(1) transactions
- Schema version table for future migrations
- Thread-safety via `Lock` + `check_same_thread=False`
- Context manager support and explicit `close()` method

**P0E-002 DeferredStorageBackend SQLite flush** — Added `flush_to_sqlite()` to
`DeferredStorageBackend` (`src/kailash/tracking/storage/deferred.py`). After execution,
all in-memory task tracking data is written to SQLite in a single ACID transaction using
`executemany()`. The audit event accumulation method `add_audit_events()` allows
`RuntimeAuditGenerator` EATP events to be included atomically in the same flush. The
`flush_to_filesystem()` JSON path is kept for backward compatibility but deprecated.

**P0E-003 LocalRuntime SQLite wiring** — All four `flush_to_filesystem()` call sites in
`local.py` (happy path + 3 error paths) replaced with `_flush_deferred_storage_sqlite()`,
a helper that:

1. Collects `RuntimeAuditGenerator` events via `add_audit_events()` before flushing
2. Calls `flush_to_sqlite()` (preferred ACID path)
3. Falls back to `flush_to_filesystem()` if `flush_to_sqlite()` is unavailable
4. Suppresses flush errors on error paths (log_warning=False) to avoid masking the
   original exception

## What Did NOT Change

- **Public API**: No changes to `runtime.execute()`, `WorkflowBuilder`, or any node interface.
- **networkx dependency**: Still used in `graph.py` (core DAG operations), `cyclic_runner.py`,
  `conditional_execution.py`, `visualization.py`, and `hierarchical_switch_executor.py`.
- **VP#3 validation**: `Node.execute()` still calls `validate_inputs()` — this is the
  authoritative validation point and was intentionally preserved.
- **Build-time operations**: `workflow.build()` performance was not optimized (already fast enough).

## Benchmark Results

Framework overhead measured with `tests/benchmarks/bench_framework_overhead.py` using
PythonCodeNode with minimal code (`result = {'v': 1}`), `enable_monitoring=False`,
`enable_resource_limits=False`.

### Per-Node Framework Overhead (with monitoring disabled)

| Nodes | Total/Node | Exec/Node | FW/Node | FW % |
| ----- | ---------- | --------- | ------- | ---- |
| 1     | 164us      | 99us      | 66us    | 40%  |
| 5     | 140us      | 98us      | 43us    | 30%  |
| 10    | 138us      | 93us      | 45us    | 32%  |
| 20    | 137us      | 94us      | 43us    | 31%  |
| 50    | 139us      | 98us      | 41us    | 30%  |
| 100   | 152us      | 100us     | 52us    | 34%  |

### Component Breakdown

| Component                       | Per-Node | Notes                    |
| ------------------------------- | -------- | ------------------------ |
| Input preparation               | ~4.0us   | `_prepare_node_inputs()` |
| Output storage                  | ~0.07us  | Dict assignment          |
| Content-aware success detection | ~0.10us  | Check for 'success' key  |
| Trust verification (disabled)   | ~0.36us  | Short-circuit check      |
| MetricsCollector (psutil off)   | ~1.5us   | P0D-001: no thread spawn |
| MetricsCollector (psutil on)    | ~71us    | Thread spawn + join      |
| Workflow validate (amortized)   | ~1.4us   | One-time per execution   |
| Conditional check (amortized)   | ~1.7us   | One-time per execution   |

### Cache Performance

| Cache                   | Uncached | Cached | Speedup |
| ----------------------- | -------- | ------ | ------- |
| Topological sort (20n)  | 38.9us   | 52.5ns | 742x    |
| Topological sort (100n) | 280.6us  | 43.1ns | 6504x   |
| DAG/cycle edges (20n)   | 2.8us    | 47.2ns | 60x     |
| DAG/cycle edges (100n)  | 12.4us   | 46.7ns | 265x    |

### Monitoring Overhead (CARE Persistence)

| Nodes | MON ON | MON OFF | Ratio | Overhead |
| ----- | ------ | ------- | ----- | -------- |
| 5     | 1.3ms  | 0.8ms   | 1.61x | 0.5ms    |
| 10    | 2.4ms  | 1.7ms   | 1.45x | 0.8ms    |
| 20    | 4.4ms  | 3.2ms   | 1.35x | 1.1ms    |
| 50    | 10.6ms | 7.9ms   | 1.34x | 2.7ms    |

Monitoring ON = in-memory tracking (~35us/node) + single batch file write at end.
Previously ~132ms/node (3200x slowdown). Now ~34% overhead.

### SQLite Flush Performance (P0E)

Post-execution flush comparison (benchmark J in `bench_framework_overhead.py`):

| Tasks | SQLite flush | File flush | Ratio | SQLite/task |
| ----- | ------------ | ---------- | ----- | ----------- |
| 5     | ~1.5ms       | ~0.4ms     | ~3.5x | ~300us      |
| 10    | ~1.7ms       | ~0.5ms     | ~3.4x | ~170us      |
| 20    | ~2.0ms       | ~0.6ms     | ~3.3x | ~100us      |
| 50    | ~2.8ms       | ~0.9ms     | ~3.1x | ~56us       |

SQLite flush includes: WAL journal open, schema version check, `executemany()` batch insert
in single ACID transaction, WAL checkpoint. First-open overhead dominates for small task
counts; per-task marginal cost is ~10-20us. Both paths are post-execution only (zero I/O
in the hot path). The additional ~1-2ms for SQLite provides ACID crash recovery and
queryable audit storage vs flat JSON batch files.

### Build Time

| Nodes | Total  | Per-Node |
| ----- | ------ | -------- |
| 10    | 244us  | 24.4us   |
| 50    | 1.27ms | 25.3us   |
| 100   | 2.73ms | 27.3us   |

## Regression Tests

113+ regression tests guard these optimizations against reversion:

- `tests/unit/runtime/test_phase0a_optimizations.py` (17 tests)
- `tests/unit/runtime/test_phase0b_optimizations.py` (22 tests)
- `tests/unit/runtime/test_phase0c_optimizations.py` (14 tests)
- `tests/unit/runtime/test_phase0d_optimizations.py` (34 tests)
- `tests/unit/runtime/test_phase0e_optimizations.py` (26 tests)

Tests verify both source-level invariants (e.g., "no `nx.topological_sort` in execution method")
and functional correctness (e.g., "multi-node workflow executes correctly with caching").

Phase 0e tests additionally verify ACID data integrity, WAL concurrent access, batch insert
performance, audit event persistence, schema migrations, and context manager cleanup.

## Performance Configuration

```python
# Default: optimized for speed (resource checks disabled)
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(workflow.build())

# Opt-in: enable psutil resource limit checks
with LocalRuntime(enable_resource_limits=True) as runtime:
    results, run_id = runtime.execute(workflow.build())

# Maximum performance: disable both resource limits and monitoring
with LocalRuntime(enable_resource_limits=False, enable_monitoring=False) as runtime:
    results, run_id = runtime.execute(workflow.build())
```

## networkx Analysis

networkx cannot be fully removed from the SDK. It is used in:

- **`graph.py`**: `nx.DiGraph` as core data structure (nodes, edges, predecessors, successors,
  in_edges, topological_sort, simple_cycles). Replacing would require a custom graph class.
- **`cyclic_runner.py`**: Cycle detection and cycle group computation.
- **`conditional_execution.py`**: Ancestor/descendant traversal for branch skipping.
- **`visualization/`**: Graph layout and rendering.
- **`hierarchical_switch_executor.py`**: Switch-case dependency analysis.

networkx has been **removed from the hot path** (local.py, async_local.py) via Phase 0c.
The remaining usages are cold-path (build, visualization, configuration) where networkx
performance is acceptable. Full removal would require ~2000 lines of custom graph code
with significant correctness risk for marginal performance gain on non-hot paths.
