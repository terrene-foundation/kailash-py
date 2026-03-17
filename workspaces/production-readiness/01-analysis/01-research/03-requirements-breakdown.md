# Requirements Breakdown: Production Readiness

**Date**: 2026-03-17
**Source**: `01-production-readiness-analysis.md`, `01-project-brief.md`, source code review
**Prepared by**: requirements-analyst

---

## Executive Summary

- **Feature**: Production readiness gap closure for kailash-py SDK
- **Complexity**: High -- spans 7 MUST-FIX items, 9 SHOULD-FIX items across durability, observability, and infrastructure
- **Risk Level**: High -- M1/M2/M3 represent non-functional core features that return fabricated data
- **Estimated Effort**: 19-31 days across 6 phases

The most critical finding is structural: the saga coordinator, 2PC coordinator, and durable request system all simulate execution rather than performing it. This is not a missing feature -- it is functioning code that silently returns fake results, which is worse than throwing NotImplementedError because users cannot detect the failure.

---

## Dependency Graph

```
Legend: A --> B means "A must be completed before B"

M1 (saga execution) -----> S2 (workflow signals, needs real execution)
M2 (saga compensation) --> S2
M3 (2PC communication) --> S9 (multi-worker, needs real distributed txn)
M4 (workflow state capture) --> M5 (state restoration)
M5 (state restoration) ----> S2 (signals need checkpoint-aware execution)
M6 (create workflow) -------> M4 (workflow must exist to capture state)

M7 (prometheus endpoint) --- standalone, no dependencies
S1 (event store backend) --- standalone, no dependencies
S4 (persistent DLQ) -------- standalone, no dependencies
S5 (distributed CB) ------> S9 (multi-worker, shared CB is needed there)
S6 (OTel in core) ---------- standalone, no dependencies
S7 (graceful shutdown) ----- depends on knowing all subsystems (informational)

S3 (scheduling) ------------ standalone, no dependencies
S8 (workflow versioning) --- standalone, no dependencies
```

### Optimal Implementation Order

Based on the dependency graph, the correct implementation order is:

```
Phase 1 (no dependencies, highest impact):
  M1 + M2  -- saga execution wiring
  M3       -- 2PC communication wiring
  M6       -- DurableRequest._create_workflow
  M7       -- prometheus /metrics endpoint

Phase 2 (depends on M6):
  M4 + M5  -- workflow state capture and restoration

Phase 3 (no dependencies, high value):
  S1       -- SQLite event store backend
  S6       -- OpenTelemetry bridge to core
  S4       -- persistent dead letter queue

Phase 4 (benefits from Phase 1-2):
  S7       -- coordinated graceful shutdown
  S2       -- workflow signals and queries
  S3       -- scheduling / cron

Phase 5 (benefits from Phase 1-4):
  S5       -- distributed circuit breaker state
  S8       -- workflow versioning
  S9       -- multi-worker architecture
```

---

## Functional Requirements Matrix

### MUST-FIX Requirements

