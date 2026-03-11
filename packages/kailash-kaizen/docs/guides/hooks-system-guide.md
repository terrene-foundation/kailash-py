# Hooks System Guide

**Status**: ✅ Implemented (Phase 3)
**Location**: `src/kaizen/core/autonomy/hooks/`
**Tests**: 63 unit tests + integration tests (100% passing)

## Overview

The Hooks System provides event-driven extension points for autonomous agents, enabling:

- **10 lifecycle events** covering all key agent operations
- **Priority-based execution** with stable sorting (CRITICAL → HIGH → NORMAL → LOW)
- **Error isolation** - hook failures don't crash agent
- **Async execution** with 5-second timeout per hook
- **4 built-in hooks** for logging, metrics, cost tracking, and performance profiling
- **Filesystem discovery** for user-defined hooks

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      HookManager                            │
│  - Event registry (10 events)                              │
│  - Priority-based execution                                 │
│  - Error isolation per hook                                 │
│  - Filesystem discovery                                     │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────▼───────────┐
    │   Hook Handlers    │
    │  - LoggingHook     │
    │  - MetricsHook     │
    │  - CostTrackingHook│
    │  - PerformanceHook │
    └────────────────────┘
```

## Core Concepts

### 10 Lifecycle Events

```python
class HookEvent(Enum):
    # Tool usage
    PRE_TOOL_USE = "pre_tool_use"       # Before tool execution
    POST_TOOL_USE = "post_tool_use"     # After tool execution

    # Agent loop
    PRE_AGENT_LOOP = "pre_agent_loop"   # Before agent step
    POST_AGENT_LOOP = "post_agent_loop" # After agent step

    # Specialist invocation
    PRE_SPECIALIST_INVOKE = "pre_specialist_invoke"   # Before specialist call
    POST_SPECIALIST_INVOKE = "post_specialist_invoke" # After specialist call

    # Permission checks
    PRE_PERMISSION_CHECK = "pre_permission_check"   # Before permission check
    POST_PERMISSION_CHECK = "post_permission_check" # After permission check

    # Checkpoints
    PRE_CHECKPOINT_SAVE = "pre_checkpoint_save"   # Before checkpoint save
    POST_CHECKPOINT_SAVE = "post_checkpoint_save" # After checkpoint save
```

### Hook Priorities

```python
class HookPriority(Enum):
    CRITICAL = 0  # Execute first (security, validation)
    HIGH = 1      # Important operations (auditing, compliance)
    NORMAL = 2    # Default priority (logging, metrics)
    LOW = 3       # Execute last (cleanup, optional tasks)
```

### Hook Context

```python
@dataclass
class HookContext:
    """Context passed to hook handlers"""
    event_type: HookEvent       # Which event triggered this hook
    agent_id: str               # Agent identifier
    timestamp: float            # When event occurred
    data: dict[str, Any]        # Event-specific data
    metadata: dict[str, Any]    # Additional context
```

### Hook Result

```python
@dataclass
class HookResult:
    """Result returned by hook handler"""
    success: bool                       # Did hook succeed?
    data: dict[str, Any] = {}          # Result data
    error: str | None = None           # Error message if failed
    should_stop_propagation: bool = False  # Stop other hooks?
```

## Quick Start

### 1. Basic Hook Registration

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookContext, HookResult

# Create manager
hook_manager = HookManager()

# Define hook handler
async def my_hook(context: HookContext) -> HookResult:
    print(f"Tool {context.data['tool_name']} executed")
    return HookResult(success=True)

# Register for event
hook_manager.register(HookEvent.POST_TOOL_USE, my_hook)

# Trigger event
await hook_manager.trigger(
    HookEvent.POST_TOOL_USE,
    agent_id="agent1",
    data={"tool_name": "web_search", "result": "..."}
)
```

### 2. Using Built-in Hooks

```python
from kaizen.core.autonomy.hooks import HookManager
from kaizen.core.autonomy.hooks.builtin import (
    LoggingHook,
    MetricsHook,
    CostTrackingHook,
    PerformanceProfilerHook
)

hook_manager = HookManager()

# Register built-in hooks
hook_manager.register_hook(LoggingHook())
hook_manager.register_hook(MetricsHook())
hook_manager.register_hook(CostTrackingHook())
hook_manager.register_hook(PerformanceProfilerHook())

# Built-in hooks automatically handle their events
# LoggingHook logs all 10 events
# MetricsHook tracks counts and timing
# CostTrackingHook accumulates LLM costs
# PerformanceProfilerHook measures latencies
```

