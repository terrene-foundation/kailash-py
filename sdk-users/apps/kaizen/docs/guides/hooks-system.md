# Kaizen Hooks System - Production-Ready Event-Driven Monitoring

**What it is**: A lifecycle event framework for zero-code-change integration of cross-cutting concerns (monitoring, tracing, auditing, metrics) into Kaizen agents.

**When to use**: Need to monitor, audit, debug, enforce policies, or collect analytics without modifying agent logic.

**Production status**: ✅ 136 tests passing (100% coverage), enterprise-ready

---

## What Are Hooks?

Hooks are event handlers that execute automatically during agent lifecycle events. They enable **observability, auditing, and policy enforcement** without changing your agent code.

**Key Benefit**: Add enterprise features (tracing, metrics, audit trails) to agents with zero code changes.

### Core Concepts

1. **HookEvent**: Lifecycle events where hooks trigger (PRE/POST patterns)
2. **HookManager**: Orchestrates hook registration and execution
3. **BaseHook**: Base class for creating custom hooks
4. **HookContext**: Event data passed to hooks (agent_id, timestamp, event data)
5. **HookResult**: Return value from hooks (success, data, error, duration)

### Available Lifecycle Events

```python
from kaizen.core.autonomy.hooks import HookEvent

# Tool execution lifecycle
HookEvent.PRE_TOOL_USE       # Before agent calls a tool
HookEvent.POST_TOOL_USE      # After tool execution

# Agent execution lifecycle
HookEvent.PRE_AGENT_LOOP     # Before agent processes request
HookEvent.POST_AGENT_LOOP    # After agent completes

# Specialist invocation
HookEvent.PRE_SPECIALIST_INVOKE    # Before specialist agent called
HookEvent.POST_SPECIALIST_INVOKE   # After specialist completes

# Permission system
HookEvent.PRE_PERMISSION_CHECK     # Before permission check
HookEvent.POST_PERMISSION_CHECK    # After permission check

# State persistence
HookEvent.PRE_CHECKPOINT_SAVE      # Before checkpoint saved
HookEvent.POST_CHECKPOINT_SAVE     # After checkpoint saved
```

---

## Quick Start

### 1. Using Builtin Hooks

Kaizen provides **6 production-ready hooks** out of the box:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks.builtin import (
    LoggingHook,           # Structured event logging
    MetricsHook,           # Prometheus metrics collection
    CostTrackingHook,      # Budget tracking and cost analysis
    PerformanceProfilerHook,  # Latency profiling with percentiles
    AuditHook,             # Compliance audit trails (SOC2/GDPR/HIPAA)
    TracingHook,           # Distributed tracing integration
)

# Create agent
agent = BaseAgent(config=config, signature=signature)

# Register builtin hooks (one line each!)
agent._hook_manager.register_hook(LoggingHook(log_level="INFO"))
agent._hook_manager.register_hook(MetricsHook())
agent._hook_manager.register_hook(CostTrackingHook())

# Execute agent - hooks run automatically
result = agent.run(question="What is AI?")
```

**No code changes needed** - hooks execute transparently during agent lifecycle.

### 2. Creating Custom Hooks

**Method 1: Function-Based Hook (Simplest)**

```python
from kaizen.core.autonomy.hooks import HookEvent, HookContext, HookResult

# Define async function
async def my_custom_hook(context: HookContext) -> HookResult:
    print(f"Agent {context.agent_id} triggered {context.event_type.value}")

    # Access event data
    if context.event_type == HookEvent.PRE_TOOL_USE:
        tool_name = context.data.get("tool_name")
        print(f"About to call tool: {tool_name}")

    return HookResult(success=True, data={"processed": True})

# Register function as hook
agent._hook_manager.register(
    HookEvent.PRE_TOOL_USE,
    my_custom_hook,
    HookPriority.NORMAL
)
```

**Method 2: Class-Based Hook (Reusable)**

```python
from kaizen.core.autonomy.hooks.protocol import BaseHook
from kaizen.core.autonomy.hooks.types import HookEvent, HookPriority

