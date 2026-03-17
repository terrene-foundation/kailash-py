# Architecture Decisions: Production Readiness

**Date**: 2026-03-17
**Source**: `03-requirements-breakdown.md`, source code analysis
**Prepared by**: requirements-analyst

---

## ADR-PR-001: Saga Coordinator Wiring to Node Registry

### Status

Proposed

### Context

The `SagaCoordinatorNode` (in `src/kailash/nodes/transaction/saga_coordinator.py`) manages distributed transactions via the saga pattern. Each saga step references a `node_id` (a string identifying a node type in the registry) and `parameters` (a dict of inputs). Currently, `_execute_step()` at line 364 returns a hardcoded success result, and `_compensate()` at line 431 sets `step.state = "compensated"` without executing anything.

The saga coordinator needs to actually execute the referenced nodes. The question is **how** it should resolve and invoke them.

Three approaches were considered:

1. **Direct call via NodeRegistry** -- Saga coordinator imports `NodeRegistry`, calls `NodeRegistry.get(step.node_id)`, instantiates the node class, and calls `async_run()`.
2. **Message passing via event bus** -- Saga coordinator publishes a `StepExecuteRequest` message, a separate executor subscribes and runs the node, publishes `StepExecuteResult`.
3. **Event-driven via the EventStore** -- Saga coordinator appends a `STEP_EXECUTE_REQUESTED` event, a reactor processes the event and appends `STEP_EXECUTE_COMPLETED`.

### Decision

**Option 1: Direct call via NodeRegistry.**

The saga coordinator will directly resolve nodes through `NodeRegistry.get()` and execute them inline via `async_run()`.

Implementation pattern:

```python
async def _execute_step(self, step: SagaStep, inputs: Dict[str, Any]) -> Dict[str, Any]:
    step.state = "running"
    step.start_time = time.time()

    self._log_event("step_started", {"step_id": step.step_id, "node_id": step.node_id})

    try:
        # Resolve node from registry
        node_class = NodeRegistry.get(step.node_id)
        node_instance = node_class(**step.parameters)

        # Merge saga context with step parameters for execution
        execution_inputs = {**self.saga_context, **step.parameters}

        # Execute with timeout
        if hasattr(node_instance, 'async_run'):
            result = await asyncio.wait_for(
                node_instance.async_run(**execution_inputs),
                timeout=self.timeout
            )
        else:
            result = node_instance.run(**execution_inputs)

        # Normalize result to expected format
        if not isinstance(result, dict):
            result = {"status": "success", "data": result}
        elif "status" not in result:
            result["status"] = "success"

        step.state = "completed"
        step.result = result
        step.end_time = time.time()

        self._log_event("step_completed", {
            "step_id": step.step_id,
            "duration": step.end_time - step.start_time,
        })
        return result

    except Exception as e:
        step.state = "failed"
        step.error = str(e)
        step.end_time = time.time()
        self._log_event("step_failed", {"step_id": step.step_id, "error": str(e)})
        raise
```

### Consequences

#### Positive

- **Simplest implementation**: Uses existing `NodeRegistry` infrastructure with zero new components.
- **Debuggable**: Stack traces show the full call chain from saga coordinator through node execution.
- **Testable**: Unit tests can register mock nodes in the registry and verify execution.
- **No new dependencies**: No message broker, no event bus infrastructure needed.
- **Consistent with existing patterns**: The `LocalRuntime` already resolves nodes via the registry in the same way.
- **Performance**: Zero overhead beyond the node execution itself. No serialization/deserialization of messages.

#### Negative

- **In-process only**: Saga steps execute in the same process as the coordinator. Cannot distribute steps across workers without future modification.
- **Tight coupling to NodeRegistry**: The saga coordinator has a direct import dependency on the registry. However, this is the same coupling the entire runtime has, so it is not introducing a new architectural concern.
- **No retry isolation**: If a node execution hangs, it blocks the saga coordinator's async task. Mitigated by `asyncio.wait_for` timeout.

### Alternatives Considered

#### Option 2: Message Passing via Event Bus

