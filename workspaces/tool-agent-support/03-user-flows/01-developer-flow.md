# User Flow 1: Developer Building and Deploying a Tool Agent

**Persona**: Alex, a Python developer using COC methodology (Claude Code + MCP)
**Goal**: Build a "market-analyzer" agent, validate it in a composite pipeline, deploy to CARE Platform
**Deliverables exercised**: P1, P2, P3, P5, P6

---

## Flow Diagram

```
[1. Write Agent] → [2. Introspect] → [3. Create Manifest] → [4. Validate Composition]
                                                                       ↓
[8. Monitor Trust] ← [7. Discover via Catalog] ← [6. Deploy] ← [5. Budget Check]
```

---

## Step-by-Step

### Step 1: Write the Agent (existing Kaizen pattern)

Alex writes a Kaizen BaseAgent:

```python
# agents/market_analyzer.py
from kaizen.core.agents import BaseAgent
from kaizen.signatures.core import Signature

class MarketAnalyzerSignature(Signature):
    """Analyzes market data for portfolio rebalancing."""
    market_data: str
    analysis_type: str = "comprehensive"
    # Output
    risk_score: float
    recommendations: list[str]

class MarketAnalyzer(BaseAgent):
    signature = MarketAnalyzerSignature
    tools = ["search_market_data", "calculate_risk"]
```

**Deliverable**: None (existing Kaizen pattern)
**MCP tool**: None (developer writes code)

---

### Step 2: Introspect the Agent (P1)

Alex (or COC) introspects the agent to extract metadata:

```python
from kaizen.deploy import introspect_agent

info = introspect_agent("agents.market_analyzer", "MarketAnalyzer")
# Returns:
# {
#     "name": "MarketAnalyzer",
#     "module": "agents.market_analyzer",
#     "description": "Analyzes market data for portfolio rebalancing.",
#     "input_schema": {"market_data": "str", "analysis_type": "str"},
#     "output_schema": {"risk_score": "float", "recommendations": "list[str]"},
#     "tools": ["search_market_data", "calculate_risk"],
#     "capabilities": ["market_research", "risk_analysis"]
# }
```

**Via MCP** (P2, future): `validate_agent_code("agents.market_analyzer", "MarketAnalyzer")`

**Deliverable**: P1 (deploy/introspect.py)

---

### Step 3: Create Manifest (P1)

Alex creates `kaizen.toml`:

```toml
[agent]
name = "market-analyzer"
module = "agents.market_analyzer"
class = "MarketAnalyzer"

[agent.metadata]
description = "Analyzes market data for portfolio rebalancing"
capabilities = ["market_research", "risk_analysis"]

[agent.capabilities]
tools = ["search_market_data", "calculate_risk"]
supported_models = ["claude-sonnet-4-20250514", "gpt-4o"]

[governance]
purpose = "Market data analysis for portfolio rebalancing"
risk_level = "medium"
data_access_needed = ["market_data"]
suggested_posture = "supervised"
```

Or programmatically:

```python
from kaizen.manifest import AgentManifest

manifest = AgentManifest.from_introspection(info)
manifest.governance.purpose = "Market data analysis for portfolio rebalancing"
manifest.governance.risk_level = "medium"
manifest.governance.suggested_posture = "supervised"
manifest.to_toml("kaizen.toml")
```

**Deliverable**: P1 (manifest/agent.py, manifest/governance.py, manifest/loader.py)

---

### Step 4: Validate Composite Pipeline (P3)

Alex builds a 3-agent composite and validates before deployment:

```python
from kaizen.composition import validate_dag, check_schema_compatibility

composition = [
    {"name": "document-classifier", "inputs_from": []},
    {"name": "market-analyzer", "inputs_from": ["document-classifier"]},
    {"name": "risk-reporter", "inputs_from": ["market-analyzer"]},
]

# DAG validation
result = validate_dag(composition)
assert result.is_valid  # No cycles
assert result.topological_order == ["document-classifier", "market-analyzer", "risk-reporter"]

# Schema compatibility between agents
compat = check_schema_compatibility(
    output_schema=classifier_output_schema,
    input_schema=analyzer_input_schema,
)
assert compat.compatible  # Schemas pipe correctly
```

**Via MCP** (P2): `catalog_deps("composite-analyzer")` and `catalog_check_compatibility(...)`

**Deliverable**: P3 (composition/dag_validator.py, composition/schema_compat.py)

---