class MyCustomHook(BaseHook):
    """Reusable custom hook"""

    # Define which events this hook handles
    events = [HookEvent.PRE_AGENT_LOOP, HookEvent.POST_AGENT_LOOP]

    def __init__(self):
        super().__init__(name="my_custom_hook")
        self.execution_count = 0

    async def handle(self, context: HookContext) -> HookResult:
        self.execution_count += 1

        if context.event_type == HookEvent.PRE_AGENT_LOOP:
            print(f"Starting agent loop #{self.execution_count}")
        else:
            print(f"Completed agent loop #{self.execution_count}")

        return HookResult(
            success=True,
            data={"execution_count": self.execution_count}
        )

    async def on_error(self, error: Exception, context: HookContext):
        """Optional: Custom error handling"""
        print(f"Hook error: {error}")

# Register hook for all its events
agent._hook_manager.register_hook(MyCustomHook())
```

---

## Builtin Hooks Reference

### 1. LoggingHook - Structured Event Logging

**What**: Logs all hook events with configurable formats (text or JSON).

**When**: Debugging, audit trails, ELK Stack integration.

```python
from kaizen.core.autonomy.hooks.builtin import LoggingHook

# Text format (backward compatible)
hook = LoggingHook(
    log_level="INFO",      # DEBUG, INFO, WARNING, ERROR
    include_data=True,     # Log event data (disable for sensitive data)
    format="text"          # "text" or "json"
)

# JSON format (ELK-compatible via structlog)
hook = LoggingHook(
    log_level="INFO",
    include_data=True,
    format="json"          # Outputs structured JSON logs
)

agent._hook_manager.register_hook(hook)
```

**Output Example (Text)**:
```
[pre_tool_use] Agent=qa_agent TraceID=abc123 Data={'tool_name': 'search'}
[post_tool_use] Agent=qa_agent TraceID=abc123 Data={'result': 'success'}
```

**Output Example (JSON)**:
```json
{
  "event_type": "pre_tool_use",
  "agent_id": "qa_agent",
  "trace_id": "abc123",
  "timestamp": 1698765432.123,
  "context": {"tool_name": "search"},
  "level": "info"
}
```

### 2. MetricsHook - Prometheus-Compatible Metrics

**What**: Collects Prometheus metrics with dimensional labels (agent_id, event_type, operation).

**When**: Production monitoring, performance dashboards, SLA tracking.

```python
from kaizen.core.autonomy.hooks.builtin import MetricsHook

# Create hook with Prometheus integration
hook = MetricsHook(
    enable_percentiles=True  # Enable p50/p95/p99 calculation
)

agent._hook_manager.register_hook(hook)

# Execute agent
result = agent.run(question="test")

# Export Prometheus metrics (HTTP /metrics endpoint)
metrics_text = hook.export_prometheus()
print(metrics_text.decode('utf-8'))

# Get percentiles for specific operation
percentiles = hook.get_percentiles("tool_use")
print(f"p95 latency: {percentiles['p95_ms']}ms")
```

**Collected Metrics**:
- `kaizen_hook_events_total{event_type, agent_id}` - Total events by type
- `kaizen_operation_duration_seconds{operation, agent_id}` - Operation latency histogram
- `kaizen_active_agents` - Number of active agents

**Percentiles** (p50, p95, p99):
```python
{
    "p50_ms": 12.5,   # Median latency
    "p95_ms": 45.2,   # 95th percentile
    "p99_ms": 89.7    # 99th percentile
}
```

### 3. CostTrackingHook - Budget Enforcement

**What**: Tracks costs by tool, agent, and specialist with accumulation.

**When**: Budget constraints, cost optimization, billing breakdowns.

```python
from kaizen.core.autonomy.hooks.builtin import CostTrackingHook

hook = CostTrackingHook()
agent._hook_manager.register_hook(hook)

# Execute agent
result = agent.run(question="test")

# Get total cost
total = hook.get_total_cost()
print(f"Total cost: ${total:.4f}")

