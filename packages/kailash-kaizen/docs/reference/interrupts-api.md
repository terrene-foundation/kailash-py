# Interrupts API Reference

**Version**: 1.0.0
**Module**: `kaizen.core.autonomy.interrupts`
**Purpose**: Graceful agent shutdown with interrupt handling

## Overview

The Interrupts API provides graceful shutdown capabilities for autonomous agents through interrupt signals (Ctrl+C, timeouts, budget limits) with checkpoint preservation. The system ensures agents can be safely interrupted at any time with automatic state saving for resumption.

### Key Features

- **OS Signal Handling**: SIGINT (Ctrl+C), SIGTERM, SIGUSR1 integration
- **Multiple Interrupt Sources**: USER, SIGNAL, TIMEOUT, BUDGET, PROGRAMMATIC
- **Shutdown Modes**: GRACEFUL (finish cycle) vs IMMEDIATE (stop now)
- **Checkpoint Integration**: Automatic state preservation on interrupt
- **Interrupt Propagation**: Parent-to-child agent interrupt coordination
- **Hook Integration**: PRE/POST_INTERRUPT events for observability
- **Handler Architecture**: TimeoutInterruptHandler, BudgetInterruptHandler
- **Thread-Safe**: Works across sync and async contexts

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Interrupt System                         │
│                                                              │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────┐       │
│  │ OS Signals │  │   Timeouts   │  │ Budget Limits │       │
│  │ SIGINT/    │  │ Background   │  │ Cost Tracking │       │
│  │ SIGTERM    │  │ Monitor      │  │ Auto-Trigger  │       │
│  └─────┬──────┘  └──────┬───────┘  └───────┬───────┘       │
│        │                 │                  │               │
│        └─────────────────┼──────────────────┘               │
│                          │                                   │
│                  ┌───────▼─────────┐                         │
│                  │ InterruptManager│                         │
│                  │                 │                         │
│                  │ • request()     │                         │
│                  │ • is_interrupted│                         │
│                  │ • execute_      │                         │
│                  │   shutdown()    │                         │
│                  └────────┬────────┘                         │
│                           │                                   │
│         ┌─────────────────┼─────────────────┐               │
│         │                 │                 │               │
│  ┌──────▼────────┐ ┌─────▼──────┐ ┌────────▼────────┐      │
│  │ HookManager   │ │StateManager│ │ Child Managers  │      │
│  │ PRE/POST      │ │Checkpoint  │ │ Propagate to    │      │
│  │ _INTERRUPT    │ │Saving      │ │ Children        │      │
│  └───────────────┘ └────────────┘ └─────────────────┘      │
│                                                              │
│  ┌───────────────────────────────────────────────┐          │
│  │              InterruptStatus                   │          │
│  │  interrupted: bool                             │          │
│  │  reason: InterruptReason                       │          │
│  │  checkpoint_id: str | None                     │          │
│  └───────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
```

## Core Types

### InterruptMode

**Purpose**: Specifies how to handle interrupt

**Definition**:
```python
from enum import Enum

class InterruptMode(Enum):
    """
    How to handle interrupt.

    GRACEFUL: Finish current step, then checkpoint and stop
    IMMEDIATE: Stop now, checkpoint if possible
    """

    GRACEFUL = "graceful"
    IMMEDIATE = "immediate"
```

**Values**:
- **GRACEFUL**: Complete current autonomous loop cycle, save checkpoint, then stop (recommended)
- **IMMEDIATE**: Stop execution immediately, attempt checkpoint if possible (may be incomplete)

**Usage**:
```python
from kaizen.core.autonomy.interrupts import InterruptMode

# Request graceful shutdown (recommended)
interrupt_manager.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.USER,
    message="User requested shutdown"
)

# Request immediate shutdown (emergency)
interrupt_manager.request_interrupt(
    mode=InterruptMode.IMMEDIATE,
    source=InterruptSource.SIGNAL,
    message="Critical error detected"
)
```

---

### InterruptSource

**Purpose**: Identifies origin of interrupt

**Definition**:
```python
from enum import Enum

class InterruptSource(Enum):
    """
    Source of interrupt.

    SIGNAL: OS signal (SIGINT, SIGTERM, SIGUSR1)
    TIMEOUT: Execution time limit exceeded
    BUDGET: Token/cost budget exceeded
    USER: User requested via control protocol
    PROGRAMMATIC: Code-initiated interrupt (hook, policy)
    """

    SIGNAL = "signal"
    TIMEOUT = "timeout"
    BUDGET = "budget"
    USER = "user"
    PROGRAMMATIC = "programmatic"
```

**Values**:
- **SIGNAL**: OS signal (Ctrl+C = SIGINT, kill = SIGTERM, custom = SIGUSR1)
- **TIMEOUT**: TimeoutInterruptHandler detected execution time limit exceeded
- **BUDGET**: BudgetInterruptHandler detected cost budget exceeded
- **USER**: User-initiated via control protocol or API
- **PROGRAMMATIC**: Hook, policy, or code-initiated interrupt

**Usage**:
```python
from kaizen.core.autonomy.interrupts import InterruptSource, InterruptMode

# Timeout handler triggers interrupt
interrupt_manager.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.TIMEOUT,
    message="Execution timeout exceeded (300s)",
    metadata={"timeout_seconds": 300}
)

