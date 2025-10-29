# Kaizen Hooks System

**Quick reference for lifecycle event hooks and hook management**

## Overview

The hooks system provides zero-code-change observability through lifecycle events. Register hooks that execute on PRE/POST events (agent loop, tool use, checkpoints) without modifying agent logic.

**Location**: `kaizen.core.autonomy.hooks`
**Performance**: <5ms overhead (p95), <0.56KB memory per hook
**Opt-in**: Enable via `config.hooks_enabled=True`

## Quick Start

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookContext, HookResult, HookPriority
from kaizen.core.base_agent import BaseAgent

# Define custom hook
async def my_hook(context: HookContext) -> HookResult:
    print(f"Event: {context.event_type}, Agent: {context.agent_id}")
    return HookResult(success=True)

# Register hook
hook_manager = HookManager()
hook_manager.register(HookEvent.PRE_AGENT_LOOP, my_hook, HookPriority.NORMAL)

# Use with agent
agent = BaseAgent(config=config, signature=signature, hook_manager=hook_manager)
```

## Lifecycle Events

### Available HookEvents

**Agent Lifecycle**:
- `PRE_AGENT_LOOP`: Before agent execution starts
- `POST_AGENT_LOOP`: After agent execution completes

**Tool Execution**:
- `PRE_TOOL_USE`: Before tool is called
- `POST_TOOL_USE`: After tool completes

**Specialist Invocation**:
- `PRE_SPECIALIST_INVOKE`: Before specialist call
- `POST_SPECIALIST_INVOKE`: After specialist call

**Permission Checks**:
- `PRE_PERMISSION_CHECK`: Before permission check
- `POST_PERMISSION_CHECK`: After permission check

**Checkpoints**:
- `PRE_CHECKPOINT_SAVE`: Before checkpoint save
- `POST_CHECKPOINT_SAVE`: After checkpoint save

## HookContext

Context passed to every hook:

```python
@dataclass
class HookContext:
    event_type: HookEvent          # Which event triggered
    agent_id: str                  # Agent identifier
    trace_id: str                  # Unique trace ID
    timestamp: float               # Event timestamp
    data: Dict[str, Any]           # Event-specific data
    metadata: Dict[str, Any]       # Optional metadata
```

## HookResult

Return value from hooks:

```python
@dataclass
class HookResult:
    success: bool                  # Hook execution success
    data: Dict[str, Any] = {}      # Optional result data
    error: str | None = None       # Error message if failed
```

## Hook Priorities

Control execution order with priorities:

```python
class HookPriority(Enum):
    CRITICAL = 0     # Execute first (e.g., security, validation)
    HIGH = 1         # Important operations (e.g., audit trails, tracing)
    NORMAL = 2       # Default priority (e.g., logging, metrics)
    LOW = 3          # Execute last (e.g., cleanup, optional tasks)
```

## HookManager

Centralized hook registration and execution:

```python
manager = HookManager()

# Register hook for specific event
manager.register(HookEvent.PRE_AGENT_LOOP, my_hook, HookPriority.HIGH)

# Register hook for all events it declares
manager.register_hook(my_hook_object)

# Trigger event (internal, called by BaseAgent)
result = await manager.trigger(event_type, context)
```

## Builtin Hooks

### 1. LoggingHook
Structured logging with event tracking.

```python
from kaizen.core.autonomy.hooks.builtin import LoggingHook

hook = LoggingHook()
agent._hook_manager.register_hook(hook)
```

### 2. MetricsHook
Performance metrics collection.

```python
from kaizen.core.autonomy.hooks.builtin import MetricsHook

hook = MetricsHook()
agent._hook_manager.register_hook(hook)
```

### 3. CostTrackingHook
Track LLM API costs per agent execution.

```python
from kaizen.core.autonomy.hooks.builtin import CostTrackingHook

hook = CostTrackingHook()
agent._hook_manager.register_hook(hook)
```

### 4. PerformanceHook
Track execution time and performance statistics.

```python
from kaizen.core.autonomy.hooks.builtin import PerformanceHook