### 3. Custom Hook with Priority

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookPriority
from kaizen.core.autonomy.hooks.protocol import BaseHook

class SecurityValidationHook(BaseHook):
    """Validate tool usage for security"""

    # Define which events this hook handles
    events = [HookEvent.PRE_TOOL_USE]

    # Set priority to CRITICAL (execute first)
    priority = HookPriority.CRITICAL

    async def handle(self, context: HookContext) -> HookResult:
        tool_name = context.data.get("tool_name")

        # Validate tool is allowed
        if tool_name in ["rm", "delete", "destroy"]:
            return HookResult(
                success=False,
                error=f"Tool {tool_name} not allowed",
                should_stop_propagation=True  # Block execution
            )

        return HookResult(success=True)

# Register with automatic priority
hook_manager.register_hook(SecurityValidationHook())
```

### 4. Hook Stats and Monitoring

```python
# Get execution statistics
stats = hook_manager.get_hook_stats()

print(f"Total triggers: {stats['total_triggers']}")
print(f"Total successes: {stats['total_successes']}")
print(f"Total failures: {stats['total_failures']}")

# Per-event stats
for event, event_stats in stats['by_event'].items():
    print(f"{event}: {event_stats['triggers']} triggers, {event_stats['failures']} failures")

# Reset stats
hook_manager.reset_stats()
```

## Built-in Hooks

### 1. LoggingHook

Structured logging for all lifecycle events.

```python
from kaizen.core.autonomy.hooks.builtin import LoggingHook

hook = LoggingHook(log_level="INFO")
hook_manager.register_hook(hook)

# Logs all 10 events with structured format:
# INFO - Event: POST_TOOL_USE, Agent: agent1, Tool: web_search
```

### 2. MetricsHook

Prometheus-compatible metrics tracking.

```python
from kaizen.core.autonomy.hooks.builtin import MetricsHook

hook = MetricsHook()
hook_manager.register_hook(hook)

# Get metrics
metrics = hook.get_metrics()
print(f"Tool calls: {metrics['tool_use_count']}")
print(f"Agent steps: {metrics['agent_loop_count']}")
print(f"Avg tool latency: {metrics['avg_tool_latency_ms']:.2f}ms")
```

### 3. CostTrackingHook

LLM cost accumulation by agent and tool.

```python
from kaizen.core.autonomy.hooks.builtin import CostTrackingHook

hook = CostTrackingHook()
hook_manager.register_hook(hook)

# Cost tracked automatically from tool/agent/specialist calls
# with "estimated_cost_usd" in context.data

# Get total cost
total = hook.get_total_cost()
print(f"Total spent: ${total:.4f}")

# Get per-agent costs
agent_costs = hook.get_costs_by_agent()
for agent_id, cost in agent_costs.items():
    print(f"{agent_id}: ${cost:.4f}")
```

### 4. PerformanceProfilerHook

Latency tracking for performance analysis.

```python
from kaizen.core.autonomy.hooks.builtin import PerformanceProfilerHook

hook = PerformanceProfilerHook()
hook_manager.register_hook(hook)

# Get latency statistics
stats = hook.get_latency_stats()
print(f"Avg latency: {stats['avg_latency_ms']:.2f}ms")
print(f"P50: {stats['p50_latency_ms']:.2f}ms")
print(f"P95: {stats['p95_latency_ms']:.2f}ms")
print(f"P99: {stats['p99_latency_ms']:.2f}ms")
```

## Patterns

### Pattern 1: Pre/Post Hook Pair

```python
# Track timing with pre/post hooks
timing_data = {}

async def pre_tool_hook(context: HookContext) -> HookResult:
    tool_name = context.data['tool_name']
    timing_data[tool_name] = time.time()
    return HookResult(success=True)

async def post_tool_hook(context: HookContext) -> HookResult:
    tool_name = context.data['tool_name']
    elapsed = time.time() - timing_data.pop(tool_name, 0)
    print(f"{tool_name} took {elapsed:.3f}s")
    return HookResult(success=True)

