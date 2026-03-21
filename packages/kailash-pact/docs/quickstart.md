# Quickstart: PACT Governance in 10 Minutes

This guide takes you from zero to running governance using the university example. By the end, you will have an organization with departments, roles, clearances, and envelopes -- and you will have verified actions against them.

## 1. Install

```bash
pip install pact
```

## 2. Define Your Organization in YAML

Create a file called `my-org.yaml`:

```yaml
org_id: "quickstart-university"
name: "Quickstart University"

departments:
  - id: d-academics
    name: Academic Affairs
  - id: d-admin
    name: Administration

teams:
  - id: t-cs
    name: CS Department
  - id: t-finance
    name: Finance

roles:
  - id: r-president
    name: President
    heads: d-academics
  - id: r-dean
    name: Dean of Engineering
    reports_to: r-president
    heads: t-cs
  - id: r-professor
    name: CS Professor
    reports_to: r-dean
  - id: r-vp-admin
    name: VP Administration
    reports_to: r-president
    heads: d-admin
  - id: r-finance-director
    name: Finance Director
    reports_to: r-vp-admin
    heads: t-finance

clearances:
  - role: r-president
    level: secret
  - role: r-dean
    level: confidential
  - role: r-professor
    level: restricted
  - role: r-vp-admin
    level: restricted
  - role: r-finance-director
    level: restricted

envelopes:
  - target: r-dean
    defined_by: r-president
    financial:
      max_spend_usd: 50000
    operational:
      allowed_actions: [read, write, approve, hire]

  - target: r-professor
    defined_by: r-dean
    financial:
      max_spend_usd: 5000
    operational:
      allowed_actions: [read, write]
```

## 3. Load and Create the Engine

```python
from pact.governance.yaml_loader import load_org_yaml
from pact.governance.engine import GovernanceEngine

# Load the YAML definition
loaded = load_org_yaml("my-org.yaml")

# Create the governance engine (compiles the org automatically)
engine = GovernanceEngine(loaded.org_definition)

# See the compiled org structure
org = engine.get_org()
print(f"Organization: {engine.org_name}")
print(f"Nodes: {len(org.nodes)}")
for addr in sorted(org.nodes.keys()):
    node = org.nodes[addr]
    print(f"  {addr}: {node.name} ({node.node_type.value})")
```

Output:

```
Organization: Quickstart University
Nodes: 10
  D1: Academic Affairs (D)
  D1-R1: President (R)
  D1-R1-D1: Administration (D)
  D1-R1-D1-R1: VP Administration (R)
  D1-R1-D1-R1-T1: Finance (T)
  D1-R1-D1-R1-T1-R1: Finance Director (R)
  D1-R1-T1: CS Department (T)
  D1-R1-T1-R1: Dean of Engineering (R)
  D1-R1-T1-R1-R1: CS Professor (R)
```

## 4. Apply Clearances and Envelopes

The YAML loader returns clearance and envelope specs that need to be applied after compilation resolves positional addresses:

```python
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.envelopes import RoleEnvelope
from pact.governance.envelope_adapter import GovernanceEnvelopeAdapter
from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)

# Apply clearances from YAML specs
for spec in loaded.clearances:
    # Resolve role_id to positional address
    node = org.get_node_by_role_id(spec.role_id)
    if node is None:
        continue
    clearance = RoleClearance(
        role_address=node.address,
        max_clearance=ConfidentialityLevel(spec.level),
        compartments=frozenset(spec.compartments),
        nda_signed=spec.nda_signed,
        granted_by_role_address=node.address,
    )
    engine.grant_clearance(node.address, clearance)

# Apply envelopes from YAML specs
for spec in loaded.envelopes:
    target_node = org.get_node_by_role_id(spec.target)
    definer_node = org.get_node_by_role_id(spec.defined_by)
    if target_node is None or definer_node is None:
        continue

    # Build constraint envelope from spec
    financial = None
    if spec.financial:
        financial = FinancialConstraintConfig(**spec.financial)
    operational = OperationalConstraintConfig(
        **(spec.operational or {})
    )

    envelope_config = ConstraintEnvelopeConfig(
        id=f"env-{spec.target}",
        financial=financial,
        operational=operational,
    )

    role_envelope = RoleEnvelope(
        id=f"env-{spec.target}",
        defining_role_address=definer_node.address,
        target_role_address=target_node.address,
        envelope=envelope_config,
    )
    engine.set_role_envelope(role_envelope)

print("Clearances and envelopes applied.")
```