# Budget handler triggers interrupt
interrupt_manager.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.BUDGET,
    message="Budget exceeded ($5.00)",
    metadata={"budget_usd": 5.0, "spent_usd": 5.12}
)
```

---

### InterruptReason

**Purpose**: Complete interrupt context with metadata

**Definition**:
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass
class InterruptReason:
    """
    Details about why interrupt occurred.

    Captures complete context for debugging and auditing.
    """

    source: InterruptSource
    mode: InterruptMode
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Human-readable string representation"""
        return (
            f"Interrupt({self.source.value}, {self.mode.value}): "
            f"{self.message} at {self.timestamp.isoformat()}"
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to JSON-serializable dictionary.

        Returns:
            Dictionary with enum values as strings
        """
        return {
            "source": self.source.value,
            "mode": self.mode.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
```

**Fields**:
- **source** (`InterruptSource`): Origin of interrupt
- **mode** (`InterruptMode`): How interrupt should be handled
- **message** (`str`): Human-readable reason
- **timestamp** (`datetime`): When interrupt was requested (UTC)
- **metadata** (`dict[str, Any]`): Additional context (signal number, budget details, etc.)

**Methods**:
- **`__str__() -> str`**: Human-readable representation
- **`to_dict() -> dict[str, Any]`**: JSON-serializable dictionary

**Usage**:
```python
from kaizen.core.autonomy.interrupts import InterruptReason, InterruptSource, InterruptMode

# Create interrupt reason
reason = InterruptReason(
    source=InterruptSource.TIMEOUT,
    mode=InterruptMode.GRACEFUL,
    message="Execution timeout exceeded (300s)",
    metadata={"timeout_seconds": 300, "elapsed_seconds": 305}
)

# Human-readable output
print(reason)
# Output: Interrupt(timeout, graceful): Execution timeout exceeded (300s) at 2025-10-25T12:34:56

# Serialize for logging
import json
print(json.dumps(reason.to_dict(), indent=2))
# Output:
# {
#   "source": "timeout",
#   "mode": "graceful",
#   "message": "Execution timeout exceeded (300s)",
#   "timestamp": "2025-10-25T12:34:56",
#   "metadata": {
#     "timeout_seconds": 300,
#     "elapsed_seconds": 305
#   }
# }
```

---

### InterruptStatus

**Purpose**: Shutdown status with checkpoint information

**Definition**:
```python
from dataclasses import dataclass

@dataclass
class InterruptStatus:
    """
    Current interrupt status after shutdown.

    Includes checkpoint information for resume capability.
    """

    interrupted: bool
    reason: InterruptReason | None = None
    checkpoint_id: str | None = None  # Checkpoint saved before interrupt

    def can_resume(self) -> bool:
        """Check if execution can be resumed from checkpoint"""
        return self.checkpoint_id is not None
```

**Fields**:
- **interrupted** (`bool`): Whether shutdown was due to interrupt (vs normal completion)
- **reason** (`InterruptReason | None`): Why interrupt occurred
- **checkpoint_id** (`str | None`): Checkpoint saved during shutdown (for resumption)

**Methods**:
- **`can_resume() -> bool`**: Returns `True` if checkpoint was saved and execution can be resumed

**Usage**:
```python
from kaizen.core.autonomy.interrupts import InterruptManager

# Execute shutdown
status = await interrupt_manager.execute_shutdown(state_manager, agent_state)

# Check if resumption is possible
if status.can_resume():
    print(f"Checkpoint saved: {status.checkpoint_id}")
    print("Run again to resume from where you left off")
else:
    print("No checkpoint saved - execution must restart from beginning")

# Access interrupt details
if status.reason:
    print(f"Interrupted by: {status.reason.source.value}")
    print(f"Mode: {status.reason.mode.value}")
    print(f"Message: {status.reason.message}")
```

---

### InterruptedError

**Purpose**: Exception raised when agent execution is interrupted

**Definition**:
```python
class InterruptedError(Exception):
    """
    Exception raised when agent execution is interrupted.

    Raised when an interrupt is detected during autonomous loop execution.
    Contains the interrupt reason for debugging and recovery.
    """

    def __init__(self, message: str, reason: InterruptReason | None = None):
        super().__init__(message)
        self.reason = reason
```

**Attributes**:
- **reason** (`InterruptReason | None`): Full interrupt context

**Usage**:
```python
from kaizen.core.autonomy.interrupts import InterruptedError

try:
    result = await agent.run_autonomous(task="Long running task")
except InterruptedError as e:
    print(f"Agent interrupted: {e}")

    # Access interrupt details
    if e.reason:
        print(f"Source: {e.reason.source.value}")
        print(f"Mode: {e.reason.mode.value}")
        print(f"Message: {e.reason.message}")
        print(f"Timestamp: {e.reason.timestamp}")

        # Check for checkpoint
        checkpoint_id = e.reason.metadata.get("checkpoint_id")
        if checkpoint_id:
            print(f"Checkpoint saved: {checkpoint_id}")
```

---

## InterruptManager

**Purpose**: Orchestrates interrupt signals and graceful shutdown

**Location**: `kaizen.core.autonomy.interrupts.manager`