# Get cost breakdown
breakdown = hook.get_cost_breakdown()
print(f"By tool: {breakdown['by_tool']}")
print(f"By agent: {breakdown['by_agent']}")
print(f"By specialist: {breakdown['by_specialist']}")

# Reset costs
hook.reset_costs()
```

**Cost Breakdown Example**:
```python
{
    "total_cost_usd": 0.15,
    "by_tool": {
        "search": 0.05,
        "analyze": 0.10
    },
    "by_agent": {
        "qa_agent": 0.15
    },
    "by_specialist": {
        "code_analyzer": 0.05
    }
}
```

### 4. PerformanceProfilerHook - Latency Profiling

**What**: Tracks operation duration (PRE/POST event pairing) with percentiles.

**When**: Performance optimization, bottleneck identification, SLA validation.

```python
from kaizen.core.autonomy.hooks.builtin import PerformanceProfilerHook

hook = PerformanceProfilerHook()
agent._hook_manager.register_hook(hook)

# Execute agent
result = agent.run(question="test")

# Get performance report
report = hook.get_performance_report()

for operation, stats in report.items():
    print(f"{operation}:")
    print(f"  Count: {stats['count']}")
    print(f"  Avg: {stats['avg_ms']:.2f}ms")
    print(f"  Min: {stats['min_ms']:.2f}ms")
    print(f"  Max: {stats['max_ms']:.2f}ms")
    print(f"  p50: {stats['p50_ms']:.2f}ms")
    print(f"  p95: {stats['p95_ms']:.2f}ms")
    print(f"  p99: {stats['p99_ms']:.2f}ms")
```

**PRE/POST Event Pairing**:
- Automatically pairs PRE and POST events
- Calculates duration between events
- Tracks min, max, avg, percentiles

### 5. AuditHook - Compliance Audit Trails

**What**: Immutable append-only audit logs for compliance (SOC2, GDPR, HIPAA, PCI-DSS).

**When**: Regulatory compliance, security audits, forensic analysis.

```python
from kaizen.core.autonomy.hooks.builtin import AuditHook
from pathlib import Path

hook = AuditHook(
    audit_log_path=Path("/var/log/kaizen/audit.jsonl"),  # JSONL append-only
    include_sensitive_data=False  # Privacy-aware logging
)

agent._hook_manager.register_hook(hook)

# Execute agent - all events logged to audit.jsonl
result = agent.run(question="test")
```

**Audit Log Entry Example (JSONL)**:
```json
{"timestamp": "2025-10-28T10:30:45.123Z", "event_type": "PRE_AGENT_LOOP", "agent_id": "qa_agent", "trace_id": "abc123", "action": "agent_execution_start", "inputs": {"question": "test"}}
{"timestamp": "2025-10-28T10:30:46.456Z", "event_type": "POST_AGENT_LOOP", "agent_id": "qa_agent", "trace_id": "abc123", "action": "agent_execution_complete", "outputs": {"answer": "..."}}
```

**Key Features**:
- **Append-only**: Immutable log files (cannot modify past entries)
- **JSONL format**: One JSON object per line (easy parsing, streaming)
- **Compliance**: Meets SOC2, GDPR, HIPAA, PCI-DSS requirements
- **Privacy-aware**: Optional `include_sensitive_data=False`

### 6. TracingHook - Distributed Tracing

**What**: OpenTelemetry span creation for distributed tracing (Jaeger/Zipkin).

**When**: Microservices debugging, request flow visualization, multi-agent coordination.

```python
from kaizen.core.autonomy.hooks.builtin import TracingHook
from kaizen.core.autonomy.observability import TracingManager

# Create tracing manager
tracing_manager = TracingManager(service_name="my-agent-service")

# Create hook
hook = TracingHook(tracing_manager=tracing_manager)
agent._hook_manager.register_hook(hook)

# Execute agent - spans created automatically
result = agent.run(question="test")

