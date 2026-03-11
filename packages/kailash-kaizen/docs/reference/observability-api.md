# Observability (Hooks) API Reference

**Version**: v0.6.3+
**Location**: `kaizen.core.autonomy.hooks`

## Overview

The **Hooks System** provides event-driven observability for autonomous agents with lifecycle event hooks, automatic monitoring, and production-ready integrations. Hooks enable you to instrument agent execution, track performance, audit actions, and integrate with distributed tracing systems.

### Key Features

- **14 Lifecycle Events**: Pre/post hooks for agent loops, tool use, permissions, checkpoints, interrupts, specialists
- **Priority-Based Execution**: Critical → High → Normal → Low execution order
- **Error Isolation**: Hook failures don't crash agent execution
- **Timeout Protection**: 0.5s default timeout prevents hook blocking (Security Fix #10)
- **Performance Tracking**: Automatic statistics (call count, success rate, duration)
- **Builtin Hooks**: Audit trail, distributed tracing, cost tracking, Prometheus metrics, logging, profiling
- **Async-First**: All hooks are async for non-blocking execution
- **Filesystem Discovery**: Automatic hook loading from directories
- **Production-Ready**: Used in enterprise deployments with OpenTelemetry, Jaeger, Prometheus

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        HookManager                          │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Event Registry (dict[HookEvent, list[(Priority, Hook)]│ │
│  │   PRE_TOOL_USE    → [(CRITICAL, audit), (HIGH, trace)]│ │
│  │   POST_TOOL_USE   → [(NORMAL, cost), (NORMAL, metrics)]│ │
│  │   PRE_AGENT_LOOP  → [(HIGH, trace), (NORMAL, log)]   │ │
│  └───────────────────────────────────────────────────────┘ │
│                            │                                 │
│                            ▼                                 │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Execution Pipeline (priority-ordered, timeout-protected)│ │
│  │   1. Execute hooks in priority order (0→3)            │ │
│  │   2. Timeout protection (0.5s per hook)               │ │
│  │   3. Error isolation (failures logged, not propagated)│ │
│  │   4. Statistics tracking (duration, success/failure)  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                       BaseAgent Integration                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  PRE/POST    │  │  PRE/POST    │  │  PRE/POST    │      │
│  │ AGENT_LOOP   │  │  TOOL_USE    │  │ CHECKPOINT   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      Builtin Hooks                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ AuditHook    │  │ TracingHook  │  │ CostTracking │      │
│  │ PostgreSQL   │  │ OpenTelemetry│  │ LLM Costs    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ MetricsHook  │  │ LoggingHook  │  │ Profiler     │      │
│  │ Prometheus   │  │ Structured   │  │ Percentiles  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Types

### HookEvent

**Lifecycle events where hooks can be triggered.**

```python
class HookEvent(Enum):
    """Lifecycle events for hook triggering"""

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

    # Interrupt handling integration
    PRE_INTERRUPT = "pre_interrupt"
    POST_INTERRUPT = "post_interrupt"
```

**Event Semantics:**

- **PRE events**: Triggered BEFORE operation starts (e.g., before tool execution)
- **POST events**: Triggered AFTER operation completes (e.g., after tool returns result)

**Typical Event Flow:**

```
PRE_AGENT_LOOP
  ├─ PRE_PERMISSION_CHECK
  │    └─ POST_PERMISSION_CHECK
  ├─ PRE_TOOL_USE
  │    └─ POST_TOOL_USE
  ├─ PRE_CHECKPOINT_SAVE (if auto-checkpoint enabled)
  │    └─ POST_CHECKPOINT_SAVE
  └─ POST_AGENT_LOOP
```

---

### HookPriority

**Priority levels for controlling hook execution order.**

```python
class HookPriority(Enum):
    """Priority levels for hook execution order (lower = earlier)"""

    CRITICAL = 0  # Execute first (logging, auditing)
    HIGH = 1      # Execute early (metrics, monitoring)
    NORMAL = 2    # Default priority (most hooks)
    LOW = 3       # Execute last (cleanup, notifications)
```

**Execution Order:**

Within each event, hooks execute in priority order: CRITICAL → HIGH → NORMAL → LOW.

**Use Cases:**

- **CRITICAL**: Audit logging (must run first for compliance)
- **HIGH**: Distributed tracing (early context propagation)
- **NORMAL**: Cost tracking, metrics collection (standard monitoring)
- **LOW**: Notifications, cleanup (run after all processing)

---

### HookContext

**Context data passed to hook handlers.**

```python
@dataclass
class HookContext:
    """Context passed to hook handlers"""

    event_type: HookEvent           # Which event triggered this hook
    agent_id: str                   # ID of agent that triggered event
    timestamp: float                # Unix timestamp (auto-set if None)
    data: dict[str, Any]            # Event-specific data
    metadata: dict[str, Any]        # Optional additional metadata
    trace_id: str | None            # Distributed tracing ID (auto-generated if None)

    def __post_init__(self):
        """Ensure timestamp is set"""
        if self.timestamp is None:
            self.timestamp = time.time()
```

**Fields:**

- **event_type**: Which lifecycle event triggered this hook (e.g., `HookEvent.PRE_TOOL_USE`)
- **agent_id**: Unique identifier for the agent instance
- **timestamp**: Unix timestamp when event occurred (auto-set to `time.time()` if None)
- **data**: Event-specific data (e.g., `{"tool_name": "read_file", "params": {...}}`)
- **metadata**: Optional metadata (e.g., `{"session_id": "abc123", "user_id": "user456"}`)
- **trace_id**: Distributed tracing correlation ID (auto-generated UUID if None)

**Event-Specific Data:**

Different events populate `data` with different fields:

```python
# PRE_TOOL_USE / POST_TOOL_USE
data = {
    "tool_name": "read_file",
    "params": {"file_path": "/path/to/file"},
    "result": {...},              # POST only
    "estimated_cost_usd": 0.001,  # POST only
}

# PRE_AGENT_LOOP / POST_AGENT_LOOP
data = {
    "inputs": {"question": "What is AI?"},
    "result": {"answer": "..."},  # POST only
    "success": True,              # POST only
}

# PRE_CHECKPOINT_SAVE / POST_CHECKPOINT_SAVE
data = {
    "checkpoint_id": "ckpt_abc123",
    "step_number": 42,
    "state_size_bytes": 1024,     # POST only
}
```

---

### HookResult

**Result returned by hook handlers.**

```python
@dataclass
class HookResult:
    """Result returned by hook handler"""

    success: bool                      # Whether hook executed successfully
    data: dict[str, Any] | None = None # Optional result data
    error: str | None = None           # Error message (required if success=False)
    duration_ms: float = 0.0           # Execution duration (set by HookManager)

    def __post_init__(self):
        """Validate result"""
        if not self.success and self.error is None:
            raise ValueError("Unsuccessful hook result must include error message")
```

**Fields:**

- **success**: `True` if hook executed successfully, `False` if error occurred
- **data**: Optional result data (e.g., `{"audit_event_id": 123}`)
- **error**: Error message (required if `success=False`)
- **duration_ms**: Execution duration in milliseconds (set automatically by HookManager)

**Validation:**

- If `success=False`, `error` must be provided (raises `ValueError` otherwise)
- Hook failures are isolated - they don't crash agent execution

---

## HookHandler Protocol and BaseHook

### HookHandler (Protocol)

**Protocol defining hook handler interface.**

```python
@runtime_checkable
class HookHandler(Protocol):
    """Protocol for hook handlers (must be async)"""

    @abstractmethod
    async def handle(self, context: HookContext) -> HookResult:
        """
        Handle hook event.

        Args:
            context: Hook execution context with event type and data

        Returns:
            HookResult indicating success/failure and optional data

        Raises:
            Exception: Any exception will be caught by HookManager
        """
        ...
```

**Requirements:**

- Must implement `async def handle(self, context: HookContext) -> HookResult`
- All hooks must be async (no sync hook support)
- Exceptions are automatically caught by HookManager (error isolation)

---

### BaseHook

**Base class for hook implementations.**

```python
class BaseHook:
    """
    Base class for hook implementations.

    Provides common functionality and error handling for hooks.
    """

    def __init__(self, name: str):
        """
        Initialize hook with a name.

        Args:
            name: Unique identifier for this hook (used in logging/stats)
        """
        self.name = name

    async def handle(self, context: HookContext) -> HookResult:
        """
        Handle hook event. Override this in subclasses.

        Args:
            context: Hook execution context

        Returns:
            HookResult with success status and optional data

        Raises:
            NotImplementedError: If not overridden in subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.handle() must be implemented"
        )

    async def on_error(self, error: Exception, context: HookContext) -> None:
        """
        Optional error handler called when handle() raises an exception.

        Override this to implement custom error handling (logging, notifications, etc.)

        Args:
            error: The exception that was raised
            context: The hook context that caused the error
        """
        pass

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}(name={self.name!r})"
```

**Usage Pattern:**

```python
class MyCustomHook(BaseHook):
    """Custom hook for monitoring agent execution."""

    def __init__(self):
        super().__init__(name="my_custom_hook")
        self.call_count = 0

    async def handle(self, context: HookContext) -> HookResult:
        """Track agent execution."""
        self.call_count += 1

        print(f"[{context.event_type.value}] Agent {context.agent_id} executed")

        return HookResult(
            success=True,
            data={"call_count": self.call_count}
        )

    async def on_error(self, error: Exception, context: HookContext) -> None:
        """Log errors to stderr."""
        print(f"ERROR in {self.name}: {error}", file=sys.stderr)
```

---

## HookManager

**Manages hook registration and execution.**

```python
class HookManager:
    """
    Manages hook registration and execution.

    Handles async execution, error isolation, timeouts, and statistics tracking.
    """

    def __init__(self):
        """Initialize empty hook registry"""
        self._hooks: dict[HookEvent, list[tuple[HookPriority, HookHandler]]] = (
            defaultdict(list)
        )
        self._hook_stats: dict[str, dict[str, Any]] = {}
```

### Registration Methods

#### register()

**Register a hook handler for an event.**

```python
def register(
    self,
    event_type: HookEvent | str,
    handler: HookHandler | Callable[[HookContext], Awaitable[HookResult]],
    priority: HookPriority = HookPriority.NORMAL,
) -> None:
    """
    Register a hook handler for an event.

    Args:
        event_type: Event to trigger hook on (HookEvent or string)
        handler: Hook handler (HookHandler instance or async callable)
        priority: Execution priority (lower = earlier)

    Raises:
        ValueError: If event_type is invalid string

    Example:
        >>> hook_manager = HookManager()
        >>>
        >>> # Option 1: Register BaseHook instance
        >>> audit_hook = AuditHook(audit_provider)
        >>> hook_manager.register(HookEvent.PRE_TOOL_USE, audit_hook, HookPriority.CRITICAL)
        >>>
        >>> # Option 2: Register async function directly
        >>> async def log_tool_use(context: HookContext) -> HookResult:
        ...     print(f"Tool used: {context.data.get('tool_name')}")
        ...     return HookResult(success=True)
        >>> hook_manager.register("post_tool_use", log_tool_use)
    """
```

**Features:**

- Accepts `HookEvent` enum or string (e.g., `"pre_tool_use"`)
- Accepts `BaseHook` instance or plain async function
- Automatically wraps async functions in `FunctionHookAdapter`
- Maintains priority-sorted order (stable sort preserves registration order within priority)

**Example:**

```python
hook_manager = HookManager()

# Register with enum
hook_manager.register(HookEvent.PRE_TOOL_USE, my_hook, HookPriority.HIGH)

# Register with string
hook_manager.register("post_tool_use", my_hook, HookPriority.NORMAL)

# Register async function directly
async def simple_logger(context: HookContext) -> HookResult:
    logger.info(f"Event: {context.event_type.value}")
    return HookResult(success=True)

hook_manager.register(HookEvent.PRE_AGENT_LOOP, simple_logger)
```

---

#### register_hook()

**Register a hook for all events it declares.**

```python
def register_hook(
    self,
    hook: BaseHook,
    priority: HookPriority = HookPriority.NORMAL,
) -> None:
    """
    Register a hook for all events it declares.

    Convenience method that automatically registers a hook for all events
    specified in its 'events' attribute.

    Args:
        hook: Hook instance to register (must have 'events' attribute)
        priority: Execution priority (lower = earlier)

    Raises:
        ValueError: If hook doesn't have 'events' attribute

    Example:
        >>> from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        >>> from kaizen.core.autonomy.observability.tracing_manager import TracingManager
        >>>
        >>> manager = TracingManager(service_name="my-service")
        >>> tracing_hook = TracingHook(tracing_manager=manager)
        >>>
        >>> hook_manager = HookManager()
        >>> hook_manager.register_hook(tracing_hook)  # Registers for all events in tracing_hook.events
    """
```

**Hook Events Attribute:**

Builtin hooks declare which events they handle:

```python
class CostTrackingHook(BaseHook):
    events: ClassVar[list[HookEvent]] = [
        HookEvent.POST_TOOL_USE,
        HookEvent.POST_AGENT_LOOP,
        HookEvent.POST_SPECIALIST_INVOKE,
    ]
```

**Example:**

```python
from kaizen.core.autonomy.hooks.builtin.cost_tracking_hook import CostTrackingHook

hook_manager = HookManager()

# Register for all POST events (3 events)
cost_hook = CostTrackingHook()
hook_manager.register_hook(cost_hook, priority=HookPriority.NORMAL)

# Equivalent to:
# hook_manager.register(HookEvent.POST_TOOL_USE, cost_hook, HookPriority.NORMAL)
# hook_manager.register(HookEvent.POST_AGENT_LOOP, cost_hook, HookPriority.NORMAL)
# hook_manager.register(HookEvent.POST_SPECIALIST_INVOKE, cost_hook, HookPriority.NORMAL)
```

---

#### unregister()

**Unregister hook(s) for an event.**

```python
def unregister(
    self,
    event_type: HookEvent | str,
    handler: HookHandler | None = None
) -> int:
    """
    Unregister hook(s) for an event.

    Args:
        event_type: Event type to unregister from (HookEvent or string)
        handler: Specific handler to remove (None = remove all for event)

    Returns:
        Number of hooks removed

    Raises:
        ValueError: If event_type is invalid string

    Example:
        >>> # Remove specific hook
        >>> removed = hook_manager.unregister(HookEvent.PRE_TOOL_USE, audit_hook)
        >>> print(f"Removed {removed} hooks")  # 1
        >>>
        >>> # Remove all hooks for event
        >>> removed = hook_manager.unregister("post_tool_use")
        >>> print(f"Removed {removed} hooks")  # e.g., 3
    """
```

**Behavior:**

- If `handler=None`: Remove ALL hooks for the event
- If `handler` specified: Remove only that specific handler
- Returns count of hooks removed

---

### Execution Methods

#### trigger()

**Trigger all hooks for an event type.**

```python
async def trigger(
    self,
    event_type: HookEvent | str,
    agent_id: str,
    data: dict[str, Any],
    timeout: float = 0.5,  # Reduced from 5.0 to 0.5 seconds (SECURITY FIX #10)
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> list[HookResult]:
    """
    Trigger all hooks for an event type.

    Executes hooks in priority order with error isolation and timeout protection.

    Args:
        event_type: Event that occurred (HookEvent or string)
        agent_id: ID of agent triggering the event
        data: Event-specific data
        timeout: Max execution time per hook in seconds (default: 0.5s)
        metadata: Optional additional metadata
        trace_id: Distributed tracing ID (auto-generated UUID if None)

    Returns:
        List of HookResult from each executed hook (in priority order)

    Raises:
        ValueError: If event_type is invalid string

    Example:
        >>> # Trigger PRE_TOOL_USE hooks
        >>> results = await hook_manager.trigger(
        ...     event_type=HookEvent.PRE_TOOL_USE,
        ...     agent_id="research_agent",
        ...     data={
        ...         "tool_name": "read_file",
        ...         "params": {"file_path": "/data/report.pdf"}
        ...     },
        ...     metadata={"session_id": "sess_123"},
        ...     timeout=1.0  # Allow 1s per hook
        ... )
        >>>
        >>> for result in results:
        ...     if result.success:
        ...         print(f"Hook succeeded: {result.data}")
        ...     else:
        ...         print(f"Hook failed: {result.error}")
    """
```

**Execution Flow:**

1. **Context Creation**: Creates `HookContext` with event type, agent ID, timestamp, data, metadata, trace ID
2. **Hook Retrieval**: Gets registered hooks for event (sorted by priority)
3. **Sequential Execution**: Executes each hook in priority order (CRITICAL → HIGH → NORMAL → LOW)
4. **Timeout Protection**: Each hook has `timeout` seconds to complete (default 0.5s)
5. **Error Isolation**: Hook failures logged, not propagated (returns `HookResult(success=False, error=...)`)
6. **Statistics Tracking**: Updates call count, success/failure count, duration stats

**Timeout Behavior:**

- If hook exceeds timeout: Returns `HookResult(success=False, error="Hook timeout: {name}")`
- Security Fix #10: Reduced default timeout from 5.0s to 0.5s to prevent malicious hooks from blocking agent execution

**Example:**

```python
# Trigger hooks with custom timeout
results = await hook_manager.trigger(
    event_type="post_tool_use",
    agent_id="code_agent",
    data={
        "tool_name": "execute_bash",
        "result": {"stdout": "Hello World", "exit_code": 0},
        "estimated_cost_usd": 0.002
    },
    timeout=2.0  # Allow 2s for expensive hooks (e.g., database writes)
)

# Check results
for i, result in enumerate(results):
    if result.success:
        print(f"Hook {i}: OK ({result.duration_ms:.1f}ms)")
    else:
        print(f"Hook {i}: FAILED - {result.error}")
```

---

### Statistics Methods

#### get_stats()

**Get hook performance statistics.**

```python
def get_stats(self) -> dict[str, dict[str, Any]]:
    """
    Get hook performance statistics.

    Returns:
        Dictionary mapping hook names to their stats:
        {
            "hook_name": {
                "call_count": 100,
                "success_count": 98,
                "failure_count": 2,
                "total_duration_ms": 1250.5,
                "avg_duration_ms": 12.5,
                "max_duration_ms": 45.2
            }
        }

    Example:
        >>> stats = hook_manager.get_stats()
        >>> for hook_name, metrics in stats.items():
        ...     print(f"{hook_name}:")
        ...     print(f"  Calls: {metrics['call_count']}")
        ...     print(f"  Success Rate: {metrics['success_count'] / metrics['call_count'] * 100:.1f}%")
        ...     print(f"  Avg Duration: {metrics['avg_duration_ms']:.2f}ms")
    """
```

**Tracked Metrics:**

- **call_count**: Total number of hook executions
- **success_count**: Number of successful executions
- **failure_count**: Number of failed executions (timeout or exception)
- **total_duration_ms**: Cumulative execution time
- **avg_duration_ms**: Average execution time (`total_duration_ms / call_count`)
- **max_duration_ms**: Maximum execution time observed

---

### Discovery Methods

#### discover_filesystem_hooks()

**Discover and load hooks from filesystem.**

```python
async def discover_filesystem_hooks(self, hooks_dir: Path) -> int:
    """
    Discover and load hooks from filesystem.

    Loads all .py files from hooks_dir that define hook classes or functions.

    Args:
        hooks_dir: Directory containing hook files (.py)

    Returns:
        Number of hooks discovered and registered

    Raises:
        OSError: If hooks_dir doesn't exist or isn't readable

    Example:
        >>> from pathlib import Path
        >>>
        >>> # Load hooks from custom directory
        >>> hooks_dir = Path("./my_hooks")
        >>> discovered_count = await hook_manager.discover_filesystem_hooks(hooks_dir)
        >>> print(f"Loaded {discovered_count} hooks from {hooks_dir}")
    """
```

**Discovery Process:**

1. **Find Hook Files**: Scans `hooks_dir` for `*.py` files (excludes `__init__.py`)
2. **Dynamic Import**: Loads each module using `importlib.util.spec_from_file_location()`
3. **Class Discovery**: Finds all `BaseHook` subclasses in module
4. **Instantiation**: Attempts to instantiate hook with zero-argument constructor
5. **Registration**: Registers hook for all events in its `events` attribute

**Hook File Structure:**

```python
# my_hooks/monitoring_hook.py

from kaizen.core.autonomy.hooks.protocol import BaseHook
from kaizen.core.autonomy.hooks.types import HookContext, HookEvent, HookResult
from typing import ClassVar

class MonitoringHook(BaseHook):
    """Custom monitoring hook."""

    # Declare which events to handle
    events: ClassVar[list[HookEvent]] = [
        HookEvent.PRE_AGENT_LOOP,
        HookEvent.POST_AGENT_LOOP,
    ]

    def __init__(self):
        """Zero-argument constructor required for discovery."""
        super().__init__(name="monitoring_hook")
        self.start_times = {}

    async def handle(self, context: HookContext) -> HookResult:
        """Track agent loop execution times."""
        if context.event_type == HookEvent.PRE_AGENT_LOOP:
            self.start_times[context.trace_id] = context.timestamp
        else:  # POST_AGENT_LOOP
            duration = context.timestamp - self.start_times.pop(context.trace_id, context.timestamp)
            print(f"Agent loop duration: {duration * 1000:.1f}ms")

        return HookResult(success=True)
```

---

## Builtin Hooks

### AuditHook

**PostgreSQL-backed audit trail integration.**

```python
class AuditHook(BaseHook):
    """
    Integrates AuditTrailProvider with hook system for automatic audit logging.

    Features:
    - Automatic audit logging for all hook events
    - PostgreSQL-backed persistence
    - trace_id storage in JSONB metadata
    - Event filtering (optional: log only specific events)
    - Compliance-ready audit trail
    """

    events: ClassVar[list[HookEvent]] = list(HookEvent)  # All events

    def __init__(
        self,
        audit_provider: "AuditTrailProvider",
        event_filter: list[HookEvent] | None = None,
    ):
        """
        Initialize audit hook.

        Args:
            audit_provider: AuditTrailProvider instance for PostgreSQL logging
            event_filter: Optional list of events to log (None = log all events)

        Example:
            >>> from kaizen.security.audit import AuditTrailProvider
            >>>
            >>> audit_provider = AuditTrailProvider(
            ...     conn_string="postgresql://user:pass@localhost/audit_db"
            ... )
            >>>
            >>> # Log all events
            >>> audit_hook = AuditHook(audit_provider)
            >>>
            >>> # Log only tool use
            >>> audit_hook = AuditHook(
            ...     audit_provider,
            ...     event_filter=[HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
            ... )
            >>>
            >>> hook_manager.register_hook(audit_hook, priority=HookPriority.CRITICAL)
        """
        super().__init__(name="audit_hook")
        self.audit_provider = audit_provider
        self.event_filter = event_filter

    async def handle(self, context: HookContext) -> HookResult:
        """
        Log hook event to audit trail.

        Args:
            context: Hook execution context

        Returns:
            HookResult with audit_event_id or skipped=True
        """
```

**Audit Trail Schema:**

```sql
CREATE TABLE audit_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    user_id VARCHAR(255) NOT NULL,        -- agent_id
    action VARCHAR(255) NOT NULL,         -- event_type
    result VARCHAR(50) NOT NULL,          -- success/error/failure
    metadata JSONB                        -- trace_id, data, metadata
);
```

**Usage Example:**

```python
from kaizen.security.audit import AuditTrailProvider
from kaizen.core.autonomy.hooks.builtin.audit_hook import AuditHook

# Setup audit provider
audit_provider = AuditTrailProvider(
    conn_string="postgresql://localhost/audit_db"
)

# Create audit hook (log tool use only)
audit_hook = AuditHook(
    audit_provider,
    event_filter=[HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
)

# Register with CRITICAL priority (run first)
hook_manager.register_hook(audit_hook, priority=HookPriority.CRITICAL)

# All tool use will now be audited to PostgreSQL
```

---

### TracingHook

**Distributed tracing with OpenTelemetry and Jaeger.**

```python
class TracingHook(BaseHook):
    """
    Hook for distributed tracing with OpenTelemetry and Jaeger.

    Automatically creates OpenTelemetry spans for hook events with parent-child
    hierarchy, exception recording, and span status based on hook results.

    Features:
    - Automatic span creation for hook events
    - Parent-child span hierarchy (PRE_AGENT_LOOP → PRE_TOOL_USE → POST_TOOL_USE)
    - Event filtering support (trace only specified events)
    - Span attributes from HookContext
    - Exception recording from HookResult errors
    - Span status based on HookResult success
    - Performance: <3% overhead compared to baseline
    """

    events: ClassVar[list[HookEvent]] = list(HookEvent)

    def __init__(
        self,
        tracing_manager: TracingManager,
        events_to_trace: Optional[List[HookEvent]] = None,
    ):
        """
        Initialize TracingHook with TracingManager and optional event filter.

        Args:
            tracing_manager: TracingManager for span creation
            events_to_trace: Optional list of events to trace (None = all events)

        Example:
            >>> from kaizen.core.autonomy.observability.tracing_manager import TracingManager
            >>> from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
            >>>
            >>> # Setup tracing manager
            >>> manager = TracingManager(
            ...     service_name="my-agent",
            ...     jaeger_endpoint="http://localhost:14268/api/traces"
            ... )
            >>>
            >>> # Create tracing hook (trace tool use only)
            >>> hook = TracingHook(
            ...     tracing_manager=manager,
            ...     events_to_trace=[HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
            ... )
            >>>
            >>> hook_manager.register_hook(hook, priority=HookPriority.HIGH)
        """
        super().__init__(name="tracing_hook")
        self.tracing_manager = tracing_manager
        self.events_to_trace = events_to_trace or []
        self._active_spans = {}  # Key: (trace_id, event_pair), Value: (span, start_time)

    async def handle(self, context: HookContext) -> HookResult:
        """
        Handle hook event and create OpenTelemetry span.

        Creates span for event with attributes from HookContext. Handles parent-child
        span hierarchy by checking metadata for parent_span_id. Records exceptions
        and sets span status based on hook execution.

        Args:
            context: Hook context with event details

        Returns:
            HookResult with span_created=True/False and span metadata
        """
```

**Span Hierarchy:**

```
agent_loop (PRE → POST)
  ├─ tool_use:read_file (PRE → POST)
  ├─ tool_use:execute_bash (PRE → POST)
  └─ checkpoint_save (PRE → POST)
```

**Span Attributes:**

```python
span.set_attribute("agent.id", context.agent_id)
span.set_attribute("event.type", context.event_type.value)
span.set_attribute("trace.id", context.trace_id)
span.set_attribute("duration.ms", duration_ms)

# Tool use specific
span.set_attribute("tool.name", context.data["tool_name"])
span.set_attribute("tool.params", json.dumps(context.data["params"]))
```

**Usage Example:**

```python
from kaizen.core.autonomy.observability.tracing_manager import TracingManager
from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook

# Setup tracing manager
tracing_manager = TracingManager(
    service_name="research-agent",
    jaeger_endpoint="http://localhost:14268/api/traces"
)

# Create tracing hook
tracing_hook = TracingHook(
    tracing_manager=tracing_manager,
    events_to_trace=[
        HookEvent.PRE_AGENT_LOOP,
        HookEvent.POST_AGENT_LOOP,
        HookEvent.PRE_TOOL_USE,
        HookEvent.POST_TOOL_USE,
    ]
)

# Register with HIGH priority
hook_manager.register_hook(tracing_hook, priority=HookPriority.HIGH)

# View traces at http://localhost:16686 (Jaeger UI)
```

---

### CostTrackingHook

**LLM API cost tracking per tool/agent/specialist.**

```python
class CostTrackingHook(BaseHook):
    """
    Tracks LLM API costs per tool invocation and agent execution.

    Accumulates costs and provides per-tool and per-agent breakdowns.
    """

    events: ClassVar[list[HookEvent]] = [
        HookEvent.POST_TOOL_USE,
        HookEvent.POST_AGENT_LOOP,
        HookEvent.POST_SPECIALIST_INVOKE,
    ]

    def __init__(self):
        """Initialize cost tracking hook"""
        super().__init__(name="cost_tracking_hook")

        # Cost accumulators
        self.total_cost_usd = 0.0
        self.costs_by_tool: dict[str, float] = defaultdict(float)
        self.costs_by_agent: dict[str, float] = defaultdict(float)
        self.costs_by_specialist: dict[str, float] = defaultdict(float)

    async def handle(self, context: HookContext) -> HookResult:
        """Track costs for the event."""

    def get_total_cost(self) -> float:
        """Get total accumulated cost in USD."""

    def get_cost_breakdown(self) -> dict[str, dict[str, float]]:
        """
        Get detailed cost breakdown.

        Returns:
            {
                "total_cost_usd": 1.25,
                "by_tool": {
                    "read_file": 0.01,
                    "execute_bash": 0.05,
                    "search_web": 0.20
                },
                "by_agent": {
                    "research_agent": 0.80,
                    "code_agent": 0.45
                },
                "by_specialist": {
                    "data_specialist": 0.60,
                    "writing_specialist": 0.15
                }
            }
        """

    def reset_costs(self) -> None:
        """Reset all cost counters"""
```

**Usage Example:**

```python
from kaizen.core.autonomy.hooks.builtin.cost_tracking_hook import CostTrackingHook

# Create cost tracking hook
cost_hook = CostTrackingHook()

# Register for POST events
hook_manager.register_hook(cost_hook, priority=HookPriority.NORMAL)

# Run agent...
result = agent.run(question="What is quantum computing?")

# Get cost breakdown
breakdown = cost_hook.get_cost_breakdown()
print(f"Total cost: ${breakdown['total_cost_usd']:.4f}")
print(f"By tool: {breakdown['by_tool']}")
print(f"By agent: {breakdown['by_agent']}")

# Output:
# Total cost: $0.0025
# By tool: {'llm_generate': 0.0025}
# By agent: {'qa_agent': 0.0025}
```

---

### MetricsHook

**Prometheus-compatible metrics collection with agent ID hashing (Security Fix #11).**

```python
class MetricsHook(BaseHook):
    """
    Collects Prometheus-compatible metrics with dimensional labels.

    Features:
    - Native prometheus_client integration
    - Counter/Histogram/Gauge metrics
    - Dimensional labels (agent_id, event_type, operation)
    - Percentile calculation (p50/p95/p99) via PerformanceProfilerHook integration
    - HTTP /metrics endpoint support
    - Agent ID hashing to prevent information disclosure (SECURITY FIX #11)
    """

    events: ClassVar[list[HookEvent]] = list(HookEvent)

    def __init__(
        self,
        registry: Optional[CollectorRegistry] = None,
        enable_percentiles: bool = True,
        profiler: Optional[PerformanceProfilerHook] = None,
        hash_agent_ids: bool = False,  # SECURITY FIX #11
    ):
        """
        Initialize metrics hook with Prometheus integration.

        Args:
            registry: Prometheus registry (creates new if None)
            enable_percentiles: Enable percentile calculation via profiler
            profiler: PerformanceProfilerHook instance (creates new if None and percentiles enabled)
            hash_agent_ids: Hash agent IDs before exposing in metrics (SECURITY FIX #11)

        Example:
            >>> from prometheus_client import CollectorRegistry
            >>>
            >>> # Production usage with agent ID hashing
            >>> registry = CollectorRegistry()
            >>> hook = MetricsHook(
            ...     registry=registry,
            ...     hash_agent_ids=True  # Prevents agent enumeration
            ... )
            >>>
            >>> hook_manager.register_hook(hook, priority=HookPriority.HIGH)
        """
        super().__init__(name="metrics_hook")
        self.registry = registry or CollectorRegistry()
        self.hash_agent_ids = hash_agent_ids

        # Define Prometheus metrics
        self.event_counter = Counter(
            "kaizen_hook_events_total",
            "Total hook events by type and agent",
            ["event_type", "agent_id"],
            registry=self.registry,
        )

        self.operation_duration = Histogram(
            "kaizen_operation_duration_seconds",
            "Operation duration by type and agent",
            ["operation", "agent_id"],
            registry=self.registry,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
        )

        self.active_agents = Gauge(
            "kaizen_active_agents",
            "Number of active agents",
            registry=self.registry
        )

    async def handle(self, context: HookContext) -> HookResult:
        """Collect metrics for the event with optional agent ID hashing."""

    def export_prometheus(self) -> bytes:
        """
        Export metrics in Prometheus text format.

        Returns:
            Metrics in Prometheus exposition format (bytes)
        """

    def get_percentiles(self, operation: str) -> dict[str, float]:
        """
        Get p50/p95/p99 percentiles for operation.

        Returns:
            {"p50_ms": 12.5, "p95_ms": 45.2, "p99_ms": 89.1}
        """
```

**Metrics Exposed:**

```
# HELP kaizen_hook_events_total Total hook events by type and agent
# TYPE kaizen_hook_events_total counter
kaizen_hook_events_total{event_type="pre_tool_use",agent_id="research_agent"} 42

# HELP kaizen_operation_duration_seconds Operation duration by type and agent
# TYPE kaizen_operation_duration_seconds histogram
kaizen_operation_duration_seconds_bucket{operation="tool_use",agent_id="research_agent",le="0.005"} 0
kaizen_operation_duration_seconds_bucket{operation="tool_use",agent_id="research_agent",le="0.01"} 5
...

# HELP kaizen_active_agents Number of active agents
# TYPE kaizen_active_agents gauge
kaizen_active_agents 3
```

**Security Fix #11 (Agent ID Hashing):**

```python
# Without hashing (exposes agent IDs)
kaizen_hook_events_total{agent_id="research_agent"} 42

# With hashing (prevents enumeration)
kaizen_hook_events_total{agent_id="5d41402abc4b2a76"} 42
```

**Usage Example:**

```python
from prometheus_client import CollectorRegistry, start_http_server
from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook

# Create Prometheus registry
registry = CollectorRegistry()

# Create metrics hook with agent ID hashing (production)
metrics_hook = MetricsHook(
    registry=registry,
    enable_percentiles=True,
    hash_agent_ids=True  # SECURITY: Hash agent IDs
)

# Register hook
hook_manager.register_hook(metrics_hook, priority=HookPriority.HIGH)

# Expose metrics on HTTP port 8000
start_http_server(8000, registry=registry)

# Metrics available at: http://localhost:8000/metrics

# Get percentiles
percentiles = metrics_hook.get_percentiles("tool_use")
print(f"p95 latency: {percentiles['p95_ms']:.1f}ms")
```

---

## Usage Examples

### Basic: Register and Trigger Hooks

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookPriority
from kaizen.core.autonomy.hooks.types import HookContext, HookResult

# Create hook manager
hook_manager = HookManager()

# Define async hook function
async def log_tool_use(context: HookContext) -> HookResult:
    """Log tool usage to stdout."""
    tool_name = context.data.get("tool_name", "unknown")
    print(f"[{context.agent_id}] Using tool: {tool_name}")
    return HookResult(success=True)

# Register hook
hook_manager.register(
    event_type=HookEvent.PRE_TOOL_USE,
    handler=log_tool_use,
    priority=HookPriority.NORMAL
)

# Trigger hooks
results = await hook_manager.trigger(
    event_type=HookEvent.PRE_TOOL_USE,
    agent_id="research_agent",
    data={
        "tool_name": "read_file",
        "params": {"file_path": "/data/report.pdf"}
    }
)

# Check results
for result in results:
    if result.success:
        print(f"Hook executed in {result.duration_ms:.1f}ms")
    else:
        print(f"Hook failed: {result.error}")
```

---

### Advanced: Multi-Hook Registration with Priorities

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookPriority
from kaizen.core.autonomy.hooks.builtin import (
    AuditHook,
    TracingHook,
    CostTrackingHook,
    MetricsHook,
)

# Setup dependencies
audit_provider = AuditTrailProvider(conn_string="postgresql://...")
tracing_manager = TracingManager(service_name="my-agent")

# Create hooks
audit_hook = AuditHook(audit_provider)
tracing_hook = TracingHook(tracing_manager)
cost_hook = CostTrackingHook()
metrics_hook = MetricsHook(hash_agent_ids=True)

# Register with priorities
hook_manager = HookManager()

# CRITICAL: Audit (must run first for compliance)
hook_manager.register_hook(audit_hook, priority=HookPriority.CRITICAL)

# HIGH: Tracing (early context propagation)
hook_manager.register_hook(tracing_hook, priority=HookPriority.HIGH)

# NORMAL: Cost tracking and metrics
hook_manager.register_hook(cost_hook, priority=HookPriority.NORMAL)
hook_manager.register_hook(metrics_hook, priority=HookPriority.NORMAL)

# Hooks execute in order: audit → tracing → cost → metrics
```

---

### Production: BaseAgent Integration

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks import HookManager, HookEvent
from kaizen.core.autonomy.hooks.builtin import MetricsHook, CostTrackingHook

# Create hook manager
hook_manager = HookManager()

# Register production hooks
metrics_hook = MetricsHook(hash_agent_ids=True)
cost_hook = CostTrackingHook()

hook_manager.register_hook(metrics_hook, priority=HookPriority.HIGH)
hook_manager.register_hook(cost_hook, priority=HookPriority.NORMAL)

# Create agent with hook manager
agent = BaseAgent(
    config=config,
    signature=signature,
    hook_manager=hook_manager  # BaseAgent will trigger hooks automatically
)

# Run agent - hooks execute automatically
result = agent.run(question="What is AI?")

# Get cost breakdown
breakdown = cost_hook.get_cost_breakdown()
print(f"Total cost: ${breakdown['total_cost_usd']:.4f}")

# Get metrics
stats = hook_manager.get_stats()
print(f"Metrics hook called {stats['metrics_hook']['call_count']} times")
```

**BaseAgent Hook Triggers:**

BaseAgent automatically triggers hooks at these points:

1. **PRE_AGENT_LOOP**: Before agent execution starts
2. **PRE_TOOL_USE**: Before each tool is executed
3. **POST_TOOL_USE**: After each tool completes
4. **POST_AGENT_LOOP**: After agent execution completes

---

### Production: Checkpoint Integration

```python
from kaizen.core.autonomy.state import StateManager, FilesystemStorage
from kaizen.core.autonomy.hooks import HookManager, HookEvent
from kaizen.core.autonomy.hooks.builtin import AuditHook

# Create state manager
storage = FilesystemStorage(base_dir="./checkpoints")
state_manager = StateManager(
    storage=storage,
    checkpoint_frequency=10  # Checkpoint every 10 steps
)

# Create hook manager with audit hook
hook_manager = HookManager()
audit_hook = AuditHook(audit_provider)
hook_manager.register_hook(audit_hook, priority=HookPriority.CRITICAL)

# StateManager triggers hooks automatically:
# - PRE_CHECKPOINT_SAVE: Before saving checkpoint
# - POST_CHECKPOINT_SAVE: After saving checkpoint

# Save checkpoint with hook triggers
checkpoint_id = await state_manager.save_checkpoint(
    agent_state,
    hook_manager=hook_manager  # Pass hook manager for automatic triggers
)

# Hooks log checkpoint saves to audit trail
```

---

### Production: Interrupt Integration

```python
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.hooks import HookManager, HookEvent
from kaizen.core.autonomy.hooks.builtin import AuditHook

# Create interrupt manager
interrupt_manager = InterruptManager()

# Create hook manager
hook_manager = HookManager()
audit_hook = AuditHook(audit_provider)
hook_manager.register_hook(audit_hook, priority=HookPriority.CRITICAL)

# InterruptManager triggers hooks automatically:
# - PRE_INTERRUPT: Before interrupt processing starts
# - POST_INTERRUPT: After interrupt completes

# Request interrupt with hook triggers
interrupt_manager.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.USER,
    message="User requested shutdown",
    hook_manager=hook_manager  # Pass hook manager for automatic triggers
)

# Hooks log interrupts to audit trail
```

---

## Testing

### Unit Testing: Hook Implementation

```python
import pytest
from kaizen.core.autonomy.hooks.types import HookContext, HookEvent, HookResult
from kaizen.core.autonomy.hooks.protocol import BaseHook

class TestCustomHook:
    """Unit tests for custom hook implementation."""

    @pytest.mark.asyncio
    async def test_hook_execution(self):
        """Test hook executes successfully."""
        # Create custom hook
        class CounterHook(BaseHook):
            def __init__(self):
                super().__init__(name="counter_hook")
                self.count = 0

            async def handle(self, context: HookContext) -> HookResult:
                self.count += 1
                return HookResult(success=True, data={"count": self.count})

        hook = CounterHook()

        # Create context
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=1234567890.0,
            data={"tool_name": "test_tool"}
        )

        # Execute hook
        result = await hook.handle(context)

        # Verify result
        assert result.success is True
        assert result.data == {"count": 1}
        assert hook.count == 1

    @pytest.mark.asyncio
    async def test_hook_error_handling(self):
        """Test hook error handling."""
        class FailingHook(BaseHook):
            def __init__(self):
                super().__init__(name="failing_hook")

            async def handle(self, context: HookContext) -> HookResult:
                raise ValueError("Intentional failure")

            async def on_error(self, error: Exception, context: HookContext) -> None:
                assert isinstance(error, ValueError)
                assert str(error) == "Intentional failure"

        hook = FailingHook()
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=1234567890.0,
            data={}
        )

        # Should raise ValueError
        with pytest.raises(ValueError):
            await hook.handle(context)
```

---

### Integration Testing: HookManager

```python
import pytest
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookPriority
from kaizen.core.autonomy.hooks.types import HookContext, HookResult
from kaizen.core.autonomy.hooks.protocol import BaseHook

class TestHookManager:
    """Integration tests for HookManager."""

    @pytest.mark.asyncio
    async def test_hook_registration(self):
        """Test hook registration and triggering."""
        hook_manager = HookManager()

        # Create test hook
        class TestHook(BaseHook):
            def __init__(self):
                super().__init__(name="test_hook")
                self.called = False

            async def handle(self, context: HookContext) -> HookResult:
                self.called = True
                return HookResult(success=True)

        hook = TestHook()

        # Register hook
        hook_manager.register(HookEvent.PRE_TOOL_USE, hook)

        # Trigger hook
        results = await hook_manager.trigger(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={"tool_name": "test_tool"}
        )

        # Verify execution
        assert len(results) == 1
        assert results[0].success is True
        assert hook.called is True

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test hooks execute in priority order."""
        hook_manager = HookManager()
        execution_order = []

        # Create hooks with different priorities
        async def critical_hook(context: HookContext) -> HookResult:
            execution_order.append("critical")
            return HookResult(success=True)

        async def normal_hook(context: HookContext) -> HookResult:
            execution_order.append("normal")
            return HookResult(success=True)

        async def low_hook(context: HookContext) -> HookResult:
            execution_order.append("low")
            return HookResult(success=True)

        # Register in reverse order (should execute by priority)
        hook_manager.register(HookEvent.PRE_TOOL_USE, low_hook, HookPriority.LOW)
        hook_manager.register(HookEvent.PRE_TOOL_USE, normal_hook, HookPriority.NORMAL)
        hook_manager.register(HookEvent.PRE_TOOL_USE, critical_hook, HookPriority.CRITICAL)

        # Trigger hooks
        await hook_manager.trigger(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={}
        )

        # Verify execution order (CRITICAL → NORMAL → LOW)
        assert execution_order == ["critical", "normal", "low"]

    @pytest.mark.asyncio
    async def test_timeout_protection(self):
        """Test hook timeout protection."""
        import asyncio

        hook_manager = HookManager()

        # Create slow hook
        async def slow_hook(context: HookContext) -> HookResult:
            await asyncio.sleep(2.0)  # Exceeds 0.5s default timeout
            return HookResult(success=True)

        hook_manager.register(HookEvent.PRE_TOOL_USE, slow_hook)

        # Trigger with timeout
        results = await hook_manager.trigger(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={},
            timeout=0.1  # 100ms timeout
        )

        # Verify timeout result
        assert len(results) == 1
        assert results[0].success is False
        assert "timeout" in results[0].error.lower()
```

---

### E2E Testing: BaseAgent Integration

```python
import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.hooks import HookManager, HookEvent
from kaizen.core.autonomy.hooks.builtin import CostTrackingHook

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_baseagent_hook_integration():
    """
    E2E test: BaseAgent with cost tracking hook.

    Validates:
    - Hooks execute during agent operation
    - Cost tracking accumulates correctly
    - Hook statistics are accurate
    """
    # Create hook manager with cost tracking
    hook_manager = HookManager()
    cost_hook = CostTrackingHook()
    hook_manager.register_hook(cost_hook)

    # Create agent with hook manager
    agent = BaseAgent(
        config=config,
        signature=signature,
        hook_manager=hook_manager
    )

    # Run agent
    result = agent.run(question="What is quantum computing?")

    # Verify hooks executed
    stats = hook_manager.get_stats()
    assert "cost_tracking_hook" in stats
    assert stats["cost_tracking_hook"]["call_count"] > 0

    # Verify cost tracking
    breakdown = cost_hook.get_cost_breakdown()
    assert breakdown["total_cost_usd"] > 0
    assert "qa_agent" in breakdown["by_agent"]
```

---

## Related Documentation

- **[Checkpoint API](checkpoint-api.md)** - State persistence with checkpoint hooks
- **[Interrupts API](interrupts-api.md)** - Graceful shutdown with interrupt hooks
- **[Coordination API](coordination-api.md)** - Meta-controller with specialist invoke hooks
- **[Hooks System Guide](../guides/hooks-system-guide.md)** - Comprehensive usage guide
- **[BaseAgent Architecture](../guides/baseagent-architecture.md)** - Agent lifecycle and hook integration

---

## Version History

- **v0.6.3**: Initial release with 14 lifecycle events
- **v0.6.4**: Security Fix #10 - Reduced default timeout from 5.0s to 0.5s
- **v0.6.5**: Security Fix #11 - Added agent ID hashing in MetricsHook

---

**Complete API Reference for Kaizen Observability (Hooks) System**