### Step 5: Budget Check (P6)

Before deployment, check budget availability:

```python
from kaizen.core.autonomy.budget import BudgetTracker

tracker = BudgetTracker(allocated=500.00)
estimate = tracker.check(estimated_cost=0.05)  # Per-invocation estimate
# {"allowed": True, "remaining": 500.00, "monthly": 500.00, "consumed": 0.00}
```

**Deliverable**: P6 (budget/tracker.py)

---

### Step 6: Deploy Agent (P1)

Deploy to CARE Platform (or local registry):

```python
from kaizen.deploy import deploy

# Remote deployment to CARE Platform
result = deploy(manifest, target_url="https://care.example.com/api/agents", api_key="...")

# OR local-only (no CARE Platform required)
result = deploy(manifest)  # Registers in local file-based registry
```

**Via MCP** (P2): `deploy_agent("kaizen.toml")`

**Deliverable**: P1 (deploy/client.py)

---

### Step 7: Discover via Catalog (P2)

Other developers (or COC) discover the agent:

```
# Via MCP tool call (COC conversation)
catalog_search(query="market analysis", capabilities=["risk_analysis"])
→ [{"name": "market-analyzer", "posture": "supervised", "cost_avg": "$0.05", ...}]

catalog_describe("market-analyzer")
→ Full detail: schema, constraints, performance, access, governance

catalog_schema("market-analyzer")
→ Input/output JSON Schema for code generation
```

**Deliverable**: P2 (catalog_server/tools/discovery.py)

---

### Step 8: Monitor Trust Evolution (P5)

The deployed agent starts under SUPERVISED posture. Over time:

```python
from eatp.postures import PostureStateMachine, PostureEvidence, TrustPosture

# After 100 successful executions...
evidence = PostureEvidence(
    observation_count=100,
    success_rate=0.97,
    time_at_current_posture_hours=168.0,  # 1 week
    anomaly_count=1,
    source="automated_monitor",
)

# Posture upgrade evaluation
machine = PostureStateMachine()
request = machine.create_upgrade_request(
    agent_id="market-analyzer",
    current=TrustPosture.SUPERVISED,
    target=TrustPosture.SHARED_PLANNING,
    evidence=evidence,
)
result = machine.transition(request)
# result.success == True → agent now at SHARED_PLANNING
```

**Deliverable**: P5 (postures.py extensions)

---

## COC Conversation Example

```
Developer: "I need a market analysis agent that scores risk and recommends rebalancing"

COC/Claude: [calls catalog_search("market analysis", capabilities=["risk_analysis"])]
  → "I found 0 matching agents. I'll build one. Let me scaffold it."

COC/Claude: [writes MarketAnalyzer agent code]
  → [calls validate_agent_code("agents.market_analyzer", "MarketAnalyzer")]
  → "Agent validates. Extracting manifest..."

COC/Claude: [calls introspect_agent(...)]
  → [generates kaizen.toml with governance section]
  → "Manifest ready. Suggested posture: supervised. Deploy?"

Developer: "Yes, deploy it and add it to the document-review composite"

COC/Claude: [calls validate_dag([...composite with market-analyzer...])]
  → "DAG is valid. Checking schema compatibility..."
  → [calls check_schema_compatibility(classifier_output, analyzer_input)]
  → "Compatible. Deploying..."
  → [calls deploy_agent("kaizen.toml")]
  → "Deployed under SUPERVISED posture. It will need 100 successful ops to earn SHARED_PLANNING."
```

---

## Error Paths

| Step | Error                 | Handling                                                                                       |
| ---- | --------------------- | ---------------------------------------------------------------------------------------------- |
| 2    | Agent class not found | `introspect_agent` raises `ModuleNotFoundError` with clear message                             |
| 3    | Invalid TOML          | `AgentManifest.from_toml` raises `ManifestValidationError` with field-level details            |
| 4    | Cycle detected        | `validate_dag` returns `ValidationResult(is_valid=False, cycles=[...])`                        |
| 4    | Schema incompatible   | `check_schema_compatibility` returns `CompatibilityResult(compatible=False, mismatches=[...])` |
| 5    | Budget exceeded       | `tracker.check` returns `{allowed: False}`, `tracker.reserve` returns `False`                  |
| 6    | CARE API unreachable  | `deploy` falls back to local registry, returns `DeployResult(mode="local")`                    |
| 6    | Auth failed           | `deploy` raises `DeployAuthError` with instructions                                            |
