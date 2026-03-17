# Implementation Plan: kailash-py Production Readiness

**Date**: 2026-03-17
**Status**: DRAFT — awaiting human review
**Sources**: 6 research documents in `01-analysis/01-research/`

---

## Strategic Context

The Rust team identified 7 MUST-FIX and 9 SHOULD-FIX gaps. Our analysis confirmed 5 Critical, 2 Major (downgraded from Critical), found 8 additional missed stubs, and identified an architectural root cause: the runtime lacks dynamic node invocation, making saga/2PC execution stubs a design gap, not just missing code.

**Key insight from COC assessment**: The saga/2PC system was generated in a single AI session that never imported `NodeRegistry`. It's "Completion Theater" — internally consistent, passes its own tests, but the integration seam is entirely stubbed.

**Key insight from enterprise assessment**: The stub returns fabricated success (`{"status": "success"}`) rather than throwing `NotImplementedError`. This is trust-destroying for enterprise evaluators — it's the difference between "incomplete" and "deceptive."

---

## Scope Decision: SDK vs Engine

Before implementation, we must decide scope. The Rust team's brief assumes kailash-py should become a workflow engine (like Temporal/Cadence). Some gaps (S2 signals, S8 versioning, S9 multi-worker, N1 continue-as-new) only matter if we're building an engine.

**Recommendation**: kailash-py is a **workflow SDK** — it orchestrates computation within a process. Items targeting engine-level capabilities should be Phase 5+ or deferred to a separate `kailash-engine` package. This keeps the core SDK focused and avoids scope creep.

**In scope for production readiness**: M1-M5, M7, S1, S6, S7 (things that make current features work correctly)
**Requires ADR before implementation**: M3 (2PC transport), S2 (signals), S5 (distributed CB)
**Deferred (engine-level)**: S3 (scheduler), S8 (versioning), S9 (multi-worker), N1 (continue-as-new)

---

## Phase 1: Trust Restoration (3-4 days)

**Goal**: Distributed transactions produce real results. POC-ready.

### 1a. Saga Execution Wiring (M1 + M2) — 2 days

**Architecture**: Per ADR-PR-001, use `NodeExecutor` protocol with default `RegistryNodeExecutor`:

```python
class NodeExecutor(Protocol):
    async def execute(self, node_type: str, params: dict) -> dict: ...
    async def compensate(self, node_type: str, params: dict) -> dict: ...

class RegistryNodeExecutor:
    def __init__(self, registry: NodeRegistry):
        self._registry = registry

    async def execute(self, node_type: str, params: dict) -> dict:
        node_cls = self._registry.get(node_type)
        node = node_cls()
        return await asyncio.wait_for(node.async_run(**params), timeout=300)
```

**Changes**:

- `saga_coordinator.py`: Replace lines 364-369 with `self._executor.execute(step.node_id, step.parameters)`
- `saga_coordinator.py`: Replace lines 430-431 with `self._executor.compensate(step.compensation_node_id, step.compensation_parameters)`
- Add `executor: Optional[NodeExecutor] = None` parameter to `SagaCoordinatorNode.__init__`
- Default to `RegistryNodeExecutor(NodeRegistry)` when no executor provided

**Done criteria**:

- Saga steps invoke real nodes and return their actual results
- Compensation invokes real compensation nodes
- Failed step triggers compensation of completed steps with real execution
- Tests use `MockNodeExecutor` for unit tests, real `RegistryNodeExecutor` for integration tests

### 1b. 2PC Local Participant Execution (M3) — 1-2 days

**Architecture**: Per ADR-PR-001, 2PC participants can be local nodes (same-process) or remote endpoints. Start with local:

```python
class ParticipantTransport(Protocol):
    async def prepare(self, participant: Participant, tx_id: str) -> Vote: ...
    async def commit(self, participant: Participant, tx_id: str) -> bool: ...
    async def abort(self, participant: Participant, tx_id: str) -> bool: ...

class LocalNodeTransport:
    """Participants are nodes in the same process."""
    ...

class HttpTransport:
    """Participants are HTTP endpoints. Future implementation."""
    ...
```

**Changes**:

- `two_phase_commit.py`: Replace `_send_prepare_request`, `_send_commit_request`, `_send_abort_request` with `self._transport.prepare/commit/abort`
- Add `transport: Optional[ParticipantTransport] = None` parameter
- Ship `LocalNodeTransport` as default, `HttpTransport` as optional

**Done criteria**:

- 2PC prepare/commit/abort invoke real participant nodes
- Timeout handling works with real execution
- Participant vote reflects actual node outcome

### 1c. Prometheus Endpoint (M7) — 0.5 day

**Changes**:

- `servers/workflow_server.py`: Add `@self.app.get("/metrics")` endpoint calling `MetricsRegistry.export_metrics(format="prometheus")`
- Wire same endpoint into `EnterpriseWorkflowServer` and `DurableWorkflowServer`

**Done criteria**:

- `curl localhost:PORT/metrics` returns valid Prometheus text format
- Prometheus can scrape the endpoint

---

## Phase 2: Durability Completion (4-6 days)

**Goal**: Checkpoints work. Events persist. Shutdown is clean.

### 2a. Checkpoint State Capture/Restore (M4 + M5) — 3-5 days

**Architecture**: Replay-based approach (ADR decision). The runtime skips already-completed nodes and feeds cached outputs to downstream nodes.

**Changes**:

- `runtime/local.py`: Add `ExecutionTracker` that records per-node completion and outputs during `execute()`
- `durable_request.py:387-403`: Implement `_capture_workflow_state()` to serialize `ExecutionTracker` state
- `durable_request.py:425-432`: Implement `_restore_workflow_state()` to populate tracker with cached results
- `runtime/local.py`: Modify execution loop to check tracker for cached results before executing a node

