# Trust Posture and Constraint Systems (CARE Phase 4)

This guide explains how to use Kaizen's posture and constraint systems for fine-grained agent behavior control. These systems build on the EATP trust lineage to provide runtime governance over what agents can do and how much autonomy they have.

## Overview

The posture and constraint systems provide two complementary control mechanisms:

- **Trust Postures**: Define _how_ an agent's actions are handled (full autonomy, supervised, requires approval, blocked)
- **Constraint Dimensions**: Define _what_ an agent can do (cost limits, time windows, rate limits, data access)

Use postures when you need to control the level of human oversight. Use constraints when you need to bound specific operational parameters. Use both together for comprehensive governance.

```python
from kaizen.trust import (
    # Postures
    TrustPosture,
    PostureStateMachine,
    PostureAwareAgent,
    PostureCircuitBreaker,
    # Constraints
    ConstraintDimensionRegistry,
    MultiDimensionEvaluator,
    InteractionMode,
)
from kaizen.trust.constraints.builtin import register_builtin_dimensions
```

## Trust Postures

The posture system defines five levels of agent autonomy, from full independence to complete lockdown.

### The Five Postures

| Posture         | Autonomy Level | Behavior                                                |
| --------------- | -------------- | ------------------------------------------------------- |
| `FULL_AUTONOMY` | 5              | Execute immediately without restrictions                |
| `ASSISTED`      | 4              | Notify, wait for cancel window, then execute with audit |
| `SUPERVISED`    | 3              | Execute with detailed audit logging                     |
| `HUMAN_DECIDES` | 2              | Queue for human approval before execution               |
| `BLOCKED`       | 1              | Reject all actions                                      |

```python
from kaizen.trust import TrustPosture

# Postures are comparable by autonomy level
assert TrustPosture.FULL_AUTONOMY > TrustPosture.SUPERVISED
assert TrustPosture.BLOCKED < TrustPosture.HUMAN_DECIDES

# Check upgrade/downgrade relationships
posture = TrustPosture.SUPERVISED
assert posture.can_upgrade_to(TrustPosture.FULL_AUTONOMY)
assert posture.can_downgrade_to(TrustPosture.BLOCKED)
```

### When to Use Each Posture

- **FULL_AUTONOMY**: Proven agents in low-risk contexts. The agent has earned trust through demonstrated reliability.
- **ASSISTED**: Moderate-risk operations where quick human intervention might be needed. The agent notifies before acting and waits briefly for cancellation.
- **SUPERVISED**: Default starting point for most agents. All actions are logged but not blocked.
- **HUMAN_DECIDES**: High-risk operations or untrusted agents. Every action requires explicit approval.
- **BLOCKED**: Emergency lockdown or revoked trust. The agent cannot execute any actions.

## Posture State Machine

The `PostureStateMachine` manages posture transitions with guards and history tracking.

### Basic Usage

```python
from kaizen.trust import PostureStateMachine, TrustPosture
from kaizen.trust.postures import PostureTransitionRequest

# Create state machine (default posture is SUPERVISED)
machine = PostureStateMachine(
    default_posture=TrustPosture.SUPERVISED,
    require_upgrade_approval=True,  # Upgrades require requester_id
)

# Set initial posture for an agent
machine.set_posture("agent-001", TrustPosture.SUPERVISED)

# Get current posture
posture = machine.get_posture("agent-001")  # TrustPosture.SUPERVISED
```

### Posture Transitions

Transitions are governed by guards that can approve or reject changes:

```python
from kaizen.trust.postures import PostureTransitionRequest, TransitionResult

# Request an upgrade
request = PostureTransitionRequest(
    agent_id="agent-001",
    from_posture=TrustPosture.SUPERVISED,
    to_posture=TrustPosture.FULL_AUTONOMY,
    reason="Agent has proven reliable over 30 days",
    requester_id="admin-001",  # Required for upgrades
)

result: TransitionResult = machine.transition(request)

if result.success:
    print(f"Upgraded to {result.to_posture.value}")
else:
    print(f"Blocked by: {result.blocked_by}")
    print(f"Reason: {result.reason}")
```

### Transition Types

The `PostureTransition` enum describes what kind of change is happening:

| Type                  | Meaning                                                       |
| --------------------- | ------------------------------------------------------------- |
| `UPGRADE`             | Moving to higher autonomy (e.g., SUPERVISED -> FULL_AUTONOMY) |
| `DOWNGRADE`           | Moving to lower autonomy (e.g., FULL_AUTONOMY -> SUPERVISED)  |
| `MAINTAIN`            | No change in autonomy level                                   |
| `EMERGENCY_DOWNGRADE` | Immediate downgrade bypassing all guards                      |

