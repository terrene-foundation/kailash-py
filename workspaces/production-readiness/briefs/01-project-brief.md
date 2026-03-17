# Production Readiness Brief: kailash-py

> This workspace was created by the kailash-rs team for the kailash-py dev team to action.

**Date**: 2026-03-17
**Analysis source**: `/workspaces/production-readiness/01-analysis/01-research/01-production-readiness-analysis.md`

---

## Executive Summary

The kailash-py SDK has strong foundations in durability primitives (saga, checkpoints, event store, circuit breaker) and monitoring infrastructure (metrics, dashboard, tracking). However, several critical features are stubbed or incomplete, and the SDK lacks the horizontal scaling, workflow interaction, and observability wiring needed for production deployment at scale.

The most urgent issue is that the saga coordinator and 2PC coordinator simulate node execution rather than actually running it -- making the distributed transaction system non-functional despite having well-designed state management and storage backends.

---

## Priority-Rated Gap Register

### MUST FIX (Blocks production use)

| ID | Gap | Location | Impact |
|----|-----|----------|--------|
| **M1** | Saga step execution is simulated | `saga_coordinator.py:364-369` | Saga coordinator returns fake results; compensation never runs real nodes |
| **M2** | Saga compensation is simulated | `saga_coordinator.py:431` | Failed sagas mark steps "compensated" without running compensation nodes |
| **M3** | 2PC participant communication simulated | `two_phase_commit.py` | Two-phase commit never contacts actual participant endpoints |
| **M4** | Workflow state capture is stubbed | `durable_request.py:388-403` | Resume from checkpoint re-executes entire workflow, not from checkpoint position |
| **M5** | Workflow state restoration is a no-op | `durable_request.py:426-432` | `_restore_workflow_state()` is `pass` |
| **M6** | DurableRequest._create_workflow is incomplete | `durable_request.py:337-364` | TODO for parsing request body into workflow nodes |
| **M7** | No Prometheus `/metrics` endpoint | servers/*.py | Prometheus export function exists but no HTTP endpoint serves it |

### SHOULD FIX (Required for production confidence)

| ID | Gap | Location | Impact |
|----|-----|----------|--------|
| **S1** | Event store has no persistent backend | `event_store.py` | All events lost on restart; users must implement their own StorageBackend |
| **S2** | No workflow signals or queries | -- | Cannot interact with running workflows (approve, reject, query state) |
| **S3** | No scheduling/cron system | -- | Users need external scheduler for recurring workflows |
| **S4** | Dead letter queue is in-memory only | `resilience.py:126` | DLQ data lost on restart; no automatic retry from DLQ |
| **S5** | No distributed circuit breaker state | `circuit_breaker.py` | Each process has independent CB state; multi-worker deploys have inconsistent failure detection |
| **S6** | OpenTelemetry not wired to core runtime | Kaizen has it, core doesn't | Agent tracing exists but workflow execution has no distributed traces |
| **S7** | No coordinated graceful shutdown | servers, middleware | Runtime shuts down gracefully but checkpoint manager, event store, CBs may not |
| **S8** | No workflow versioning | -- | Cannot run multiple workflow versions simultaneously or migrate running workflows |
| **S9** | No multi-worker architecture | -- | Single-process only; no task queue, no work distribution |

### NICE TO HAVE (Improves operational excellence)

| ID | Gap | Location | Impact |
|----|-----|----------|--------|
| **N1** | Continue-as-new pattern | -- | Long-running workflows accumulate unbounded history |
| **N2** | Dashboard is static HTML, not live | `dashboard.py` | Auto-refresh via page reload; no WebSocket-based live updates on main dashboard |
| **N3** | No Kubernetes deployment manifests | -- | Users must create their own K8s config |
| **N4** | No system-wide resource quotas | -- | No max concurrent workflows, memory limits per workflow |
| **N5** | Ship a default EventStore persistent backend | -- | Reduce time to production; SQLite or filesystem backend would suffice |
| **N6** | Pause/resume for running workflows | -- | Cannot suspend mid-execution; only checkpoint-based restart |
| **N7** | Connection dashboard not integrated | `connection_dashboard.py` | Standalone aiohttp app, not part of main server |

---

## Key Differences: kailash-py vs kailash-rs

### Python SDK strengths (features Rust does NOT have)

| Feature | Python Location | Notes |
|---------|----------------|-------|
| Saga storage backends (Redis, DB) | `saga_state_storage.py` | Pluggable, ships 3 implementations |
| Bulkhead isolation | `core/resilience/bulkhead.py` | Partition-based resource isolation |
| HTML monitoring dashboard | `visualization/dashboard.py` | Real-time metrics visualization |
| Rich testing framework | `testing/` | MockNode, fixtures, async helpers |
| Event store with projections | `middleware/gateway/event_store.py` | Event sourcing with derived state |
| Durable workflow server | `servers/durable_workflow_server.py` | Layered server with checkpointing |
| Rate limiting nodes | `nodes/api/rate_limiting.py` | Token bucket + sliding window |
| Request deduplication | `middleware/gateway/deduplicator.py` | Idempotency key support |
| DAG-to-cyclic migration | `workflow/migration.py` | Automated pattern conversion |
| Connection pool actor model | `core/actors/` | Adaptive pool controller |

### Rust SDK strengths (features Python does NOT have)

| Feature | Rust Location | Notes |
|---------|--------------|-------|
| EATP trust protocol (full) | `crates/eatp/` | Ed25519, multi-sig, reasoning traces |
| Trust-plane with file locking | `crates/trust-plane/` | Dual-lock, glob constraints |
| Shadow enforcer | `crates/kailash-kaizen/` | Dual-config rollout |
| Atomic circuit breaker FSM | `crates/kailash-kaizen/` | All-atomic, DashMap-backed |
| Three-layer resource lifecycle | `crates/kailash-core/` | Access/Ownership/Lifecycle |
| WASM plugin system | `crates/kailash-plugin/` | Sandboxed extensions |
| 6 language bindings | `bindings/`, `ffi/` | Python, Ruby, Node, WASM, Go, Java |
| 25-435x performance advantage | all crates | Compiled, zero-copy |

---

## Recommended Implementation Order

### Phase 1: Fix critical stubs (estimated: 2-3 days)

1. **M1+M2**: Wire saga step execution to actual node registry -- the SagaCoordinatorNode must look up `step.node_id` in the node registry and execute it, then do the same for compensation nodes
2. **M3**: Wire 2PC participant communication to actual HTTP endpoints or node execution
3. **M4+M5+M6**: Implement workflow state capture and restoration in DurableRequest

### Phase 2: Observability wiring (estimated: 2-3 days)

4. **M7**: Add `/metrics` Prometheus endpoint to WorkflowServer and EnterpriseWorkflowServer, wiring the existing `MetricsRegistry._export_prometheus()`
5. **S6**: Bridge Kaizen's OpenTelemetry tracing into the core runtime execution pipeline

### Phase 3: Production durability (estimated: 3-5 days)

6. **S1**: Ship a SQLite-based EventStore backend (the tracking system already uses SQLite with WAL -- reuse that pattern)
7. **S4**: Persist the dead letter queue and add DLQ monitoring
8. **S7**: Implement coordinated graceful shutdown across all subsystems

### Phase 4: Workflow interaction (estimated: 5-7 days)

9. **S2**: Implement workflow signal and query handlers -- allow external callers to send signals to running workflows (e.g., approval) and query workflow state
10. **S3**: Add a built-in scheduler (APScheduler integration or custom) with cron expression support
11. **S8**: Implement workflow versioning with version-aware routing

### Phase 5: Scale-out readiness (estimated: 5-10 days)

12. **S5**: Distributed circuit breaker state via Redis
13. **S9**: Multi-worker architecture with task queue (recommend ARQ or custom Redis-based queue)
14. **N1**: Continue-as-new pattern for long-running workflows

### Phase 6: Polish (estimated: 2-3 days)

15. **N2**: Upgrade dashboard to WebSocket-based live updates
16. **N3**: Kubernetes manifests and Helm chart
17. **N4**: System-wide resource quotas
18. **N5**: Default persistent EventStore backend
19. **N7**: Integrate connection dashboard into main server

---

## Total Estimated Effort

| Phase | Description | Effort | Priority |
|-------|-------------|--------|----------|
| 1 | Fix critical stubs | 2-3 days | MUST |
| 2 | Observability wiring | 2-3 days | MUST |
| 3 | Production durability | 3-5 days | SHOULD |
| 4 | Workflow interaction | 5-7 days | SHOULD |
| 5 | Scale-out readiness | 5-10 days | SHOULD |
| 6 | Polish | 2-3 days | NICE |
| **Total** | | **19-31 days** | |

---

## Files Referenced

Core durability:
- `/src/kailash/nodes/transaction/saga_coordinator.py`
- `/src/kailash/nodes/transaction/saga_state_storage.py`
- `/src/kailash/nodes/transaction/two_phase_commit.py`
- `/src/kailash/middleware/gateway/checkpoint_manager.py`
- `/src/kailash/middleware/gateway/durable_request.py`
- `/src/kailash/middleware/gateway/event_store.py`
- `/src/kailash/core/resilience/circuit_breaker.py`

Monitoring/visibility:
- `/src/kailash/monitoring/metrics.py`
- `/src/kailash/visualization/dashboard.py`
- `/src/kailash/visualization/api.py`
- `/src/kailash/tracking/manager.py`
- `/src/kailash/tracking/storage/database.py`
- `/src/kailash/servers/enterprise_workflow_server.py`

Developer experience:
- `/src/kailash/testing/__init__.py`
- `/src/kailash/runtime/testing.py`
- `/src/kailash/workflow/resilience.py`
- `/src/kailash/nodes/api/rate_limiting.py`

Infrastructure:
- `/src/kailash/core/resilience/bulkhead.py`
- `/src/kailash/middleware/gateway/deduplicator.py`
- `/packages/kailash-kaizen/src/kaizen/core/autonomy/observability/tracing_manager.py`
- `/packages/trust-plane/src/trustplane/delegation.py`