| ID  | Requirement                                           | Input                                                      | Output                                                | Business Logic                                                                                 | Edge Cases                                                                       | SDK Mapping                                      |
| --- | ----------------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------ |
| M1  | Saga step execution wired to node registry            | `SagaStep.node_id`, `SagaStep.parameters`                  | Real node execution result                            | Look up `node_id` in `NodeRegistry`, instantiate, call `async_run(**parameters)`               | Node not found, node raises exception, timeout, node returns non-dict            | `NodeRegistry.get()`, `AsyncNode.async_run()`    |
| M2  | Saga compensation wired to node registry              | `SagaStep.compensation_node_id`, `compensation_parameters` | Real compensation result                              | Look up compensation node, execute, handle compensation failure                                | No compensation node, compensation itself fails, partial compensation            | `NodeRegistry.get()`, `AsyncNode.async_run()`    |
| M3  | 2PC participant communication wired to real endpoints | `TwoPhaseCommitParticipant.endpoint`, transaction context  | HTTP response with vote/ack                           | Send HTTP request to participant endpoint, parse response, handle timeouts                     | Endpoint unreachable, partial network failure, slow response, malformed response | `aiohttp.ClientSession` or `httpx.AsyncClient`   |
| M4  | Workflow state capture implemented                    | Running `Workflow` instance                                | Dict with completed nodes, outputs, execution context | Walk workflow graph, collect completed node IDs and their outputs, serialize                   | Circular workflows, large intermediate results, non-serializable outputs         | `Workflow.nodes`, `LocalRuntime` execution state |
| M5  | Workflow state restoration implemented                | Checkpoint dict with workflow state                        | Resumed workflow execution from checkpoint position   | Reconstruct workflow, mark completed nodes as done, feed cached outputs, resume from next node | State schema version mismatch, missing node definitions, stale state             | `Workflow`, `LocalRuntime`                       |
| M6  | DurableRequest.\_create_workflow implemented          | Request body with workflow config                          | Configured `Workflow` with nodes and connections      | Parse request body JSON, create nodes via `WorkflowBuilder`, connect them, validate            | Malformed JSON, unknown node types, invalid connections, missing required params | `WorkflowBuilder`, `NodeRegistry`                |
| M7  | Prometheus /metrics HTTP endpoint                     | HTTP GET /metrics                                          | Prometheus text format response                       | Call `MetricsRegistry._export_prometheus()`, return as text/plain with correct content type    | Empty metrics, concurrent requests, large metric payload                         | `MetricsRegistry`, `FastAPI` route               |

### SHOULD-FIX Requirements

| ID  | Requirement                         | Input                                | Output                                      | Business Logic                                                                          | Edge Cases                                                                                       | SDK Mapping                                                          |
| --- | ----------------------------------- | ------------------------------------ | ------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| S1  | SQLite event store backend          | Events via `StorageBackend` protocol | Persistent events in SQLite                 | Implement `append(key, events)` and `get(key)` against SQLite with WAL mode             | Concurrent writes, disk full, DB corruption, large event payloads                                | `EventStore.storage_backend`, `SQLiteStorage` patterns from tracking |
| S2  | Workflow signals and queries        | Signal name + payload, query name    | Signal delivery confirmation, query result  | Register signal handlers on workflow, deliver signals to running workflows, query state | Workflow not running, duplicate signals, handler throws, concurrent signals                      | New `WorkflowSignalManager`                                          |
| S3  | Scheduling / cron system            | Cron expression, workflow definition | Scheduled workflow executions               | Parse cron expressions, schedule workflow runs, handle missed executions                | Timezone handling, overlapping runs, scheduler crash recovery                                    | New `WorkflowScheduler`                                              |
| S4  | Persistent dead letter queue        | Failed execution data                | Persisted DLQ entries with retry capability | Store failed items to SQLite, provide retry API, DLQ monitoring                         | DLQ full, retry storm, duplicate entries                                                         | `WorkflowResilience._dead_letter_queue`                              |
| S5  | Distributed circuit breaker state   | Circuit breaker state changes        | Shared state across processes               | Store CB state in Redis, read-before-write with CAS, handle Redis unavailability        | Redis down (fall back to local), split brain, stale reads                                        | `CircuitBreakerManager`, Redis                                       |
| S6  | OpenTelemetry wired to core runtime | Workflow execution events            | OTel spans with parent-child hierarchy      | Create tracer, instrument `LocalRuntime.execute()`, create spans per node               | OTel SDK not installed (graceful degrade), high-cardinality attributes, span context propagation | `TracingManager` patterns from Kaizen                                |
| S7  | Coordinated graceful shutdown       | SIGTERM / shutdown signal            | Clean shutdown of all subsystems            | Register all subsystems (event store, CB manager, checkpoint manager), drain in order   | Shutdown timeout, hung subsystem, partial shutdown                                               | `atexit`, `signal` handlers                                          |
| S8  | Workflow versioning                 | Versioned workflow definitions       | Version-aware routing and execution         | Store version with workflow, route to correct version, support parallel versions        | Version conflicts, running workflow version deprecated, migration of in-flight workflows         | New `WorkflowVersionManager`                                         |
| S9  | Multi-worker architecture           | Task queue, worker pool config       | Distributed workflow execution              | Task queue (Redis-backed), worker registration, task assignment, result collection      | Worker crash, task timeout, duplicate execution, queue full                                      | New infrastructure, optional Redis dependency                        |