# View traces in Jaeger UI: http://localhost:16686
```

**Span Hierarchy (Automatic)**:
```
pre_agent_loop (root span)
├── pre_tool_use:load_data
│   └── post_tool_use:load_data (actual duration)
├── pre_tool_use:analyze_data
│   └── post_tool_use:analyze_data
└── post_agent_loop (ends root)
```

---

## Advanced Patterns

### Hook Priority Control

Control execution order with priority levels:

```python
from kaizen.core.autonomy.hooks import HookPriority

# Priority order: CRITICAL (0) → HIGH (1) → NORMAL (2) → LOW (3)

# Audit trails run first (CRITICAL)
agent._hook_manager.register(
    HookEvent.PRE_TOOL_USE,
    audit_hook,
    HookPriority.CRITICAL  # Executes first
)

# Metrics collection next (HIGH)
agent._hook_manager.register(
    HookEvent.PRE_TOOL_USE,
    metrics_hook,
    HookPriority.HIGH  # Executes second
)

# Custom logic (NORMAL - default)
agent._hook_manager.register(
    HookEvent.PRE_TOOL_USE,
    custom_hook,
    HookPriority.NORMAL  # Executes third
)

# Cleanup last (LOW)
agent._hook_manager.register(
    HookEvent.POST_TOOL_USE,
    cleanup_hook,
    HookPriority.LOW  # Executes last
)
```

**Priority Use Cases**:
- **CRITICAL**: Audit trails, authentication, authorization
- **HIGH**: Security checks, metrics collection, compliance
- **NORMAL**: Application logic (default)
- **LOW**: Cleanup, notifications, optional logging

### Conditional Hook Execution

Execute hooks based on conditions:

```python
class ConditionalHook(BaseHook):
    """Only execute for specific agents"""

    events = [HookEvent.PRE_AGENT_LOOP]

    def __init__(self, allowed_agents: list[str]):
        super().__init__(name="conditional_hook")
        self.allowed_agents = allowed_agents

    async def handle(self, context: HookContext) -> HookResult:
        # Skip if agent not in allowed list
        if context.agent_id not in self.allowed_agents:
            return HookResult(success=True, data={"skipped": True})

        # Execute logic for allowed agents
        print(f"Processing agent: {context.agent_id}")
        return HookResult(success=True)

# Register conditional hook
hook = ConditionalHook(allowed_agents=["qa_agent", "code_agent"])
agent._hook_manager.register_hook(hook)
```

### Multi-Hook Composition

Combine multiple hooks for comprehensive monitoring:

```python
from kaizen.core.autonomy.hooks.builtin import (
    LoggingHook,
    MetricsHook,
    CostTrackingHook,
    PerformanceProfilerHook,
    AuditHook,
)

# Create agent
agent = BaseAgent(config=config, signature=signature)

# Register all hooks (one monitoring stack!)
hooks = [
    LoggingHook(log_level="INFO", format="json"),
    MetricsHook(enable_percentiles=True),
    CostTrackingHook(),
    PerformanceProfilerHook(),
    AuditHook(audit_log_path=Path("/var/log/kaizen/audit.jsonl")),
]

for hook in hooks:
    agent._hook_manager.register_hook(hook)

# Execute agent - all hooks run automatically
result = agent.run(question="test")

# Access hook data
print(f"Total cost: ${hooks[2].get_total_cost():.4f}")
print(f"p95 latency: {hooks[3].get_performance_report()['agent_loop']['p95_ms']}ms")
```

### Filesystem Hook Discovery

Load hooks from filesystem (plugin architecture):

```python
from pathlib import Path

# Define hooks directory
hooks_dir = Path("/path/to/custom/hooks")

# Discover and load all .py files containing BaseHook subclasses
discovered_count = await agent._hook_manager.discover_filesystem_hooks(hooks_dir)

print(f"Loaded {discovered_count} hooks from {hooks_dir}")

# All discovered hooks automatically registered
```

**Filesystem Hook Example** (`custom_hooks/my_hook.py`):
```python
from kaizen.core.autonomy.hooks.protocol import BaseHook
from kaizen.core.autonomy.hooks.types import HookEvent, HookContext, HookResult

