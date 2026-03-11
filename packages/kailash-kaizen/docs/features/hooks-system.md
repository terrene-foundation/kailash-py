

# Hooks System

## What is the Hooks System?

The Hooks System is a lifecycle event framework for autonomous agents that enables **zero-code-change integration** of cross-cutting concerns like monitoring, tracing, auditing, and metrics collection.

Hooks allow you to inject custom behavior at key points in agent execution:
- Before/after agent loops
- Before/after tool usage
- On agent state changes
- On custom lifecycle events

**Key Benefits:**
- ✅ **Zero code changes** - Add observability without modifying agent logic
- ✅ **Composable** - Mix and match multiple hooks
- ✅ **Production-ready** - Enterprise features (tracing, metrics, auditing)
- ✅ **High performance** - <5ms overhead (p95), <0.56KB memory per hook

## When to Use Hooks

Use hooks when you need to:

1. **Monitor agent behavior** - Collect metrics, traces, or logs
2. **Audit agent actions** - Comply with SOC2, GDPR, HIPAA requirements
3. **Debug production issues** - Track execution flow without code changes
4. **Enforce policies** - Validate inputs/outputs, enforce timeouts
5. **Collect analytics** - Track agent performance and success rates

## Core Concepts

### Hook Events

Events that trigger hook execution:

| Event | When Triggered | Use Case |
|-------|----------------|----------|
| `PRE_AGENT_LOOP` | Before agent processes a request | Input validation, tracing start |
| `POST_AGENT_LOOP` | After agent completes processing | Metrics collection, tracing end |
| `PRE_TOOL_USE` | Before agent calls a tool | Tool usage auditing |
| `POST_TOOL_USE` | After tool execution completes | Tool performance tracking |

### Hook Priority

Controls execution order when multiple hooks exist for the same event:

- `HIGHEST = 0` - Runs first (e.g., audit trails, authentication)
- `HIGH = 1` - Security, compliance hooks
- `NORMAL = 2` - Default priority
- `LOW = 3` - Cleanup, optional logging
- `LOWEST = 4` - Runs last

### Hook Context

Data available to hooks during execution:

```python
class HookContext:
    event_type: HookEvent       # Which event triggered this hook
    agent_id: str               # ID of the agent
    timestamp: float            # When event occurred
    data: Dict[str, Any]        # Event-specific data (inputs, outputs)
    metadata: Dict[str, Any]    # Optional metadata
    trace_id: str               # Distributed tracing ID
```

### Hook Result

Return value from hook execution:

```python
class HookResult:
    success: bool               # Did hook execute successfully?
    data: Dict[str, Any]        # Optional data from hook
    error: str | None           # Error message if failed
```

## Quick Start

### Basic Hook Registration

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookEvent,
    HookContext,
    HookResult,
    HookPriority,
)

# 1. Create hook function
async def my_hook(context: HookContext) -> HookResult:
    print(f"Agent {context.agent_id} is executing!")
    return HookResult(success=True)

# 2. Register hook
hook_manager = HookManager()
hook_manager.register(
    HookEvent.PRE_AGENT_LOOP,
    my_hook,
    HookPriority.NORMAL
)

# 3. Attach to agent
agent = BaseAgent(
    config=my_config,
    signature=my_signature,
    hook_manager=hook_manager  # ← Hooks enabled
)

# 4. Run agent (hooks execute automatically)
result = agent.run(question="What is AI?")
```

### Multiple Hooks

Register multiple hooks for comprehensive observability:

```python
hook_manager = HookManager()

# Tracing
hook_manager.register(HookEvent.PRE_AGENT_LOOP, start_trace, HookPriority.HIGH)
hook_manager.register(HookEvent.POST_AGENT_LOOP, end_trace, HookPriority.HIGH)

# Metrics
hook_manager.register(HookEvent.PRE_AGENT_LOOP, record_start, HookPriority.NORMAL)
hook_manager.register(HookEvent.POST_AGENT_LOOP, record_end, HookPriority.NORMAL)

