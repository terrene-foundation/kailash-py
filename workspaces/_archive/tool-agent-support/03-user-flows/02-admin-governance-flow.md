# User Flow 2: Platform Admin Governing Tool Agents

**Persona**: Marcus, platform admin at an enterprise using CARE Platform
**Goal**: Approve application grants, manage posture progression, monitor budgets
**Deliverables exercised**: P1, P2, P5, P6

---

## Flow Diagram

```
[1. App Registration Request] → [2. Review Manifest] → [3. Approve Operating Envelope]
                                                                    ↓
[7. Codify Template] ← [6. Review Posture Evidence] ← [5. Monitor Budget] ← [4. Agents Auto-Govern]
```

---

## Step-by-Step

### Step 1: Application Registration Request

Developer Alex submits an application registration via `app.toml`:

```toml
[application]
name = "contract-review-tool"
description = "Contract review pipeline for legal team"
owner = "alex.chen@example.com"
org_unit = "risk-management"
duration = "6 months"

[application.agents_requested]
agents = ["document-classifier", "pii-redactor", "compliance-checker", "market-analyzer"]
justification = "Need document processing and compliance checking for contract review"

[application.budget]
monthly = 500
```

Marcus receives this via CARE Platform dashboard or MCP tool:

```
# Marcus via MCP (COC for governance)
app_status("contract-review-tool")
→ {
    "status": "pending_approval",
    "owner": "alex.chen@example.com",
    "agents_requested": ["document-classifier", "pii-redactor", "compliance-checker", "market-analyzer"],
    "budget_monthly": 500,
    "justification": "..."
  }
```

**Deliverable**: P1 (manifest/app.py), P2 (tools/application.py)

---

### Step 2: Review Manifest Governance Section

Marcus reviews the governance metadata for each requested agent:

```
catalog_describe("market-analyzer")
→ {
    "governance": {
      "purpose": "Market data analysis for portfolio rebalancing",
      "risk_level": "medium",
      "data_access_needed": ["market_data"],
      "suggested_posture": "supervised"
    },
    "posture": "SUPERVISED",
    "trust_score": "B+ (0.78)",
    "cost_per_call_avg": "$0.05 (last 30d, 1.2K calls)"
  }
```

**Deliverable**: P1 (manifest/governance.py), P2 (tools/discovery.py)

---

### Step 3: Approve Operating Envelope

Marcus approves the application with an Operating Envelope that covers all requested agents:

- Allowed capabilities: `[document_processing, compliance_checking, risk_analysis, market_research]`
- Allowed tools: `[file-reader, taxonomy-lookup, search_market_data, calculate_risk]`
- Budget ceiling: $500/month
- Posture ceiling: SHARED_PLANNING (agents can earn up to this, not beyond)
- Duration: 6 months (renewable)

Within this envelope, agents auto-govern on deployment. No per-agent approval needed.

**Deliverable**: P5 (posture ceiling), P6 (budget ceiling)

---

### Step 4: Agents Auto-Govern Within Envelope

When Alex deploys agents within the approved envelope:

```
deploy_agent("kaizen.toml")
→ {
    "agent_name": "market-analyzer",
    "status": "active",           ← NOT "draft" — auto-governed within envelope
    "governance_match": true,
    "envelope_check": "capabilities=['market_research','risk_analysis'] ⊆ envelope",
    "posture": "SUPERVISED",
    "trust_chain": "genesis → marcus-approval → alex-delegation"
  }
```

No queue. No wait. The Operating Envelope pre-authorized this.

**Deliverable**: P1 (deploy), P5 (posture assignment)

---

### Step 5: Monitor Budget Consumption

Marcus monitors budget across applications:

```python
from kaizen.core.autonomy.budget import BudgetTracker

# Application budget view
tracker = BudgetTracker(allocated=500.00, consumed=127.50)
status = tracker.check(estimated_cost=0.05)
# {"allowed": True, "remaining": 372.50, "monthly": 500.00, "consumed": 127.50}

# Alert thresholds
# At 80% ($400 consumed): Marcus gets notified
# At 95% ($475 consumed): Agent posture auto-downgrades to SUPERVISED
# At 100% ($500 consumed): Agent invocations blocked
```

**Via MCP** (P2, future): `budget_status("contract-review-tool")`

**Deliverable**: P6 (budget/tracker.py), P5 (posture-budget integration)

---

### Step 6: Review Posture Evidence

After weeks of operation, the market-analyzer agent has accumulated evidence:

```python
from eatp.postures import PostureEvidence, EvaluationResult, TrustPosture

evidence = PostureEvidence(
    observation_count=500,
    success_rate=0.98,
    time_at_current_posture_hours=720.0,  # 30 days
    anomaly_count=3,
    source="automated_monitor",
)

# System recommends upgrade
evaluation = EvaluationResult(
    decision="approved",
    rationale="Success rate 98% exceeds 95% threshold. 500 operations over 30 days. 3 anomalies within tolerance.",
    suggested_posture=TrustPosture.SHARED_PLANNING,
    evidence_summary=evidence.to_dict(),
    evaluator_id="posture-evaluator-auto",
)
```

Marcus reviews the evidence and approves (or the system auto-approves per template):

```python
machine = PostureStateMachine()
result = machine.transition(upgrade_request)
# result.success == True → market-analyzer now at SHARED_PLANNING
```

**Deliverable**: P5 (PostureEvidence, EvaluationResult, PostureStateMachine)

---

### Step 7: Codify Governance Template

After manually governing several similar agents, Marcus creates a governance template:

```python
# Template: "medium-risk-analytics"
# Applies to: agents with risk_level="medium" and capabilities containing "risk_analysis"
# Auto-governance rules:
#   - Start at SUPERVISED
#   - Upgrade to SHARED_PLANNING after 500 ops, 95% success, 30 days
#   - Upgrade to CONTINUOUS_INSIGHT after 2000 ops, 98% success, 90 days
#   - Never auto-upgrade beyond CONTINUOUS_INSIGHT (requires manual for DELEGATED)
#   - Budget ceiling: $1000/month per application
#   - Data access: market_data (read-only), no PII, no external
```

Future agents matching this template auto-govern without Marcus's intervention.

**Deliverable**: P1 (governance metadata matches templates), P5 (posture progression rules)

---

## Emergency Flow: Posture Downgrade

```
[Anomaly detected] → [Evidence threshold crossed] → [Emergency downgrade]
     ↓                                                       ↓
[Marcus notified] ← [Audit trail recorded] ← [Agent at PSEUDO_AGENT]
```

```python
# Budget exhaustion triggers automatic downgrade
if tracker.remaining() <= 0:
    machine.emergency_downgrade(
        agent_id="market-analyzer",
        reason="budget_exhausted",
        initiated_by="system:budget_monitor",
    )
    # → Agent immediately at PSEUDO_AGENT
    # → All invocations require explicit approval
    # → Audit trail records: who, when, why
```

**Deliverable**: P5 (emergency_downgrade), P6 (threshold events)

---

## Governance Decision Points

| Decision                 | Data Source                               | Deliverable |
| ------------------------ | ----------------------------------------- | ----------- |
| Approve/deny application | App manifest, agent governance metadata   | P1          |
| Set posture ceiling      | Risk level from governance manifest       | P1, P5      |
| Allocate budget          | Application budget request                | P6          |
| Upgrade posture          | PostureEvidence (success rate, ops, time) | P5          |
| Emergency downgrade      | Budget exhaustion, anomaly detection      | P5, P6      |
| Template creation        | Pattern from repeated manual decisions    | P1, P5      |