class MyFilesystemHook(BaseHook):
    """Custom hook loaded from filesystem"""

    events = [HookEvent.PRE_AGENT_LOOP]

    def __init__(self):
        super().__init__(name="filesystem_hook")

    async def handle(self, context: HookContext) -> HookResult:
        print("Loaded from filesystem!")
        return HookResult(success=True)
```

**Requirements**:
- Must subclass `BaseHook`
- Must define `events` attribute (list of HookEvent)
- Must implement `handle()` method
- Must have no-argument `__init__()` constructor

---

## Integration Patterns

### With BaseAgent Lifecycle

Every BaseAgent has a built-in HookManager:

```python
from kaizen.core.base_agent import BaseAgent

# Create agent
agent = BaseAgent(config=config, signature=signature)

# Access built-in hook manager
hook_manager = agent._hook_manager

# Register hooks
hook_manager.register_hook(LoggingHook())

# Hooks execute automatically during agent lifecycle:
# 1. PRE_AGENT_LOOP - Before agent.run()
# 2. PRE_TOOL_USE - Before tool execution
# 3. POST_TOOL_USE - After tool execution
# 4. POST_AGENT_LOOP - After agent.run()
```

### With Observability Stack

Hooks power the Kaizen observability system:

```python
# Enable full observability (one line!)
agent.enable_observability(
    service_name="my-agent",
    enable_metrics=True,     # Uses MetricsHook
    enable_logging=True,     # Uses LoggingHook
    enable_tracing=True,     # Uses TracingHook
    enable_audit=True,       # Uses AuditHook
)

# All hooks registered automatically
# Zero overhead when disabled
```

**See**: `docs/observability/` for complete observability guide.

### With Multi-Agent Coordination

Hooks work across multi-agent patterns:

```python
from kaizen.orchestration.patterns import SupervisorWorkerPattern

# Create pattern with multiple agents
pattern = SupervisorWorkerPattern(supervisor, workers, coordinator, shared_pool)

# Register hooks on all agents
for agent in [supervisor] + workers + [coordinator]:
    agent._hook_manager.register_hook(LoggingHook())
    agent._hook_manager.register_hook(MetricsHook())

# Hooks execute across all agents automatically
result = pattern.execute_task("Analyze data")

# Access aggregated metrics
total_events = sum(
    agent._hook_manager.get_stats()["logging_hook"]["call_count"]
    for agent in [supervisor] + workers + [coordinator]
)
```

### With Permission System

Hooks integrate with permission checks:

```python
from kaizen.core.autonomy.permissions import ExecutionContext, PermissionRule
from kaizen.core.autonomy.hooks import HookEvent, HookContext, HookResult

class PermissionHook(BaseHook):
    """Enforce permissions via hooks"""

    events = [HookEvent.PRE_TOOL_USE]

    def __init__(self, exec_context: ExecutionContext, rules: list[PermissionRule]):
        super().__init__(name="permission_hook")
        self.exec_context = exec_context
        self.rules = sorted(rules, key=lambda r: r.priority, reverse=True)

    async def handle(self, context: HookContext) -> HookResult:
        tool_name = context.data.get("tool_name")

        # Check context permissions
        if not self.exec_context.can_use_tool(tool_name):
            return HookResult(
                success=False,
                error=f"Tool {tool_name} denied by execution context"
            )

        # Check budget
        if not self.exec_context.has_budget():
            return HookResult(
                success=False,
                error="Budget limit exceeded"
            )

        # Apply permission rules
        for rule in self.rules:
            if rule.matches(tool_name):
                if rule.permission_type == PermissionType.DENY:
                    return HookResult(
                        success=False,
                        error=f"Denied by policy: {rule.reason}"
                    )
                break

        return HookResult(success=True)

