# Durability Patterns

You are an expert in Kailash's durable-execution primitives — `ExecutionTracker` (per-node checkpoints), `Checkpoint` / `ExecutionJournal` / `DurableRequest` (per-request state machine + audit trail), `CheckpointManager` + `DBCheckpointStore` (tiered persistence), and `DurableWorkflowServer` (server-mode wiring). Guide users through engagement, the resume-from-checkpoint contract, and the trade-off between piecemeal primitives and the full server.

> Source: `src/kailash/runtime/execution_tracker.py`, `src/kailash/middleware/gateway/durable_request.py`, `src/kailash/middleware/gateway/checkpoint_manager.py`, `src/kailash/infrastructure/checkpoint_store.py`, `src/kailash/servers/durable_workflow_server.py`.

## ExecutionTracker — Per-Node Checkpoint Primitive

`ExecutionTracker` is JSON-serializable per-node completion state. The runtime calls `record_completion(node_id, output)` after each node; on restore, `from_dict(...)` rebuilds the tracker and the runtime SKIPS already-completed nodes by reading `is_completed(node_id)` and replaying `get_output(node_id)`.

### When To Engage

- "I want this workflow to resume from where it crashed instead of restarting from node 1"
- "Long-running workflow with side-effecting nodes (LLM calls, paid API requests, DB writes) — re-running from zero is unsafe"
- "I need to inspect what nodes actually completed in a failed run"

### Setup

```python
# DO — runtime + DurableRequest manages the tracker for you
from kailash.middleware.gateway.durable_request import DurableRequest
req = DurableRequest()
await req.execute_workflow(workflow)  # tracker checkpointed automatically

# DO — direct use for custom orchestration
from kailash.runtime.execution_tracker import ExecutionTracker
tracker = ExecutionTracker()
tracker.record_completion("extract", {"rows": 1000})
tracker.record_completion("transform", {"rows": 1000, "valid": 998})
serialized = tracker.to_dict()
# ...persist serialized somewhere durable...
restored = ExecutionTracker.from_dict(serialized)
assert restored.is_completed("extract")
assert restored.get_output("extract") == {"rows": 1000}

# DO NOT — track completion in a sidecar dict and skip the helper
completed = {}
completed["extract"] = run_node("extract")  # no JSON serializability guarantee
```

**Why:** `ExecutionTracker._serialize` enforces JSON-friendliness on every recorded output and degrades gracefully (logs a warning, stores `str(value)` with `_serialization_degraded=True`) when an output is non-serializable. A sidecar dict gives no such guarantee, and a non-serializable output silently breaks the round-trip on the next restore.

## Checkpoint + ExecutionJournal + DurableRequest

`DurableRequest` is the per-request state machine that owns:

- `RequestState` (INITIALIZED → VALIDATED → WORKFLOW_CREATED → EXECUTING → CHECKPOINTED → COMPLETED / FAILED / CANCELLED / RESUMING)
- `ExecutionJournal` — append-only audit trail of every state transition (`record(event_type, data)`)
- `ExecutionTracker` — per-node completion (above)
- `Checkpoint` — serialized blob persisted at validation, workflow-creation, and workflow-completion boundaries
- `CancellationToken` for graceful interruption

### Resume-From-Checkpoint Contract

```python
# DO — explicit checkpoint_manager wiring; restores cached node outputs
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager
from kailash.middleware.gateway.durable_request import DurableRequest

mgr = CheckpointManager(disk_storage=disk, retention_hours=24)
req = DurableRequest(request_id="req_abc", checkpoint_manager=mgr)
try:
    await req.execute_workflow(workflow)
except WorkflowCancelledError:
    # Process restart; same request_id resumes where it left off
    req2 = DurableRequest(request_id="req_abc", checkpoint_manager=mgr)
    await req2.resume()  # ExecutionTracker replays cached node outputs

# DO NOT — use DurableRequest without a checkpoint_manager when durability matters
req = DurableRequest()  # checkpoint_manager=None → checkpoints are in-memory only
# (process crash erases everything; resume() has no state to restore from)
```

**Why:** A `DurableRequest` without a wired `CheckpointManager` is a state machine with no persistence — the journal lives in process memory and dies with the process. The wiring is what makes the request actually durable. The advertised resume contract holds only when both the request_id and the checkpoint backing store survive the crash.

In-flight integration work tying `DurableRequest` resume into the LocalRuntime hot path is tracked at the SDK's open LocalRuntime-resume integration issue.

## CheckpointManager + DBCheckpointStore — Persistence Tiers

`CheckpointManager` provides tiered storage (memory → disk → optional cloud) with optional gzip compression for blobs above 1KB. `DBCheckpointStore` adds a dialect-portable SQL backend that implements the same `StorageBackend` protocol, suitable for production deployments that already have a shared database.

