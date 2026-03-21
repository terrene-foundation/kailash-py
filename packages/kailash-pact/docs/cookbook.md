# Cookbook

Working recipes for common governance tasks. Each recipe is self-contained and can be run directly.

## Recipe 1: Create an Organization from Python

```python
from pact.build.config.schema import DepartmentConfig, TeamConfig
from pact.build.org.builder import OrgDefinition
from pact.governance.compilation import RoleDefinition, compile_org
from pact.governance.engine import GovernanceEngine

# Define the org structure
org = OrgDefinition(
    org_id="my-org",
    name="My Organization",
    departments=[
        DepartmentConfig(department_id="d-exec", name="Executive"),
        DepartmentConfig(department_id="d-ops", name="Operations"),
    ],
    teams=[
        TeamConfig(id="t-support", name="Support", workspace="ws-support"),
    ],
    roles=[
        RoleDefinition(
            role_id="r-ceo",
            name="CEO",
            is_primary_for_unit="d-exec",
        ),
        RoleDefinition(
            role_id="r-coo",
            name="COO",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-ops",
        ),
        RoleDefinition(
            role_id="r-support-lead",
            name="Support Lead",
            reports_to_role_id="r-coo",
            is_primary_for_unit="t-support",
        ),
    ],
)

engine = GovernanceEngine(org)
compiled = engine.get_org()
for addr in sorted(compiled.nodes.keys()):
    print(f"  {addr}: {compiled.nodes[addr].name}")
```

## Recipe 2: Load an Organization from YAML

```python
from pact.governance.yaml_loader import load_org_yaml
from pact.governance.engine import GovernanceEngine

loaded = load_org_yaml("my-org.yaml")
engine = GovernanceEngine(loaded.org_definition)

print(f"Loaded: {engine.org_name}")
print(f"Departments: {len([n for n in engine.get_org().nodes.values() if n.node_type.value == 'D'])}")
```

## Recipe 3: Set Up Role Envelopes

```python
from pact.governance.envelopes import RoleEnvelope
from pact.build.config.schema import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)

# CEO sets envelope for COO
coo_envelope = RoleEnvelope(
    id="env-coo",
    defining_role_address="D1-R1",      # CEO
    target_role_address="D1-R1-D1-R1",  # COO
    envelope=ConstraintEnvelopeConfig(
        id="env-coo",
        financial=FinancialConstraintConfig(
            max_spend_usd=100000,
            requires_approval_above_usd=25000,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "approve", "hire", "deploy"],
            blocked_actions=["terminate_contract"],
        ),
    ),
)
engine.set_role_envelope(coo_envelope)

# COO sets tighter envelope for Support Lead
support_envelope = RoleEnvelope(
    id="env-support",
    defining_role_address="D1-R1-D1-R1",        # COO
    target_role_address="D1-R1-D1-R1-T1-R1",    # Support Lead
    envelope=ConstraintEnvelopeConfig(
        id="env-support",
        financial=FinancialConstraintConfig(
            max_spend_usd=5000,
            requires_approval_above_usd=1000,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write"],
        ),
    ),
)
engine.set_role_envelope(support_envelope)
```

## Recipe 4: Grant Clearances

```python
from pact.governance.clearance import RoleClearance
from pact.build.config.schema import ConfidentialityLevel

# CEO gets SECRET clearance (self-granted as root authority)
engine.grant_clearance(
    "D1-R1",
    RoleClearance(
        role_address="D1-R1",
        max_clearance=ConfidentialityLevel.SECRET,
        nda_signed=True,
        granted_by_role_address="D1-R1",
    ),
)

# COO gets CONFIDENTIAL clearance
engine.grant_clearance(
    "D1-R1-D1-R1",
    RoleClearance(
        role_address="D1-R1-D1-R1",
        max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        granted_by_role_address="D1-R1",
    ),
)

# Support Lead gets RESTRICTED with a compartment
engine.grant_clearance(
    "D1-R1-D1-R1-T1-R1",
    RoleClearance(
        role_address="D1-R1-D1-R1-T1-R1",
        max_clearance=ConfidentialityLevel.RESTRICTED,
        compartments=frozenset({"customer-data"}),
        granted_by_role_address="D1-R1-D1-R1",
    ),
)
```