**Definition**:
```python
import logging
import signal
from typing import Any, Awaitable, Callable

import anyio

from .types import InterruptMode, InterruptReason, InterruptSource, InterruptStatus

class InterruptManager:
    """
    Manages interrupt signals and graceful shutdown.

    Handles OS signals (SIGINT, SIGTERM), programmatic interrupts,
    and coordinates shutdown sequence with checkpointing.
    """

    def __init__(self):
        """Initialize interrupt manager"""
        self._interrupted = anyio.Event()
        self._interrupt_reason: InterruptReason | None = None
        self._shutdown_callbacks: list[Callable[[], Awaitable[None]]] = []
        self._signal_handlers_installed = False
        self._original_handlers: dict[int, Any] = {}
        self._child_managers: list["InterruptManager"] = []
        self.hook_manager: Any = None  # Optional HookManager
```

### Methods

#### install_signal_handlers()

**Purpose**: Install OS signal handlers (SIGINT, SIGTERM, SIGUSR1)

**Signature**:
```python
def install_signal_handlers(self) -> None:
    """
    Install OS signal handlers (SIGINT, SIGTERM, SIGUSR1).

    Idempotent - can be called multiple times safely.
    """
```

**Behavior**:
- Installs handler for SIGINT (Ctrl+C)
- Installs handler for SIGTERM (kill command)
- Attempts to install handler for SIGUSR1 (custom signal, Unix only)
- Stores original handlers for restoration
- Idempotent - multiple calls are safe

**Example**:
```python
from kaizen.core.autonomy.interrupts import InterruptManager

# Create manager
interrupt_manager = InterruptManager()

# Install signal handlers
interrupt_manager.install_signal_handlers()

# Now Ctrl+C will trigger graceful shutdown
# Original handlers will be restored on cleanup
```

---

#### uninstall_signal_handlers()

**Purpose**: Restore original signal handlers

**Signature**:
```python
def uninstall_signal_handlers(self) -> None:
    """
    Restore original signal handlers.

    Call during cleanup or testing.
    """
```

**Example**:
```python
# Cleanup after execution
interrupt_manager.uninstall_signal_handlers()
```

---

#### request_interrupt()

**Purpose**: Request interrupt (thread-safe)

**Signature**:
```python
def request_interrupt(
    self,
    mode: InterruptMode,
    source: InterruptSource,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Request interrupt (thread-safe).

    Can be called from signal handlers, async code, or other threads.

    Args:
        mode: How to handle interrupt (GRACEFUL or IMMEDIATE)
        source: Source of interrupt
        message: Human-readable reason
        metadata: Additional context
    """
```

**Args**:
- **mode** (`InterruptMode`): GRACEFUL or IMMEDIATE
- **source** (`InterruptSource`): Origin of interrupt
- **message** (`str`): Human-readable reason
- **metadata** (`dict[str, Any] | None`): Additional context

**Notes**:
- Thread-safe - can be called from signal handlers
- Idempotent - duplicate requests are ignored
- Sets internal `anyio.Event` for async waiting

**Example**:
```python
# User-initiated shutdown
interrupt_manager.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.USER,
    message="User requested shutdown",
    metadata={"user_id": "user_123"}
)

# Timeout-triggered shutdown
interrupt_manager.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.TIMEOUT,
    message="Execution timeout exceeded (300s)",
    metadata={"timeout_seconds": 300}
)
```

---

#### is_interrupted()

**Purpose**: Check if interrupt has been requested (non-blocking)

**Signature**:
```python
def is_interrupted(self) -> bool:
    """
    Check if interrupt has been requested (non-blocking).

    Returns:
        True if interrupt requested
    """
```

**Example**:
```python
# Check in autonomous loop
async def autonomous_loop():
    while not interrupt_manager.is_interrupted():
        # Execute cycle
        await execute_cycle()

        # Check again
        if interrupt_manager.is_interrupted():
            break
```

---

#### wait_for_interrupt()

**Purpose**: Wait for interrupt signal (blocking)

**Signature**:
```python
async def wait_for_interrupt(
    self, timeout: float | None = None
) -> InterruptReason | None:
    """
    Wait for interrupt signal (blocking).

    Args:
        timeout: Maximum time to wait (None = wait forever)

    Returns:
        InterruptReason if interrupted, None if timeout
    """
```

**Args**:
- **timeout** (`float | None`): Maximum wait time in seconds (None = wait forever)

**Returns**:
- `InterruptReason` if interrupted
- `None` if timeout expired

**Example**:
```python
# Wait for interrupt with 60s timeout
reason = await interrupt_manager.wait_for_interrupt(timeout=60.0)

if reason:
    print(f"Interrupted: {reason.message}")
else:
    print("No interrupt within 60s")
```

---

#### register_shutdown_callback()

**Purpose**: Register callback to run before shutdown

**Signature**:
```python
def register_shutdown_callback(
    self, callback: Callable[[], Awaitable[None]]
) -> None:
    """
    Register callback to run before shutdown.

    Callbacks are executed in registration order during shutdown.

    Args:
        callback: Async function to call during shutdown
    """
```

**Args**:
- **callback** (`Callable[[], Awaitable[None]]`): Async function to execute

**Notes**:
- Callbacks execute in registration order
- Exceptions in callbacks are logged but don't prevent shutdown
- Useful for cleanup (close connections, flush logs, etc.)

**Example**:
```python
# Register cleanup callbacks
async def close_database():
    await db.close()
    print("Database closed")

async def flush_logs():
    await log_handler.flush()
    print("Logs flushed")

interrupt_manager.register_shutdown_callback(close_database)
interrupt_manager.register_shutdown_callback(flush_logs)

# Both will execute on shutdown
```

---

#### execute_shutdown()

**Purpose**: Execute graceful shutdown sequence