### Adding Custom Guards

Guards validate transitions before they happen:

```python
from kaizen.trust.postures import TransitionGuard, PostureTransition

# Require approval from security team for upgrades above SUPERVISED
security_guard = TransitionGuard(
    name="security_team_approval",
    check_fn=lambda req: (
        req.metadata.get("security_approved", False)
        if req.to_posture > TrustPosture.SUPERVISED
        else True
    ),
    applies_to=[PostureTransition.UPGRADE],
    reason_on_failure="Security team approval required for high autonomy",
)

machine.add_guard(security_guard)

# This will fail without security_approved=True
request = PostureTransitionRequest(
    agent_id="agent-001",
    from_posture=TrustPosture.SUPERVISED,
    to_posture=TrustPosture.FULL_AUTONOMY,
    requester_id="admin-001",
    metadata={},  # Missing security_approved
)
result = machine.transition(request)
assert not result.success
assert result.blocked_by == "security_team_approval"
```

### Emergency Downgrade

For security incidents, bypass all guards and immediately block an agent:

```python
result = machine.emergency_downgrade(
    agent_id="agent-001",
    reason="Detected anomalous behavior pattern",
    requester_id="security-bot",
)

# Agent is now BLOCKED regardless of previous posture
assert machine.get_posture("agent-001") == TrustPosture.BLOCKED
```

### Querying Transition History

```python
# Get all transitions for an agent
history = machine.get_transition_history(agent_id="agent-001", limit=10)

for result in history:
    print(f"{result.timestamp}: {result.from_posture.value} -> {result.to_posture.value}")
    print(f"  Type: {result.transition_type.value}")
    print(f"  Success: {result.success}")
    if not result.success:
        print(f"  Blocked by: {result.blocked_by}")
```

## Circuit Breaker

The `PostureCircuitBreaker` automatically downgrades agent postures when failures accumulate, protecting the system from cascading failures.

### Why Circuit Breakers for Trust

When an agent starts failing repeatedly, continuing to grant it high autonomy is risky. The circuit breaker:

1. Tracks weighted failures per agent
2. Opens the circuit (blocks/downgrades) when threshold is exceeded
3. Waits for recovery timeout
4. Tests with limited calls (half-open state)
5. Restores normal operation if tests pass

### Configuration

```python
from kaizen.trust import PostureCircuitBreaker, CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=5,          # Weighted failures to open circuit
    recovery_timeout=60,          # Seconds before testing recovery
    half_open_max_calls=3,        # Test calls allowed in half-open
    failure_window_seconds=300,   # Window for counting failures
    severity_weights={            # Weight multipliers by severity
        "low": 0.5,
        "medium": 1.0,
        "high": 2.0,
        "critical": 5.0,
    },
    downgrade_on_open="human_decides",  # Posture when circuit opens
)

breaker = PostureCircuitBreaker(
    posture_machine=machine,
    config=config,
)
```

### Recording Failures

```python
# Record a failure (severity affects weighted count)
await breaker.record_failure(
    agent_id="agent-001",
    error_type="ConnectionError",
    error_message="Failed to connect to upstream API",
    action="api_call",
    severity="medium",  # low, medium, high, critical
)

# Check if agent can proceed
if await breaker.can_proceed("agent-001"):
    # Execute action
    await breaker.record_success("agent-001")
else:
    # Circuit is open - action blocked
    pass
```

### Circuit States

```python
from kaizen.trust import CircuitState

state = breaker.get_state("agent-001")

if state == CircuitState.CLOSED:
    # Normal operation - failures are counted
    pass
elif state == CircuitState.OPEN:
    # Failures exceeded threshold - executions blocked
    # Posture has been downgraded
    pass
elif state == CircuitState.HALF_OPEN:
    # Testing recovery - limited calls allowed
    pass
```

### State Lifecycle

```
CLOSED ──[weighted failures >= threshold]──> OPEN
   ^                                           |
   |                                           | [recovery_timeout elapsed]
   |                                           v
   └───[half_open_max_calls successes]─── HALF_OPEN
                                              |
                                              | [any failure]
                                              v
                                            OPEN
```

### Metrics