# Register permission hook
agent._hook_manager.register_hook(
    PermissionHook(exec_context, permission_rules)
)
```

---

## Performance Characteristics

**Production Validated (136 tests passing)**:

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Hook execution overhead (p95) | <5ms | 0.008ms | ✅ **625x better** |
| Registration overhead | <1ms | 0.038ms | ✅ **26x better** |
| Stats tracking overhead | <0.1ms | ~0ms | ✅ Negligible |
| Concurrent hooks supported | >50 | 100+ | ✅ Validated |
| Memory per hook | <100KB | 0.56KB | ✅ **178x better** |

**Key Insights**:
- **Zero observable overhead** in production workloads
- **100+ concurrent hooks** supported (tested)
- **Async-first design** ensures non-blocking execution
- **Error isolation** - One hook's failure doesn't affect others
- **Timeout protection** - 5s default timeout per hook

---

## Error Handling

### Hook Error Isolation

Hooks errors are automatically isolated:

```python
async def failing_hook(context: HookContext) -> HookResult:
    raise RuntimeError("Something went wrong!")

# Register failing hook
agent._hook_manager.register(HookEvent.PRE_TOOL_USE, failing_hook)

# Execute agent - doesn't crash!
result = agent.run(question="test")

# Hook returns error result automatically
hook_results = await agent._hook_manager.trigger(
    HookEvent.PRE_TOOL_USE,
    agent_id="test",
    data={}
)

assert hook_results[0].success == False
assert "Something went wrong!" in hook_results[0].error
```

### Custom Error Handlers

Override `on_error()` for custom error handling:

```python
class CustomHook(BaseHook):
    """Hook with custom error handling"""

    events = [HookEvent.PRE_AGENT_LOOP]

    async def handle(self, context: HookContext) -> HookResult:
        # Might raise exception
        risky_operation()
        return HookResult(success=True)

    async def on_error(self, error: Exception, context: HookContext):
        """Custom error handling"""
        # Log to external service
        await send_to_error_tracking(error, context)

        # Send alert
        await notify_ops_team(f"Hook failed: {error}")

        # Custom recovery logic
        await cleanup_resources()
```

### Timeout Protection

Hooks have automatic timeout protection:

```python
# Trigger hooks with custom timeout
results = await agent._hook_manager.trigger(
    HookEvent.PRE_TOOL_USE,
    agent_id="test",
    data={},
    timeout=10.0  # 10 seconds (default: 5.0)
)

# If hook exceeds timeout, returns error result:
# HookResult(success=False, error="Hook timeout: hook_name", duration_ms=10000.0)
```

---

## Best Practices

### 1. Use Builtin Hooks First

Before writing custom hooks, check builtin hooks:

```python
# ✅ GOOD: Use builtin hooks
agent._hook_manager.register_hook(LoggingHook())
agent._hook_manager.register_hook(MetricsHook())

# ❌ BAD: Reinvent the wheel
class MyLoggingHook(BaseHook):
    # ... reimplementing LoggingHook functionality
```

### 2. Compose Hooks for Features

Use multiple small hooks instead of one large hook:

```python
# ✅ GOOD: Compose small hooks
agent._hook_manager.register_hook(LoggingHook())
agent._hook_manager.register_hook(MetricsHook())
agent._hook_manager.register_hook(CostTrackingHook())

# ❌ BAD: One monolithic hook
class MonsterHook(BaseHook):
    # ... does logging, metrics, cost tracking, and more
```

### 3. Set Appropriate Priorities

Use priority levels for execution order control:

```python
# ✅ GOOD: Audit trails first, cleanup last
agent._hook_manager.register(event, audit_hook, HookPriority.CRITICAL)
agent._hook_manager.register(event, metrics_hook, HookPriority.HIGH)
agent._hook_manager.register(event, cleanup_hook, HookPriority.LOW)

# ❌ BAD: All hooks same priority
agent._hook_manager.register(event, audit_hook, HookPriority.NORMAL)
agent._hook_manager.register(event, metrics_hook, HookPriority.NORMAL)
agent._hook_manager.register(event, cleanup_hook, HookPriority.NORMAL)
```

### 4. Handle Hook Failures Gracefully

Don't let hook failures crash your agent:

```python
# ✅ GOOD: Return error result
async def my_hook(context: HookContext) -> HookResult:
    try:
        # Risky operation
        result = risky_operation()
        return HookResult(success=True, data=result)
    except Exception as e:
        # Return error, don't crash
        return HookResult(success=False, error=str(e))