---

## Detailed Scope Definitions

### M1: Saga Step Execution Wiring

**Current State**: `saga_coordinator.py:364-369` returns hardcoded `{"status": "success", "data": {"step_result": f"Result of {step.name}"}}` without executing any node.

**In Scope**:

- Modify `_execute_step()` to look up `step.node_id` in `NodeRegistry`
- Instantiate the node class with `step.parameters`
- Call `async_run(**step.parameters)` (or `run()` for sync nodes)
- Pass saga context as additional input (merge with step parameters)
- Handle node execution timeout via `asyncio.wait_for`
- Propagate node outputs to saga context
- Preserve existing state machine transitions (PENDING -> RUNNING -> COMPLETED/FAILED)

**Out of Scope**:

- Parallel step execution (saga pattern is sequential by definition)
- Cross-process saga coordination (that is S9 territory)
- Saga-specific retry logic beyond the existing `retry_policy` dict (exists but unused)

**Done Criteria**:

- `_execute_step()` instantiates and runs the actual node referenced by `step.node_id`
- `_compensate()` instantiates and runs the actual compensation node
- Node execution failures trigger proper compensation chain
- Saga context is updated with real node outputs
- State persistence reflects actual execution results

**Test Requirements**:

1. Unit test: Create saga with 3 registered mock nodes, execute, verify each node's `async_run` was called with correct parameters
2. Unit test: Create saga where step 2 fails, verify compensation runs step 1's compensation node in reverse order
3. Unit test: Node not found in registry raises appropriate `NodeExecutionError`
4. Unit test: Node timeout is respected via `asyncio.wait_for`
5. Integration test: Saga with real CSV reader + data processor nodes, verify actual data flows through

---

### M2: Saga Compensation Wiring

**Current State**: `saga_coordinator.py:431` sets `step.state = "compensated"` without running any compensation node.

**In Scope**:

- Modify `_compensate()` to look up `step.compensation_node_id` in `NodeRegistry`
- Execute compensation node with `step.compensation_parameters` merged with the step's original result
- Handle compensation node failure (log, add to compensation_errors, continue with next step)
- Respect reverse-order compensation (already implemented in loop structure)

**Out of Scope**:

- Compensation retry policies (would be a separate enhancement)
- Compensation timeout separate from step timeout

**Done Criteria**:

- Compensation runs real nodes when saga steps fail
- Partial compensation correctly reports which steps compensated and which failed
- Compensation receives the original step's result for informed rollback

**Test Requirements**:

1. Unit test: Step 3 fails, compensation runs step 2 and step 1 compensation nodes in reverse
2. Unit test: Compensation node itself fails, saga enters FAILED state with compensation_errors populated
3. Unit test: Step with no `compensation_node_id` is skipped during compensation (existing behavior preserved)

---

### M3: 2PC Participant Communication

**Current State**: `two_phase_commit.py:567-587` simulates prepare/commit with `asyncio.sleep(0.1)` and hardcoded `ParticipantVote.PREPARED`.

**In Scope**:

- Replace `_send_prepare_request()` with real HTTP POST to `participant.endpoint/prepare`
- Replace `_send_commit_request()` with real HTTP POST to `participant.endpoint/commit`
- Replace `_send_abort_request()` with real HTTP POST to `participant.endpoint/abort`
- Parse participant response to determine vote (PREPARED, ABORT)
- Handle HTTP errors, timeouts, malformed responses
- Use connection pooling (`aiohttp.ClientSession` or `httpx.AsyncClient`)

**Out of Scope**:

- gRPC participant protocol (HTTP-only for now)
- Participant discovery (endpoints are configured manually)
- TLS/mTLS for participant communication (separate security enhancement)