hook = PerformanceHook()
agent._hook_manager.register_hook(hook)
```

## Custom Hooks

### Async Hook Function

```python
async def custom_hook(context: HookContext) -> HookResult:
    # Access event data
    event_type = context.event_type
    data = context.data

    # Perform custom logic
    if event_type == HookEvent.PRE_TOOL_USE:
        tool_name = data.get("tool_name")
        print(f"Tool {tool_name} about to execute")

    return HookResult(success=True, data={"processed": True})
```

### Stateful Hook Class

```python
class CustomHook:
    def __init__(self, config):
        self.config = config
        self.state = {}

    async def handle(self, context: HookContext) -> HookResult:
        # Access instance state
        self.state[context.trace_id] = context.timestamp

        # Custom processing
        return HookResult(success=True)
```

## BaseAgent Integration

BaseAgent automatically includes a HookManager:

```python
# Access agent's hook manager
hook_manager = agent._hook_manager

# Register custom hooks
hook_manager.register(HookEvent.PRE_AGENT_LOOP, my_hook)

# Or pass hook manager during initialization
agent = BaseAgent(
    config=config,
    signature=signature,
    hook_manager=custom_hook_manager
)
```

## Common Patterns

### PRE/POST Event Pairing

```python
class TimingHook:
    def __init__(self):
        self.start_times = {}

    async def pre_event(self, context: HookContext) -> HookResult:
        self.start_times[context.trace_id] = time.time()
        return HookResult(success=True)

    async def post_event(self, context: HookContext) -> HookResult:
        duration = time.time() - self.start_times.pop(context.trace_id)
        print(f"Operation took {duration*1000:.1f}ms")
        return HookResult(success=True)

# Register paired hooks
timing = TimingHook()
manager.register(HookEvent.PRE_AGENT_LOOP, timing.pre_event)
manager.register(HookEvent.POST_AGENT_LOOP, timing.post_event)
```

### Event Filtering

```python
async def filtered_hook(context: HookContext) -> HookResult:
    # Only process specific events
    if context.event_type not in [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]:
        return HookResult(success=True)  # Skip other events

    # Process tool events
    tool_name = context.data.get("tool_name")
    print(f"Tool event: {tool_name}")

    return HookResult(success=True)
```

### Multi-Agent Coordination

```python
class SharedMetricsHook:
    def __init__(self):
        self.metrics = {}  # Shared across all agents

    async def handle(self, context: HookContext) -> HookResult:
        agent_id = context.agent_id

        # Track per-agent metrics
        if agent_id not in self.metrics:
            self.metrics[agent_id] = {"calls": 0}

        self.metrics[agent_id]["calls"] += 1

        return HookResult(success=True)

# Use same hook instance for all agents
shared_hook = SharedMetricsHook()
agent1._hook_manager.register(HookEvent.POST_AGENT_LOOP, shared_hook.handle)
agent2._hook_manager.register(HookEvent.POST_AGENT_LOOP, shared_hook.handle)
```

## Use Cases

### Observability
- Distributed tracing (Jaeger/Zipkin)
- Metrics collection (Prometheus)
- Structured logging (ELK Stack)
- Performance monitoring

### Compliance
- Audit trails (SOC2, GDPR, HIPAA)
- Security logging
- Access control enforcement
- Data retention policies

### Reliability
- Circuit breakers
- Rate limiting
- Error tracking
- Retry logic

### Business Intelligence
- Cost tracking
- Usage analytics
- A/B testing
- Feature flags

## Testing

```python
import pytest
from kaizen.core.autonomy.hooks import HookContext, HookEvent

async def test_custom_hook():
    # Create test context
    context = HookContext(
        event_type=HookEvent.PRE_AGENT_LOOP,
        agent_id="test-agent",
        trace_id="trace-123",
        timestamp=time.time(),
        data={"inputs": {"question": "test"}},
        metadata={}
    )

    # Test hook
    result = await my_hook(context)

    assert result.success is True
    assert "processed" in result.data
```

## Resources

- **Implementation**: `src/kaizen/core/autonomy/hooks/`
- **Examples**: `examples/autonomy/hooks/` (audit_trail_example.py, distributed_tracing_example.py, prometheus_metrics_example.py)
- **Docs**: `docs/features/hooks-system.md`, `docs/guides/hooks-system-guide.md`
- **Tests**: `tests/unit/core/autonomy/hooks/`, `tests/integration/autonomy/test_baseagent_hooks.py`