**Signature**:
```python
async def execute_shutdown(
    self, state_manager: Any = None, agent_state: Any = None
) -> InterruptStatus:
    """
    Execute graceful shutdown sequence.

    1. Execute shutdown callbacks
    2. Save checkpoint (if state_manager provided)
    3. Return interrupt status

    Args:
        state_manager: Optional StateManager for checkpointing
        agent_state: Optional AgentState to checkpoint

    Returns:
        InterruptStatus with checkpoint information
    """
```

**Args**:
- **state_manager** (`StateManager | None`): StateManager for checkpoint saving
- **agent_state** (`AgentState | None`): Agent state to save

**Returns**:
- `InterruptStatus` with checkpoint ID (if saved)

**Example**:
```python
# Execute shutdown with checkpoint
status = await interrupt_manager.execute_shutdown(
    state_manager=state_manager,
    agent_state=current_agent_state
)

if status.can_resume():
    print(f"Checkpoint saved: {status.checkpoint_id}")
else:
    print("No checkpoint saved")
```

---

#### propagate_to_children()

**Purpose**: Propagate interrupt to child managers

**Signature**:
```python
def propagate_to_children(self) -> None:
    """
    Propagate interrupt to all child managers.

    Interrupts all tracked child managers with same mode and updated message.
    Safe to call even if no children tracked.
    """
```

**Notes**:
- Automatically propagates parent's interrupt to all children
- Updates message to indicate propagation
- Skips children that are already interrupted

**Example**:
```python
# Parent agent with child workers
parent_interrupt = InterruptManager()
worker1_interrupt = InterruptManager()
worker2_interrupt = InterruptManager()

# Track children
parent_interrupt.add_child_manager(worker1_interrupt)
parent_interrupt.add_child_manager(worker2_interrupt)

# Parent interrupted
parent_interrupt.request_interrupt(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.USER,
    message="User Ctrl+C"
)

# Propagate to children
parent_interrupt.propagate_to_children()

# worker1 and worker2 are now interrupted
assert worker1_interrupt.is_interrupted()
assert worker2_interrupt.is_interrupted()
```

---

#### request_interrupt_with_hooks()

**Purpose**: Request interrupt with PRE_INTERRUPT hook support

**Signature**:
```python
async def request_interrupt_with_hooks(
    self,
    mode: InterruptMode,
    source: InterruptSource,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """
    Request interrupt with PRE_INTERRUPT hook support.

    Triggers PRE_INTERRUPT hooks before setting interrupt. Hooks can block
    the interrupt by returning success=False.

    Args:
        mode: How to handle interrupt (GRACEFUL or IMMEDIATE)
        source: Source of interrupt
        message: Human-readable reason
        metadata: Additional context

    Returns:
        True if interrupt was set, False if blocked by hook
    """
```

**Returns**:
- `True` if interrupt was set successfully
- `False` if blocked by PRE_INTERRUPT hook

**Example**:
```python
# Hook can block critical operations
result = await interrupt_manager.request_interrupt_with_hooks(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.USER,
    message="User requested shutdown"
)

if result:
    print("Interrupt set successfully")
else:
    print("Interrupt blocked by hook (critical operation in progress)")
```

---

#### execute_shutdown_with_hooks()

**Purpose**: Execute shutdown with POST_INTERRUPT hook support

**Signature**:
```python
async def execute_shutdown_with_hooks(
    self, state_manager: Any = None, agent_state: Any = None
) -> InterruptStatus:
    """
    Execute shutdown with POST_INTERRUPT hook support.

    Triggers POST_INTERRUPT hooks after shutdown completion.

    Args:
        state_manager: Optional StateManager for checkpointing
        agent_state: Optional AgentState to checkpoint

    Returns:
        InterruptStatus with checkpoint information
    """
```

**Example**:
```python
# Execute shutdown with POST_INTERRUPT hooks
status = await interrupt_manager.execute_shutdown_with_hooks(
    state_manager=state_manager,
    agent_state=current_agent_state
)

# POST_INTERRUPT hooks have been triggered
# Can be used for audit logging, metrics, alerts
```

---

## Interrupt Handlers

### TimeoutInterruptHandler

**Purpose**: Automatically interrupt after time limit

**Location**: `kaizen.core.autonomy.interrupts.handlers.timeout`

**Definition**:
```python
import logging
import anyio
from ..manager import InterruptManager
from ..types import InterruptMode, InterruptSource

class TimeoutInterruptHandler:
    """
    Automatically interrupt after time limit.

    Monitors execution time and triggers GRACEFUL interrupt when timeout exceeded.
    """

    def __init__(
        self,
        interrupt_manager: InterruptManager,
        timeout_seconds: float,
        warning_threshold: float = 0.8,
    ):
        """
        Initialize timeout handler.

        Args:
            interrupt_manager: InterruptManager to trigger interrupts
            timeout_seconds: Maximum execution time
            warning_threshold: Fraction of timeout at which to warn (0.8 = 80%)
        """
        self.interrupt_manager = interrupt_manager
        self.timeout_seconds = timeout_seconds
        self.warning_threshold = warning_threshold
        self._cancel_scope: anyio.CancelScope | None = None
        self._task_group: anyio.abc.TaskGroup | None = None
        self._warned = False

    async def start(self) -> None:
        """
        Start timeout monitoring.

        Creates background task that will trigger interrupt after timeout.
        """

    async def stop(self) -> None:
        """
        Stop timeout monitoring.

        Cancels background task if running.
        """

    def get_elapsed_time(self) -> float:
        """
        Get elapsed time since start.

        Returns:
            Elapsed time in seconds (approximation)
        """

    def get_remaining_time(self) -> float:
        """
        Get remaining time before timeout.

        Returns:
            Remaining time in seconds
        """
```