### Wiring Against Real PostgreSQL

```python
# DO — DBCheckpointStore through the shared ConnectionManager
from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager

conn = ConnectionManager(os.environ["KAILASH_DATABASE_URL"])
await conn.initialize()
db_store = DBCheckpointStore(conn)
await db_store.initialize()                              # CREATE TABLE IF NOT EXISTS
mgr = CheckpointManager(disk_storage=db_store, retention_hours=24)

# DO NOT — instantiate a separate ConnectionManager per store
db_store = DBCheckpointStore(ConnectionManager(url))     # parallel pool
# (violates infrastructure-sql.md "share a single ConnectionManager via StoreFactory")
```

**Why:** A separate `ConnectionManager` per store creates a parallel pool competing for the same `max_connections` budget, recreating the pool-exhaustion failure mode the StoreFactory pattern was introduced to prevent. Routing all stores through the shared `ConnectionManager` keeps pool math single-source-of-truth.

### Compression Threshold

`CheckpointManager(compression_threshold_bytes=1024)` means blobs above 1KB are gzipped; below the threshold, raw bytes go straight through. The `compressed` boolean column (DBCheckpointStore) is set automatically based on the gzip magic-number prefix.

```python
# DO — accept the default 1KB threshold unless metrics show ratio < 0.5 average
mgr = CheckpointManager()
# DO NOT — disable compression to "save CPU" without measuring blob distribution
mgr = CheckpointManager(compression_enabled=False)  # 10x storage growth on text-heavy workflows
```

**Why:** The default threshold + ratio metric (`mgr.compression_ratio_sum / mgr.save_count`) is the operational signal that tells you whether the threshold is right; turning compression off blind kills the signal AND the storage savings.

## DurableWorkflowServer — Full Server Wiring

`DurableWorkflowServer` extends `WorkflowServer` with checkpointing + dedup + event sourcing in one constructor. Use it when:

- You want one process that owns the full durability stack (request lifecycle, dedup, event store, recovery endpoints)
- Endpoints opt into durability per-route (`durability_opt_in=True`, the default) so unimportant routes don't pay the checkpoint cost
- You need the `/durability/...` recovery endpoints out-of-the-box

### Engage The Full Server vs Piecemeal Primitives

```python
# DO — full server wiring when you own the HTTP surface
from kailash.servers.durable_workflow_server import DurableWorkflowServer

server = DurableWorkflowServer(
    title="My API",
    enable_durability=True,
    durability_opt_in=True,    # opt-in per endpoint
    # CheckpointManager / RequestDeduplicator / EventStore default-constructed
)

# DO — piecemeal primitives when embedding into a different HTTP framework
mgr = CheckpointManager(disk_storage=db_store)
req = DurableRequest(checkpoint_manager=mgr)
await req.execute_workflow(workflow)
# (caller owns dedup + audit trail wiring separately)

# DO NOT — half-wire the server (durability=True but no shared checkpoint store
# across replicas) — checkpoints land on local disk and resume() across replicas fails
server = DurableWorkflowServer(enable_durability=True)  # default = local DiskStorage
# kubectl scale deployment server --replicas=3
# Replica A creates a checkpoint on its disk; replica B handles the resume; can't find it
```

**Why:** `DurableWorkflowServer` is convenient ONLY when the storage backend is shared across the replica fleet (use `DBCheckpointStore` or a cloud storage backend). For a single-process service the default `DiskStorage` is correct; for replicated services it's a quiet failure mode the moment a replica restarts and another replica tries to resume.

## Independence Note

Kailash describes durable execution on its own terms. The primitives above are designed for Kailash workflows and request lifecycles; they do not interoperate with, port from, or replace any other product's durable-execution model. Compare implementations only to other Kailash patterns.

## Test Tier Recommendation

Tier 2 (real PostgreSQL + real `DBCheckpointStore` + real `DurableRequest`) is the only tier that proves the resume contract. Tier 1 tests against `ExecutionTracker.to_dict() / from_dict()` prove the helper round-trips JSON; they do not prove that the runtime calls the tracker on every node completion or that `CheckpointManager.save_checkpoint` actually persists to the wired backend.

In-flight integration work tying durable execution into the LocalRuntime resume path is tracked at the SDK's open durable-execution integration issue.

## Related

- `scheduler-patterns.md` — recurring workflows that benefit from durability when triggered
- `task-queue-patterns.md` — companion for distributing durable work across a worker fleet
- `connection-manager-patterns.md` — required reading before wiring `DBCheckpointStore` against shared infrastructure
- `progressive-infrastructure.md` — Level 1/2 is the appropriate tier for a shared checkpoint store