# Audit
hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_start, HookPriority.HIGHEST)
hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_end, HookPriority.HIGHEST)

# All 6 hooks execute automatically on agent.run()
```

## Production Examples

### 1. Distributed Tracing

Track agent execution across services with OpenTelemetry:

```python
class DistributedTracingHook:
    """Integrate OpenTelemetry tracing."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.active_spans = {}

    async def start_span(self, context: HookContext) -> HookResult:
        # Create OpenTelemetry span
        from opentelemetry import trace
        tracer = trace.get_tracer(self.service_name)
        span = tracer.start_span(f"agent.{context.agent_id}.loop")

        # Store for completion
        self.active_spans[context.trace_id] = span

        return HookResult(success=True, data={"span_started": True})

    async def end_span(self, context: HookContext) -> HookResult:
        # Complete span
        span = self.active_spans.pop(context.trace_id)
        span.set_attribute("agent.id", context.agent_id)
        span.end()

        return HookResult(success=True, data={"span_ended": True})

# Usage
tracing_hook = DistributedTracingHook("my-agent-service")
hook_manager.register(HookEvent.PRE_AGENT_LOOP, tracing_hook.start_span, HookPriority.HIGH)
hook_manager.register(HookEvent.POST_AGENT_LOOP, tracing_hook.end_span, HookPriority.HIGH)
```

**See**: `examples/autonomy/hooks/distributed_tracing_example.py`

### 2. Prometheus Metrics

Collect and export metrics for monitoring:

```python
class PrometheusMetricsHook:
    """Collect Prometheus metrics."""

    def __init__(self):
        from prometheus_client import Counter, Histogram

        self.loop_duration = Histogram(
            'agent_loop_duration_seconds',
            'Agent loop duration',
            ['agent_id']
        )
        self.loop_total = Counter(
            'agent_loop_total',
            'Total agent loops',
            ['agent_id']
        )
        self.loop_start_times = {}

    async def record_start(self, context: HookContext) -> HookResult:
        import time
        self.loop_start_times[context.trace_id] = time.time()
        self.loop_total.labels(agent_id=context.agent_id).inc()
        return HookResult(success=True)

    async def record_end(self, context: HookContext) -> HookResult:
        import time
        duration = time.time() - self.loop_start_times.pop(context.trace_id)
        self.loop_duration.labels(agent_id=context.agent_id).observe(duration)
        return HookResult(success=True, data={"duration": duration})

# Usage
metrics_hook = PrometheusMetricsHook()
hook_manager.register(HookEvent.PRE_AGENT_LOOP, metrics_hook.record_start)
hook_manager.register(HookEvent.POST_AGENT_LOOP, metrics_hook.record_end)
```

**See**: `examples/autonomy/hooks/prometheus_metrics_example.py`

### 3. Audit Trail (Compliance)

Create immutable audit logs for SOC2/GDPR/HIPAA compliance:

```python
@dataclass
class AuditEntry:
    timestamp: str
    event_type: str
    agent_id: str
    trace_id: str
    action: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    duration_ms: float
    success: bool

class AuditTrailHook:
    """Immutable audit trail for compliance."""

    def __init__(self, audit_log_path: Path):
        self.audit_log_path = audit_log_path
        self.loop_start_times = {}

    async def record_start(self, context: HookContext) -> HookResult:
        import time
        self.loop_start_times[context.trace_id] = time.time()

        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            event_type="AGENT_LOOP_START",
            agent_id=context.agent_id,
            trace_id=context.trace_id,
            action="agent_execution_start",
            inputs=context.data.get("inputs", {}),
            outputs={},
            duration_ms=0,
            success=True
        )

        # Append-only (immutable)
        with open(self.audit_log_path, "a") as f:
            json.dump(asdict(entry), f)
            f.write("\n")

        return HookResult(success=True, data={"audit_recorded": True})

    async def record_end(self, context: HookContext) -> HookResult:
        # Similar to record_start, but with outputs and duration
        # ...
        return HookResult(success=True)

# Usage
audit_hook = AuditTrailHook(Path("/var/log/kaizen/audit.jsonl"))
hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_hook.record_start, HookPriority.HIGHEST)
hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_hook.record_end, HookPriority.HIGHEST)
```

**See**: `examples/autonomy/hooks/audit_trail_example.py`

## Advanced Usage

### Custom Hook Classes

Create reusable hook classes with `BaseHook`:

```python
from kaizen.core.autonomy.hooks.protocol import BaseHook

class LoggingHook(BaseHook):
    """Reusable logging hook."""

    events = [HookEvent.PRE_AGENT_LOOP, HookEvent.POST_AGENT_LOOP]
    priority = HookPriority.NORMAL

    def __init__(self, logger_name: str):
        super().__init__(name="logging_hook")
        self.logger = logging.getLogger(logger_name)

    async def handle(self, context: HookContext) -> HookResult:
        if context.event_type == HookEvent.PRE_AGENT_LOOP:
            self.logger.info(f"Agent {context.agent_id} starting")
        else:
            self.logger.info(f"Agent {context.agent_id} completed")

        return HookResult(success=True)

# Usage (register for all events automatically)
logging_hook = LoggingHook("my_agent")
hook_manager.register_hook(logging_hook)  # ← Registers for both events
```

### Filesystem Hook Discovery

Load hooks dynamically from a directory:

```python
from pathlib import Path

# Create hooks directory structure:
# hooks/
#   ├── tracing.py
#   ├── metrics.py
#   └── audit.py

# Each file defines a BaseHook class
hook_manager = HookManager()
discovered_count = await hook_manager.discover_filesystem_hooks(
    Path("/path/to/hooks")
)

print(f"Discovered {discovered_count} hooks")
```

**Hook file format**:
```python
# hooks/tracing.py
from kaizen.core.autonomy.hooks.protocol import BaseHook
from kaizen.core.autonomy.hooks.types import *

class TracingHook(BaseHook):
    events = [HookEvent.PRE_AGENT_LOOP, HookEvent.POST_AGENT_LOOP]
    priority = HookPriority.HIGH

    def __init__(self):
        super().__init__(name="tracing_hook")

    async def handle(self, context: HookContext) -> HookResult:
        # Implementation here
        return HookResult(success=True)
```

### Error Isolation

Hooks are isolated - one hook's failure doesn't affect others:

```python
async def failing_hook(context: HookContext) -> HookResult:
    raise ValueError("Intentional error")

async def success_hook(context: HookContext) -> HookResult:
    return HookResult(success=True)

hook_manager.register(HookEvent.PRE_AGENT_LOOP, failing_hook)
hook_manager.register(HookEvent.PRE_AGENT_LOOP, success_hook)

# Agent runs successfully - error logged but isolated
result = agent.run(question="Test")  # ✅ Works
```

### Hook Timeouts

Protect against slow hooks:

```python
# Default timeout: 5 seconds per hook
results = await hook_manager.trigger(
    HookEvent.PRE_AGENT_LOOP,
    agent_id="my_agent",
    data={"inputs": {}},
    timeout=10.0  # Custom timeout
)
```

## Performance Characteristics

The Hooks System is designed for production use with minimal overhead:

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Hook execution overhead (p95) | <5ms | 0.008ms | ✅ **625x better** |
| Registration overhead | <1ms | 0.038ms | ✅ **26x better** |
| Stats tracking overhead | <0.1ms | ~0ms | ✅ Negligible |
| Concurrent hooks supported | >50 | 100+ | ✅ Validated |
| Memory per hook | <100KB | 0.56KB | ✅ **178x better** |

**Performance validated**: 8 performance benchmarks in `tests/performance/test_hooks_performance.py`

## Testing

### Unit Tests

Test hooks in isolation:

```python
import pytest
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import *

@pytest.mark.asyncio
async def test_my_hook():
    # Arrange
    hook_manager = HookManager()

    call_count = 0

    async def my_hook(context: HookContext) -> HookResult:
        nonlocal call_count
        call_count += 1
        return HookResult(success=True)

    hook_manager.register(HookEvent.PRE_AGENT_LOOP, my_hook)

    # Act
    results = await hook_manager.trigger(
        HookEvent.PRE_AGENT_LOOP,
        agent_id="test_agent",
        data={}
    )

    # Assert
    assert call_count == 1
    assert len(results) == 1
    assert results[0].success
```

### Integration Tests

Test hooks with real agents:

```python
@pytest.mark.asyncio
async def test_hooks_with_agent():
    # Arrange
    hook_manager = HookManager()
    hook_called = False

    async def my_hook(context: HookContext) -> HookResult:
        nonlocal hook_called
        hook_called = True
        return HookResult(success=True)

    hook_manager.register(HookEvent.PRE_AGENT_LOOP, my_hook)

    agent = BaseAgent(
        config=MyConfig(),
        signature=MySignature(),
        hook_manager=hook_manager
    )

    # Act
    result = agent.run(question="Test")

    # Assert
    assert hook_called  # Hook was triggered
    assert result is not None  # Agent still works
```

## Best Practices

### 1. Use Priorities Wisely

**DO:**
```python
# Audit first (HIGHEST), metrics last (NORMAL)
hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_hook, HookPriority.HIGHEST)
hook_manager.register(HookEvent.PRE_AGENT_LOOP, metrics_hook, HookPriority.NORMAL)
```

**DON'T:**
```python
# All at NORMAL - unpredictable order
hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_hook, HookPriority.NORMAL)
hook_manager.register(HookEvent.PRE_AGENT_LOOP, metrics_hook, HookPriority.NORMAL)
```

### 2. Keep Hooks Fast

**DO:**
```python
async def fast_hook(context: HookContext) -> HookResult:
    # Quick operation
    metrics.increment("agent_calls")
    return HookResult(success=True)
```

**DON'T:**
```python
async def slow_hook(context: HookContext) -> HookResult:
    # Slow I/O in hook - blocks agent execution
    await upload_to_s3(context.data)  # ❌ Bad
    return HookResult(success=True)
```

**BETTER:**
```python
async def async_hook(context: HookContext) -> HookResult:
    # Queue for background processing
    background_queue.put(context.data)  # ✅ Good
    return HookResult(success=True)
```

### 3. Handle Errors Gracefully

**DO:**
```python
async def resilient_hook(context: HookContext) -> HookResult:
    try:
        # Potentially failing operation
        await external_api.log(context.data)
        return HookResult(success=True)
    except Exception as e:
        # Log error but don't fail
        logger.error(f"Hook failed: {e}")
        return HookResult(success=False, error=str(e))
```

**DON'T:**
```python
async def fragile_hook(context: HookContext) -> HookResult:
    # Unhandled exception - hook system catches it, but better to handle
    await external_api.log(context.data)  # ❌ May crash
    return HookResult(success=True)
```

### 4. Use Structured Data

**DO:**
```python
async def structured_hook(context: HookContext) -> HookResult:
    # Return structured data
    return HookResult(
        success=True,
        data={
            "duration_ms": 123.45,
            "status": "completed",
            "trace_id": context.trace_id
        }
    )
```

**DON'T:**
```python
async def unstructured_hook(context: HookContext) -> HookResult:
    # Generic data - hard to use
    return HookResult(success=True, data={"info": "done"})  # ❌ Vague
```

## Troubleshooting

### Hook Not Triggering

**Problem**: Hook doesn't execute when agent runs.

**Solution**:
```python
# 1. Verify hook is registered
stats = hook_manager.get_stats()
print(f"Registered hooks: {stats}")

# 2. Check event type matches
# PRE_AGENT_LOOP only triggers BEFORE agent runs
hook_manager.register(HookEvent.PRE_AGENT_LOOP, my_hook)  # ← Event must match

# 3. Ensure agent has hook_manager
agent = BaseAgent(..., hook_manager=hook_manager)  # ← Must pass hook_manager
```

### Slow Agent Execution

**Problem**: Agent takes longer after adding hooks.

**Solution**:
```python
# 1. Profile hook execution
import time

async def profiled_hook(context: HookContext) -> HookResult:
    start = time.time()
    # ... hook logic ...
    duration_ms = (time.time() - start) * 1000
    print(f"Hook took {duration_ms:.2f}ms")
    return HookResult(success=True)

# 2. Move slow operations to background
async def optimized_hook(context: HookContext) -> HookResult:
    # Queue for background processing
    asyncio.create_task(slow_operation(context.data))  # Non-blocking
    return HookResult(success=True)
```

### Hook Errors Breaking Agent

**Problem**: Hook error causes agent to fail.

**Solution**: Hooks are isolated by default - errors are logged but don't break agent execution. If you're seeing failures, check if you're manually raising exceptions:

```python
# ❌ BAD: Re-raising exceptions
async def bad_hook(context: HookContext) -> HookResult:
    try:
        risky_operation()
    except Exception as e:
        raise  # ❌ Don't do this

# ✅ GOOD: Return error result
async def good_hook(context: HookContext) -> HookResult:
    try:
        risky_operation()
        return HookResult(success=True)
    except Exception as e:
        return HookResult(success=False, error=str(e))  # ✅ Graceful
```

## API Reference

### HookManager

```python
class HookManager:
    def register(
        self,
        event_type: HookEvent | str,
        handler: Callable[[HookContext], Awaitable[HookResult]],
        priority: HookPriority = HookPriority.NORMAL
    ) -> None:
        """Register a hook handler for an event."""

    def register_hook(
        self,
        hook: BaseHook,
        priority: HookPriority = HookPriority.NORMAL
    ) -> None:
        """Register a BaseHook for all its declared events."""

    def unregister(
        self,
        event_type: HookEvent | str,
        handler: HookHandler | None = None
    ) -> int:
        """Unregister hooks. Returns count removed."""

    async def trigger(
        self,
        event_type: HookEvent | str,
        agent_id: str,
        data: Dict[str, Any],
        timeout: float = 5.0,
        metadata: Dict[str, Any] | None = None,
        trace_id: str | None = None
    ) -> List[HookResult]:
        """Trigger all hooks for an event."""

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get hook performance statistics."""

    async def discover_filesystem_hooks(
        self,
        hooks_dir: Path
    ) -> int:
        """Discover and load hooks from filesystem."""