**Constructor Args**:
- **interrupt_manager** (`InterruptManager`): Manager to trigger interrupts
- **timeout_seconds** (`float`): Maximum execution time in seconds
- **warning_threshold** (`float`): Fraction at which to warn (default: 0.8 = 80%)

**Methods**:
- **`start() -> None`**: Start background monitoring task
- **`stop() -> None`**: Stop monitoring and cancel background task
- **`get_elapsed_time() -> float`**: Get elapsed time since start
- **`get_remaining_time() -> float`**: Get remaining time before timeout

**Example**:
```python
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.interrupts.handlers.timeout import TimeoutInterruptHandler

# Create interrupt manager
interrupt_manager = InterruptManager()

# Create timeout handler (300s = 5 minutes)
timeout_handler = TimeoutInterruptHandler(
    interrupt_manager=interrupt_manager,
    timeout_seconds=300.0,
    warning_threshold=0.8  # Warn at 240s (80%)
)

# Start monitoring
await timeout_handler.start()

# Execute long-running task
try:
    result = await execute_task()
finally:
    # Stop monitoring
    await timeout_handler.stop()

# Check if interrupted
if interrupt_manager.is_interrupted():
    reason = interrupt_manager.get_interrupt_reason()
    print(f"Timeout: {reason.message}")
```

---

### BudgetInterruptHandler

**Purpose**: Automatically interrupt when cost budget exceeded

**Location**: `kaizen.core.autonomy.interrupts.handlers.budget`

**Definition**:
```python
import logging
from ..manager import InterruptManager
from ..types import InterruptMode, InterruptSource

class BudgetInterruptHandler:
    """
    Automatically interrupt when budget exceeded.

    Tracks cumulative cost and triggers GRACEFUL interrupt at budget limit.
    """

    def __init__(
        self,
        interrupt_manager: InterruptManager,
        budget_usd: float,
        warning_threshold: float = 0.8,
    ):
        """
        Initialize budget handler.

        Args:
            interrupt_manager: InterruptManager to trigger interrupts
            budget_usd: Maximum cost budget in USD
            warning_threshold: Fraction of budget at which to warn (0.8 = 80%)
        """
        self.interrupt_manager = interrupt_manager
        self.budget_usd = budget_usd
        self.warning_threshold = warning_threshold
        self._current_cost_usd = 0.0
        self._warned = False

    def track_cost(self, cost_usd: float) -> None:
        """
        Track cost from operation.

        Call this after each operation that incurs cost (LLM call, tool use).

        Args:
            cost_usd: Cost of operation in USD
        """

    def get_current_cost(self) -> float:
        """
        Get current cost.

        Returns:
            Current cost in USD
        """

    def get_remaining_budget(self) -> float:
        """
        Get remaining budget.

        Returns:
            Remaining budget in USD (may be negative if exceeded)
        """

    def get_budget_usage_percent(self) -> float:
        """
        Get budget usage percentage.

        Returns:
            Percentage of budget used (0-100+)
        """

    def reset(self) -> None:
        """
        Reset cost tracking.

        Use when starting new execution or after checkpoint.
        """
```

**Constructor Args**:
- **interrupt_manager** (`InterruptManager`): Manager to trigger interrupts
- **budget_usd** (`float`): Maximum cost budget in USD
- **warning_threshold** (`float`): Fraction at which to warn (default: 0.8 = 80%)

**Methods**:
- **`track_cost(cost_usd: float) -> None`**: Track cost from operation (LLM call, tool use)
- **`get_current_cost() -> float`**: Get total cost spent
- **`get_remaining_budget() -> float`**: Get remaining budget (may be negative)
- **`get_budget_usage_percent() -> float`**: Get usage percentage (0-100+)
- **`reset() -> None`**: Reset cost tracking

**Example**:
```python
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.interrupts.handlers.budget import BudgetInterruptHandler

# Create interrupt manager
interrupt_manager = InterruptManager()

# Create budget handler ($5.00 limit)
budget_handler = BudgetInterruptHandler(
    interrupt_manager=interrupt_manager,
    budget_usd=5.0,
    warning_threshold=0.8  # Warn at $4.00 (80%)
)

# Track costs during execution
async def execute_with_budget():
    # LLM call
    result1 = await llm.call("prompt1")
    budget_handler.track_cost(0.12)  # $0.12

    # Another LLM call
    result2 = await llm.call("prompt2")
    budget_handler.track_cost(0.08)  # $0.08

    # Check status
    print(f"Spent: ${budget_handler.get_current_cost():.2f}")
    print(f"Remaining: ${budget_handler.get_remaining_budget():.2f}")
    print(f"Usage: {budget_handler.get_budget_usage_percent():.1f}%")

    # Continue until budget exceeded...
    # Interrupt will trigger automatically at $5.00

# Execute
await execute_with_budget()

# Check if interrupted
if interrupt_manager.is_interrupted():
    reason = interrupt_manager.get_interrupt_reason()
    print(f"Budget exceeded: {reason.message}")
```

---

## Integration Examples

### Basic Ctrl+C Handling

**Pattern**: Handle Ctrl+C gracefully with checkpoint saving