- **Description**: Saga coordinator publishes `StepExecuteRequest` to an in-process or Redis-backed message bus. A `StepExecutor` service subscribes, resolves the node, executes it, and publishes `StepExecuteResult`.
- **Pros**: Decouples coordinator from execution; enables future multi-worker distribution; natural retry semantics.
- **Cons**: Requires building or integrating a message bus; adds latency (serialization, bus routing); significantly more complex for zero immediate benefit; over-engineering for the current single-process architecture.
- **Why rejected**: The SDK is currently single-process. Adding message bus infrastructure for in-process communication creates unnecessary complexity. When S9 (multi-worker) is implemented, the saga coordinator can be adapted to use task queues, but that should happen at S9 time, not now.

#### Option 3: Event-Driven via EventStore

- **Description**: Saga coordinator appends `STEP_EXECUTE_REQUESTED` event to EventStore. A reactor reads events and executes nodes. Results flow back as `STEP_EXECUTE_COMPLETED` events.
- **Pros**: Full audit trail of execution requests; event sourcing alignment; decouples execution timing.
- **Cons**: EventStore is currently in-memory with no persistent backend (that is gap S1); adds significant latency due to polling; complex to implement correctly (ordering, exactly-once processing); the EventStore is designed for audit/replay, not command routing.
- **Why rejected**: Conflates event sourcing (recording what happened) with command routing (making things happen). The EventStore is the wrong abstraction for this. The saga coordinator already records events via `_log_event()` for audit purposes.

### Implementation Notes

1. **Fail-fast validation**: Add node_id validation in `_add_step()` so users learn about missing nodes at step definition time, not execution time.
2. **Timeout**: Use `asyncio.wait_for(node.async_run(...), timeout=step_timeout or self.timeout)`.
3. **Result normalization**: Nodes may return various dict structures. Normalize to `{"status": "success|error", "data": ...}` pattern.
4. **Compensation**: Same pattern applies -- `NodeRegistry.get(step.compensation_node_id)` with the original step result passed as input.

---

## ADR-PR-002: Distributed Circuit Breaker State -- Redis as Optional Extension

### Status

Proposed

### Context

The `ConnectionCircuitBreaker` (in `src/kailash/core/resilience/circuit_breaker.py`) maintains state entirely in-process using Python objects (`CircuitState`, `CircuitBreakerMetrics`, a `deque` rolling window). The `CircuitBreakerManager` manages multiple named breakers.

In a multi-worker deployment (multiple uvicorn workers, multiple Docker containers, Kubernetes pods), each worker has its own independent circuit breaker state. This means:

- Worker A may have an OPEN breaker while Worker B's breaker is CLOSED
- Error rate calculations are per-worker, missing the system-wide picture
- A failing downstream service may get hammered by workers whose individual breakers haven't tripped

The question is whether distributed state should be part of the core SDK or an optional extension.

### Decision

**Distributed circuit breaker state via Redis will be an optional extension, not part of core.**

The architecture will be:

1. **Core SDK** (`src/kailash/core/resilience/circuit_breaker.py`): Remains unchanged. In-process circuit breaker state for single-process deployments. This is the default.

2. **Optional extension** (`src/kailash/core/resilience/distributed_circuit_breaker.py`): New module that wraps `ConnectionCircuitBreaker` with Redis-backed state sharing. Activated via configuration:

```python
# Single-process (default, no Redis needed):
manager = CircuitBreakerManager()

# Multi-worker (requires Redis):
from kailash.core.resilience.distributed_circuit_breaker import DistributedCircuitBreakerManager
manager = DistributedCircuitBreakerManager(redis_url="redis://localhost:6379")
```

3. **State sharing protocol**: Last-write-wins with TTL-based expiration. Not strongly consistent -- eventual consistency is acceptable for circuit breakers because:
   - A few extra requests leaking through during state propagation is tolerable
   - The alternative (distributed locking) adds latency to every request
   - Circuit breakers are a heuristic, not a transaction boundary

