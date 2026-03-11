# ADR-014: Hooks System Architecture

## Status
**Proposed** - Phase 2 Implementation (Weeks 18-22)

**Priority**: P1 - HIGH (enables extensibility and customization)

## Context

Kaizen agents currently have **no extension points** for custom behavior during execution. Users cannot:

**Missing Capabilities**:
- Inject custom logging before/after tool usage
- Add custom metrics collection at agent loop boundaries
- Implement custom approval gates beyond permission system
- Add compliance checks at critical execution points
- Track custom events for debugging or auditing
- Modify agent behavior without forking core code

**Problem**: Users need **non-invasive extension points** to customize agent behavior without modifying Kaizen internals.

**Inspiration**: Claude Code provides a [hooks system](https://github.com/anthropics/claude-code) with 6 event types that enable powerful customizations:
- `PreToolUse` / `PostToolUse` - Tool execution boundaries
- `PreAgentLoop` / `PostAgentLoop` - Agent iteration boundaries
- `PreUserPromptSubmit` / `PostUserPromptSubmit` - User input boundaries

**Requirements**:
1. Event-driven hook system with well-defined lifecycle events
2. Support both programmatic (Python) and filesystem (`.kaizen/hooks/`) hooks
3. Async-first for non-blocking execution
4. Error isolation (hook failures don't crash agent)
5. Performance targets: <5ms overhead per hook call
6. Integration with Control Protocol, Permission System, Specialist System

## Decision

We will implement a **Hooks System** in `kaizen/core/autonomy/hooks/` with the following design:

### Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│ BaseAgent / Specialist (Execution Layer)                │
│ - await hooks.trigger("pre_tool_use", tool_name, ...)   │
│ - await hooks.trigger("post_tool_use", result, ...)     │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Trigger events
                        ▼
┌──────────────────────────────────────────────────────────┐
│ HookManager (Orchestration)                              │
│ - register_hook(event_type, handler)                     │
│ - trigger(event_type, context) → results                 │
│ - Handles async execution, error isolation, timeouts     │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Registered hooks
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Hook Handlers (User-Defined)                             │
│ - Programmatic: Python functions/classes                 │
│ - Filesystem: .kaizen/hooks/*.py                         │
└──────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Event Types (`kaizen/core/autonomy/hooks/types.py`)

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any, Literal

class HookEvent(Enum):
    """Lifecycle events where hooks can be triggered"""

    # Tool execution lifecycle
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"

    # Agent execution lifecycle
    PRE_AGENT_LOOP = "pre_agent_loop"
    POST_AGENT_LOOP = "post_agent_loop"

    # Specialist invocation lifecycle
    PRE_SPECIALIST_INVOKE = "pre_specialist_invoke"
    POST_SPECIALIST_INVOKE = "post_specialist_invoke"

    # Permission system integration
    PRE_PERMISSION_CHECK = "pre_permission_check"
    POST_PERMISSION_CHECK = "post_permission_check"

    # State persistence integration
    PRE_CHECKPOINT_SAVE = "pre_checkpoint_save"
    POST_CHECKPOINT_SAVE = "post_checkpoint_save"

@dataclass
class HookContext:
    """Context passed to hook handlers"""
    event_type: HookEvent
    agent_id: str
    timestamp: float
    data: dict[str, Any]  # Event-specific data
    metadata: dict[str, Any] = None  # Optional metadata

@dataclass
class HookResult:
    """Result returned by hook handler"""
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0
```

#### 2. Hook Handler Protocol (`kaizen/core/autonomy/hooks/protocol.py`)

```python
from typing import Protocol, runtime_checkable
from abc import abstractmethod

@runtime_checkable
class HookHandler(Protocol):
    """Protocol for hook handlers (sync or async)"""

    @abstractmethod
    async def handle(self, context: HookContext) -> HookResult:
        """Handle hook event. Must be async."""
        pass

# Convenience base class
class BaseHook:
    """Base class for hook implementations"""

    def __init__(self, name: str):
        self.name = name

    async def handle(self, context: HookContext) -> HookResult:
        """Override this method in subclasses"""
        raise NotImplementedError(f"{self.__class__.__name__}.handle() must be implemented")

    async def on_error(self, error: Exception, context: HookContext) -> None:
        """Optional error handler"""
        pass
```

#### 3. Hook Manager (`kaizen/core/autonomy/hooks/manager.py`)

```python
from typing import Callable, Awaitable
import anyio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class HookManager:
    """Manages hook registration and execution"""

    def __init__(self):
        self._hooks: dict[HookEvent, list[HookHandler]] = defaultdict(list)
        self._hook_stats: dict[str, dict] = {}

    def register(
        self,
        event_type: HookEvent | str,
        handler: HookHandler | Callable[[HookContext], Awaitable[HookResult]]
    ) -> None:
        """Register a hook handler for an event"""
        if isinstance(event_type, str):
            event_type = HookEvent(event_type)

        # Wrap callable in adapter if needed
        if callable(handler) and not isinstance(handler, HookHandler):
            handler = FunctionHookAdapter(handler)

        self._hooks[event_type].append(handler)
        logger.info(f"Registered hook for {event_type.value}: {getattr(handler, 'name', repr(handler))}")

    async def trigger(
        self,
        event_type: HookEvent | str,
        agent_id: str,
        data: dict[str, Any],
        timeout: float = 5.0
    ) -> list[HookResult]:
        """Trigger all hooks for an event type"""
        if isinstance(event_type, str):
            event_type = HookEvent(event_type)

        handlers = self._hooks.get(event_type, [])
        if not handlers:
            return []

        context = HookContext(
            event_type=event_type,
            agent_id=agent_id,
            timestamp=time.time(),
            data=data
        )

        results = []
        for handler in handlers:
            try:
                # Execute with timeout
                with anyio.fail_after(timeout):
                    start_time = time.perf_counter()
                    result = await handler.handle(context)
                    result.duration_ms = (time.perf_counter() - start_time) * 1000
                    results.append(result)

                    # Track stats
                    self._update_stats(handler, result.duration_ms, success=True)

            except TimeoutError:
                error_msg = f"Hook timeout: {getattr(handler, 'name', repr(handler))}"
                logger.error(error_msg)
                results.append(HookResult(success=False, error=error_msg))
                self._update_stats(handler, timeout * 1000, success=False)

            except Exception as e:
                error_msg = f"Hook error: {str(e)}"
                logger.exception(f"Hook failed: {getattr(handler, 'name', repr(handler))}")
                results.append(HookResult(success=False, error=error_msg))
                self._update_stats(handler, 0, success=False)

                # Call error handler if available
                if hasattr(handler, 'on_error'):
                    try:
                        await handler.on_error(e, context)
                    except Exception as err_e:
                        logger.error(f"Error handler failed: {err_e}")

        return results

    def _update_stats(self, handler: HookHandler, duration_ms: float, success: bool) -> None:
        """Track hook performance statistics"""
        handler_name = getattr(handler, 'name', repr(handler))
        if handler_name not in self._hook_stats:
            self._hook_stats[handler_name] = {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration_ms": 0.0,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0
            }

        stats = self._hook_stats[handler_name]
        stats["call_count"] += 1
        stats["success_count" if success else "failure_count"] += 1
        stats["total_duration_ms"] += duration_ms
        stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["call_count"]
        stats["max_duration_ms"] = max(stats["max_duration_ms"], duration_ms)

    def get_stats(self) -> dict[str, dict]:
        """Get hook performance statistics"""
        return self._hook_stats.copy()

class FunctionHookAdapter(BaseHook):
    """Adapter to use plain functions as hooks"""

    def __init__(self, func: Callable[[HookContext], Awaitable[HookResult]]):
        super().__init__(name=func.__name__)
        self._func = func

    async def handle(self, context: HookContext) -> HookResult:
        return await self._func(context)
```

#### 4. Built-In Hooks (`kaizen/core/autonomy/hooks/builtin/`)

```python
# kaizen/core/autonomy/hooks/builtin/logging_hook.py

class LoggingHook(BaseHook):
    """Logs all hook events for debugging"""

    def __init__(self, log_level: str = "INFO"):
        super().__init__(name="logging_hook")
        self.log_level = log_level

    async def handle(self, context: HookContext) -> HookResult:
        logger.log(
            getattr(logging, self.log_level),
            f"[{context.event_type.value}] Agent={context.agent_id} Data={context.data}"
        )
        return HookResult(success=True)

# kaizen/core/autonomy/hooks/builtin/metrics_hook.py

class MetricsHook(BaseHook):
    """Collects metrics for monitoring systems (Prometheus, etc.)"""

    def __init__(self, metrics_backend: str = "prometheus"):
        super().__init__(name="metrics_hook")
        self.metrics_backend = metrics_backend
        self.counters: dict[str, int] = defaultdict(int)

    async def handle(self, context: HookContext) -> HookResult:
        # Increment counter for this event type
        metric_name = f"kaizen_hook_{context.event_type.value}"
        self.counters[metric_name] += 1

        # In production, push to actual metrics backend
        # For now, just track in-memory

        return HookResult(success=True, data={"metric": metric_name, "count": self.counters[metric_name]})

# kaizen/core/autonomy/hooks/builtin/cost_tracking_hook.py

class CostTrackingHook(BaseHook):
    """Tracks LLM API costs per tool invocation"""

    def __init__(self):
        super().__init__(name="cost_tracking_hook")
        self.total_cost_usd = 0.0
        self.costs_by_tool: dict[str, float] = defaultdict(float)

    async def handle(self, context: HookContext) -> HookResult:
        if context.event_type == HookEvent.POST_TOOL_USE:
            tool_name = context.data.get("tool_name", "unknown")
            estimated_cost = context.data.get("estimated_cost_usd", 0.0)

            self.total_cost_usd += estimated_cost
            self.costs_by_tool[tool_name] += estimated_cost

            return HookResult(
                success=True,
                data={
                    "total_cost_usd": self.total_cost_usd,
                    "tool_cost_usd": estimated_cost,
                    "tool_name": tool_name
                }
            )

        return HookResult(success=True)
```

### Integration with BaseAgent

```python
# kaizen/core/base_agent.py

class BaseAgent(Node):
    def __init__(self, config: BaseAgentConfig):
        super().__init__(config)
        self.hook_manager = HookManager()
        self._init_hooks()

    def _init_hooks(self) -> None:
        """Initialize hooks from config"""
        if hasattr(self.config, 'hooks'):
            for hook_def in self.config.hooks:
                self.hook_manager.register(hook_def.event_type, hook_def.handler)

    async def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute tool with hook points"""

        # Pre-tool-use hooks
        await self.hook_manager.trigger(
            HookEvent.PRE_TOOL_USE,
            agent_id=self.config.name,
            data={"tool_name": tool_name, "tool_input": tool_input}
        )

        # Execute tool
        result = await self._execute_tool_internal(tool_name, tool_input)

        # Post-tool-use hooks
        await self.hook_manager.trigger(
            HookEvent.POST_TOOL_USE,
            agent_id=self.config.name,
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "result": result,
                "estimated_cost_usd": self._estimate_cost(tool_name, result)
            }
        )

        return result

    async def run(self, **kwargs) -> dict[str, Any]:
        """Agent execution loop with hook points"""

        # Pre-agent-loop hooks
        await self.hook_manager.trigger(
            HookEvent.PRE_AGENT_LOOP,
            agent_id=self.config.name,
            data={"inputs": kwargs}
        )

        # Run agent
        result = await super().run(**kwargs)

        # Post-agent-loop hooks
        await self.hook_manager.trigger(
            HookEvent.POST_AGENT_LOOP,
            agent_id=self.config.name,
            data={"inputs": kwargs, "result": result}
        )

        return result
```

### User-Defined Hooks via KaizenOptions

```python
# User code

from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult, HookEvent

class CustomComplianceHook(BaseHook):
    """Custom hook for GDPR compliance checks"""

    def __init__(self):
        super().__init__(name="gdpr_compliance_hook")

    async def handle(self, context: HookContext) -> HookResult:
        if context.event_type == HookEvent.PRE_TOOL_USE:
            tool_name = context.data.get("tool_name")

            # Check if tool accesses PII
            if tool_name in ["DatabaseQuery", "FileRead"]:
                # Verify GDPR consent
                has_consent = await self._check_gdpr_consent(context.data)

                if not has_consent:
                    return HookResult(
                        success=False,
                        error="GDPR consent required for PII access"
                    )

        return HookResult(success=True)

    async def _check_gdpr_consent(self, data: dict) -> bool:
        # Real implementation would check consent database
        return True

# Register programmatically
from kaizen import KaizenOptions

options = KaizenOptions(
    hooks=[
        {"event_type": HookEvent.PRE_TOOL_USE, "handler": CustomComplianceHook()},
        {"event_type": HookEvent.POST_TOOL_USE, "handler": CostTrackingHook()},
    ]
)
```

### Filesystem-Based Hooks (`.kaizen/hooks/`)

```python
# .kaizen/hooks/custom_logger.py

from kaizen.core.autonomy.hooks import BaseHook, HookContext, HookResult

class CustomLoggerHook(BaseHook):
    """Custom logging hook loaded from filesystem"""

    def __init__(self):
        super().__init__(name="custom_logger")

    async def handle(self, context: HookContext) -> HookResult:
        # Custom logging logic
        with open("/var/log/kaizen/hooks.log", "a") as f:
            f.write(f"[{context.timestamp}] {context.event_type.value}: {context.data}\n")

        return HookResult(success=True)

# Kaizen auto-discovers this if setting_sources includes "project"
# Discovery pattern: .kaizen/hooks/*.py → find classes implementing HookHandler
```

## Consequences

### Positive

1. **✅ Non-Invasive Extensibility**: Users can customize behavior without forking Kaizen
2. **✅ Event-Driven Architecture**: Clean separation of concerns
3. **✅ Error Isolation**: Hook failures don't crash agents
4. **✅ Performance Tracking**: Built-in stats for hook overhead
5. **✅ Programmatic + Filesystem**: Flexible registration methods
6. **✅ Type-Safe**: HookHandler protocol ensures correct implementation

### Negative

1. **⚠️ Performance Overhead**: Each hook adds latency (target: <5ms)
2. **⚠️ Complexity**: More extension points = more things to debug
3. **⚠️ Learning Curve**: Users must understand event lifecycle
4. **⚠️ Security**: Filesystem hooks can execute arbitrary code

### Mitigations

1. **Performance**: Async execution, timeouts, stats tracking
2. **Complexity**: Clear documentation, built-in hooks as examples
3. **Learning Curve**: Visual diagrams of event flow, code examples
4. **Security**: Sandboxing for filesystem hooks, code review recommendations

## Performance Targets

| Metric | Target | Validation |
|--------|--------|------------|
| Hook execution overhead | <5ms per hook | Benchmark with 100 hooks |
| Hook registration overhead | <1ms | Measure during initialization |
| Stats tracking overhead | <0.1ms | Measure stats update time |
| Memory per hook | <100KB | 1000 hooks, measure delta |
| Concurrent hook execution | >50 concurrent | Load test with parallel agents |

See `PERFORMANCE_PARITY_PLAN.md` for full benchmarking strategy.

## Alternatives Considered

### Alternative 1: Middleware Pattern (Flask/Django Style)
```python
@agent.middleware
def my_middleware(next_handler):
    # Before
    result = next_handler()
    # After
    return result
```
**Rejected**: Harder to compose multiple middlewares, less explicit event types

### Alternative 2: Observer Pattern (Pure OOP)
```python
agent.attach_observer(MyObserver())
```
**Rejected**: No clear event boundaries, tight coupling

### Alternative 3: Decorator-Based Hooks
```python
@hook(HookEvent.PRE_TOOL_USE)
async def my_hook(context):
    pass
```
**Rejected**: Global state for registration, harder to test

## Implementation Plan

**Phase 2 Timeline**: Weeks 18-22 (5 weeks)

| Week | Tasks |
|------|-------|
| 18 | Implement core types, HookHandler protocol, HookManager |
| 19 | BaseAgent integration, basic event triggers |
| 20 | Built-in hooks (logging, metrics, cost tracking) |
| 21 | Filesystem hook discovery, KaizenOptions integration |
| 22 | Performance benchmarks, documentation, examples |

**Deliverables**:
- [ ] `kaizen/core/autonomy/hooks/` module (~800 lines)
- [ ] 3 built-in hooks (logging, metrics, cost tracking)
- [ ] Filesystem hook discovery system
- [ ] 40+ unit/integration tests
- [ ] 5 example hooks
- [ ] Performance benchmark suite
- [ ] Comprehensive documentation

## Testing Strategy

### Tier 1: Unit Tests (Mock Execution)
```python
def test_hook_manager_registration():
    manager = HookManager()
    hook = LoggingHook()
    manager.register(HookEvent.PRE_TOOL_USE, hook)

    assert HookEvent.PRE_TOOL_USE in manager._hooks
    assert hook in manager._hooks[HookEvent.PRE_TOOL_USE]

async def test_hook_execution():
    manager = HookManager()
    hook = MockHook()
    manager.register(HookEvent.PRE_TOOL_USE, hook)

    results = await manager.trigger(
        HookEvent.PRE_TOOL_USE,
        agent_id="test-agent",
        data={"tool_name": "Read"}
    )

    assert len(results) == 1
    assert results[0].success is True
```

### Tier 2: Integration Tests (Real Hooks, Local Agent)
```python
@pytest.mark.tier2
async def test_hooks_with_real_agent():
    config = BaseAgentConfig(name="test-agent")
    agent = BaseAgent(config=config)

    # Register hook
    cost_hook = CostTrackingHook()
    agent.hook_manager.register(HookEvent.POST_TOOL_USE, cost_hook)

    # Execute tool
    result = await agent.execute_tool("Read", {"file_path": "/tmp/test.txt"})

    # Verify hook was called
    assert cost_hook.total_cost_usd > 0
```

### Tier 3: E2E Tests (Real Filesystem Hooks)
```python
@pytest.mark.tier3
async def test_filesystem_hook_discovery():
    # Create .kaizen/hooks/custom_hook.py
    create_hook_file(".kaizen/hooks/custom_hook.py")

    # Load hooks from filesystem
    options = KaizenOptions(setting_sources=["project"])
    agent = BaseAgent.from_options(options)

    # Verify hook was discovered and registered
    assert "custom_hook" in agent.hook_manager._hooks
```

## Documentation Requirements

- [ ] **ADR** (this document)
- [ ] **API Reference**: `docs/reference/hooks-api.md`
- [ ] **Tutorial**: `docs/guides/hooks-tutorial.md`
- [ ] **Built-in Hooks**: `docs/reference/builtin-hooks.md`
- [ ] **Custom Hooks Guide**: `docs/guides/custom-hooks.md`
- [ ] **Troubleshooting**: `docs/reference/hooks-troubleshooting.md`

## References

1. **Gap Analysis**: `.claude/improvements/CLAUDE_AGENT_SDK_KAIZEN_GAP_ANALYSIS.md`
2. **Implementation Proposal**: `.claude/improvements/KAIZEN_AUTONOMOUS_AGENT_ENHANCEMENT_PROPOSAL.md` (Section 3.4)
3. **Performance Plan**: `.claude/improvements/PERFORMANCE_PARITY_PLAN.md` (Phase 2)
4. **Claude Code Hooks**: How Claude Code enables extensibility via event-driven hooks

## Dependencies

**This ADR depends on**:
- 011: Control Protocol (for hook-based approvals)
- 013: Specialist System (for specialist-specific hooks)

**Other ADRs depend on this**:
- 015: State Persistence (for checkpoint hooks)
- 016: Interrupt Mechanism (for interrupt hooks)
- 017: Observability (for monitoring hooks)

## Approval

**Proposed By**: Kaizen Architecture Team
**Date**: 2025-10-19
**Reviewers**: TBD
**Status**: Proposed (awaiting team review)

---

**Next ADR**: 015: State Persistence Strategy (checkpointing and resume)