```python
import asyncio
from kaizen.core.autonomy.interrupts import InterruptManager, InterruptMode, InterruptSource
from kaizen.core.autonomy.state import StateManager, FilesystemStorage

async def main():
    # Create interrupt manager
    interrupt_manager = InterruptManager()

    # Install signal handlers
    interrupt_manager.install_signal_handlers()

    # Create state manager for checkpointing
    storage = FilesystemStorage(base_dir="./checkpoints")
    state_manager = StateManager(storage=storage)

    # Execute task
    try:
        result = await execute_long_task(interrupt_manager)
        print("Task completed successfully")
    except KeyboardInterrupt:
        # Ctrl+C pressed
        print("\nCtrl+C detected! Initiating graceful shutdown...")

        # Execute shutdown
        status = await interrupt_manager.execute_shutdown(
            state_manager=state_manager,
            agent_state=current_state
        )

        if status.can_resume():
            print(f"Checkpoint saved: {status.checkpoint_id}")
            print("Run again to resume from where you left off")
    finally:
        # Cleanup
        interrupt_manager.uninstall_signal_handlers()

async def execute_long_task(interrupt_manager):
    for i in range(100):
        if interrupt_manager.is_interrupted():
            print(f"Interrupted at step {i}")
            break

        # Simulate work
        await asyncio.sleep(1)
        print(f"Step {i+1}/100")

if __name__ == "__main__":
    asyncio.run(main())
```

**Output (after Ctrl+C)**:
```
Step 1/100
Step 2/100
^C
Ctrl+C detected! Initiating graceful shutdown...
Checkpoint saved: ckpt_a1b2c3d4
Run again to resume from where you left off
```

---

### Timeout-Based Interrupts

**Pattern**: Automatically interrupt after time limit

```python
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.interrupts.handlers.timeout import TimeoutInterruptHandler

async def main():
    # Create interrupt manager
    interrupt_manager = InterruptManager()

    # Create timeout handler (5 minutes)
    timeout_handler = TimeoutInterruptHandler(
        interrupt_manager=interrupt_manager,
        timeout_seconds=300.0,
        warning_threshold=0.8  # Warn at 4 minutes
    )

    # Start monitoring
    await timeout_handler.start()

    try:
        # Execute task
        result = await execute_task(interrupt_manager)

        if interrupt_manager.is_interrupted():
            reason = interrupt_manager.get_interrupt_reason()
            print(f"Timeout: {reason.message}")
        else:
            print("Task completed within timeout")
    finally:
        # Stop monitoring
        await timeout_handler.stop()

async def execute_task(interrupt_manager):
    for i in range(1000):
        if interrupt_manager.is_interrupted():
            break

        await asyncio.sleep(1)
```

---

### Budget-Based Interrupts

**Pattern**: Automatically interrupt when cost budget exceeded

```python
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.interrupts.handlers.budget import BudgetInterruptHandler

async def main():
    # Create interrupt manager
    interrupt_manager = InterruptManager()

    # Create budget handler ($10.00 limit)
    budget_handler = BudgetInterruptHandler(
        interrupt_manager=interrupt_manager,
        budget_usd=10.0,
        warning_threshold=0.8  # Warn at $8.00
    )

    # Execute task with budget tracking
    try:
        result = await execute_with_budget(interrupt_manager, budget_handler)

        if interrupt_manager.is_interrupted():
            reason = interrupt_manager.get_interrupt_reason()
            print(f"Budget exceeded: {reason.message}")
            print(f"Spent: ${budget_handler.get_current_cost():.2f}")
        else:
            print("Task completed within budget")
    finally:
        print(f"Final cost: ${budget_handler.get_current_cost():.2f}")

async def execute_with_budget(interrupt_manager, budget_handler):
    for i in range(100):
        if interrupt_manager.is_interrupted():
            break

        # Simulate LLM call with cost
        result = await llm_call()
        budget_handler.track_cost(0.15)  # Track $0.15 per call

        print(f"Step {i+1}: ${budget_handler.get_current_cost():.2f} / $10.00")
```

---

### Parent-Child Interrupt Propagation

**Pattern**: Propagate interrupt from parent to child agents

```python
from kaizen.core.autonomy.interrupts import InterruptManager, InterruptMode, InterruptSource

async def main():
    # Create parent interrupt manager
    parent_interrupt = InterruptManager()
    parent_interrupt.install_signal_handlers()

    # Create child workers
    worker1_interrupt = InterruptManager()
    worker2_interrupt = InterruptManager()

    # Track children
    parent_interrupt.add_child_manager(worker1_interrupt)
    parent_interrupt.add_child_manager(worker2_interrupt)

    # Execute parent task
    try:
        # Start workers
        worker1_task = asyncio.create_task(
            execute_worker(worker1_interrupt, "Worker 1")
        )
        worker2_task = asyncio.create_task(
            execute_worker(worker2_interrupt, "Worker 2")
        )

        # Parent loop
        for i in range(100):
            if parent_interrupt.is_interrupted():
                print("Parent interrupted - propagating to children...")
                parent_interrupt.propagate_to_children()
                break

            await asyncio.sleep(1)

        # Wait for workers to finish
        await asyncio.gather(worker1_task, worker2_task)

    finally:
        parent_interrupt.uninstall_signal_handlers()

async def execute_worker(interrupt_manager, name):
    for i in range(100):
        if interrupt_manager.is_interrupted():
            reason = interrupt_manager.get_interrupt_reason()
            print(f"{name} interrupted: {reason.message}")
            break

        await asyncio.sleep(0.5)
        print(f"{name} - Step {i+1}")
```