## Recipe 5: Create a Cross-Functional Bridge

```python
from pact.governance.access import PactBridge
from pact.build.config.schema import ConfidentialityLevel
from datetime import datetime, timedelta, UTC

# Bilateral standing bridge between CEO and COO
engine.create_bridge(PactBridge(
    id="bridge-exec",
    role_a_address="D1-R1",
    role_b_address="D1-R1-D1-R1",
    bridge_type="standing",
    max_classification=ConfidentialityLevel.CONFIDENTIAL,
    bilateral=True,
))

# Scoped bridge with expiration (for a project)
engine.create_bridge(PactBridge(
    id="bridge-project-x",
    role_a_address="D1-R1-D1-R1",        # COO
    role_b_address="D1-R1-D1-R1-T1-R1",  # Support Lead
    bridge_type="scoped",
    max_classification=ConfidentialityLevel.RESTRICTED,
    operational_scope=("project-x",),
    bilateral=False,  # COO can read Support data, but not reverse
    expires_at=datetime.now(UTC) + timedelta(days=90),
))
```

## Recipe 6: Create a Knowledge Share Policy

```python
from pact.governance.access import KnowledgeSharePolicy
from pact.build.config.schema import ConfidentialityLevel

# Operations shares RESTRICTED data with Support
engine.create_ksp(KnowledgeSharePolicy(
    id="ksp-ops-to-support",
    source_unit_address="D1-R1-D1",          # Operations department
    target_unit_address="D1-R1-D1-R1-T1",    # Support team
    max_classification=ConfidentialityLevel.RESTRICTED,
    created_by_role_address="D1-R1-D1-R1",   # COO authorized
))
```

## Recipe 7: Check Knowledge Access

```python
from pact.governance.knowledge import KnowledgeItem
from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel

# A confidential operations report
report = KnowledgeItem(
    item_id="ops-report-q4",
    classification=ConfidentialityLevel.CONFIDENTIAL,
    owning_unit_address="D1-R1-D1",  # Operations department
)

# CEO checks access at CONTINUOUS_INSIGHT posture
decision = engine.check_access(
    "D1-R1",
    report,
    TrustPostureLevel.CONTINUOUS_INSIGHT,
)
print(f"CEO: allowed={decision.allowed}, reason={decision.reason}")

# Support Lead checks access at SUPERVISED posture
decision = engine.check_access(
    "D1-R1-D1-R1-T1-R1",
    report,
    TrustPostureLevel.SUPERVISED,
)
print(f"Support Lead: allowed={decision.allowed}, reason={decision.reason}")
```

## Recipe 8: Create a Governed Agent

```python
from pact.governance.agent import PactGovernedAgent, GovernanceBlockedError
from pact.governance.decorators import governed_tool
from pact.build.config.schema import TrustPostureLevel

# Define tools with governance metadata
@governed_tool("read", cost=0.0)
def read_document(doc_id: str) -> str:
    return f"Contents of {doc_id}"

@governed_tool("write", cost=10.0)
def write_report(content: str) -> str:
    return f"Report written: {content}"

@governed_tool("deploy", cost=500.0)
def deploy_to_production() -> str:
    return "Deployed to production"

# Create a governed agent for the Support Lead role
agent = PactGovernedAgent(
    engine=engine,
    role_address="D1-R1-D1-R1-T1-R1",
    posture=TrustPostureLevel.SUPERVISED,
)

# Register tools with the agent
agent.register_tool("read", cost=0.0)
agent.register_tool("write", cost=10.0)
agent.register_tool("deploy", cost=500.0)

# Execute through governance
result = agent.execute_tool("read", _tool_fn=lambda: read_document("doc-1"))
print(f"Read result: {result}")

# This will be BLOCKED (deploy is not in allowed_actions for Support Lead)
try:
    agent.execute_tool("deploy", _tool_fn=deploy_to_production)
except GovernanceBlockedError as e:
    print(f"Blocked: {e.verdict.reason}")
```