```python
metrics = breaker.get_metrics("agent-001")

print(f"State: {metrics['state']}")
print(f"Failure count: {metrics['failure_count']}")
print(f"Weighted failures: {metrics['weighted_failures']}")
print(f"Current posture: {metrics['current_posture']}")

if metrics['state'] == 'open':
    print(f"Time until half-open: {metrics['time_until_half_open']}s")

if 'original_posture' in metrics:
    print(f"Original posture: {metrics['original_posture']}")
```

## Posture-Aware Agent

The `PostureAwareAgent` wraps any Kaizen agent to enforce posture-based behavior.

### Basic Wrapping

```python
from kaizen.trust import PostureAwareAgent, PostureStateMachine, TrustPosture
from kaizen.core.base_agent import BaseAgent

# Your base agent
base_agent = MyAgent(config)

# Posture management
machine = PostureStateMachine()
machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

# Wrap with posture awareness
agent = PostureAwareAgent(
    base_agent=base_agent,
    agent_id="agent-001",
    posture_machine=machine,
)

# Execute respects posture
result = await agent.run(query="What is AI?")
```

### Execution Behavior by Posture

| Posture         | Behavior                                                                     |
| --------------- | ---------------------------------------------------------------------------- |
| `FULL_AUTONOMY` | Direct execution, no restrictions                                            |
| `ASSISTED`      | Notify handler, wait for cancel window (default 5s), then execute with audit |
| `SUPERVISED`    | Execute with detailed audit logging                                          |
| `HUMAN_DECIDES` | Call approval handler, execute only if approved                              |
| `BLOCKED`       | Raise `PermissionError` immediately                                          |

### Approval Handler

For `HUMAN_DECIDES` posture, implement the `ApprovalHandler` protocol:

```python
from kaizen.trust import ApprovalHandler
from typing import Dict, Any

class MyApprovalHandler:
    """Routes approval requests to human operators."""

    async def request_approval(
        self,
        agent_id: str,
        action_description: str,
        kwargs: Dict[str, Any],
    ) -> bool:
        # Your approval logic (Slack, email, dashboard, etc.)
        # Return True to approve, False to deny
        response = await self.send_to_approval_queue(
            agent_id=agent_id,
            action=action_description,
            params=kwargs,
        )
        return response.approved

# Use with PostureAwareAgent
agent = PostureAwareAgent(
    base_agent=base_agent,
    agent_id="agent-001",
    posture_machine=machine,
    approval_handler=MyApprovalHandler(),
)
```

### Notification Handler

For `ASSISTED` posture, implement the `NotificationHandler` protocol:

```python
from kaizen.trust import NotificationHandler
from typing import Dict, Any

class MyNotificationHandler:
    """Sends notifications before assisted execution."""

    async def notify(
        self,
        agent_id: str,
        message: str,
        action_kwargs: Dict[str, Any],
    ) -> None:
        # Send notification (Slack, webhook, etc.)
        await self.slack_client.post(
            channel="#agent-actions",
            text=f"{message}\nParams: {action_kwargs}",
        )

agent = PostureAwareAgent(
    base_agent=base_agent,
    agent_id="agent-001",
    posture_machine=machine,
    notification_handler=MyNotificationHandler(),
    assisted_delay_seconds=10.0,  # Cancel window duration
)
```

### Cancelling Assisted Execution

During the cancel window, you can stop execution:

```python
# In another task/thread
if agent.cancel_pending():
    print("Execution cancelled")
```

### Audit Trail

`PostureAwareAgent` maintains an audit log for `SUPERVISED` and `ASSISTED` modes:

```python
from kaizen.trust import AuditEntry

# Access audit log
for entry in agent.audit_log:
    print(f"{entry.timestamp}: {entry.action}")
    print(f"  Posture: {entry.posture.value}")
    print(f"  Duration: {entry.duration_ms}ms")
    if entry.error:
        print(f"  Error: {entry.error}")
```

## Trust Metrics

The `TrustMetricsCollector` provides observability for posture and constraint systems.

### Collecting Metrics

```python
from kaizen.trust import TrustMetricsCollector, TrustPosture

collector = TrustMetricsCollector()

# Record posture for each agent
collector.record_posture("agent-001", TrustPosture.FULL_AUTONOMY)
collector.record_posture("agent-002", TrustPosture.SUPERVISED)
collector.record_posture("agent-003", TrustPosture.BLOCKED)

# Record transitions
collector.record_transition("upgrade")
collector.record_transition("downgrade")

# Record circuit breaker events
collector.record_circuit_breaker_open()
collector.record_emergency_downgrade()

# Record constraint evaluations
collector.record_constraint_evaluation(
    passed=True,
    failed_dimensions=[],
    gaming_flags=[],
    duration_ms=5.2,
)
```