**Output (after Ctrl+C)**:
```
Worker 1 - Step 1
Worker 2 - Step 1
Worker 1 - Step 2
^C
Parent interrupted - propagating to children...
Worker 1 interrupted: Propagated from parent: User requested graceful shutdown (Ctrl+C)
Worker 2 interrupted: Propagated from parent: User requested graceful shutdown (Ctrl+C)
```

---

### Hook Integration

**Pattern**: Use hooks for interrupt observability

```python
from kaizen.core.autonomy.hooks import HookManager, HookEvent, HookContext, HookResult
from kaizen.core.autonomy.interrupts import InterruptManager

# Define interrupt tracking hook
async def track_interrupt_hook(context: HookContext) -> HookResult:
    """Track interrupt events for audit logging."""
    import json
    from datetime import datetime

    # Extract interrupt data
    interrupt_data = context.data

    # Log to audit file
    with open("interrupt_audit.jsonl", "a") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "event": "interrupt",
            "agent_id": context.agent_id,
            "source": interrupt_data.get("interrupt_source"),
            "mode": interrupt_data.get("interrupt_mode"),
            "message": interrupt_data.get("interrupt_message")
        }, f)
        f.write("\n")

    return HookResult(success=True)

# Setup
hook_manager = HookManager()
hook_manager.register(HookEvent.PRE_INTERRUPT, track_interrupt_hook)

interrupt_manager = InterruptManager()
interrupt_manager.hook_manager = hook_manager

# Request interrupt with hooks
result = await interrupt_manager.request_interrupt_with_hooks(
    mode=InterruptMode.GRACEFUL,
    source=InterruptSource.USER,
    message="User requested shutdown"
)

# Hook was executed - check audit log
with open("interrupt_audit.jsonl") as f:
    print(f.read())
```

---

## Testing

### Unit Tests

**Test interrupt request and status**:

```python
import pytest
from kaizen.core.autonomy.interrupts import (
    InterruptManager,
    InterruptMode,
    InterruptSource,
    InterruptReason,
)

@pytest.mark.asyncio
async def test_interrupt_request():
    """Test basic interrupt request."""
    manager = InterruptManager()

    # Initially not interrupted
    assert not manager.is_interrupted()

    # Request interrupt
    manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test interrupt"
    )

    # Now interrupted
    assert manager.is_interrupted()

    # Get reason
    reason = manager.get_interrupt_reason()
    assert reason is not None
    assert reason.source == InterruptSource.USER
    assert reason.mode == InterruptMode.GRACEFUL
    assert reason.message == "Test interrupt"

@pytest.mark.asyncio
async def test_duplicate_interrupt_ignored():
    """Test that duplicate interrupts are ignored."""
    manager = InterruptManager()

    # First interrupt
    manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="First"
    )

    # Second interrupt (should be ignored)
    manager.request_interrupt(
        mode=InterruptMode.IMMEDIATE,
        source=InterruptSource.TIMEOUT,
        message="Second"
    )

    # Should keep first reason
    reason = manager.get_interrupt_reason()
    assert reason.message == "First"
```

---

### Integration Tests

**Test timeout handler integration**:

```python
import pytest
import asyncio
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.interrupts.handlers.timeout import TimeoutInterruptHandler

@pytest.mark.asyncio
async def test_timeout_handler_triggers_interrupt():
    """Test timeout handler triggers interrupt."""
    manager = InterruptManager()

    # Create timeout handler (2 seconds)
    handler = TimeoutInterruptHandler(
        interrupt_manager=manager,
        timeout_seconds=2.0,
        warning_threshold=0.5  # Warn at 1s
    )

    # Start monitoring
    await handler.start()

    # Wait for timeout
    await asyncio.sleep(2.5)

    # Should be interrupted
    assert manager.is_interrupted()

    # Check reason
    reason = manager.get_interrupt_reason()
    assert reason.source == InterruptSource.TIMEOUT
    assert "timeout exceeded" in reason.message.lower()

    # Cleanup
    await handler.stop()
```

---

### E2E Tests

**Test full interrupt workflow with checkpoint**:

```python
import pytest
import tempfile
from pathlib import Path
from kaizen.core.autonomy.interrupts import InterruptManager, InterruptMode, InterruptSource
from kaizen.core.autonomy.state import StateManager, AgentState, FilesystemStorage

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_interrupt_with_checkpoint_preservation():
    """Test interrupt preserves checkpoint for resumption."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create interrupt manager
        interrupt_manager = InterruptManager()

        # Create state manager
        storage = FilesystemStorage(base_dir=tmpdir)
        state_manager = StateManager(storage=storage)

        # Create agent state
        agent_state = AgentState(
            agent_id="test_agent",
            step_number=42,
            status="running",
            conversation_history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"}
            ]
        )

        # Request interrupt
        interrupt_manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test interrupt"
        )

        # Execute shutdown
        status = await interrupt_manager.execute_shutdown(
            state_manager=state_manager,
            agent_state=agent_state
        )

        # Verify checkpoint saved
        assert status.interrupted
        assert status.can_resume()
        assert status.checkpoint_id is not None

        # Verify reason
        assert status.reason.source == InterruptSource.USER
        assert status.reason.mode == InterruptMode.GRACEFUL

        # Load checkpoint
        restored_state = await state_manager.load_checkpoint(status.checkpoint_id)

        # Verify state preserved
        assert restored_state.agent_id == "test_agent"
        assert restored_state.step_number == 42
        assert restored_state.status == "interrupted"
        assert len(restored_state.conversation_history) == 2

        # Verify interrupt metadata
        assert "interrupt_reason" in restored_state.metadata
        interrupt_data = restored_state.metadata["interrupt_reason"]
        assert interrupt_data["source"] == "user"
        assert interrupt_data["mode"] == "graceful"
```

