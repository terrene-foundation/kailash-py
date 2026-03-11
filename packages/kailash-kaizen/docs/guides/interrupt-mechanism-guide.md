# Interrupt Mechanism Guide

**Status**: ✅ Implemented (Phase 3)
**Location**: `src/kaizen/core/autonomy/interrupts/`
**Tests**: 66 unit tests + integration tests (100% passing)

## Overview

The Interrupt Mechanism provides graceful shutdown coordination for autonomous agents, supporting:

- **Thread-safe interrupts** from signal handlers, timeouts, budgets, or user requests
- **Graceful vs Immediate modes** for controlled shutdown behavior
- **Automatic checkpoint creation** before shutdown
- **Shutdown callbacks** for cleanup operations
- **Built-in handlers** for timeout and budget monitoring

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    InterruptManager                         │
│  - Thread-safe interrupt flag (anyio.Event)                │
│  - Shutdown callback coordination                           │
│  - Checkpoint integration                                   │
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
    ┌────────▼───────────┐          ┌────────▼──────────┐
    │  Signal Handlers   │          │  Interrupt Handlers│
    │  (SIGINT, SIGTERM) │          │  (Timeout, Budget) │
    └────────────────────┘          └───────────────────┘
```

## Core Types

### InterruptMode

```python
class InterruptMode(Enum):
    GRACEFUL = "graceful"    # Finish current step, then checkpoint and stop
    IMMEDIATE = "immediate"  # Stop now, checkpoint if possible
```

### InterruptSource

```python
class InterruptSource(Enum):
    SIGNAL = "signal"              # OS signal (SIGINT, SIGTERM, SIGUSR1)
    TIMEOUT = "timeout"            # Execution time limit exceeded
    BUDGET = "budget"              # Token/cost budget exceeded
    USER = "user"                  # User requested via control protocol
    PROGRAMMATIC = "programmatic"  # Code-initiated interrupt
```

### InterruptReason

```python
@dataclass
class InterruptReason:
    source: InterruptSource
    mode: InterruptMode
    message: str
    timestamp: datetime
    metadata: dict[str, Any]
```

### InterruptStatus

```python
@dataclass
class InterruptStatus:
    interrupted: bool
    reason: InterruptReason | None
    checkpoint_id: str | None  # Checkpoint saved before interrupt

    def can_resume(self) -> bool:
        """Check if execution can be resumed from checkpoint"""
        return self.checkpoint_id is not None
```

## Quick Start

### 1. Basic Signal Handling

```python
from kaizen.core.autonomy.interrupts import InterruptManager

# Create manager
manager = InterruptManager()

# Install signal handlers (SIGINT, SIGTERM)
manager.install_signal_handlers()

try:
    # Agent loop
    while not manager.is_interrupted():
        # Do work...
        step_result = agent.step()

        # Check interrupt periodically
        if manager.is_interrupted():
            print("Interrupt received, stopping...")
            break
finally:
    # Clean up
    manager.uninstall_signal_handlers()
```

### 2. With Checkpoint Integration

```python
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.state import StateManager, AgentState, FilesystemStorage

# Setup
storage = FilesystemStorage(base_dir="checkpoints/")
state_manager = StateManager(storage=storage)
interrupt_manager = InterruptManager()

# Install handlers
interrupt_manager.install_signal_handlers()

# Create agent state
agent_state = AgentState(agent_id="agent1", status="running")

try:
    # Agent loop
    for step in range(100):
        if interrupt_manager.is_interrupted():
            break

        # Update state
        agent_state.step_number = step
        # ... do work ...

finally:
    # Graceful shutdown with checkpoint
    status = await interrupt_manager.execute_shutdown(
        state_manager=state_manager,
        agent_state=agent_state
    )

    print(f"Shutdown complete. Checkpoint: {status.checkpoint_id}")

    if status.can_resume():
        print(f"Can resume from checkpoint {status.checkpoint_id}")
```

### 3. Timeout Monitoring

```python
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.handlers import TimeoutInterruptHandler

manager = InterruptManager()

# Create timeout handler (5 minutes)
timeout_handler = TimeoutInterruptHandler(
    interrupt_manager=manager,
    timeout_seconds=300.0,
    warning_threshold=0.8  # Warn at 80% (4 minutes)
)

# Start monitoring in background
async with anyio.create_task_group() as tg:
    tg.start_soon(timeout_handler.start)

    # Agent execution
    while not manager.is_interrupted():
        # Do work...
        await agent.step()

    # Timeout handler will trigger interrupt after 5 minutes
```

### 4. Budget Monitoring

```python
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.handlers import BudgetInterruptHandler

manager = InterruptManager()