### Querying Metrics

```python
from kaizen.trust import PostureMetrics, ConstraintMetrics

# Posture metrics
posture_metrics: PostureMetrics = collector.get_posture_metrics()

print(f"Distribution: {posture_metrics.posture_distribution}")
# {'full_autonomy': 1, 'supervised': 1, 'blocked': 1, ...}

print(f"Average autonomy level: {posture_metrics.average_posture_level}")
# 3.0 (average of levels 5, 3, 1)

print(f"Transitions: {posture_metrics.transitions_by_type}")
# {'upgrade': 1, 'downgrade': 1}

print(f"Circuit breaker opens: {posture_metrics.circuit_breaker_opens}")
print(f"Emergency downgrades: {posture_metrics.emergency_downgrades}")

# Constraint metrics
constraint_metrics: ConstraintMetrics = collector.get_constraint_metrics()

print(f"Total evaluations: {constraint_metrics.evaluations_total}")
print(f"Pass rate: {constraint_metrics.evaluations_passed / constraint_metrics.evaluations_total}")
print(f"Failed dimensions: {constraint_metrics.dimension_failures}")
print(f"Anti-gaming flags: {constraint_metrics.anti_gaming_flags}")
print(f"Avg evaluation time: {constraint_metrics.average_evaluation_time_ms}ms")
```

### Integration with Monitoring

```python
# Export to Prometheus, Datadog, etc.
metrics_dict = posture_metrics.to_dict()
metrics_dict.update(constraint_metrics.to_dict())

# Push to your monitoring system
await monitoring_client.push_metrics(metrics_dict)
```

## Constraint Dimensions

Constraint dimensions define specific operational boundaries for agents. Each dimension handles one aspect of constraint evaluation.

### The ConstraintDimension Protocol

Every constraint dimension implements:

```python
from abc import ABC, abstractmethod
from kaizen.trust.constraints import ConstraintDimension, ConstraintValue, ConstraintCheckResult
from typing import Any, Dict, List

class ConstraintDimension(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier (e.g., 'cost_limit')"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description"""
        pass

    @abstractmethod
    def parse(self, value: Any) -> ConstraintValue:
        """Parse raw value into ConstraintValue"""
        pass

    @abstractmethod
    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        """Check if constraint is satisfied given context"""
        pass

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        """Validate child constraint is tighter than parent (EATP requirement)"""
        # Default: numeric comparison where lower = tighter
        return float(child.parsed) <= float(parent.parsed)

    def compose(self, constraints: List[ConstraintValue]) -> ConstraintValue:
        """Combine multiple constraints into most restrictive"""
        # Default: pick minimum numeric value
        return min(constraints, key=lambda c: float(c.parsed))
```

### ConstraintValue and ConstraintCheckResult

```python
from kaizen.trust.constraints import ConstraintValue, ConstraintCheckResult

# ConstraintValue holds parsed constraint data
value = ConstraintValue(
    dimension="cost_limit",
    raw_value="1000",
    parsed=1000.0,
    metadata={"unit": "cents"},
)

# ConstraintCheckResult reports evaluation outcome
result = ConstraintCheckResult(
    satisfied=True,
    reason="within budget",
    remaining=500.0,  # Optional: remaining capacity
    used=500.0,       # Optional: amount used
    limit=1000.0,     # Optional: the limit value
)
```

### Creating Custom Dimensions

```python
from kaizen.trust.constraints import (
    ConstraintDimension,
    ConstraintValue,
    ConstraintCheckResult,
)
from typing import Any, Dict

class TokenLimitDimension(ConstraintDimension):
    """Limits tokens per request."""

    @property
    def name(self) -> str:
        return "token_limit"

    @property
    def description(self) -> str:
        return "Maximum tokens per request"

    @property
    def requires_audit(self) -> bool:
        return True  # Log all token usage

    def parse(self, value: Any) -> ConstraintValue:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot parse token limit: {value}") from e

        if parsed < 0:
            raise ValueError(f"Token limit must be non-negative: {parsed}")

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
            metadata={},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        limit = constraint.parsed
        used = context.get("tokens_used", 0)

        remaining = max(0, limit - used)
        satisfied = used <= limit

        return ConstraintCheckResult(
            satisfied=satisfied,
            reason="within limit" if satisfied else f"exceeded by {used - limit}",
            remaining=float(remaining),
            used=float(used),
            limit=float(limit),
        )
```