---

## Production Patterns

### Double Ctrl+C Pattern

**Pattern**: First Ctrl+C = graceful, second Ctrl+C = immediate

```python
import signal
from kaizen.core.autonomy.interrupts import InterruptManager, InterruptMode, InterruptSource

def setup_signal_handlers(interrupt_manager: InterruptManager) -> None:
    """Setup signal handlers with double Ctrl+C pattern."""

    def sigint_handler(signum: int, frame):
        """Handle SIGINT (Ctrl+C)."""
        if interrupt_manager.is_interrupted():
            # Second Ctrl+C - immediate shutdown
            print("\n⚠️  Second Ctrl+C! Immediate shutdown...\n")
            interrupt_manager.request_interrupt(
                mode=InterruptMode.IMMEDIATE,
                source=InterruptSource.SIGNAL,
                message="User requested immediate shutdown (double Ctrl+C)",
                metadata={"signal": signum, "double_ctrl_c": True}
            )
        else:
            # First Ctrl+C - graceful shutdown
            print("\n⚠️  Ctrl+C detected! Initiating graceful shutdown...")
            print("   Press Ctrl+C again for immediate shutdown.\n")
            interrupt_manager.request_interrupt(
                mode=InterruptMode.GRACEFUL,
                source=InterruptSource.SIGNAL,
                message="User requested graceful shutdown (Ctrl+C)",
                metadata={"signal": signum}
            )

    signal.signal(signal.SIGINT, sigint_handler)
```

---

### Shutdown Callbacks for Cleanup

**Pattern**: Register cleanup callbacks to run before shutdown

```python
from kaizen.core.autonomy.interrupts import InterruptManager

async def setup_shutdown_callbacks(interrupt_manager: InterruptManager):
    """Register cleanup callbacks."""

    # Close database connections
    async def close_database():
        await db.close()
        print("Database connections closed")

    # Flush logs
    async def flush_logs():
        await log_handler.flush()
        print("Logs flushed")

    # Send shutdown notification
    async def notify_shutdown():
        await notification_service.send("Agent shutting down")
        print("Shutdown notification sent")

    # Register callbacks (execute in order)
    interrupt_manager.register_shutdown_callback(close_database)
    interrupt_manager.register_shutdown_callback(flush_logs)
    interrupt_manager.register_shutdown_callback(notify_shutdown)
```

---

### Combined Timeout and Budget Limits

**Pattern**: Use both timeout and budget handlers

```python
from kaizen.core.autonomy.interrupts import InterruptManager
from kaizen.core.autonomy.interrupts.handlers.timeout import TimeoutInterruptHandler
from kaizen.core.autonomy.interrupts.handlers.budget import BudgetInterruptHandler

async def execute_with_limits():
    """Execute with both timeout and budget limits."""
    interrupt_manager = InterruptManager()

    # Create timeout handler (10 minutes)
    timeout_handler = TimeoutInterruptHandler(
        interrupt_manager=interrupt_manager,
        timeout_seconds=600.0
    )

    # Create budget handler ($20.00)
    budget_handler = BudgetInterruptHandler(
        interrupt_manager=interrupt_manager,
        budget_usd=20.0
    )

    # Start monitoring
    await timeout_handler.start()

    try:
        # Execute task
        for i in range(1000):
            if interrupt_manager.is_interrupted():
                reason = interrupt_manager.get_interrupt_reason()

                if reason.source == InterruptSource.TIMEOUT:
                    print(f"Stopped by timeout: {reason.message}")
                elif reason.source == InterruptSource.BUDGET:
                    print(f"Stopped by budget: {reason.message}")

                break

            # Simulate work with cost
            await llm_call()
            budget_handler.track_cost(0.05)

            await asyncio.sleep(1)

    finally:
        await timeout_handler.stop()

        # Report final status
        print(f"Time elapsed: {timeout_handler.get_elapsed_time():.1f}s")
        print(f"Budget spent: ${budget_handler.get_current_cost():.2f}")
```

---

## Related Documentation

- **[Checkpoint API Reference](./checkpoint-api.md)**: State persistence for resumption
- **[Memory API Reference](./memory-api.md)**: 3-tier memory system
- **[Hooks API Reference](./observability-api.md)**: Event-driven observability with PRE/POST_INTERRUPT hooks
- **[BaseAgent Architecture](../guides/baseagent-architecture.md)**: Autonomous agent integration

---

## Version History

**v1.0.0** (2025-10-25):
- Initial release with InterruptManager, TimeoutInterruptHandler, BudgetInterruptHandler
- OS signal handling (SIGINT, SIGTERM, SIGUSR1)
- Checkpoint integration for state preservation
- Parent-child interrupt propagation
- Hook integration (PRE/POST_INTERRUPT events)
- Thread-safe interrupt requests
- Graceful and immediate shutdown modes

---

**Complete Interrupts API documentation** | Production-ready graceful shutdown with checkpoint preservation