4. **Redis unavailability fallback**: If Redis is unreachable, fall back to local-only state with a warning log. The circuit breaker continues to function per-worker. This preserves the fail-open principle for the circuit breaker infrastructure itself (circuit breaker infra failure should not break the application).

### Consequences

#### Positive

- **No new hard dependencies in core**: Users who do not need multi-worker circuit breakers never need Redis. The core SDK stays lightweight.
- **Clear upgrade path**: Single-process users get correct behavior with zero configuration. Multi-worker users opt in to Redis by switching manager class.
- **Resilient to Redis failure**: Local-only fallback means Redis issues do not cascade to application failures.
- **Existing API preserved**: `CircuitBreakerManager` API remains identical. `DistributedCircuitBreakerManager` is a drop-in replacement with the same methods.

#### Negative

- **Two code paths**: Local and distributed circuit breakers may diverge over time if not carefully maintained.
- **Eventual consistency**: Workers may briefly disagree on circuit state. This is acceptable but should be documented.
- **Redis dependency for multi-worker**: Users who want distributed state must run Redis. This is a common requirement and not burdensome.

### Alternatives Considered

#### Option A: Distributed State in Core (Always-on Redis)

- **Description**: Make `CircuitBreakerManager` always use Redis. Configure via `KAILASH_REDIS_URL` environment variable.
- **Pros**: Single code path; all users get correct multi-worker behavior.
- **Cons**: Forces Redis dependency on all users, including single-process CLI tools, testing, and local development. Adds 10-50ms latency to every circuit breaker check (Redis round-trip). Violates the Kailash principle that core SDK has minimal dependencies.
- **Why rejected**: Most SDK users run single-process (local development, CLI tools, small deployments). Forcing Redis on all users for a feature only needed at scale is the wrong trade-off.

#### Option B: File-Based Shared State

- **Description**: Use a shared filesystem (NFS, shared volume) with file-based state. Similar to trust-plane file locking.
- **Pros**: No Redis dependency; works with shared volumes.
- **Cons**: File locking across NFS is unreliable; higher latency than Redis; not suitable for Kubernetes ephemeral volumes; trust-plane file locking works within a single host, not across hosts.
- **Why rejected**: File-based distributed state is fragile across hosts. Redis is the standard answer for this problem.

#### Option C: Database-Backed State (SQLite/PostgreSQL)

- **Description**: Store circuit breaker state in the tracking database (SQLite or PostgreSQL).
- **Pros**: Reuses existing database infrastructure.
- **Cons**: SQLite cannot be shared across processes (WAL mode allows concurrent readers but writers must be on same host); PostgreSQL adds a heavier dependency than Redis; database round-trip is slower than Redis for this access pattern (frequent reads, moderate writes).
- **Why rejected**: Circuit breaker state is hot data (checked on every request). Redis is purpose-built for this access pattern.

### Implementation Notes

1. **Redis state key**: `kailash:cb:{breaker_name}` containing JSON with `{state, failure_count, success_count, last_state_change, error_rate}`.
2. **TTL**: Set Redis TTL to `2 * recovery_timeout` so stale state expires.
3. **Publish/Subscribe**: Optionally use Redis pub/sub for state change notifications (optimization, not required for correctness).
4. **Dependency**: Add `redis` to `kailash[distributed]` optional dependency group.

---

## ADR-PR-003: OpenTelemetry Integration -- Independent in Core with Shared Configuration

### Status

Proposed

### Context

OpenTelemetry tracing exists in Kaizen (`packages/kailash-kaizen/src/kaizen/core/autonomy/observability/tracing_manager.py`) but not in the core SDK (`src/kailash/`). The core runtime executes workflows and nodes but produces no distributed traces. Users running Kaizen agents get agent-level tracing, but the workflow execution underneath is a black box.

The question is how OTel should be integrated into the core SDK:

1. **Bridge from Kaizen**: Import Kaizen's `TracingManager` and use it from core.
2. **Independent in core**: Build a new `WorkflowTracingManager` in core that follows the same patterns.
3. **Shared library**: Extract tracing into a shared package that both core and Kaizen consume.

### Decision