## Constraint Registry

The `ConstraintDimensionRegistry` manages dimension plugins with security review for custom dimensions.

### Registering Dimensions

```python
from kaizen.trust.constraints import ConstraintDimensionRegistry
from kaizen.trust.constraints.builtin import register_builtin_dimensions

# Create registry
registry = ConstraintDimensionRegistry()

# Register all built-in dimensions (auto-approved)
register_builtin_dimensions(registry)

# Register custom dimension (requires review)
registry.register(TokenLimitDimension(), requires_review=True)

# Check pending reviews
pending = registry.pending_review()  # ['token_limit']
```

### Security Review Workflow

Custom dimensions require approval before use:

```python
# Dimension is registered but pending
assert registry.has("token_limit")
assert registry.get("token_limit") is None  # Cannot retrieve pending

# After security review, approve it
registry.approve_dimension("token_limit", reviewer="security-team")

# Now it can be used
dim = registry.get("token_limit")
assert dim is not None
```

### Built-in vs Custom Dimensions

Built-in dimensions (auto-approved):

- `cost_limit`
- `time_window`
- `resources`
- `rate_limit`
- `data_access`
- `communication`

Custom dimensions require:

1. Registration with `requires_review=True`
2. Security team approval via `approve_dimension()`
3. Documented rationale for the constraint

### Testing Mode

For testing, allow unreviewed dimensions:

```python
registry = ConstraintDimensionRegistry(allow_unreviewed=True)
registry.register(TokenLimitDimension(), requires_review=True)

# Can retrieve immediately in test mode
dim = registry.get("token_limit")
assert dim is not None
```

## Multi-Dimension Evaluator

The `MultiDimensionEvaluator` checks actions against multiple constraint dimensions with configurable interaction logic.

### Basic Evaluation

```python
from kaizen.trust.constraints import (
    ConstraintDimensionRegistry,
    MultiDimensionEvaluator,
    InteractionMode,
)
from kaizen.trust.constraints.builtin import register_builtin_dimensions

# Setup
registry = ConstraintDimensionRegistry()
register_builtin_dimensions(registry)

evaluator = MultiDimensionEvaluator(
    registry=registry,
    enable_anti_gaming=True,
)

# Evaluate constraints against context
result = evaluator.evaluate(
    constraints={
        "cost_limit": 1000,
        "rate_limit": "100/minute",
    },
    context={
        "cost_used": 500,
        "requests_in_period": 50,
    },
    mode=InteractionMode.CONJUNCTIVE,
    agent_id="agent-001",
)

if result.satisfied:
    print("All constraints satisfied")
else:
    print(f"Failed dimensions: {result.failed_dimensions}")
```

### Interaction Modes

| Mode           | Logic                      | Use Case                            |
| -------------- | -------------------------- | ----------------------------------- |
| `INDEPENDENT`  | Majority must pass         | Flexible constraints with tolerance |
| `CONJUNCTIVE`  | ALL must pass (AND)        | Strict enforcement - default        |
| `DISJUNCTIVE`  | ANY can pass (OR)          | Alternative constraint paths        |
| `HIERARCHICAL` | First dimension determines | Priority-based evaluation           |

```python
from kaizen.trust.constraints import InteractionMode

# Conjunctive: ALL constraints must pass
result = evaluator.evaluate(
    constraints={"cost_limit": 100, "rate_limit": 10},
    context={"cost_used": 200, "requests_in_period": 5},
    mode=InteractionMode.CONJUNCTIVE,
)
# Failed: cost_limit failed even though rate_limit passed

# Disjunctive: ANY constraint passing is enough
result = evaluator.evaluate(
    constraints={"cost_limit": 100, "rate_limit": 10},
    context={"cost_used": 200, "requests_in_period": 5},
    mode=InteractionMode.DISJUNCTIVE,
)
# Passed: rate_limit passed

# Independent: Majority must pass
result = evaluator.evaluate(
    constraints={"cost_limit": 100, "rate_limit": 10, "time_window": "09:00-17:00"},
    context={"cost_used": 200, "requests_in_period": 5, "current_time": datetime.now()},
    mode=InteractionMode.INDEPENDENT,
)
# Depends on how many pass out of 3
```

### Anti-Gaming Detection