**Done Criteria**:

- 2PC coordinator makes real HTTP calls to participant endpoints
- Participant vote is determined from HTTP response, not hardcoded
- Network failures result in ABORT vote
- Timeout handling works correctly per participant

**Test Requirements**:

1. Unit test with `aiohttp.test_utils.TestServer`: 3 participants, all vote PREPARED, transaction commits
2. Unit test: One participant returns ABORT, transaction aborts and all receive abort messages
3. Unit test: One participant times out, transaction aborts
4. Unit test: Network error to one participant, transaction aborts
5. Integration test: Real HTTP servers as participants (can use `aiohttp.web.Application`)

---

### M4 + M5: Workflow State Capture and Restoration

**Current State**: `durable_request.py:388-403` returns skeleton dict with empty lists. `durable_request.py:426-432` is `pass`.

**In Scope**:

- `_capture_workflow_state()`: Walk the workflow DAG, collect completed node IDs, collect their outputs from runtime execution context, serialize to dict
- `_restore_workflow_state()`: Reconstruct execution state, mark nodes as completed, inject cached outputs, configure runtime to skip completed nodes
- Handle non-serializable outputs (log warning, skip that output)

**Out of Scope**:

- Resuming mid-node execution (checkpoint granularity is per-node, not within a node)
- Distributed state sharing for multi-worker resume
- Cyclic workflow checkpoint (DAG-only for now)

**Done Criteria**:

- Checkpoint captures which nodes completed and their outputs
- Resume skips completed nodes and feeds their cached outputs to downstream nodes
- Resume from checkpoint produces the same final result as a fresh run (for deterministic nodes)

**Test Requirements**:

1. Unit test: 5-node linear workflow, checkpoint after node 3, resume executes only nodes 4 and 5
2. Unit test: Node outputs from checkpoint are correctly wired to downstream node inputs
3. Unit test: Resume from latest checkpoint works when no specific checkpoint ID provided
4. Unit test: Non-serializable output is handled gracefully (warning logged, checkpoint still created)

---

### M6: DurableRequest.\_create_workflow

**Current State**: `durable_request.py:337-364` creates an empty `Workflow` with a TODO for adding nodes.

**In Scope**:

- Parse `request.body["workflow"]` for node definitions and connections
- Use `WorkflowBuilder` pattern: `add_node(node_type, node_id, parameters)` and `connect()`
- Validate node types exist in registry
- Validate connections are valid

**Out of Scope**:

- GraphQL or complex query languages for workflow definition
- Workflow template expansion (separate feature)

**Done Criteria**:

- Request body with workflow JSON creates a real, executable workflow
- Invalid node types raise clear errors
- Invalid connections raise clear errors

**Test Requirements**:

1. Unit test: Request body with 2 nodes and 1 connection creates correct workflow
2. Unit test: Unknown node type in request body raises ValueError with helpful message
3. Unit test: Missing required parameters raises validation error

---

### M7: Prometheus /metrics Endpoint

**Current State**: `MetricsRegistry._export_prometheus()` generates correct Prometheus text format. No HTTP endpoint serves it.

**In Scope**:

- Add `GET /metrics` route to `WorkflowServer` and `EnterpriseWorkflowServer`
- Return `MetricsRegistry.export_metrics(format="prometheus")` with `Content-Type: text/plain; version=0.0.4; charset=utf-8`
- No authentication on `/metrics` (standard Prometheus scraping pattern)

**Out of Scope**:

- OpenMetrics format (Prometheus text format is sufficient)
- Push-based metrics (Prometheus is pull-based)
- Custom metric labels per-server-instance

**Done Criteria**:

- `GET /metrics` returns valid Prometheus text format
- Response includes all registered collectors (validation, security, performance)
- Prometheus can scrape the endpoint without errors

**Test Requirements**:

1. Unit test: HTTP GET /metrics returns 200 with `text/plain` content type
2. Unit test: Response body parses as valid Prometheus text format
3. Unit test: Metrics include expected metric names (kailash*validation*_, kailash*security*_, kailash*performance*\*)