**Option 2: Independent implementation in core with shared configuration conventions.**

The core SDK will have its own `WorkflowTracingManager` in `src/kailash/monitoring/tracing.py` that:

1. Is self-contained -- no import from Kaizen
2. Follows the same OTel patterns as Kaizen's `TracingManager` (OTLP exporter, BatchSpanProcessor)
3. Uses the same configuration environment variables so both systems export to the same collector
4. Creates spans that are linkable to Kaizen agent spans via shared trace context

```python
# src/kailash/monitoring/tracing.py

# Conditional import -- OTel is optional
_OTEL_AVAILABLE = False
try:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import set_span_in_context, Status, StatusCode
    _OTEL_AVAILABLE = True
except ImportError:
    pass


class WorkflowTracingManager:
    """OpenTelemetry tracing for workflow execution.

    Creates spans for:
    - Workflow execution (root span)
    - Individual node execution (child spans)
    - Error events (exception recording)

    Gracefully degrades to no-op when opentelemetry is not installed.
    Install with: pip install kailash[tracing]
    """

    def __init__(
        self,
        service_name: str = "kailash-workflow",
        otlp_endpoint: str | None = None,
        enabled: bool = True,
    ):
        self.enabled = enabled and _OTEL_AVAILABLE
        if not self.enabled:
            return

        endpoint = otlp_endpoint or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"
        )
        # ... TracerProvider setup identical to Kaizen patterns ...
```

**Shared configuration conventions** (not code sharing):

| Environment Variable          | Used By       | Purpose                |
| ----------------------------- | ------------- | ---------------------- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Core + Kaizen | Collector endpoint     |
| `OTEL_SERVICE_NAME`           | Core + Kaizen | Service identification |
| `KAILASH_TRACING_ENABLED`     | Core + Kaizen | Enable/disable         |

**Span hierarchy when both are active**:

```
Kaizen Agent Span (from TracingManager)
  |
  +-- Workflow Execution Span (from WorkflowTracingManager)
        |
        +-- Node: CSVReader (child span)
        +-- Node: DataProcessor (child span)
        +-- Node: OutputWriter (child span)
```

This hierarchy is achieved by propagating the OTel context from Kaizen's agent span into the workflow execution. When a Kaizen agent triggers a workflow, the agent's current span becomes the parent of the workflow span. When the core SDK runs standalone (no Kaizen), the workflow span is the root.

### Consequences

#### Positive

- **No circular dependency**: Core SDK does not import from Kaizen. Kaizen depends on core, not the other way around.
- **Independent lifecycle**: Core tracing can be versioned, tested, and released independently.
- **Works without Kaizen**: Users of core SDK get tracing without installing Kaizen.
- **Graceful degradation**: `_OTEL_AVAILABLE = False` path means zero runtime cost when OTel is not installed.
- **Unified view**: Both systems export to the same collector, producing connected traces.

#### Negative

- **Pattern duplication**: TracerProvider setup code is duplicated between core and Kaizen. This is acceptable because:
  1. The setup code is <30 lines
  2. The two managers serve different abstraction levels (workflows vs agents)
  3. They may diverge as requirements differ

- **Configuration coupling**: Both systems must agree on environment variable names. This is a feature, not a bug -- it ensures unified configuration.

### Alternatives Considered

#### Option 1: Bridge from Kaizen

- **Description**: Core SDK imports `kaizen.core.autonomy.observability.tracing_manager.TracingManager` and uses it for workflow tracing.
- **Pros**: Single tracing implementation; no code duplication.
- **Cons**: Creates circular dependency (core depends on Kaizen, Kaizen depends on core). Forces core SDK users to install Kaizen even if they do not use agents. Violates the architecture principle that core is the foundation layer.
- **Why rejected**: Core cannot depend on Kaizen. This would invert the dependency hierarchy.

#### Option 3: Shared Library (kailash-tracing package)