The evaluator detects manipulation patterns:

```python
result = evaluator.evaluate(
    constraints={"cost_limit": 1000},
    context={"cost_used": 960},  # 96% usage - boundary pushing
    agent_id="agent-001",
)

if result.anti_gaming_flags:
    for flag in result.anti_gaming_flags:
        print(f"Gaming detected: {flag}")
        # "boundary_pushing:cost_limit (usage_ratio=0.96)"
```

**Detection patterns:**

| Pattern              | Detection                                                     |
| -------------------- | ------------------------------------------------------------- |
| Boundary pushing     | `usage_ratio > 0.95` for any dimension                        |
| Constraint splitting | 8+ of last 10 evaluations have small ops (`used/limit < 0.1`) |

### EATP Tightening Validation

A fundamental EATP security property: delegations can only TIGHTEN constraints, never loosen them.

```python
# Parent grants agent $100 budget
parent_constraints = {"cost_limit": 100}

# Valid: child tightens to $50
child_constraints = {"cost_limit": 50}
violations = evaluator.validate_tightening(parent_constraints, child_constraints)
assert violations == []  # Valid

# Invalid: child loosens to $200
child_constraints = {"cost_limit": 200}
violations = evaluator.validate_tightening(parent_constraints, child_constraints)
# ["Dimension 'cost_limit': child constraint (200) is looser than parent (100)"]
```

## Built-in Dimensions

### CostLimitDimension

Maximum cost budget in cents.

```python
from kaizen.trust.constraints.builtin import CostLimitDimension

dim = CostLimitDimension()
constraint = dim.parse(1000.0)  # $10.00

result = dim.check(constraint, {"cost_used": 500.0})
assert result.satisfied  # Within budget
assert result.remaining == 500.0
```

**Context keys:** `cost_used`

### TimeDimension

Allowed time windows in "HH:MM-HH:MM" format.

```python
from kaizen.trust.constraints.builtin import TimeDimension
from datetime import datetime

dim = TimeDimension()
constraint = dim.parse("09:00-17:00")  # Business hours

result = dim.check(constraint, {"current_time": datetime(2025, 1, 15, 10, 30)})
assert result.satisfied  # 10:30 is within 09:00-17:00

# Overnight windows work too
constraint = dim.parse("22:00-06:00")  # Night shift
```

**Context keys:** `current_time` (datetime or time, defaults to now)

### ResourceDimension

Resource access patterns using glob syntax.

```python
from kaizen.trust.constraints.builtin import ResourceDimension

dim = ResourceDimension()
constraint = dim.parse(["data/**", "logs/*.log"])

result = dim.check(constraint, {"resource_requested": "data/users.json"})
assert result.satisfied  # Matches data/**

result = dim.check(constraint, {"resource_requested": "secrets/api.key"})
assert not result.satisfied  # Does not match any pattern
```

**Context keys:** `resource_requested`

### RateLimitDimension

Request rate limits as integer or "N/period" format.

```python
from kaizen.trust.constraints.builtin import RateLimitDimension

dim = RateLimitDimension()

# Simple count
constraint = dim.parse(100)

# With period
constraint = dim.parse("100/minute")  # Also: second, hour, day

result = dim.check(constraint, {"requests_in_period": 50})
assert result.satisfied
assert result.remaining == 50
```

**Context keys:** `requests_in_period`

### DataAccessDimension

Data classification and PII controls.

```python
from kaizen.trust.constraints.builtin import DataAccessDimension

dim = DataAccessDimension()

# Simple mode
constraint = dim.parse("no_pii")
result = dim.check(constraint, {"contains_pii": True})
assert not result.satisfied  # PII blocked

# With classification
constraint = dim.parse({
    "mode": "allow_all",
    "allowed_classifications": ["internal", "external"],
})
result = dim.check(constraint, {"data_classification": "restricted"})
assert not result.satisfied  # Restricted not in allowed list
```

**Modes:** `no_pii`, `internal_only`, `allow_all`
**Context keys:** `contains_pii`, `data_classification`

### CommunicationDimension

External communication restrictions.

```python
from kaizen.trust.constraints.builtin import CommunicationDimension

dim = CommunicationDimension()

# Block all external
constraint = dim.parse("none")

# Internal only
constraint = dim.parse("internal_only")
result = dim.check(constraint, {"communication_target": "api.internal.company.com"})
assert result.satisfied

# Allowed domains
constraint = dim.parse({
    "mode": "allowed_domains",
    "allowed_domains": ["api.openai.com", "anthropic.com"],
})
result = dim.check(constraint, {"communication_target": "api.openai.com"})
assert result.satisfied
```