## 5. Verify Actions

Now use the engine to check whether roles can perform actions:

```python
# The professor tries to read (should be AUTO_APPROVED)
verdict = engine.verify_action("D1-R1-T1-R1-R1", "read")
print(f"Professor reads: {verdict.level} -- {verdict.reason}")

# The professor tries to approve (should be BLOCKED -- not in allowed actions)
verdict = engine.verify_action("D1-R1-T1-R1-R1", "approve")
print(f"Professor approves: {verdict.level} -- {verdict.reason}")

# The dean tries a $40,000 action (should be AUTO_APPROVED)
verdict = engine.verify_action(
    "D1-R1-T1-R1", "hire", context={"cost": 40000}
)
print(f"Dean hires at $40k: {verdict.level} -- {verdict.reason}")

# The dean tries a $60,000 action (should be BLOCKED -- exceeds max_spend)
verdict = engine.verify_action(
    "D1-R1-T1-R1", "hire", context={"cost": 60000}
)
print(f"Dean hires at $60k: {verdict.level} -- {verdict.reason}")
```

Output:

```
Professor reads: auto_approved -- Action 'read' is within all constraint dimensions
Professor approves: blocked -- Action 'approve' is not in the allowed actions list: ['read', 'write']
Dean hires at $40k: auto_approved -- Action 'hire' is within all constraint dimensions
Dean hires at $60k: blocked -- Action cost ($60000.00) exceeds financial limit ($50000.00)
```

## 6. Check Knowledge Access

Test whether roles can access classified information:

```python
from pact.governance.knowledge import KnowledgeItem
from pact.build.config.schema import TrustPostureLevel

# A confidential research document owned by the CS department
research_doc = KnowledgeItem(
    item_id="doc-research-001",
    classification=ConfidentialityLevel.CONFIDENTIAL,
    owning_unit_address="D1-R1-T1",  # CS Department
)

# The Dean (CONFIDENTIAL clearance, SHARED_PLANNING posture) checks access
decision = engine.check_access(
    "D1-R1-T1-R1",
    research_doc,
    TrustPostureLevel.SHARED_PLANNING,
)
print(f"Dean accesses research: allowed={decision.allowed}, reason={decision.reason}")

# The Professor (RESTRICTED clearance) tries the same
decision = engine.check_access(
    "D1-R1-T1-R1-R1",
    research_doc,
    TrustPostureLevel.SHARED_PLANNING,
)
print(f"Professor accesses research: allowed={decision.allowed}, reason={decision.reason}")
```

## 7. Get a Governance Context for an Agent

When you assign an AI agent to a role, give it a frozen GovernanceContext -- a read-only snapshot of what it is allowed to do:

```python
ctx = engine.get_context(
    "D1-R1-T1-R1-R1",  # Professor address
    posture=TrustPostureLevel.SUPERVISED,
)

print(f"Role: {ctx.role_address}")
print(f"Posture: {ctx.posture.value}")
print(f"Allowed actions: {sorted(ctx.allowed_actions)}")
print(f"Effective clearance: {ctx.effective_clearance_level.value}")
print(f"Compartments: {sorted(ctx.compartments)}")

# The context is frozen -- agents cannot modify their own constraints
# ctx.posture = TrustPostureLevel.DELEGATED  # This raises FrozenInstanceError
```

## What's Next

- **[Architecture](architecture.md)** -- Understand the GovernanceEngine internals
- **[Vertical Guide](vertical-guide.md)** -- Build your own domain on PACT
- **[YAML Schema](yaml-schema.md)** -- Full YAML format reference
- **[Cookbook](cookbook.md)** -- Recipes for common tasks
- **[API Reference](api.md)** -- REST endpoints for programmatic governance
