# User Flows: Production Readiness

**Date**: 2026-03-17

---

## Flow 1: Enterprise POC Evaluation (Current — Broken)

```
Enterprise team → Install kailash → Define saga workflow → Execute saga
                                                              ↓
                                          All steps return fake "success"
                                                              ↓
                                          Team inspects downstream services
                                                              ↓
                                          Nothing actually happened
                                                              ↓
                                          Trust destroyed → SDK disqualified
```

## Flow 2: Enterprise POC Evaluation (After Phase 1)

```
Enterprise team → Install kailash → Define saga workflow → Execute saga
                                                              ↓
                                          NodeExecutor resolves step.node_id
                                                              ↓
                                          Real nodes execute, real results return
                                                              ↓
                                          Step fails → Compensation runs real rollback
                                                              ↓
                                          POC validates → Proceed to production eval
```

---

## Flow 3: Production Deployment (Current — Missing Observability)

```
SRE team → Deploy kailash service → Configure Prometheus scrape
                                        ↓
                              GET /metrics → 404
                                        ↓
                              No dashboards, no alerts
                                        ↓
                              Incident detected by users, not monitoring
```

## Flow 4: Production Deployment (After Phase 2)

```
SRE team → Deploy kailash service → Configure Prometheus scrape
                                        ↓
                              GET /metrics → Prometheus text format
                                        ↓
                              Grafana dashboards + alerting configured
                                        ↓
                              OTel traces visible in Jaeger
                                        ↓
                              Proactive incident detection
```

---

## Flow 5: Failure Recovery (Current — Re-executes Everything)

```
Long workflow (100 steps) → Crash at step 47 → Operator resumes from checkpoint
                                                        ↓
                                            _restore_workflow_state() is pass
                                                        ↓
                                            Workflow re-executes steps 1-100
                                                        ↓
                                            Duplicate side effects (double charges, duplicate orders)
```

## Flow 6: Failure Recovery (After Phase 2)

```
Long workflow (100 steps) → Crash at step 47 → Operator resumes from checkpoint
                                                        ↓
                                            ExecutionTracker loads cached results 1-46
                                                        ↓
                                            Workflow resumes from step 47
                                                        ↓
                                            No duplicate side effects
```

---

## Flow 7: Human-in-the-Loop (Current — Not Possible)

```
Approval workflow → Node needs human decision → ??? No signal mechanism
                                                        ↓
                                            Must use external system (Slack bot, email polling)
                                                        ↓
                                            Complex integration, brittle coordination
```

## Flow 8: Human-in-the-Loop (After Phase 4)

```
Approval workflow → Node awaits signal → External caller sends approval
                                              ↓
                                    runtime.signal(workflow_id, "approve", data)
                                              ↓
                                    Node receives signal, continues execution
                                              ↓
                                    Clean, SDK-native HITL pattern
```

---

## Implementation Flow (Developer Experience)

### Phase 1 Developer Flow

```
Developer → Read saga_coordinator.py → See NodeExecutor protocol
         → Configure SagaCoordinatorNode(executor=RegistryNodeExecutor(registry))
         → Define saga steps with real node_ids
         → Execute saga → Steps invoke real nodes
         → Step fails → Compensation invokes real rollback nodes
```

### Phase 2 Developer Flow

```
Developer → Enable checkpointing: DurableRequest(checkpoint_manager=mgr)
         → Execute workflow → Crash mid-execution
         → Resume: request.resume() → Skips completed nodes
         → Enable event persistence: EventStore(storage_backend=SqliteBackend("events.db"))
         → Events survive restart
```

### Phase 3 Developer Flow

```
Developer → pip install kailash[otel]
         → Set OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
         → Execute workflow → Traces appear in Jaeger
         → Workflow span contains node-level child spans
```

---

## Stakeholder Decision Points

| Decision                 | Options                                                          | Recommendation                            | Impact                                 |
| ------------------------ | ---------------------------------------------------------------- | ----------------------------------------- | -------------------------------------- |
| SDK vs Engine scope      | (a) SDK only (b) Full engine                                     | SDK only — defer engine items             | Reduces scope from 19-31 to 12-18 days |
| 2PC transport            | (a) Local only (b) HTTP (c) Pluggable                            | Pluggable with local default              | Unblocks Phase 1 now, HTTP added later |
| Checkpoint granularity   | (a) All nodes (b) Opt-in                                         | All nodes, auto-detect serializable       | Simplest UX, handles 90% of cases      |
| OTel dependency          | (a) Bridge from Kaizen (b) Independent                           | Independent — core can't depend on Kaizen | Clean dependency direction             |
| Stub treatment for X1-X8 | (a) Fix now (b) Replace with NotImplementedError (c) Leave as-is | Replace with NotImplementedError          | Honest stubs, no fake results          |