---

### S1: SQLite Event Store Backend

**In Scope**:

- Implement `StorageBackend` protocol (`append(key, events)`, `get(key)`) using SQLite
- Reuse patterns from `tracking/storage/database.py`: WAL mode, pragmas, schema versioning
- Table schema: `events(id INTEGER PRIMARY KEY, key TEXT, sequence INTEGER, event_data TEXT, created_at TEXT)`
- Index on `(key, sequence)` for efficient replay
- GC policy: retain events for configurable duration (default 30 days)

**Out of Scope**:

- Event compaction / snapshotting
- Cross-process event subscription (would need Redis pub/sub)
- Event schema migration

**Done Criteria**:

- Events survive process restart
- `append()` and `get()` work correctly under concurrent access
- Performance: <5ms for append, <50ms for get(key) with 10K events

**Test Requirements**:

1. Unit test: Append events, restart (new `SQLiteEventStore` instance), verify events are retrievable
2. Unit test: Concurrent append from multiple asyncio tasks
3. Unit test: `get()` respects sequence ordering
4. Performance test: Append 10K events in <5 seconds

---

### S4: Persistent Dead Letter Queue

**In Scope**:

- Add SQLite table for DLQ entries alongside event store or tracking DB
- DLQ entry: `(id, workflow_id, node_id, error, payload, created_at, retry_count, last_retry_at, status)`
- Retry API: `retry_dlq_entry(entry_id)` re-executes the failed operation
- Monitoring: `get_dlq_stats()` returns count by status, age distribution
- Bounded: max 10,000 entries, oldest evicted

**Out of Scope**:

- Automatic retry schedules
- DLQ routing rules
- Cross-service DLQ aggregation

**Done Criteria**:

- Failed executions are captured in persistent DLQ
- DLQ entries survive process restart
- Manual retry from DLQ re-executes with original inputs

**Test Requirements**:

1. Unit test: Failed workflow execution appears in DLQ
2. Unit test: DLQ entries survive process restart
3. Unit test: Retry from DLQ re-executes and succeeds (if underlying issue fixed)
4. Unit test: DLQ bounded at 10K entries, oldest evicted

---

### S6: OpenTelemetry in Core Runtime

**In Scope**:

- Create `src/kailash/monitoring/tracing.py` with `WorkflowTracingManager`
- Instrument `LocalRuntime.execute()` to create root span per workflow execution
- Create child spans per node execution with attributes: node_id, node_type, duration
- Use same OTLP exporter pattern as Kaizen `TracingManager`
- Graceful degradation: if `opentelemetry` not installed, no-op (import check at module level)
- OTel as optional dependency: `pip install kailash[tracing]`

**Out of Scope**:

- Metrics via OTel (keep existing custom metrics for now)
- Logs via OTel (keep existing logging)
- Baggage propagation across workflow boundaries

**Done Criteria**:

- Workflow execution produces OTel traces visible in Jaeger
- Each node execution is a child span of the workflow span
- Missing OTel dependency does not break SDK

**Test Requirements**:

1. Unit test: Mock tracer, verify workflow execution creates spans with correct hierarchy
2. Unit test: Without OTel installed, tracing is no-op (no errors)
3. Integration test: With Jaeger (Docker), verify traces are visible in Jaeger UI
4. Unit test: Node failure records exception in span

---

### S7: Coordinated Graceful Shutdown

**In Scope**:

- Create `ShutdownCoordinator` that registers subsystems with priority ordering
- Registration: event store, checkpoint manager, circuit breaker manager, tracking DB, runtime
- Shutdown sequence: stop accepting new work, drain in-progress work, flush buffers, close connections
- Timeout per subsystem (default 10s)
- Signal handling: SIGTERM, SIGINT

**Out of Scope**:

- Rolling restart / zero-downtime deployment (Kubernetes handles this)
- Distributed shutdown coordination

**Done Criteria**:

- SIGTERM triggers orderly shutdown of all registered subsystems
- Event store flushes buffer before closing
- In-progress workflows complete or checkpoint before shutdown
- Shutdown completes within configurable timeout