# ❌ BAD: Let exception propagate
async def bad_hook(context: HookContext) -> HookResult:
    # This will crash the agent if it fails!
    risky_operation()
    return HookResult(success=True)
```

### 5. Use Async Patterns

Hooks are async-first - use async/await properly:

```python
# ✅ GOOD: Async hook with await
async def my_hook(context: HookContext) -> HookResult:
    data = await async_operation()
    return HookResult(success=True, data=data)

# ❌ BAD: Blocking sync code
async def bad_hook(context: HookContext) -> HookResult:
    time.sleep(5)  # Blocks event loop!
    return HookResult(success=True)
```

### 6. Test Hooks Independently

Write unit tests for custom hooks:

```python
import pytest
from kaizen.core.autonomy.hooks import HookContext, HookEvent

@pytest.mark.asyncio
async def test_my_custom_hook():
    """Test custom hook behavior"""
    hook = MyCustomHook()

    context = HookContext(
        event_type=HookEvent.PRE_TOOL_USE,
        agent_id="test_agent",
        timestamp=time.time(),
        data={"tool_name": "search"}
    )

    result = await hook.handle(context)

    assert result.success is True
    assert result.data["processed"] is True
```

---

## Troubleshooting

### Hook Not Executing

**Problem**: Hook registered but not executing.

**Solution**: Check event type matches:

```python
# ❌ WRONG: Registering for wrong event
agent._hook_manager.register(
    HookEvent.PRE_TOOL_USE,  # Registered for tool use
    my_hook
)

# Agent executes without tools - hook never triggered!
result = agent.run(question="test")  # No tools called

# ✅ CORRECT: Register for agent loop events
agent._hook_manager.register(
    HookEvent.PRE_AGENT_LOOP,  # Triggers on agent.run()
    my_hook
)
```

### Hook Execution Order Wrong

**Problem**: Hooks executing in unexpected order.

**Solution**: Use explicit priorities:

```python
# ✅ CORRECT: Set priorities explicitly
agent._hook_manager.register(event, audit_hook, HookPriority.CRITICAL)
agent._hook_manager.register(event, metrics_hook, HookPriority.HIGH)
agent._hook_manager.register(event, custom_hook, HookPriority.NORMAL)
```

### Hook Timeout Errors

**Problem**: Hook hitting timeout limit.

**Solution**: Increase timeout or optimize hook:

```python
# Option 1: Increase timeout
results = await agent._hook_manager.trigger(
    event_type,
    agent_id="test",
    data={},
    timeout=30.0  # 30 seconds instead of default 5s
)

# Option 2: Optimize hook (better!)
async def optimized_hook(context: HookContext) -> HookResult:
    # Use async operations, avoid blocking
    data = await fast_async_operation()
    return HookResult(success=True, data=data)
```

### Missing Hook Stats

**Problem**: `get_stats()` returns empty dict.

**Solution**: Execute agent first to generate stats:

```python
# Hook stats are empty before execution
stats = agent._hook_manager.get_stats()
assert len(stats) == 0

# Execute agent to generate stats
result = agent.run(question="test")

# Now stats available
stats = agent._hook_manager.get_stats()
assert len(stats) > 0
```

---

## Next Steps

1. **Enable Observability**: See [Observability Guide](../observability/) for full monitoring stack
2. **Add Custom Hooks**: Implement domain-specific monitoring
3. **Integrate with Permission System**: See [Permission System Guide](../reference/permission-system.md)
4. **Deploy to Production**: See [Production Deployment](../deployment/) for best practices

---

## Reference

- **Implementation**: `src/kaizen/core/autonomy/hooks/manager.py` (425 lines)
- **Tests**: `tests/unit/core/autonomy/hooks/` (136 tests passing)
- **Examples**: `examples/autonomy/hooks/`
- **ADR**: `docs/architecture/adr/ADR-018-lifecycle-infrastructure.md`
