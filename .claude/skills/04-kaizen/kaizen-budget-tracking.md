# Kaizen Budget Tracking & Posture-Budget Integration

Atomic budget accounting with two-phase reserve/record semantics, threshold callbacks, and automatic posture transitions when budget limits are crossed.

## Overview

Two components work together for budget-aware governance:

1. **`BudgetTracker`** (EATP): Thread-safe, fail-closed budget accounting using integer microdollars (1 USD = 1,000,000 microdollars). Provides reserve/record two-phase semantics, threshold callbacks at 80/95/100%, and `on_record()` callback for custom integrations.

2. **`PostureBudgetIntegration`** (Kaizen): Links a `BudgetTracker` to EATP's `PostureStateMachine` so that budget threshold crossings automatically trigger trust posture transitions: warning at 80%, downgrade to SUPERVISED at 95%, emergency downgrade to PSEUDO_AGENT at 100%.

**Source modules**:

- `packages/eatp/src/eatp/constraints/budget_tracker.py` -- `BudgetTracker`, `BudgetSnapshot`, `BudgetCheckResult`, `BudgetEvent`
- `packages/kailash-kaizen/src/kaizen/governance/posture_budget.py` -- `PostureBudgetIntegration`

---

## BudgetTracker

### Creating a Tracker

```python
from eatp.constraints.budget_tracker import BudgetTracker, usd_to_microdollars

# Create with $10 budget
tracker = BudgetTracker(allocated_microdollars=usd_to_microdollars(10.0))
# or: BudgetTracker(allocated_microdollars=10_000_000)
```

### Two-Phase Reserve/Record

```python
# Phase 1: Reserve before the work
estimated_cost = 500_000  # $0.50
if tracker.reserve(estimated_cost):
    # Phase 2: Do work...
    actual_cost = 450_000  # $0.45
    # Phase 3: Record actual cost (releases reservation, commits actual)
    tracker.record(
        reserved_microdollars=estimated_cost,
        actual_microdollars=actual_cost,
    )
else:
    print("Insufficient budget")
```

**Key behaviors**:

- `reserve()` returns `False` (fail-closed) if insufficient budget, negative amount, or unexpected error
- `record()` uses saturating arithmetic: `_reserved` never goes below 0
- Zero-amount reservation always succeeds
- `record()` validates both arguments are non-negative integers, raises `BudgetTrackerError` otherwise

### Non-Mutating Check

```python
result = tracker.check(estimated_microdollars=500_000)

print(result.allowed)                  # True/False
print(result.remaining_microdollars)   # Available budget
print(result.committed_microdollars)   # Already spent
print(result.reserved_microdollars)    # Currently reserved
```

### Remaining Budget

```python
remaining = tracker.remaining_microdollars()
# Always >= 0 (saturating arithmetic)
```

### Threshold Callbacks

The tracker fires callbacks at fixed utilization thresholds. Each threshold fires at most once per tracker lifetime.

```python
from eatp.constraints.budget_tracker import BudgetEvent

def on_threshold(event: BudgetEvent):
    print(f"Threshold crossed: {event.event_type}")
    print(f"Remaining: {event.remaining_microdollars} microdollars")
    # event.event_type is one of: "threshold_80", "threshold_95", "exhausted"

tracker.on_threshold(on_threshold)
```

**Threshold levels**:

- `"threshold_80"`: committed >= 80% of allocated
- `"threshold_95"`: committed >= 95% of allocated
- `"exhausted"`: committed >= 100% of allocated

Callbacks are invoked **outside the lock** after `record()` to prevent deadlock when callbacks re-enter `remaining_microdollars()`, `check()`, or `snapshot()`.

### `on_record()` Callback

Fires after **every** `record()` call (not just at thresholds). Used by integrations that need custom threshold checking.

```python
def after_record():
    snap = tracker.snapshot()
    utilization = snap.committed / snap.allocated if snap.allocated > 0 else 0.0
    print(f"Budget utilization: {utilization * 100:.1f}%")

tracker.on_record(after_record)
```