**Test Requirements**:

1. Unit test: Register 3 subsystems, trigger shutdown, verify called in priority order
2. Unit test: One subsystem hangs, overall shutdown completes after timeout
3. Unit test: Event store buffer is flushed during shutdown

---

## Non-Functional Requirements

### Performance Requirements

| Metric                       | Target                         | Measurement                              |
| ---------------------------- | ------------------------------ | ---------------------------------------- |
| Saga step execution overhead | <10ms above raw node execution | Benchmark M1 vs direct node.async_run()  |
| Prometheus /metrics response | <100ms                         | HTTP response time under load            |
| SQLite event store append    | <5ms per event                 | Benchmark append latency                 |
| SQLite event store get       | <50ms for 10K events           | Benchmark get latency                    |
| OTel span creation overhead  | <1ms per span                  | Benchmark from Kaizen (already measured) |
| Graceful shutdown            | <30s total                     | Signal to process exit                   |

### Security Requirements

| Concern                   | Requirement                                                                | Enforcement                              |
| ------------------------- | -------------------------------------------------------------------------- | ---------------------------------------- |
| 2PC participant endpoints | Validate URL format, disallow localhost/internal IPs in production mode    | Input validation in `_add_participant()` |
| DLQ payload storage       | Sanitize sensitive data before DLQ persistence                             | Configurable field redaction             |
| /metrics endpoint         | No authentication (standard), but no sensitive data in metric names/labels | Review metric content                    |
| Event store data          | SQLite file permissions 0o600                                              | Follow trust-plane-security.md Rule 6    |
| Saga state storage        | Existing Redis/DB patterns already handle this                             | No change needed                         |

### Backward Compatibility Requirements

| Component                 | Compatibility Guarantee                                                                                                                                   |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SagaCoordinatorNode API   | All existing operations (create_saga, add_step, execute_saga, etc.) remain identical. Only internal behavior changes (real execution vs simulated).       |
| EventStore API            | `storage_backend` parameter remains Optional. Existing code with `storage_backend=None` continues to work (in-memory only). New SQLite backend is opt-in. |
| CircuitBreakerManager API | No API changes. Distributed state is opt-in via configuration.                                                                                            |
| DurableRequest API        | No API changes. Resume behavior improves (skip completed nodes instead of re-execute all).                                                                |
| MetricsRegistry API       | No API changes. `/metrics` endpoint is additive.                                                                                                          |

---

## Risk Assessment

### High Probability, High Impact (Critical)

1. **M1/M2: Saga node resolution failure at runtime**
   - Risk: User's node_id strings may not match registry names
   - Mitigation: Clear error messages including available nodes list (NodeRegistry.get() already does this)
   - Prevention: Validate all step node_ids during `add_step`, not just during execution

2. **M4/M5: State capture misses intermediate data**
   - Risk: Some node outputs are not JSON-serializable (e.g., file handles, connections)
   - Mitigation: Try/except around serialization with fallback to string representation
   - Prevention: Document that checkpointable workflows must produce serializable outputs

3. **S6: OTel dependency conflicts**
   - Risk: User's OTel version conflicts with SDK's OTel version
   - Mitigation: Wide version range in optional dependency spec
   - Prevention: Test against OTel 1.x and 2.x

### Medium Risk (Monitor)

1. **M3: 2PC HTTP client choice**
   - Risk: Adding aiohttp or httpx as hard dependency
   - Mitigation: Make HTTP client injectable, default to what's available
   - Prevention: Check for aiohttp first (already a dependency for some nodes), fall back to httpx

2. **S1: SQLite contention under high write load**
   - Risk: Event store write performance degrades with concurrent flushes
   - Mitigation: WAL mode handles this well for moderate loads; batch writes
   - Prevention: Benchmark at expected throughput levels

3. **S7: Shutdown ordering complexity**
   - Risk: Wrong shutdown order causes data loss (e.g., closing DB before flushing event store)
   - Mitigation: Explicit priority-based ordering with clear documentation
   - Prevention: Integration tests for shutdown sequence

