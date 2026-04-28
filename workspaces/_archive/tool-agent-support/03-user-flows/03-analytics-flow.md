# User Flow 3: Analytics and Monitoring

**Persona**: Sarah, application operator monitoring agent performance
**Goal**: Track agent metrics, budget utilization, and posture evolution across her application
**Deliverables exercised**: P4, P5, P6

---

## Flow Diagram

```
[1. Query Agent Metrics] → [2. Aggregate by Status] → [3. Check Budget Burn]
                                                              ↓
[6. Export Report] ← [5. View Posture History] ← [4. Identify Cost Trends]
```

---

## Step-by-Step

### Step 1: Query Agent Metrics (P4)

Sarah queries aggregated metrics for her application:

```python
from dataflow.query import count_by, sum_by, aggregate

# How many invocations per agent status?
status_counts = await count_by(db, AgentInvocation, group_by="status")
# {"success": 1234, "failed": 23, "timeout": 5}

# Total cost by agent?
cost_by_agent = await sum_by(db, AgentInvocation, sum_field="cost_usd", group_by="agent_name")
# {"market-analyzer": 45.67, "document-classifier": 12.34, "pii-redactor": 8.90}

# Multi-aggregation with filter
daily_stats = await aggregate(db, AgentInvocation, [
    {"function": "count", "field": "*"},
    {"function": "avg", "field": "latency_ms"},
    {"function": "sum", "field": "cost_usd"},
], group_by="date", filter={"agent_name": "market-analyzer"})
```

**Deliverable**: P4 (query/aggregation.py)

---

### Step 2: Check Budget Burn Rate (P6)

```python
from kaizen.core.autonomy.budget import BudgetTracker

tracker = BudgetTracker(allocated=500.00, consumed=127.50)

# Current status
remaining = tracker.remaining()  # Decimal('372.50')

# Projected burn
daily_avg = Decimal('4.25')  # From P4 aggregation
days_remaining = remaining / daily_avg  # ~87 days
```

**Deliverable**: P6 (budget/tracker.py), P4 (provides the data)

---

### Step 3: View Posture History (P5)

```python
from eatp.posture_store import SQLitePostureStore

store = SQLitePostureStore("postures.db")
history = store.get_history("market-analyzer", limit=10)
# [
#   TransitionResult(from=SUPERVISED, to=SHARED_PLANNING, timestamp=..., success=True),
#   TransitionResult(from=PSEUDO_AGENT, to=SUPERVISED, timestamp=..., success=True),
# ]
```

**Deliverable**: P5 (posture_store.py)

---

## Deliverable Integration Map

```
P4 (Aggregation) ──→ Provides metrics data
                         ↓
P6 (Budget) ←────── Feeds budget projections ──→ P5 (Posture)
                                                      ↓
                                              Drives governance decisions
```

The analytics flow demonstrates how P4, P5, and P6 form a feedback loop:

- P4 aggregates raw invocation data
- P6 tracks budget consumption from P4 data
- P5 uses evidence from P4/P6 to drive posture evolution