# Create budget handler ($10 limit)
budget_handler = BudgetInterruptHandler(
    interrupt_manager=manager,
    budget_usd=10.0,
    warning_threshold=0.8  # Warn at $8
)

# Track costs during execution
for step in range(100):
    if manager.is_interrupted():
        print(f"Budget exceeded: ${budget_handler.get_current_cost():.2f}")
        break

    # Do LLM call or tool use
    result = await llm.generate(prompt)
    cost = result.get("cost_usd", 0.0)

    # Track cost (automatically triggers interrupt if budget exceeded)
    budget_handler.track_cost(cost)

# Check budget status
print(f"Total cost: ${budget_handler.get_current_cost():.2f}")
print(f"Remaining: ${budget_handler.get_remaining_budget():.2f}")
print(f"Usage: {budget_handler.get_budget_usage_percent():.1f}%")
```

## Patterns

### Pattern 1: Graceful Shutdown with Cleanup

```python
import anyio

manager = InterruptManager()

# Register cleanup callbacks
async def save_results():
    await db.save(results)
    print("Results saved")

async def close_connections():
    await client.close()
    print("Connections closed")

manager.register_shutdown_callback(save_results)
manager.register_shutdown_callback(close_connections)

# Install signal handlers
manager.install_signal_handlers()

try:
    # Work...
    while not manager.is_interrupted():
        await do_work()
finally:
    # Execute all callbacks automatically
    status = await manager.execute_shutdown()
    print(f"Shutdown reason: {status.reason.message}")
```

### Pattern 2: Multiple Interrupt Sources

```python
manager = InterruptManager()

# Setup signal handling
manager.install_signal_handlers()

# Setup timeout (1 hour)
timeout_handler = TimeoutInterruptHandler(manager, timeout_seconds=3600)

# Setup budget ($50)
budget_handler = BudgetInterruptHandler(manager, budget_usd=50.0)

# Start monitoring
async with anyio.create_task_group() as tg:
    tg.start_soon(timeout_handler.start)

    # Agent execution
    while not manager.is_interrupted():
        result = await agent.step()

        # Track cost
        budget_handler.track_cost(result.get("cost", 0.0))

    # Check interrupt source
    reason = manager._interrupt_reason
    print(f"Interrupted by: {reason.source.value}")

    if reason.source == InterruptSource.TIMEOUT:
        print(f"Timeout after {timeout_handler.timeout_seconds}s")
    elif reason.source == InterruptSource.BUDGET:
        print(f"Budget exceeded: ${budget_handler.get_current_cost():.2f}")
    elif reason.source == InterruptSource.SIGNAL:
        print(f"Signal received: {reason.metadata['signal_name']}")
```

### Pattern 3: Programmatic Interrupts

```python
manager = InterruptManager()

# Custom interrupt condition
def should_stop(state: AgentState) -> bool:
    # Custom logic
    if state.step_number > 1000:
        return True
    if state.error_count > 10:
        return True
    return False

# Agent loop
while not manager.is_interrupted():
    agent_state.step_number += 1

    # Check custom condition
    if should_stop(agent_state):
        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.PROGRAMMATIC,
            message="Custom stop condition met",
            metadata={"step": agent_state.step_number}
        )
        break

    # Do work...
    await agent.step()

# Shutdown
status = await manager.execute_shutdown(state_manager, agent_state)
```

## Best Practices

### 1. Always Install and Uninstall Signal Handlers

```python
manager = InterruptManager()

try:
    manager.install_signal_handlers()
    # ... work ...
finally:
    manager.uninstall_signal_handlers()
```

### 2. Check Interrupts Frequently

```python
# Good: Check every loop iteration
while not manager.is_interrupted():
    result = await agent.step()

# Bad: Long-running operations without checks
while True:
    # Long operation with no interrupt checks
    result = await slow_operation()  # May run for minutes
```

### 3. Use Appropriate Interrupt Modes

```python
# GRACEFUL: For operations that can finish current work
manager.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.USER,
    message="User requested stop"
)

# IMMEDIATE: For critical conditions
manager.request_interrupt(
    mode=InterruptMode.IMMEDIATE,
    source=InterruptSource.PROGRAMMATIC,
    message="Critical error detected"
)
```

### 4. Always Save Checkpoints on Interrupt

```python
try:
    while not manager.is_interrupted():
        await agent.step()
finally:
    # ALWAYS call execute_shutdown to save checkpoint
    status = await manager.execute_shutdown(
        state_manager=state_manager,
        agent_state=agent_state
    )

    if status.checkpoint_id:
        print(f"Saved checkpoint: {status.checkpoint_id}")
```

### 5. Use Shutdown Callbacks for Cleanup

```python
# Register all cleanup operations
manager.register_shutdown_callback(close_database)
manager.register_shutdown_callback(flush_logs)
manager.register_shutdown_callback(send_metrics)