### Low Risk (Accept)

1. **N5: Default EventStore backend overlaps with S1**
   - The brief lists both S1 (persistent event store) and N5 (ship default backend). These are the same work item. S1 covers it.

2. **M7: Prometheus endpoint performance under many metrics**
   - Current metric count is bounded (max_series per collector). Not a concern at current scale.

---

## Integration Map

### Components to Reuse Directly

| Component                              | Location                       | Reuse For                                            |
| -------------------------------------- | ------------------------------ | ---------------------------------------------------- |
| `NodeRegistry.get()`                   | `nodes/base.py:2211`           | M1, M2 -- look up nodes by string ID                 |
| `SQLiteStorage` patterns               | `tracking/storage/database.py` | S1, S4 -- WAL mode, pragmas, schema versioning       |
| `TracingManager`                       | Kaizen `tracing_manager.py`    | S6 -- OTel provider setup, span creation patterns    |
| `MetricsRegistry._export_prometheus()` | `monitoring/metrics.py:619`    | M7 -- already generates correct format               |
| `EventStore.storage_backend` protocol  | `event_store.py:99`            | S1 -- implement `append(key, events)` and `get(key)` |
| `SagaStateStorage` interface           | `saga_state_storage.py`        | Reference pattern for pluggable backends             |

### Components Needing Modification

| Component                                               | Modification                                                          | Reason |
| ------------------------------------------------------- | --------------------------------------------------------------------- | ------ |
| `SagaCoordinatorNode._execute_step()`                   | Replace simulated execution with `NodeRegistry.get()` + `async_run()` | M1     |
| `SagaCoordinatorNode._compensate()`                     | Replace simulated compensation with real node execution               | M2     |
| `TwoPhaseCommitCoordinatorNode._send_prepare_request()` | Replace `asyncio.sleep` with real HTTP call                           | M3     |
| `TwoPhaseCommitCoordinatorNode._send_commit_request()`  | Replace `asyncio.sleep` with real HTTP call                           | M3     |
| `DurableRequest._capture_workflow_state()`              | Implement actual state capture                                        | M4     |
| `DurableRequest._restore_workflow_state()`              | Implement actual state restoration                                    | M5     |
| `DurableRequest._create_workflow()`                     | Parse request body into real workflow                                 | M6     |
| `WorkflowServer.__init__` / route setup                 | Add `/metrics` route                                                  | M7     |
| `WorkflowResilience._dead_letter_queue`                 | Replace in-memory list with persistent store                          | S4     |

### Components to Build New

| Component                 | Location                                   | Purpose                    |
| ------------------------- | ------------------------------------------ | -------------------------- |
| `SQLiteEventStoreBackend` | `middleware/gateway/event_store_sqlite.py` | S1: Persistent event store |
| `WorkflowTracingManager`  | `monitoring/tracing.py`                    | S6: Core OTel integration  |
| `ShutdownCoordinator`     | `core/lifecycle/shutdown.py`               | S7: Coordinated shutdown   |
| `PersistentDLQ`           | `workflow/dead_letter_queue.py`            | S4: Persistent DLQ         |
| `WorkflowSignalManager`   | `workflow/signals.py`                      | S2: Signal/query handling  |
| `WorkflowScheduler`       | `workflow/scheduler.py`                    | S3: Cron scheduling        |
| `WorkflowVersionManager`  | `workflow/versioning.py`                   | S8: Version management     |

---

## Implementation Checklist per Gap

### Phase 1: Fix Critical Stubs (Days 1-3)