## Recipe 9: Use the MockGovernedAgent for Testing

```python
from pact.governance.testing import MockGovernedAgent
from pact.governance.decorators import governed_tool
from pact.build.config.schema import TrustPostureLevel

@governed_tool("read", cost=0.0)
def tool_read() -> str:
    return "read_result"

@governed_tool("write", cost=10.0)
def tool_write() -> str:
    return "write_result"

# Script of actions to execute
mock = MockGovernedAgent(
    engine=engine,
    role_address="D1-R1-D1-R1-T1-R1",
    tools=[tool_read, tool_write],
    script=["read", "write", "read"],
    posture=TrustPostureLevel.SUPERVISED,
)

results = mock.run()
print(f"Results: {results}")
# Output: Results: ['read_result', 'write_result', 'read_result']
```

## Recipe 10: Get a Frozen Governance Context

```python
from pact.build.config.schema import TrustPostureLevel

# Get a frozen snapshot of governance state for an agent
ctx = engine.get_context(
    "D1-R1-D1-R1-T1-R1",
    posture=TrustPostureLevel.SUPERVISED,
)

# Inspect the context
print(f"Role: {ctx.role_address}")
print(f"Posture: {ctx.posture.value}")
print(f"Allowed actions: {sorted(ctx.allowed_actions)}")
print(f"Clearance level: {ctx.effective_clearance_level.value}")
print(f"Compartments: {sorted(ctx.compartments)}")

# Serialize for transport
data = ctx.to_dict()
print(f"Serialized: {data}")

# Deserialize
from pact.governance.context import GovernanceContext
restored = GovernanceContext.from_dict(data)
assert restored.role_address == ctx.role_address
```

## Recipe 11: Explain Governance Decisions

```python
from pact.governance.explain import describe_address, explain_access
from pact.governance.knowledge import KnowledgeItem
from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel

# Describe a positional address in human-readable form
description = describe_address("D1-R1-D1-R1-T1-R1", engine.get_org())
print(description)
# Output: Support Lead (Support > Operations)

# Get a step-by-step trace of an access decision
item = KnowledgeItem(
    item_id="secret-report",
    classification=ConfidentialityLevel.SECRET,
    owning_unit_address="D1",
    compartments=frozenset({"executive"}),
)

# You need to gather clearances manually for the explain API
clearances = {}  # Map of address -> RoleClearance
# (In practice, use engine._gather_clearances() or your own collection)

trace = explain_access(
    role_address="D1-R1-D1-R1-T1-R1",
    knowledge_item=item,
    posture=TrustPostureLevel.SUPERVISED,
    compiled_org=engine.get_org(),
    clearances=clearances,
    ksps=[],
    bridges=[],
)
print(trace)
```

## Recipe 12: Use SQLite Persistence

```python
from pact.governance.engine import GovernanceEngine

# Create engine with SQLite backend
engine = GovernanceEngine(
    org_definition,
    store_backend="sqlite",
    store_url="/tmp/my-org-governance.db",
)

# All mutations (clearances, envelopes, bridges, KSPs) are now persisted
# Restarting the engine with the same store_url loads existing state
```

## Recipe 13: Validate an Org with the CLI

```bash
# Validate a YAML org definition
python -m pact.governance.cli validate my-org.yaml

# Output:
# Validating 'my-org.yaml'...
# Organization: My Organization (my-org)
# Departments: 2, Teams: 1, Roles: 3
# Clearances: 3, Envelopes: 2, Bridges: 1, KSPs: 1
# All references valid.
```

## Recipe 14: Set Up Posture-Based Default Envelopes

```python
from pact.governance.envelopes import default_envelope_for_posture
from pact.build.config.schema import TrustPostureLevel

# Get conservative default envelopes for each posture level
for posture in TrustPostureLevel:
    env = default_envelope_for_posture(posture)
    print(f"{posture.value}:")
    print(f"  max_spend_usd: {env.financial.max_spend_usd}")
    print(f"  allowed_actions: {env.operational.allowed_actions}")
    print(f"  internal_only: {env.communication.internal_only}")
    print()
```
