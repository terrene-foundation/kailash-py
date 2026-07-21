# L3 Envelope — Budget Tracking & Enforcement

## EnvelopeTracker

Continuous multi-dimension budget tracking with atomic recording, child allocation, and reclamation.

```python
from kaizen.l3.envelope import EnvelopeTracker, PlanGradient

# Create tracker with envelope and gradient config
tracker = EnvelopeTracker(
    envelope={"financial_limit": 10000.0, "action_limit": 100},
    gradient=PlanGradient(budget_flag_threshold=0.80, budget_hold_threshold=0.95),
)

# Record consumption → returns Verdict
from kaizen.l3.envelope import CostEntry
verdict = await tracker.record_consumption(
    CostEntry(action="llm_call", dimension="financial", cost=500.0, agent_instance_id="agent-001")
)
# verdict.zone: AUTO_APPROVED (50% < 80% threshold)

# Check remaining budget
remaining = tracker.remaining()  # BudgetRemaining(financial_remaining=9500.0, ...)

# Allocate budget to child
await tracker.allocate_to_child("child-001", 3000.0)
# remaining now: 6500.0

# Reclaim from completed child
result = await tracker.reclaim("child-001", child_consumed=1800.0)
# result.reclaimed_financial: 1200.0, remaining now: 7700.0
```

## EnvelopeSplitter

Stateless budget division by ratio. Pure functions.

```python
from kaizen.l3.envelope import EnvelopeSplitter, AllocationRequest

parent_envelope = {"financial_limit": 10000.0, "action_limit": 100}
allocations = [
    AllocationRequest(child_id="analyzer", financial_ratio=0.30, temporal_ratio=0.40),
    AllocationRequest(child_id="reviewer", financial_ratio=0.50, temporal_ratio=0.40),
]

children = EnvelopeSplitter.split(parent_envelope, allocations, reserve_pct=0.10)
# children[0] = ("analyzer", {"financial_limit": 3000.0, ...})
# children[1] = ("reviewer", {"financial_limit": 5000.0, ...})
```

## EnvelopeEnforcer

Non-bypassable middleware. No `disable()`, `bypass()`, or `skip()` methods.

```python
from kaizen.l3.envelope import EnvelopeEnforcer, EnforcementContext

enforcer = EnvelopeEnforcer(tracker=tracker)

# Check before action
verdict = await enforcer.check_action(
    EnforcementContext(action="tool_call", estimated_cost=100.0, agent_instance_id="a-001")
)
if verdict.zone in ("auto_approved", "flagged"):
    # Execute action...
    await enforcer.record_action(context, actual_cost=95.0)
```

## Gradient Zones

| Zone          | Range                                 | Behavior                     |
| ------------- | ------------------------------------- | ---------------------------- |
| AUTO_APPROVED | 0% — flag_threshold (80%)             | Proceed                      |
| FLAGGED       | flag_threshold — hold_threshold (95%) | Proceed, log for review      |
| HELD          | hold_threshold — 100%                 | Suspend, wait for resolution |
| BLOCKED       | > 100% (envelope boundary)            | Reject (non-configurable)    |

## Invariants

- INV-1: Monotonically decreasing budget (except reclamation)
- INV-3: Non-bypassable enforcement
- INV-7: Finite arithmetic only (math.isfinite on all inputs)
- INV-9: Atomic cost recording (asyncio.Lock)

## Reference

- Spec: `workspaces/kaizen-l3/briefs/01-envelope-extensions.md`
- Source: `kaizen/l3/envelope/`
- Tests: `tests/unit/l3/envelope/`