- [ ] **M1**: Replace simulated `_execute_step()` with `NodeRegistry.get(step.node_id)(**params).async_run()`
- [ ] **M1**: Add node_id validation in `_add_step()` (fail-fast if node not in registry)
- [ ] **M1**: Add timeout to step execution via `asyncio.wait_for`
- [ ] **M2**: Replace simulated `_compensate()` with real compensation node execution
- [ ] **M2**: Pass original step result to compensation node for informed rollback
- [ ] **M3**: Replace `_send_prepare_request()` with HTTP POST
- [ ] **M3**: Replace `_send_commit_request()` with HTTP POST
- [ ] **M3**: Replace `_send_abort_request()` with HTTP POST
- [ ] **M3**: Add configurable HTTP client (aiohttp default)
- [ ] **M6**: Implement request body parsing into WorkflowBuilder calls
- [ ] **M6**: Validate node types and connections
- [ ] **M7**: Add `GET /metrics` route to WorkflowServer
- [ ] **M7**: Add `GET /metrics` route to EnterpriseWorkflowServer
- [ ] **M7**: Set correct Content-Type header for Prometheus scraping

### Phase 2: Checkpoint Completion (Days 4-5)

- [ ] **M4**: Implement `_capture_workflow_state()` -- collect completed nodes and outputs
- [ ] **M4**: Handle non-serializable outputs gracefully
- [ ] **M5**: Implement `_restore_workflow_state()` -- mark nodes done, inject outputs
- [ ] **M5**: Modify `_execute_workflow()` to support skip-completed-nodes mode
- [ ] **M5**: Integration test: checkpoint + resume produces same result as fresh run

### Phase 3: Production Durability (Days 6-10)

- [ ] **S1**: Create `SQLiteEventStoreBackend` implementing StorageBackend protocol
- [ ] **S1**: Schema with WAL mode, proper indexes, GC policy
- [ ] **S1**: Wire as default backend when `storage_backend=None` (configure via env var or param)
- [ ] **S6**: Create `WorkflowTracingManager` with conditional OTel import
- [ ] **S6**: Instrument `LocalRuntime.execute()` with root span
- [ ] **S6**: Instrument per-node execution with child spans
- [ ] **S6**: Add `kailash[tracing]` optional dependency group
- [ ] **S4**: Create `PersistentDLQ` with SQLite backend
- [ ] **S4**: Wire into `WorkflowResilience` as replacement for in-memory list
- [ ] **S4**: Add retry and monitoring APIs

### Phase 4: Workflow Interaction (Days 11-17)

- [ ] **S7**: Create `ShutdownCoordinator` with priority-based subsystem ordering
- [ ] **S7**: Register all subsystems (event store, CB manager, checkpoint manager)
- [ ] **S7**: Wire SIGTERM/SIGINT handlers
- [ ] **S2**: Design signal/query protocol
- [ ] **S2**: Implement `WorkflowSignalManager`
- [ ] **S2**: Wire to DurableRequest for external signal delivery
- [ ] **S3**: Evaluate APScheduler vs custom scheduler
- [ ] **S3**: Implement `WorkflowScheduler` with cron expression support

### Phase 5: Scale-Out Readiness (Days 18-28)

- [ ] **S5**: Distributed circuit breaker state via Redis (ADR required)
- [ ] **S8**: Workflow versioning with version-aware routing
- [ ] **S9**: Multi-worker architecture design and implementation (ADR required)

---

## Success Criteria

### Functional Completeness

- [ ] All 7 MUST-FIX gaps have zero simulated/stubbed behavior
- [ ] All SHOULD-FIX gaps implemented have tests proving the feature works
- [ ] Every `# TODO` and `# Simulate` comment removed from production code in touched files

### Production Confidence

- [ ] Saga coordinator executes real nodes end-to-end (not simulated)
- [ ] 2PC coordinator makes real HTTP calls to participants
- [ ] Durable request checkpoint/resume skips completed nodes
- [ ] Prometheus metrics are scrapeable by a real Prometheus instance
- [ ] Event store survives process restart
- [ ] Graceful shutdown flushes all buffers

### Developer Experience

- [ ] Clear error messages when saga step references unknown node
- [ ] OTel tracing works with `pip install kailash[tracing]` (no other config needed for local dev)
- [ ] DLQ entries are queryable and retryable via API

### Backward Compatibility

- [ ] All existing tests pass without modification
- [ ] All existing public APIs remain unchanged
- [ ] Default behavior (no configuration) is equivalent to pre-change behavior for S1, S5, S6
