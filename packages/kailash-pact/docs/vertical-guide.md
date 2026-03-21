# Building a Vertical on PACT

A vertical is a domain-specific application built on top of PACT. PACT provides the governance framework (D/T/R grammar, envelopes, clearance, access enforcement); verticals provide the domain vocabulary and business rules.

**Examples**:

- **Astra** -- Financial services vertical (MAS-regulated)
- **Arbor** -- HR governance vertical (Singapore SME)
- **University** -- Bundled example vertical (ships with PACT)

This guide walks you through building a minimal "bookstore" vertical from scratch.

## The Boundary Test

Before you write any code, understand this rule: **PACT framework code knows nothing about your domain**. If you removed all domain vocabulary from your vertical and replaced it with different domain terms, no line in `pact.governance` would change.

This means:

- Domain-specific role names (e.g., "Store Manager", "Inventory Clerk") go in YOUR code
- Domain-specific constraints (e.g., "max book order $500") go in YOUR configuration
- Domain-specific access rules (e.g., "only managers see supplier pricing") go in YOUR clearances and KSPs
- The governance engine, envelope intersection, access algorithm, and all other PACT internals remain untouched

## Step 1: Define Your D/T/R Structure

Start by mapping your organization into Departments, Teams, and Roles.

```yaml
# bookstore-org.yaml
org_id: "bookstore-001"
name: "Downtown Bookstore"

departments:
  - id: d-management
    name: Management
  - id: d-retail
    name: Retail Operations
  - id: d-warehouse
    name: Warehouse

teams:
  - id: t-floor-sales
    name: Floor Sales
  - id: t-online-sales
    name: Online Sales
  - id: t-receiving
    name: Receiving
  - id: t-shipping
    name: Shipping
  - id: t-accounting
    name: Accounting

roles:
  # Level 1: Owner
  - id: r-owner
    name: Store Owner
    heads: d-management

  # Level 2: Store Manager (reports to Owner, heads Retail)
  - id: r-store-manager
    name: Store Manager
    reports_to: r-owner
    heads: d-retail

  # Level 3: Floor Sales Lead
  - id: r-floor-lead
    name: Floor Sales Lead
    reports_to: r-store-manager
    heads: t-floor-sales

  # Level 3: Online Sales Lead
  - id: r-online-lead
    name: Online Sales Lead
    reports_to: r-store-manager
    heads: t-online-sales

  # Level 4: Sales Associate
  - id: r-sales-associate
    name: Sales Associate
    reports_to: r-floor-lead

  # Level 2: Warehouse Manager (reports to Owner, heads Warehouse)
  - id: r-warehouse-manager
    name: Warehouse Manager
    reports_to: r-owner
    heads: d-warehouse

  # Level 3: Receiving Clerk
  - id: r-receiving-clerk
    name: Receiving Clerk
    reports_to: r-warehouse-manager
    heads: t-receiving

  # Level 3: Shipping Clerk
  - id: r-shipping-clerk
    name: Shipping Clerk
    reports_to: r-warehouse-manager
    heads: t-shipping

  # Level 2: Accountant
  - id: r-accountant
    name: Accountant
    reports_to: r-owner
    heads: t-accounting
```

This produces 3 departments, 5 teams, and 9 roles across 4 levels of nesting. The compiled addresses look like:

```
D1-R1                    Store Owner (Management)
D1-R1-D1-R1              Store Manager (Retail Operations)
D1-R1-D1-R1-T1-R1        Floor Sales Lead
D1-R1-D1-R1-T1-R1-R1     Sales Associate
D1-R1-D1-R1-T2-R1        Online Sales Lead
D1-R1-D2-R1              Warehouse Manager (Warehouse)
D1-R1-D2-R1-T1-R1        Receiving Clerk
D1-R1-D2-R1-T2-R1        Shipping Clerk
D1-R1-T1-R1              Accountant (Accounting)
```

## Step 2: Define Clearances

Map your information classification needs. What data exists, and who should see it?

```yaml
clearances:
  # Owner sees everything
  - role: r-owner
    level: secret
    nda_signed: true

  # Store Manager sees retail + customer data
  - role: r-store-manager
    level: confidential

  # Floor Lead sees floor operations
  - role: r-floor-lead
    level: restricted

  # Online Lead sees online operations + customer PII
  - role: r-online-lead
    level: confidential
    compartments: [customer-pii]

  # Sales Associate sees public data only
  - role: r-sales-associate
    level: restricted

  # Warehouse Manager sees supply chain data
  - role: r-warehouse-manager
    level: confidential
    compartments: [supplier-pricing]

  # Receiving/Shipping Clerks see restricted
  - role: r-receiving-clerk
    level: restricted
  - role: r-shipping-clerk
    level: restricted

  # Accountant sees financial data
  - role: r-accountant
    level: confidential
    compartments: [financial-records]
```

Notice:

- The Online Sales Lead has CONFIDENTIAL clearance with `customer-pii` compartment, even though they are organizationally "below" the Store Manager. Clearance is independent of authority.
- The Warehouse Manager has a `supplier-pricing` compartment that even the Store Manager does not have.

## Step 3: Define Envelopes

Set spending limits and allowed actions for each role:

```yaml
envelopes:
  - target: r-store-manager
    defined_by: r-owner
    financial:
      max_spend_usd: 25000
      requires_approval_above_usd: 10000
    operational:
      allowed_actions: [read, write, approve, order, refund]

  - target: r-floor-lead
    defined_by: r-store-manager
    financial:
      max_spend_usd: 1000
      requires_approval_above_usd: 500
    operational:
      allowed_actions: [read, write, refund]

  - target: r-sales-associate
    defined_by: r-floor-lead
    financial:
      max_spend_usd: 100
    operational:
      allowed_actions: [read]

  - target: r-warehouse-manager
    defined_by: r-owner
    financial:
      max_spend_usd: 50000
      requires_approval_above_usd: 20000
    operational:
      allowed_actions: [read, write, order, receive, ship]

  - target: r-accountant
    defined_by: r-owner
    financial:
      max_spend_usd: 0
    operational:
      allowed_actions: [read, audit]
```

Key design decisions:

- Sales Associates can only read (no refunds, no orders)
- The Accountant has zero spend limit but can read and audit
- Warehouse Manager has a high spend limit for bulk orders

## Step 4: Define Information Barriers and Bridges

Decide what data should NOT flow between units, and where controlled exceptions exist:

```yaml
bridges:
  # Store Manager can see Warehouse data for inventory coordination
  - id: bridge-retail-warehouse
    role_a: r-store-manager
    role_b: r-warehouse-manager
    type: standing
    max_classification: restricted
    bilateral: true

ksps:
  # Accounting can read financial data from Retail
  - id: ksp-retail-to-accounting
    source: d-retail
    target: t-accounting
    max_classification: restricted

  # Accounting can read financial data from Warehouse
  - id: ksp-warehouse-to-accounting
    source: d-warehouse
    target: t-accounting
    max_classification: restricted
```

Notice what is NOT connected:

- No bridge between Online Sales and Warehouse -- they should not share customer PII with shipping clerks
- No KSP from Accounting to anyone -- financial records flow one way (into accounting), not out

## Step 5: Load and Use

```python
from pact.governance.yaml_loader import load_org_yaml
from pact.governance.engine import GovernanceEngine

loaded = load_org_yaml("bookstore-org.yaml")
engine = GovernanceEngine(loaded.org_definition)

# Apply clearances, envelopes, bridges, KSPs from the loaded specs
# (see quickstart.md for the full application loop)

# Now use the engine for governance decisions
verdict = engine.verify_action(
    "D1-R1-D1-R1-T1-R1-R1",  # Sales Associate
    "refund",
    {"cost": 50.0},
)
print(f"Sales Associate refund: {verdict.level}")
# Output: blocked -- 'refund' is not in allowed actions for Sales Associate
```

## Step 6: Create Governed Agents

Assign AI agents to roles and let them operate within their governance boundaries:

```python
from pact.governance.agent import PactGovernedAgent
from pact.governance.decorators import governed_tool
from pact.build.config.schema import TrustPostureLevel

@governed_tool("read", cost=0.0)
def search_inventory(query: str) -> str:
    return f"Found 3 books matching '{query}'"

@governed_tool("order", cost=200.0)
def place_order(book_id: str, quantity: int) -> str:
    return f"Ordered {quantity} copies of {book_id}"

# Create governed agent for the Warehouse Manager
agent = PactGovernedAgent(
    engine=engine,
    role_address="D1-R1-D2-R1",  # Warehouse Manager
    posture=TrustPostureLevel.SUPERVISED,
)
agent.register_tool("read", cost=0.0)
agent.register_tool("order", cost=200.0)

# The Warehouse Manager can order (within their $50k envelope)
result = agent.execute_tool("order", _tool_fn=lambda: place_order("isbn-123", 100))
print(result)  # "Ordered 100 copies of isbn-123"
```

## Project Structure

A typical vertical project looks like:

```
my-vertical/
  pyproject.toml          # depends on pact
  src/my_vertical/
    __init__.py
    config/
      org.yaml            # Your D/T/R structure
    agents/
      sales_agent.py      # Governed agents with @governed_tool
      warehouse_agent.py
    tools/
      inventory.py        # Tool implementations
      ordering.py
    server.py             # FastAPI app with governance API mounted
  tests/
    test_governance.py    # Test with MockGovernedAgent
```

Your `pyproject.toml` dependency:

```toml
[project]
dependencies = [
    "pact>=0.1.0",
]
```

## Testing Your Vertical

Use `MockGovernedAgent` for deterministic testing without LLM calls:

```python
from pact.governance.testing import MockGovernedAgent

mock = MockGovernedAgent(
    engine=engine,
    role_address="D1-R1-D1-R1-T1-R1-R1",  # Sales Associate
    tools=[search_inventory],
    script=["read", "read"],
)

results = mock.run()
assert len(results) == 2
assert "Found" in results[0]
```

Test blocked actions:

```python
import pytest
from pact.governance.agent import GovernanceBlockedError

mock = MockGovernedAgent(
    engine=engine,
    role_address="D1-R1-D1-R1-T1-R1-R1",  # Sales Associate
    tools=[place_order],  # order is not in Sales Associate's allowed actions
    script=["order"],
)

with pytest.raises(GovernanceBlockedError):
    mock.run()
```
