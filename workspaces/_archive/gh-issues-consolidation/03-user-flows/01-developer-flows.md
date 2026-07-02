# Developer Flows — How Each Feature Changes the Developer Experience

## Flow 1: PACT Engine — Before and After

### Before (current)

```python
engine = PactEngine(
    org=my_org,
    budget_usd=100.0,
    model="claude-sonnet-4-6",
)

# Submit task — governance checks ONCE at submit time
result = await engine.submit(
    role="org/engineering/R/alice",
    objective="Analyze customer data and send summary email",
)
# Problem: After submit gate passes, alice's agent can:
# - Read data outside her knowledge compartment (no per-node check)
# - Send emails during blackout hours (temporal not enforced per-action)
# - Exceed per-step financial limits (budget only checked upfront)

# Second submit reuses cached supervisor with stale budget
result2 = await engine.submit(role="org/engineering/R/alice", objective="...")
# Problem: Budget from first submit not reflected

# Agent code can escalate privileges
engine.governance.update_envelope(...)  # Mutable engine exposed
```

### After (with #234-#241 fixes)

```python
engine = PactEngine(
    org=my_org,
    budget_usd=100.0,
    model="claude-sonnet-4-6",
    enforcement_mode=EnforcementMode.SHADOW,  # #239: Safe rollout
    on_held=my_approval_handler,              # #238: Human review for HELD verdicts
)
# Init logs warnings for degenerate envelopes (#241)

# Submit task — governance enforced on EVERY node execution
result = await engine.submit(
    role="org/engineering/R/alice",
    objective="Analyze customer data and send summary email",
)
# Now: Each node (read_data, send_email) checked against alice's envelope
# - blocked_actions enforced per-node (#234)
# - temporal blackout enforced per-node (#234)
# - budget freshly computed per submit (#235)
# - NaN budget_consumed safely handled (#237)

# HELD verdicts trigger human review instead of blocking
# on_held callback can persist hold, await approval, resume (#238)

# Read-only governance — no privilege escalation
engine.governance  # Returns frozen view (#236)
# engine.governance.update_envelope(...)  → AttributeError

# Shadow mode logs all verdicts but doesn't block (#239)
# Switch to enforce after calibrating envelopes
engine.enforcement_mode = EnforcementMode.ENFORCE
```

---

## Flow 2: Bridge Approval — Before and After

### Before (current)

```python
gov = GovernanceEngine(org)
gov.compile_org()

# Vacant role can approve bridges — no vacancy check
gov.approve_bridge(
    source_address="org/finance/R/vacant_role",  # Role has no occupant!
    target_address="org/engineering/R/bob",
    approver_address="org/R/ceo",  # CEO is also vacant — still works
)

# No way to reject a bridge
# No reject_bridge() method exists
```

### After (#231 fix)

```python
gov = GovernanceEngine(org)
gov.compile_org()

# Vacant approver blocked
try:
    gov.approve_bridge(
        source_address="org/finance/R/analyst",
        target_address="org/engineering/R/bob",
        approver_address="org/R/vacant_ceo",
    )
except PactError as e:
    # "Bridge approval cannot be given by vacant role 'org/R/vacant_ceo'"

# Can now explicitly reject bridges
gov.reject_bridge(
    source_address="org/finance/R/analyst",
    target_address="org/engineering/R/bob",
    rejector_address="org/R/ceo",
)
```

---

## Flow 3: Nexus Observability — Before and After

### Before (current)

```python
app = Nexus("MyApp")
app.register_workflow("process", workflow)
await app.start()

# No way to monitor in Prometheus
# No way to stream events to browser
# get_performance_metrics() returns raw dict — not scrapeable
```

### After (#233)

```python
app = Nexus("MyApp")
app.register_workflow("process", workflow)
await app.start()

# Prometheus: scrape /metrics
# curl http://localhost:8000/metrics
# nexus_workflow_registration_seconds{workflow="process"} 0.042
# nexus_cross_channel_sync_seconds 0.015
# nexus_active_sessions 3

# SSE: stream events to browser
# const events = new EventSource("/events/stream?event_type=workflow.*");
# events.onmessage = (e) => console.log(JSON.parse(e.data));

# Python: subscribe programmatically
url = app.event_bus.sse_url()  # Returns "/events/stream"
```

---

## Flow 4: DataFlow Audit Trail — Before and After

### Before (current)

```python
db = DataFlow(models=[User, Order])
await db.start()

# Write events fire but vanish on restart
await db.express.create("User", {"id": "u1", "name": "Alice"})
# InMemoryEventBus receives event... lost if process crashes

# No way to answer: "Who changed user u1 last month?"
```

### After (#243)

```python
db = DataFlow(models=[User, Order], audit=True)
await db.start()

# Write events now persisted to database
await db.express.create("User", {"id": "u1", "name": "Alice"})
# Event stored in audit_events table

# Query audit trail
trail = await db.audit.get_trail("User", "u1")
# [{"event_type": "create", "timestamp": ..., "user_id": ..., "changes": {...}}]

# Compliance query: all changes in March
events = await db.audit.query(
    entity_type="User",
    start_time="2026-03-01",
    end_time="2026-04-01",
)
```

---

## Flow 5: ProvenancedField — Before and After

### Before (current)

```python
@db.model
class LoanEntry:
    outstanding_usd: float = 70_000_000.0
    # Where did this number come from? How reliable? What was it before?
    # No way to know.
```

### After (#242)

```python
from kailash.dataflow import Provenance

@db.model
class LoanEntry:
    outstanding_usd: Provenance[float]

# Create with provenance
await db.express.create("LoanEntry", {
    "outstanding_usd": {
        "value": 70_000_000.0,
        "source_type": "excel_cell",
        "source_detail": "Master File Sheet A1:B50",
        "confidence": 0.95,
    }
})

# Query by confidence
reliable = await db.express.list("LoanEntry", {
    "outstanding_usd.confidence": {"$gte": 0.9}
})

# Previous value tracked automatically on updates
await db.express.update("LoanEntry", "loan1", {
    "outstanding_usd": {"value": 65_000_000.0, "source_type": "api_query"}
})
# previous_value automatically set to 70_000_000.0
```

---

## Flow 6: Consumer Adapters — Before and After

### Before (current)

```python
@db.product("portfolio", mode="materialized")
async def portfolio(ctx):
    return {"loans": [...], "market": {...}}

# Every consumer gets the same raw data
# REST API, MCP tool, dashboard, chat — all must transform themselves
```

### After (#244)

```python
@db.product("portfolio", mode="materialized",
    consumers=["maturity_report", "chat_summary", "excel_export"])
async def portfolio(ctx):
    return {"loans": [...], "market": {...}}

# Register consumer-specific transforms
db.fabric.register_consumer("maturity_report", to_maturity_report)
db.fabric.register_consumer("chat_summary", to_chat_summary)
db.fabric.register_consumer("excel_export", to_excel_export)

# Consumers access their specific view
# GET /fabric/portfolio?consumer=maturity_report
# GET /fabric/portfolio?consumer=chat_summary
# GET /fabric/portfolio  → canonical data (no consumer param)
```