# Callbacks execute automatically during shutdown
# Even if one fails, others still run (error isolation)
```

## Testing

### Unit Testing Interrupts

```python
import pytest
from kaizen.core.autonomy.interrupts import InterruptManager, InterruptMode, InterruptSource

def test_interrupt_request():
    manager = InterruptManager()

    # Request interrupt
    manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test stop"
    )

    # Verify
    assert manager.is_interrupted()
    assert manager._interrupt_reason.mode == InterruptMode.GRACEFUL
    assert manager._interrupt_reason.source == InterruptSource.USER

@pytest.mark.asyncio
async def test_timeout_handler():
    manager = InterruptManager()
    handler = TimeoutInterruptHandler(manager, timeout_seconds=0.1)

    # Start monitoring
    async with anyio.create_task_group() as tg:
        tg.start_soon(handler.start)
        await anyio.sleep(0.15)

    # Should be interrupted
    assert manager.is_interrupted()
    assert manager._interrupt_reason.source == InterruptSource.TIMEOUT
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_interrupt_with_checkpoint():
    storage = FilesystemStorage(base_dir="/tmp/test_checkpoints")
    state_manager = StateManager(storage=storage)
    interrupt_manager = InterruptManager()

    # Create state
    agent_state = AgentState(agent_id="test", step_number=5)

    # Request interrupt
    interrupt_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test"
    )

    # Execute shutdown with checkpoint
    status = await interrupt_manager.execute_shutdown(
        state_manager, agent_state
    )

    # Verify checkpoint created
    assert status.checkpoint_id is not None

    # Verify can load checkpoint
    loaded = await state_manager.load_checkpoint(status.checkpoint_id)
    assert loaded.agent_id == "test"
    assert loaded.status == "interrupted"
```

## Troubleshooting

### Issue: Signal handlers not working

**Problem**: `SIGINT` doesn't trigger interrupt

**Solution**: Ensure handlers are installed before starting work:

```python
manager = InterruptManager()
manager.install_signal_handlers()  # Must call before work starts
```

### Issue: Checkpoint not saved on interrupt

**Problem**: Checkpoint is `None` after interrupt

**Solution**: Always pass both `state_manager` and `agent_state` to `execute_shutdown`:

```python
# Wrong: No checkpoint saved
status = await manager.execute_shutdown()

# Correct: Checkpoint saved
status = await manager.execute_shutdown(state_manager, agent_state)
```

### Issue: Multiple interrupts

**Problem**: Interrupt triggered multiple times

**Solution**: InterruptManager is idempotent - first interrupt wins:

```python
manager.request_interrupt(mode=InterruptMode.GRACEFUL, ...)
manager.request_interrupt(mode=InterruptMode.IMMEDIATE, ...)  # Ignored

# First reason preserved
assert manager._interrupt_reason.mode == InterruptMode.GRACEFUL
```

### Issue: Timeout not triggering

**Problem**: Timeout handler doesn't trigger interrupt after timeout

**Solution**: Ensure timeout monitoring task is started:

```python
# Must use task group to start monitoring
async with anyio.create_task_group() as tg:
    tg.start_soon(handler.start)
    # Work happens here
```

## API Reference

### InterruptManager

```python
class InterruptManager:
    def install_signal_handlers() -> None
    def uninstall_signal_handlers() -> None
    def request_interrupt(mode, source, message, metadata) -> None
    def is_interrupted() -> bool
    async def wait_for_interrupt() -> None
    def register_shutdown_callback(callback: Callable) -> None
    async def execute_shutdown_callbacks() -> None
    async def execute_shutdown(state_manager, agent_state) -> InterruptStatus
    def reset() -> None
```

### TimeoutInterruptHandler

```python
class TimeoutInterruptHandler:
    def __init__(interrupt_manager, timeout_seconds, warning_threshold=0.8)
    async def start() -> None
    async def stop() -> None
    def get_elapsed_time() -> float
    def get_remaining_time() -> float
```

### BudgetInterruptHandler

```python
class BudgetInterruptHandler:
    def __init__(interrupt_manager, budget_usd, warning_threshold=0.8)
    def track_cost(cost_usd: float) -> None
    def get_current_cost() -> float
    def get_remaining_budget() -> float
    def get_budget_usage_percent() -> float
    def reset() -> None
```

## See Also

- [State Persistence Guide](state-persistence-guide.md) - Checkpoint/resume functionality
- [Hooks System Guide](hooks-system-guide.md) - Event-driven extensions
- [ADR-015: Phase 3 Lifecycle Management](../architecture/adr/ADR-015-autonomous-agent-capability-phase-3.md)