Callbacks fire outside the lock, after threshold callbacks. Exceptions are logged and do not propagate.

### Snapshots and Persistence

```python
from eatp.constraints.budget_tracker import BudgetSnapshot

# Capture persistent state (allocated + committed only; reservations are transient)
snapshot = tracker.snapshot()

# Serialize
snapshot_dict = snapshot.to_dict()  # {"allocated": 10000000, "committed": 450000}

# Restore
restored_snapshot = BudgetSnapshot.from_dict(snapshot_dict)
restored_tracker = BudgetTracker.from_snapshot(restored_snapshot)
```

### Persistent Storage

```python
# Create tracker with auto-persistence
tracker = BudgetTracker(
    allocated_microdollars=10_000_000,
    store=my_budget_store,       # BudgetStore implementation
    tracker_id="agent-123",      # Required when store is provided
)
# Snapshots are auto-saved after each record()
# On creation, existing snapshot is auto-restored (reservations lost -- safe direction)
```

### Conversion Helpers

```python
from eatp.constraints.budget_tracker import usd_to_microdollars, microdollars_to_usd

microdollars = usd_to_microdollars(1.50)   # 1_500_000
usd = microdollars_to_usd(1_500_000)       # 1.5
```

`usd_to_microdollars()` validates that the amount is finite (rejects NaN, Inf).

---

## PostureBudgetIntegration

### Setup

```python
from eatp.constraints.budget_tracker import BudgetTracker, usd_to_microdollars
from eatp.postures import PostureStateMachine, TrustPosture
from kaizen.governance.posture_budget import PostureBudgetIntegration

# 1. Create budget tracker
tracker = BudgetTracker(allocated_microdollars=usd_to_microdollars(10.0))

# 2. Create posture state machine and register agent
state_machine = PostureStateMachine()
state_machine.register_agent("agent-123", TrustPosture.DELEGATED)

# 3. Link them
integration = PostureBudgetIntegration(
    budget_tracker=tracker,
    state_machine=state_machine,
    agent_id="agent-123",
)
```

### How It Works

The integration registers an `on_record()` callback on the BudgetTracker. After every `record()` call, it computes utilization (`committed / allocated`) and checks against three thresholds:

| Threshold   | Default | Action                                                                |
| ----------- | ------- | --------------------------------------------------------------------- |
| `warning`   | 80%     | Log a WARNING. No posture change.                                     |
| `downgrade` | 95%     | Transition agent to `SUPERVISED` via normal state machine transition. |
| `emergency` | 100%    | Emergency downgrade to `PSEUDO_AGENT` (bypasses guards).              |

Each action fires **at most once** per integration lifetime (tracked via `_fired_actions`).

### Custom Thresholds

```python
integration = PostureBudgetIntegration(
    budget_tracker=tracker,
    state_machine=state_machine,
    agent_id="agent-123",
    thresholds={
        "warning": 0.70,      # Warn at 70% instead of 80%
        "downgrade": 0.90,    # Downgrade at 90% instead of 95%
        "emergency": 1.0,     # Emergency at 100% (default)
    },
)
```

**Threshold validation**:

- Keys must be from `{"warning", "downgrade", "emergency"}` -- unknown keys raise `ValueError`
- Values must be finite numbers in `(0.0, 1.0]`
- NaN and Inf values are rejected (`math.isfinite()` check)
- Provided keys override defaults; missing keys use defaults

### Properties

```python
integration.agent_id       # "agent-123"
integration.thresholds     # {"warning": 0.8, "downgrade": 0.95, "emergency": 1.0}
```

### Downgrade Behavior

When the downgrade threshold is crossed:

1. Reads current posture from state machine
2. If already at SUPERVISED or lower, no-op (logged at INFO)
3. Creates a `PostureTransitionRequest` with reason, requester, and metadata
4. Attempts transition via `state_machine.transition()`
5. On stale-posture failure ("does not match"), refreshes posture and retries once
6. On success, logs at WARNING; on failure, logs at ERROR