hook_manager.register(HookEvent.PRE_TOOL_USE, pre_tool_hook)
hook_manager.register(HookEvent.POST_TOOL_USE, post_tool_hook)
```

### Pattern 2: Conditional Hook Execution

```python
async def conditional_hook(context: HookContext) -> HookResult:
    # Only run for specific agents
    if context.agent_id == "production_agent":
        # Do validation
        result = validate_action(context.data)
        return HookResult(success=result)

    # Skip for other agents
    return HookResult(success=True)
```

### Pattern 3: Hook with State

```python
class StatefulHook(BaseHook):
    events = [HookEvent.POST_AGENT_LOOP]

    def __init__(self):
        self.step_count = 0
        self.error_count = 0

    async def handle(self, context: HookContext) -> HookResult:
        self.step_count += 1

        if context.data.get("error"):
            self.error_count += 1

        # Alert if error rate too high
        error_rate = self.error_count / self.step_count
        if error_rate > 0.1:  # 10% threshold
            return HookResult(
                success=False,
                error=f"Error rate too high: {error_rate:.1%}",
                should_stop_propagation=True
            )

        return HookResult(success=True)
```

### Pattern 4: Multi-Event Hook

```python
class AuditHook(BaseHook):
    """Audit trail for multiple events"""

    events = [
        HookEvent.POST_TOOL_USE,
        HookEvent.POST_PERMISSION_CHECK,
        HookEvent.POST_CHECKPOINT_SAVE
    ]
    priority = HookPriority.HIGH

    def __init__(self, audit_log_path: str):
        self.log_path = audit_log_path

    async def handle(self, context: HookContext) -> HookResult:
        # Write audit entry
        entry = {
            "timestamp": context.timestamp,
            "event": context.event_type.value,
            "agent_id": context.agent_id,
            "data": context.data
        }

        async with aiofiles.open(self.log_path, "a") as f:
            await f.write(json.dumps(entry) + "\n")

        return HookResult(success=True)
```

## Advanced Usage

### Filesystem Discovery

Place hook files in `.kaizen/hooks/` directory:

```python
# .kaizen/hooks/my_custom_hook.py
from kaizen.core.autonomy.hooks import HookEvent, HookContext, HookResult
from kaizen.core.autonomy.hooks.protocol import BaseHook

class MyCustomHook(BaseHook):
    events = [HookEvent.POST_AGENT_LOOP]

    async def handle(self, context: HookContext) -> HookResult:
        # Custom logic
        return HookResult(success=True)
```

Discover and load automatically:

```python
# Discover hooks from filesystem
discovered = await hook_manager.discover_hooks_from_filesystem(
    search_path=".kaizen/hooks"
)

print(f"Discovered {len(discovered)} hooks")

# Load all discovered hooks
for hook_class in discovered:
    hook_manager.register_hook(hook_class())
```

### Hook Timeout Configuration

```python
# Default timeout is 5 seconds per hook
await hook_manager.trigger(
    HookEvent.POST_TOOL_USE,
    agent_id="agent1",
    data={"tool": "slow_tool"},
    timeout=10.0  # Custom timeout for slow operations
)
```

### Error Isolation

```python
# Even if one hook fails, others continue
async def failing_hook(context: HookContext) -> HookResult:
    raise ValueError("Hook failed!")

async def working_hook(context: HookContext) -> HookResult:
    print("This still runs!")
    return HookResult(success=True)

hook_manager.register(HookEvent.POST_TOOL_USE, failing_hook)
hook_manager.register(HookEvent.POST_TOOL_USE, working_hook)

# Trigger - failing_hook fails, but working_hook still executes
results = await hook_manager.trigger(
    HookEvent.POST_TOOL_USE,
    agent_id="agent1",
    data={}
)

# Results: [HookResult(success=False, error="..."), HookResult(success=True)]
```

## Best Practices

### 1. Use Appropriate Priorities

```python
# CRITICAL: Security, validation, blocking operations
class SecurityHook(BaseHook):
    priority = HookPriority.CRITICAL

# HIGH: Auditing, compliance, important logging
class AuditHook(BaseHook):
    priority = HookPriority.HIGH

# NORMAL: General logging, metrics (default)
class LoggingHook(BaseHook):
    priority = HookPriority.NORMAL

# LOW: Cleanup, optional operations
class CleanupHook(BaseHook):
    priority = HookPriority.LOW
```

### 2. Keep Hooks Fast

```python
# Good: Quick operations
async def fast_hook(context: HookContext) -> HookResult:
    await log_to_memory(context)  # Fast
    return HookResult(success=True)