- **Description**: Extract OTel integration into `packages/kailash-tracing/` that both core and Kaizen import.
- **Pros**: Single source of truth for tracing setup; both packages get updates simultaneously.
- **Cons**: Adds a new package to the ecosystem for <100 lines of code; increases release coordination complexity; the two use cases (workflow tracing vs agent tracing) will diverge in span attributes, naming, and hierarchy.
- **Why rejected**: The OTel setup code is small and the two tracing use cases differ enough that sharing creates more coupling than it saves. If the codebase grows to >500 lines of shared tracing logic, revisit this decision.

### Implementation Notes

1. **Optional dependency**: Add `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc` to `[tracing]` extras in `pyproject.toml`.
2. **No-op pattern**: When OTel is not installed, all methods return immediately without error. Use `if not self.enabled: return` guards.
3. **Context propagation**: When `LocalRuntime.execute()` is called from a Kaizen agent, the current OTel context is automatically propagated (OTel SDK handles this via thread-local context).
4. **Instrumentation point**: Hook into `LocalRuntime.execute()` at the top level, and into the per-node execution loop. Do not modify individual node code.

---

## ADR-PR-004: EventStore Persistent Backend -- SQLite with Pluggable Interface

### Status

Proposed

### Context

The `EventStore` (in `src/kailash/middleware/gateway/event_store.py`) has a `storage_backend` parameter that is `Optional[Any]` defaulting to `None`. When `None`, events live only in the `_event_stream` list (in-memory). The storage backend protocol requires two methods:

- `append(key: str, events: List[dict])` -- append events for a key
- `get(key: str) -> List[dict]` -- retrieve events for a key

The tracking system (`src/kailash/tracking/storage/database.py`) already has a production-grade SQLite implementation with:

- WAL mode for concurrent access
- Optimized pragmas (64MB cache, memory temp store)
- Schema versioning
- Proper indexes
- Thread safety via `threading.Lock`

The question is: what persistent backend should the EventStore ship with, and should it be pluggable?

### Decision

**Ship a SQLite backend as the default persistent backend, maintaining the existing pluggable interface.**

Architecture:

```
EventStore(storage_backend=None)          # In-memory only (existing behavior, unchanged)
EventStore(storage_backend="sqlite")      # NEW: SQLite backend at default path
EventStore(storage_backend="sqlite", storage_config={"path": "/custom/path.db"})
EventStore(storage_backend=custom_impl)   # Existing: any object with append() and get()
```

The SQLite backend will be implemented in `src/kailash/middleware/gateway/event_store_sqlite.py` as a class `SQLiteEventStoreBackend` that satisfies the storage backend protocol.

**Key design decisions within this ADR**:

1. **SQLite, not filesystem**: Filesystem backends (one file per event key) have poor performance for the `get(key)` operation when there are many events. SQLite's B-tree indexing makes `get(key)` O(log n) regardless of total event count.

2. **Separate database from tracking**: The event store SQLite database is separate from the tracking database (`~/.kailash/tracking/tracking.db`). Reasons:
   - Different access patterns (event store is append-heavy, tracking is read-heavy)
   - Different lifecycle (events may be garbage-collected aggressively, tracking data is retained)
   - Separate databases allow independent WAL checkpointing and VACUUM
   - Default path: `~/.kailash/events/event_store.db`