### Emergency Behavior

When the emergency threshold is crossed:

1. Calls `state_machine.emergency_downgrade()` which bypasses normal guards
2. Agent is forced to `PSEUDO_AGENT` regardless of current posture
3. Logs at CRITICAL level

### Integration Direction

**kaizen -> eatp**: The `PostureBudgetIntegration` lives in the `kaizen` package and depends on EATP's `BudgetTracker` and `PostureStateMachine`. It never modifies EATP internals -- it uses only the public callback API (`on_record()`).

---

## Agent-Level Cost Tracking (BaseAgent)

For basic per-invocation cost tracking without EATP:

```python
result = agent.run(question="What is AI?")

# Access cost metrics
tokens = result.get("_tokens", {})
cost = result.get("_cost", 0.0)

print(f"Tokens: {tokens}")
print(f"Cost: ${cost:.4f}")
```

For production budget management, use `BudgetTracker` + `PostureBudgetIntegration` instead of manual tracking.

---

## Complete Example

```python
from eatp.constraints.budget_tracker import BudgetTracker, usd_to_microdollars
from eatp.postures import PostureStateMachine, TrustPosture
from kaizen.governance.posture_budget import PostureBudgetIntegration

# Setup
tracker = BudgetTracker(allocated_microdollars=usd_to_microdollars(5.0))
state_machine = PostureStateMachine()
state_machine.register_agent("market-analyzer", TrustPosture.DELEGATED)

integration = PostureBudgetIntegration(
    budget_tracker=tracker,
    state_machine=state_machine,
    agent_id="market-analyzer",
    thresholds={"warning": 0.70, "downgrade": 0.90, "emergency": 1.0},
)

# Simulate work
for i in range(10):
    cost = 500_000  # $0.50 per call
    if tracker.reserve(cost):
        # ... do work ...
        tracker.record(reserved_microdollars=cost, actual_microdollars=cost)
        posture = state_machine.get_posture("market-analyzer")
        remaining = tracker.remaining_microdollars()
        print(f"Call {i+1}: posture={posture.value}, remaining=${remaining / 1_000_000:.2f}")
    else:
        print(f"Call {i+1}: budget exhausted, reserve denied")
        break

# After $3.50 spent (70%): WARNING logged
# After $4.50 spent (90%): posture -> SUPERVISED
# After $5.00 spent (100%): posture -> PSEUDO_AGENT (emergency)
```

---

## Critical Rules

- **ALWAYS** use `int` microdollars, never `float` dollars, for budget accounting -- avoids floating-point precision issues
- **ALWAYS** validate cost values with `math.isfinite()` before passing to budget operations -- NaN bypasses all comparisons
- **ALWAYS** use `reserve()` before work and `record()` after -- the two-phase protocol prevents overdraft
- **NEVER** monkey-patch `BudgetTracker` -- use `on_record()` and `on_threshold()` callbacks
- **NEVER** downgrade trust state manually when `PostureBudgetIntegration` is active -- it handles transitions
- `PostureBudgetIntegration` fires each action at most once -- if you need to reset, create a new integration instance
- Threshold callbacks run outside the lock -- they can safely call `remaining_microdollars()`, `check()`, `snapshot()`
- All `BudgetTracker` operations are thread-safe (guarded by `threading.Lock`)
- `BudgetTrackerError` inherits from EATP's `TrustError` and always includes `.details` dict

## References

- **Source**: `packages/eatp/src/eatp/constraints/budget_tracker.py`
- **Source**: `packages/kailash-kaizen/src/kaizen/governance/posture_budget.py`
- **Related**: [`kaizen-cost-tracking`](kaizen-cost-tracking.md) -- Basic per-invocation cost tracking via BaseAgent
- **Related**: [`kaizen-trust-eatp`](kaizen-trust-eatp.md) -- Full EATP trust infrastructure