```

### BaseHook

```python
class BaseHook:
    events: List[HookEvent]  # Events this hook handles
    priority: HookPriority   # Execution priority
    name: str                # Hook identifier

    async def handle(self, context: HookContext) -> HookResult:
        """Execute hook logic."""
```

## Further Reading

- **Examples**: `examples/autonomy/hooks/` - 3 production examples
- **Tests**: `tests/unit/core/autonomy/hooks/` - 9 unit tests
- **Integration Tests**: `tests/integration/autonomy/` - 15 integration tests
- **E2E Tests**: `tests/e2e/autonomy/` - 5 end-to-end tests with Ollama
- **Performance**: `tests/performance/test_hooks_performance.py` - Performance benchmarks
- **ADR**: `docs/architecture/adr/ADR-014-lifecycle-management.md` - Architecture decision

## Summary

The Hooks System enables **zero-code-change observability** for autonomous agents. Use it to:

✅ Monitor agent behavior without modifying agent code
✅ Collect metrics, traces, and audit logs for compliance
✅ Debug production issues with comprehensive execution context
✅ Enforce policies (timeouts, validation, access control)
✅ Build production-grade AI systems with enterprise observability

**Start simple**: Add one hook for logging, then expand to full observability stack (tracing + metrics + auditing) as needed.