3. **Schema**:

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_data TEXT NOT NULL,  -- JSON serialized
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_events_key_seq ON events(key, sequence);
CREATE INDEX idx_events_created ON events(created_at);
```

4. **Garbage collection**: Events older than configurable retention period (default 30 days) are deleted by a background task or on-demand `gc()` method. Matches the tracking system's maintenance pattern.

5. **Backward compatibility**: `storage_backend=None` continues to mean in-memory only. No behavior change for existing users. The string "sqlite" is a new convenience that creates a `SQLiteEventStoreBackend` internally.

### Consequences

#### Positive

- **Events survive restart**: Critical for production audit trails and event replay.
- **Proven pattern**: Reuses the same SQLite + WAL approach proven in the tracking system.
- **Zero new dependencies**: SQLite is in Python's standard library.
- **Pluggable**: Users who need PostgreSQL, Redis, or cloud-native event stores can still provide their own backend.
- **Backward compatible**: Default behavior unchanged; SQLite is opt-in.
- **Consistent with user expectations**: The brief's user research notes users are "heavy researchers" who expect data persistence by default.

#### Negative

- **Single-process write constraint**: SQLite WAL mode supports concurrent readers but only one writer. For multi-worker deployments, workers need separate event store instances or a shared PostgreSQL backend. This is acceptable because S9 (multi-worker) will address shared state separately.
- **Disk space growth**: Append-only events accumulate. Mitigated by GC policy with configurable retention.
- **Not suitable for high-throughput event sourcing**: SQLite tops out at ~10K writes/second in WAL mode. For event-heavy workloads, users should provide a dedicated backend. The SDK's buffered write pattern (batch of 100 events per flush) helps.

### Alternatives Considered

#### Option A: PostgreSQL Backend

- **Description**: Ship a PostgreSQL-backed event store using asyncpg.
- **Pros**: Multi-process safe; scalable; matches DatabaseStateStorage pattern in saga storage.
- **Cons**: Requires PostgreSQL server running; adds asyncpg dependency to core; significant operational overhead for local development.
- **Why rejected**: PostgreSQL is great for production but too heavy for the default backend. Users who need PostgreSQL can implement the 2-method protocol (`append`, `get`) themselves, which is trivial with asyncpg.

#### Option B: Filesystem Backend (One File per Key)

- **Description**: Store events as JSON files in `~/.kailash/events/{key}/` directories.
- **Pros**: Simple implementation; human-readable event files.
- **Cons**: Poor `get()` performance with many events (must read/parse all files); no indexing; file-per-event creates inode pressure; no atomic append for concurrent access.
- **Why rejected**: Does not meet the <50ms target for `get(key)` with 10K events.

#### Option C: SQLite as Default (Auto-enable)

- **Description**: Change `storage_backend=None` to auto-create SQLite backend instead of in-memory only.
- **Pros**: All users get persistence automatically; no configuration needed.
- **Cons**: Breaks backward compatibility (users expecting ephemeral event stores get persistent ones); creates files on disk without user consent; may cause issues in read-only environments or CI/CD.
- **Why rejected**: Changing default behavior violates backward compatibility. The opt-in approach (`storage_backend="sqlite"`) is safer. Can revisit in a future major version.

### Implementation Notes

1. **Thread safety**: Use `threading.Lock` for all SQLite operations, matching the tracking system pattern.
2. **Async wrapper**: The EventStore calls `await self.storage_backend.append(key, events)`. The SQLite backend's methods are actually sync. Wrap with `asyncio.to_thread()` or make them sync and let the EventStore handle the async bridging (the existing `_store_events` and `_load_from_storage` methods already handle this).
3. **Batch insert**: The EventStore already batches events (default 100). The SQLite backend should use `executemany()` for efficient batch inserts.
4. **String-based factory**: Accept `storage_backend="sqlite"` as a convenience. Internally, create `SQLiteEventStoreBackend(path=default_path)`. Accept `storage_backend="sqlite"` with `storage_config={"path": "..."}` for custom paths.

---

## Cross-ADR Dependency Map

```
ADR-PR-001 (Saga -> NodeRegistry)
    |
    +-- Independent. Can be implemented immediately.
    |
ADR-PR-002 (Distributed CB -> Redis Extension)
    |
    +-- Depends on S9 (multi-worker) for full value.
    +-- Can be implemented and tested independently.
    |
ADR-PR-003 (OTel in Core)
    |
    +-- Independent. Can be implemented immediately.
    +-- Benefits from ADR-PR-001 (saga spans are more useful with real execution).
    |
ADR-PR-004 (SQLite EventStore)
    |
    +-- Independent. Can be implemented immediately.
    +-- Benefits S4 (persistent DLQ can reuse the same SQLite patterns).
```

**Recommended implementation order**: ADR-PR-001 first (unblocks most value), ADR-PR-004 second (reuse patterns for S4 DLQ), ADR-PR-003 third (tracing is more useful after real execution works), ADR-PR-002 last (only needed for multi-worker).
