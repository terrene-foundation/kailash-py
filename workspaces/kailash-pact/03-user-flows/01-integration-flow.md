# User Flows: kailash-pact Integration

## Flow 1: Developer Installing kailash-pact

### Current State (BROKEN)

```bash
pip install kailash-pact
# Fails: eatp>=0.1.0 doesn't exist on PyPI (merged into kailash)
```

### Target State

```bash
pip install kailash>=2.0.0        # Core SDK with trust subsystem
pip install kailash-pact           # Governance framework
```

```python
from pact.governance import GovernanceEngine, compile_org
from pact.governance.config import ConstraintEnvelopeConfig

# Define org
org = OrgDefinition(...)
engine = GovernanceEngine(org)

# Check access
verdict = engine.verify_action(
    role_address="Engineering/Backend/Senior_Dev",
    action="deploy_to_production",
    context={"environment": "production"}
)
print(verdict)  # GovernanceVerdict(decision=ALLOWED, ...)
```

## Flow 2: Developer Using Governed Kaizen Agents

### Target State

```python
from kailash_kaizen import BaseAgent
from pact.governance import GovernanceEngine, PactGovernedAgent
from pact.governance.config import ConstraintEnvelopeConfig, FinancialConstraintConfig

# Create agent
agent = BaseAgent(name="data-analyst", signature="analyze {dataset}")

# Wrap with governance
engine = GovernanceEngine(org)
governed = PactGovernedAgent(
    agent=agent,
    engine=engine,
    role_address="Analytics/DataScience/Analyst",
)

# Agent execution is now governed
result = governed.run(dataset="customer_churn")
# GovernanceEngine checks clearance, envelope, access before execution
```

## Flow 3: Compliance Officer Defining Org via YAML

```yaml
# org.yaml
organization:
  name: "Acme Corp"
  departments:
    - name: Engineering
      teams:
        - name: Backend
          roles:
            - name: Senior_Dev
              clearance: CONFIDENTIAL
              envelope:
                financial:
                  max_spend_usd: 5000
                operational:
                  max_actions_per_hour: 100
        - name: ML
          roles:
            - name: Data_Scientist
              clearance: SECRET
              compartments: [customer_data, model_weights]

  bridges:
    - from: Engineering/Backend/Senior_Dev
      to: Engineering/ML/Data_Scientist
      type: standing
      max_classification: RESTRICTED

  knowledge_share_policies:
    - from_department: Engineering
      to_team: ML
      max_classification: CONFIDENTIAL
```

```python
from pact.governance import load_org_yaml, GovernanceEngine

org = load_org_yaml("org.yaml")
engine = GovernanceEngine(org)
```

## Flow 4: Auditor Reviewing Governance Decisions

```python
from pact.governance import GovernanceEngine
from pact.governance.audit import AuditChain

# Engine with audit trail
chain = AuditChain(chain_id="acme-audit-2026-q1")
engine = GovernanceEngine(org, audit_chain=chain)

# After operations...
for anchor in chain.anchors:
    print(f"{anchor.action} by {anchor.agent_id}: {anchor.result}")
    print(f"  Reasoning: {anchor.reasoning_trace}")
```

## Flow 5: REST API for External Governance Queries

```python
from pact.governance.api.router import create_governance_app

app = create_governance_app(engine, auth_token="secret")

# Endpoints:
# POST /governance/verify     — verify an action
# GET  /governance/envelope    — get effective envelope for a role
# GET  /governance/clearance   — get clearance for a role
# POST /governance/bridge      — create a cross-functional bridge
# GET  /governance/org         — get compiled org structure
# GET  /governance/explain     — explain an access decision
```

## Flow 6: CI Integration Testing

```bash
# In unified CI workflow
cd packages/kailash-pact
pip install -e ".[dev]"
pip install -e ../..  # kailash core (editable)
pytest tests/ -v --timeout=120
```

## Flow 7: Vertical Platform Integration (Astra/Arbor)

```python
# In a vertical platform (e.g., Astra)
from pact.governance import GovernanceEngine, load_org_yaml
from pact.governance.middleware import PactGovernanceMiddleware

# Load org from vertical's config
org = load_org_yaml("astra-org.yaml")
engine = GovernanceEngine(org, persist="sqlite:///governance.db")

# Add middleware to FastAPI app
app.add_middleware(PactGovernanceMiddleware, engine=engine)
# All endpoints now governed by PACT
```