# Bad: Slow operations block other hooks
async def slow_hook(context: HookContext) -> HookResult:
    await send_to_external_api(context)  # Slow, use background task
    return HookResult(success=True)

# Better: Queue work for background processing
async def better_hook(context: HookContext) -> HookResult:
    await queue.put(context)  # Fast
    return HookResult(success=True)
```

### 3. Handle Errors Gracefully

```python
async def robust_hook(context: HookContext) -> HookResult:
    try:
        result = await process_event(context)
        return HookResult(success=True, data={"result": result})
    except Exception as e:
        logger.error(f"Hook failed: {e}")
        return HookResult(
            success=False,
            error=str(e)
        )
```

### 4. Use should_stop_propagation Sparingly

```python
# Only stop propagation for critical failures
async def validation_hook(context: HookContext) -> HookResult:
    if not is_valid(context.data):
        return HookResult(
            success=False,
            error="Validation failed",
            should_stop_propagation=True  # Block other hooks
        )
    return HookResult(success=True)
```

## Testing

### Unit Testing Hooks

```python
import pytest
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookContext

@pytest.mark.asyncio
async def test_hook_execution():
    manager = HookManager()
    called = False

    async def test_hook(context: HookContext):
        nonlocal called
        called = True
        return HookResult(success=True)

    manager.register(HookEvent.POST_TOOL_USE, test_hook)

    await manager.trigger(
        HookEvent.POST_TOOL_USE,
        agent_id="test",
        data={}
    )

    assert called

@pytest.mark.asyncio
async def test_hook_priority():
    manager = HookManager()
    execution_order = []

    async def high_priority(context):
        execution_order.append("high")
        return HookResult(success=True)

    async def low_priority(context):
        execution_order.append("low")
        return HookResult(success=True)

    # Register in reverse order
    manager.register(HookEvent.POST_TOOL_USE, low_priority, HookPriority.LOW)
    manager.register(HookEvent.POST_TOOL_USE, high_priority, HookPriority.HIGH)

    await manager.trigger(HookEvent.POST_TOOL_USE, "test", {})

    # HIGH executes before LOW despite registration order
    assert execution_order == ["high", "low"]
```

## Troubleshooting

### Issue: Hook not executing

**Problem**: Registered hook doesn't fire

**Solution**: Verify event type matches trigger:

```python
# Wrong event type
hook_manager.register(HookEvent.PRE_TOOL_USE, my_hook)
await hook_manager.trigger(HookEvent.POST_TOOL_USE, ...)  # Wrong event!

# Correct
hook_manager.register(HookEvent.POST_TOOL_USE, my_hook)
await hook_manager.trigger(HookEvent.POST_TOOL_USE, ...)  # Matches
```

### Issue: Hook timeout

**Problem**: Hook exceeds 5-second timeout

**Solution**: Increase timeout or optimize hook:

```python
# Option 1: Increase timeout
await hook_manager.trigger(event, agent_id, data, timeout=10.0)

# Option 2: Optimize hook (use background task for slow work)
async def optimized_hook(context):
    asyncio.create_task(slow_operation(context))  # Background
    return HookResult(success=True)
```

### Issue: Hook prevents other hooks from running

**Problem**: One hook blocks all subsequent hooks

**Solution**: Don't use `should_stop_propagation` unless critical:

```python
# Bad: Stops all other hooks
return HookResult(success=False, should_stop_propagation=True)

# Good: Let other hooks run
return HookResult(success=False)  # Other hooks still execute
```

## API Reference

### HookManager

```python
class HookManager:
    def register(event_type, handler, priority=NORMAL) -> None
    def register_hook(hook: HookHandler) -> None
    async def trigger(event_type, agent_id, data, timeout=5.0) -> list[HookResult]
    def unregister(event_type, handler) -> bool
    def get_hook_stats() -> dict
    def reset_stats() -> None
    async def discover_hooks_from_filesystem(search_path) -> list[type]
```

### BaseHook

```python
class BaseHook:
    events: ClassVar[list[HookEvent]]    # Events to handle
    priority: ClassVar[HookPriority]     # Execution priority

    async def handle(context: HookContext) -> HookResult
```

## See Also

- [Interrupt Mechanism Guide](interrupt-mechanism-guide.md) - Graceful shutdown coordination
- [State Persistence Guide](state-persistence-guide.md) - Checkpoint/resume functionality
- [ADR-014: Hooks System](../architecture/adr/ADR-014-hooks-system.md)