**Modes:** `none`, `internal_only`, `allowed_domains`
**Context keys:** `communication_target`

## Integration Examples

### Complete Example: Posture + Constraints + Circuit Breaker

```python
from kaizen.trust import (
    TrustPosture,
    PostureStateMachine,
    PostureAwareAgent,
    PostureCircuitBreaker,
    CircuitBreakerConfig,
    TrustMetricsCollector,
)
from kaizen.trust.constraints import (
    ConstraintDimensionRegistry,
    MultiDimensionEvaluator,
    InteractionMode,
)
from kaizen.trust.constraints.builtin import register_builtin_dimensions

# 1. Setup posture management
machine = PostureStateMachine(default_posture=TrustPosture.SUPERVISED)
machine.set_posture("agent-001", TrustPosture.ASSISTED)

# 2. Setup circuit breaker
breaker = PostureCircuitBreaker(
    posture_machine=machine,
    config=CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30,
        downgrade_on_open="human_decides",
    ),
)

# 3. Setup constraints
registry = ConstraintDimensionRegistry()
register_builtin_dimensions(registry)
evaluator = MultiDimensionEvaluator(registry, enable_anti_gaming=True)

# 4. Setup metrics
metrics = TrustMetricsCollector()

# 5. Wrap agent with posture awareness
agent = PostureAwareAgent(
    base_agent=my_base_agent,
    agent_id="agent-001",
    posture_machine=machine,
    notification_handler=my_notification_handler,
    assisted_delay_seconds=5.0,
)

# 6. Execute with full governance
async def execute_with_governance(query: str, context: dict):
    # Check constraints first
    constraint_result = evaluator.evaluate(
        constraints={
            "cost_limit": 1000,
            "rate_limit": "100/minute",
        },
        context=context,
        mode=InteractionMode.CONJUNCTIVE,
        agent_id="agent-001",
    )

    if not constraint_result.satisfied:
        metrics.record_constraint_evaluation(
            passed=False,
            failed_dimensions=constraint_result.failed_dimensions,
        )
        raise PermissionError(f"Constraint violation: {constraint_result.failed_dimensions}")

    # Check circuit breaker
    if not await breaker.can_proceed("agent-001"):
        raise PermissionError("Circuit breaker open")

    # Execute with posture enforcement
    try:
        result = await agent.run(query=query)
        await breaker.record_success("agent-001")
        metrics.record_constraint_evaluation(passed=True, failed_dimensions=[])
        return result
    except Exception as e:
        await breaker.record_failure(
            agent_id="agent-001",
            error_type=type(e).__name__,
            error_message=str(e),
            action="run",
            severity="medium",
        )
        raise
```

### Custom Constraint Dimension Example

```python
from kaizen.trust.constraints import (
    ConstraintDimension,
    ConstraintValue,
    ConstraintCheckResult,
    ConstraintDimensionRegistry,
)
from typing import Any, Dict, List

class ModelAccessDimension(ConstraintDimension):
    """Restricts which AI models an agent can use."""

    @property
    def name(self) -> str:
        return "model_access"

    @property
    def description(self) -> str:
        return "Allowed AI models for agent"

    @property
    def requires_audit(self) -> bool:
        return True

    def parse(self, value: Any) -> ConstraintValue:
        if isinstance(value, str):
            models = [value]
        elif isinstance(value, (list, tuple)):
            models = list(value)
        else:
            raise ValueError(f"Model access must be string or list: {value}")

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=set(m.lower() for m in models),
            metadata={"model_count": len(models)},
        )

    def check(
        self,
        constraint: ConstraintValue,
        context: Dict[str, Any],
    ) -> ConstraintCheckResult:
        allowed_models = constraint.parsed
        requested_model = context.get("model", "").lower()

        if not requested_model:
            return ConstraintCheckResult(
                satisfied=True,
                reason="no model requested",
            )

        if requested_model in allowed_models:
            return ConstraintCheckResult(
                satisfied=True,
                reason=f"model '{requested_model}' is allowed",
            )

        return ConstraintCheckResult(
            satisfied=False,
            reason=f"model '{requested_model}' not in allowed list: {allowed_models}",
        )

    def validate_tightening(
        self,
        parent: ConstraintValue,
        child: ConstraintValue,
    ) -> bool:
        # Child must be subset of parent
        return child.parsed.issubset(parent.parsed)

    def compose(self, constraints: List[ConstraintValue]) -> ConstraintValue:
        # Intersection of all allowed models
        if not constraints:
            raise ValueError("Cannot compose empty constraints")

        result = constraints[0].parsed.copy()
        for c in constraints[1:]:
            result &= c.parsed

        return ConstraintValue(
            dimension=self.name,
            raw_value=list(result),
            parsed=result,
            metadata={"composed": True},
        )

# Register with security review
registry = ConstraintDimensionRegistry()
registry.register(ModelAccessDimension(), requires_review=True)

# After security review
registry.approve_dimension("model_access", reviewer="security-team")

# Use
evaluator = MultiDimensionEvaluator(registry)
result = evaluator.evaluate(
    constraints={"model_access": ["gpt-4", "claude-3"]},
    context={"model": "gpt-4"},
)
assert result.satisfied
```