**Done criteria**:

- Workflow crashes at step N, resumes from checkpoint, skips steps 1..N-1, continues from step N
- Cached outputs from completed steps are available to downstream nodes
- No duplicate side effects for completed steps

### 2b. SQLite EventStore Backend (S1) — 1-2 days

**Architecture**: Per ADR-PR-004, SQLite with WAL mode matching tracking system pattern.

**Changes**:

- Create `middleware/gateway/event_store_sqlite.py` implementing `StorageBackend` protocol
- Define `StorageBackend` protocol formally (currently only implicit)
- Schema: `events(id, stream_key, sequence, event_type, data, timestamp)`
- WAL mode, 64MB cache, 30-day retention with GC

**Done criteria**:

- `EventStore(storage_backend=SqliteEventStoreBackend("events.db"))` persists events across restarts
- Event replay works from persistent storage
- GC removes events older than retention period

### 2c. Coordinated Graceful Shutdown (S7) — 0.5-1 day

**Changes**:

- Create shutdown coordinator that sequences: (1) stop accepting new work, (2) wait for in-progress workflows, (3) flush event store, (4) checkpoint active states, (5) close circuit breakers, (6) close storage connections

**Done criteria**:

- `SIGTERM` triggers orderly shutdown with no data loss
- All subsystems confirm cleanup before process exits

---

## Phase 3: Observability (2-3 days)

**Goal**: Distributed tracing across workflow execution.

### 3a. OpenTelemetry in Core Runtime (S6) — 2-3 days

**Architecture**: Per ADR-PR-003, independent OTel in core with graceful degradation.

**Changes**:

- Create `runtime/tracing.py` with `WorkflowTracer` (optional dependency on `opentelemetry-api`)
- Add span creation in `LocalRuntime.execute()`: workflow span → node spans
- Share `OTEL_EXPORTER_OTLP_ENDPOINT` env var convention with Kaizen
- Kaizen agent spans become parents of workflow spans when both are active

**Done criteria**:

- `pip install kailash[otel]` enables tracing
- Without OTel installed, zero overhead (feature flag pattern)
- Jaeger shows workflow → node span hierarchy

---

## Phase 4: Workflow Interaction (3-5 days) — Requires ADR

**Goal**: Human-in-the-loop workflows.

### 4a. Workflow Signals and Queries (S2) — 3-5 days

**Requires**: ADR on signal delivery mechanism (in-process events vs external queue)

**Changes**:

- Add `SignalChannel` to workflow execution context
- Nodes can `await signal_channel.wait_for("approval")`
- External callers can `runtime.signal(workflow_id, "approval", data)`
- Query handlers: `runtime.query(workflow_id, "status")` returns registered query handler result

**Done criteria**:

- Approval workflow: node waits for signal, external caller sends approval, workflow continues
- Query returns workflow-internal state without affecting execution

---

## Phase 5+: Deferred (Engine-Level)

These items are tracked but not in the production-readiness scope:

| Item                      | Rationale for Deferral                                                                       |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| S3: Scheduler/cron        | Use external scheduler (APScheduler, Celery Beat). Not SDK responsibility.                   |
| S5: Distributed CB        | Optional Redis extension per ADR-PR-002. Only needed for multi-worker.                       |
| S8: Workflow versioning   | Engine-level concept. SDK users define versions in their own code.                           |
| S9: Multi-worker          | Requires fundamental architecture change. Separate `kailash-engine` package.                 |
| N1: Continue-as-new       | Engine pattern. Cyclic workflows serve similar purpose in SDK model.                         |
| X1: Edge migration        | Epic scope. Separate workspace if edge becomes a priority.                                   |
| X2/X3: MCP client         | Separate from production readiness. MCP server (Nexus) works; client is a different product. |
| X4: Credential backends   | Ship with `NotImplementedError` + clear docs for now. Optional extras later.                 |
| X5: Directory integration | LDAP is niche. Ship simulation with clear docs; real implementation via community.           |

---

## Risk Mitigations

| Risk                                             | Mitigation                                                                        |
| ------------------------------------------------ | --------------------------------------------------------------------------------- |
| Runtime doesn't support dynamic node invocation  | NodeExecutor protocol decouples saga from runtime internals                       |
| M4/M5 deeper than estimated (runtime monolithic) | Replay-based approach avoids modifying core execution loop; adds tracking overlay |
| 2PC transport design delays Phase 1              | Start with LocalNodeTransport only; defer HttpTransport                           |
| Stubs discovered during fix reveal more stubs    | Gap verification already found X1-X8; scope is bounded                            |
| Convention drift from Rust patterns              | COC assessment identifies 6 concepts needing Pythonic alternatives                |

---

## Summary

| Phase                | Effort         | Cumulative | Gate                                                 |
| -------------------- | -------------- | ---------- | ---------------------------------------------------- |
| 1: Trust Restoration | 3-4 days       | 3-4 days   | Saga/2PC functional, Prometheus wired                |
| 2: Durability        | 4-6 days       | 7-10 days  | Checkpoint resume, persistent events, clean shutdown |
| 3: Observability     | 2-3 days       | 9-13 days  | Distributed tracing                                  |
| 4: Interaction       | 3-5 days       | 12-18 days | Signals/queries for HITL workflows                   |
| **Total**            | **12-18 days** |            | **Production-ready (single-process)**                |

Note: This is 12-18 days vs the brief's 19-31 days because we descoped engine-level items (S3, S5, S8, S9, N1-N7) and right-sized M6/M7.
