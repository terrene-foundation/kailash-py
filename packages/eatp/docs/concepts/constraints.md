# Constraints

EATP constraints define what limits apply to an agent's actions.

## Five Dimensions

| Dimension | Example | Description |
|-----------|---------|-------------|
| **Scope** | `["read_only", "no_pii"]` | What actions/resources are allowed |
| **Financial** | `max_spend: $1000/month` | Budget limits |
| **Temporal** | `business_hours_only` | When actions can occur |
| **Communication** | `internal_only` | Who/what the agent can communicate with |
| **Data Access** | `department_data_only` | What data the agent can access |

## Tightening Invariant

The core constraint rule: **delegations can only tighten constraints, never loosen them**.

If a parent agent has `max_spend: $1000`, it can delegate to a child with `max_spend: $500` but NOT `max_spend: $2000`.

## Constraint Templates

EATP includes 6 built-in templates:

```python
from eatp.templates import get_template, list_templates

# See all templates
templates = list_templates()  # governance, finance, community, standards, audit, minimal

# Use a template
template = get_template("minimal")
```

## Spend Tracking

The spend tracker monitors financial constraints in real-time:

```python
from eatp.constraints.spend_tracker import SpendTracker, BudgetPeriod

tracker = SpendTracker()
tracker.set_budget("agent-001", 1000.0, BudgetPeriod.MONTHLY)
tracker.record_spend("agent-001", 50.0)
status = tracker.check_budget("agent-001")
# status.level == BudgetStatusLevel.OK
```

## Commerce Constraints

For agents involved in financial transactions:

```python
from eatp.constraints.commerce import CommerceConstraint, CommerceType

constraint = CommerceConstraint(
    allowed_types=[CommerceType.PURCHASE],
    max_amount=500.0,
    allowed_beneficiaries=["vendor-001"],
)
```