### Multi-Tenant Posture Management

```python
from kaizen.trust import PostureStateMachine, TrustPosture
from kaizen.trust.postures import TransitionGuard, PostureTransition

class MultiTenantPostureManager:
    """Manages postures across multiple tenants."""

    def __init__(self):
        self._machines: dict[str, PostureStateMachine] = {}

    def get_machine(self, tenant_id: str) -> PostureStateMachine:
        if tenant_id not in self._machines:
            machine = PostureStateMachine(
                default_posture=TrustPosture.SUPERVISED,
                require_upgrade_approval=True,
            )

            # Add tenant-specific guard
            machine.add_guard(TransitionGuard(
                name=f"tenant_{tenant_id}_policy",
                check_fn=lambda req: self._check_tenant_policy(tenant_id, req),
                applies_to=[PostureTransition.UPGRADE],
                reason_on_failure=f"Tenant {tenant_id} policy violation",
            ))

            self._machines[tenant_id] = machine

        return self._machines[tenant_id]

    def _check_tenant_policy(self, tenant_id: str, request) -> bool:
        # Implement tenant-specific upgrade policies
        # e.g., check subscription tier, compliance requirements
        return True

# Usage
manager = MultiTenantPostureManager()

# Tenant A operations
tenant_a_machine = manager.get_machine("tenant-a")
tenant_a_machine.set_posture("agent-001", TrustPosture.FULL_AUTONOMY)

# Tenant B has different policies
tenant_b_machine = manager.get_machine("tenant-b")
tenant_b_machine.set_posture("agent-002", TrustPosture.SUPERVISED)
```

## API Reference

### Import Paths

```python
# Posture system
from kaizen.trust import (
    TrustPosture,
    PostureStateMachine,
    PostureAwareAgent,
    PostureCircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    FailureEvent,
    ApprovalHandler,
    NotificationHandler,
    AuditEntry,
)

from kaizen.trust.postures import (
    PostureTransition,
    PostureTransitionRequest,
    TransitionResult,
    TransitionGuard,
    PostureConstraints,
    PostureResult,
    TrustPostureMapper,
)

# Constraint system
from kaizen.trust.constraints import (
    ConstraintDimension,
    ConstraintDimensionRegistry,
    ConstraintValue,
    ConstraintCheckResult,
    MultiDimensionEvaluator,
    InteractionMode,
    EvaluationResult,
)

from kaizen.trust.constraints.builtin import (
    CostLimitDimension,
    TimeDimension,
    ResourceDimension,
    RateLimitDimension,
    DataAccessDimension,
    CommunicationDimension,
    register_builtin_dimensions,
)

# Metrics
from kaizen.trust import (
    TrustMetricsCollector,
    PostureMetrics,
    ConstraintMetrics,
    POSTURE_LEVEL_MAP,
)
```

### Key Classes

| Class                         | Purpose                                     |
| ----------------------------- | ------------------------------------------- |
| `TrustPosture`                | Enum of five autonomy levels                |
| `PostureStateMachine`         | Manages posture transitions with guards     |
| `PostureCircuitBreaker`       | Auto-downgrades on failure accumulation     |
| `PostureAwareAgent`           | Wraps agents with posture enforcement       |
| `ConstraintDimension`         | Abstract base for constraint plugins        |
| `ConstraintDimensionRegistry` | Manages dimension registration and approval |
| `MultiDimensionEvaluator`     | Evaluates multi-dimension constraints       |
| `TrustMetricsCollector`       | Thread-safe metrics collection              |
