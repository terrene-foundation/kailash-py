# ADR-016: Interrupt Mechanism Design

## Status
**Implemented** - Completed 2025-10-29 (Phase 3, Week 28-29)

**Priority**: P1 - HIGH (enables user control over autonomous execution)

**Implementation Evidence**:
- 97/97 tests passing (86 unit + 11 integration) - 100% pass rate
- Full BaseAutonomousAgent integration at src/kaizen/agents/autonomous/base.py:179,234,238-240,356-357,386,807-890
- 4 working examples in examples/autonomy/interrupts/
- 558 lines of user documentation in docs/guides/interrupt-mechanism-guide.md
- All 8 functional requirements met (FR-1 through FR-8)

## Context

Kaizen agents currently have **no graceful interrupt mechanism**. Users cannot stop long-running agents without killing the process:

**Critical Problems**:
- **No user control**: Cannot stop agent mid-execution (must kill process)
- **Data loss**: Killing process loses all progress (no checkpoint saved)
- **No graceful shutdown**: Cannot finish current step before stopping
- **No feedback loop**: Cannot modify agent behavior mid-execution
- **Resource waste**: Cannot interrupt runaway agents (stuck in loops, excessive API calls)

**Production Impact**:
- Users afraid to start long-running agents (can't stop them safely)
- Agent bugs (infinite loops, excessive API calls) require process kill = data loss
- No way to implement "pause and modify" workflows
- Cannot enforce budget limits with graceful shutdown
- Cannot implement timeout mechanisms with state preservation

**Problem**: Kaizen needs a **graceful interrupt mechanism** that:
1. Allows user to interrupt agent execution at any time
2. Saves checkpoint before shutdown (no data loss)
3. Supports both graceful (finish current step) and immediate (stop now) interrupts
4. Integrates with Control Protocol (interrupt via API/CLI)
5. Integrates with State Persistence (checkpoint before stop)
6. Integrates with Hooks System (pre/post interrupt hooks)

**Inspiration**: Claude Code supports interrupts via:
- Ctrl+C signal handling
- API-based interrupts
- Graceful shutdown with state preservation
- Resume after interrupt

## Requirements

### Functional Requirements

1. **FR-1**: Support user-initiated interrupts (Ctrl+C, API call, CLI command)
2. **FR-2**: Support system-initiated interrupts (timeout, budget limit, resource limit)
3. **FR-3**: Support programmatic interrupts (from code, hooks, policies)
4. **FR-4**: Graceful shutdown mode (finish current step, then save checkpoint and stop)
5. **FR-5**: Immediate shutdown mode (stop now, save checkpoint if possible)
6. **FR-6**: Interrupt with custom message (explain why interrupt occurred)
7. **FR-7**: Resume after interrupt (from saved checkpoint)
8. **FR-8**: Interrupt propagation (interrupt all child specialists/workflows)

### Non-Functional Requirements

1. **NFR-1**: Interrupt detection latency <100ms (responsive to Ctrl+C)
2. **NFR-2**: Graceful shutdown latency <5000ms (finish current step)
3. **NFR-3**: Checkpoint save before shutdown <1000ms
4. **NFR-4**: Async-safe signal handling (no race conditions)
5. **NFR-5**: Cross-platform support (Unix signals, Windows events)

### Interrupt Types

1. **User Interrupts**:
   - Keyboard interrupt (Ctrl+C, SIGINT)
   - API interrupt (via Control Protocol)
   - CLI interrupt (kaizen interrupt <agent-id>)

2. **System Interrupts**:
   - Timeout interrupt (execution time limit exceeded)
   - Budget interrupt (cost limit exceeded)
   - Resource interrupt (memory/CPU limit exceeded)

3. **Programmatic Interrupts**:
   - Hook-based interrupt (custom policy triggers interrupt)
   - Permission interrupt (denied tool triggers interrupt)
   - Error interrupt (unrecoverable error triggers interrupt)

## Decision

We will implement an **Interrupt Mechanism** in `kaizen/core/autonomy/interrupts/` with the following design:

### Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│ User / System (Interrupt Sources)                        │
│ - Ctrl+C (SIGINT)                                        │
│ - API call (via Control Protocol)                        │
│ - Timeout / Budget limit                                 │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Interrupt signals
                        ▼
┌──────────────────────────────────────────────────────────┐
│ InterruptManager (Orchestration)                         │
│ - register_interrupt_handler(source, handler)            │
│ - request_interrupt(mode, reason) → None                 │
│ - is_interrupted() → bool                                │
│ - wait_for_interrupt() → InterruptReason                 │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Check interrupt status
                        ▼
┌──────────────────────────────────────────────────────────┐
│ BaseAgent (Execution Loop)                               │
│ - if interrupt_manager.is_interrupted(): shutdown()      │
│ - await interrupt_manager.wait_for_interrupt()           │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Graceful shutdown
                        ▼
┌──────────────────────────────────────────────────────────┐
│ State Persistence (Checkpoint Before Stop)               │
│ - await state_manager.checkpoint(final_state)            │
└──────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Interrupt Types (`kaizen/core/autonomy/interrupts/types.py`)

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

class InterruptMode(Enum):
    """How to handle interrupt"""
    GRACEFUL = "graceful"  # Finish current step, then stop
    IMMEDIATE = "immediate"  # Stop now, checkpoint if possible

class InterruptSource(Enum):
    """Source of interrupt"""
    USER = "user"  # User-initiated (Ctrl+C, API call)
    SYSTEM = "system"  # System-initiated (timeout, budget)
    PROGRAMMATIC = "programmatic"  # Code-initiated (hook, policy)

@dataclass
class InterruptReason:
    """Details about why interrupt occurred"""
    source: InterruptSource
    mode: InterruptMode
    message: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class InterruptStatus:
    """Current interrupt status"""
    interrupted: bool
    reason: InterruptReason | None = None
    checkpoint_id: str | None = None  # Checkpoint saved before interrupt
```

#### 2. Interrupt Manager (`kaizen/core/autonomy/interrupts/manager.py`)

```python
import signal
import asyncio
import anyio
from typing import Callable, Awaitable
import logging

logger = logging.getLogger(__name__)

class InterruptManager:
    """Manages interrupt signals and graceful shutdown"""

    def __init__(self):
        self._interrupted = anyio.Event()
        self._interrupt_reason: InterruptReason | None = None
        self._shutdown_callbacks: list[Callable[[], Awaitable[None]]] = []
        self._signal_handlers_installed = False

    def install_signal_handlers(self) -> None:
        """Install OS signal handlers (SIGINT, SIGTERM)"""
        if self._signal_handlers_installed:
            return

        # Handle Ctrl+C (SIGINT)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Handle termination (SIGTERM)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._signal_handlers_installed = True
        logger.info("Signal handlers installed (SIGINT, SIGTERM)")

    def _handle_signal(self, signum: int, frame) -> None:
        """Signal handler (called by OS)"""
        signal_name = signal.Signals(signum).name
        logger.warning(f"Received {signal_name}, requesting graceful shutdown")

        # Request graceful interrupt
        # Note: Can't use async in signal handler, so we use thread-safe Event
        self.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message=f"Interrupted by signal {signal_name}"
        )

    def request_interrupt(
        self,
        mode: InterruptMode,
        source: InterruptSource,
        message: str,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Request interrupt (thread-safe, can be called from signal handler)"""
        self._interrupt_reason = InterruptReason(
            source=source,
            mode=mode,
            message=message,
            timestamp=datetime.utcnow(),
            metadata=metadata or {}
        )
        self._interrupted.set()

        logger.warning(f"Interrupt requested: {message} (mode={mode.value}, source={source.value})")

    def is_interrupted(self) -> bool:
        """Check if interrupt has been requested (non-blocking)"""
        return self._interrupted.is_set()

    async def wait_for_interrupt(self, timeout: float | None = None) -> InterruptReason | None:
        """Wait for interrupt signal (blocking)"""
        try:
            if timeout:
                with anyio.fail_after(timeout):
                    await self._interrupted.wait()
            else:
                await self._interrupted.wait()

            return self._interrupt_reason

        except TimeoutError:
            return None

    def register_shutdown_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register callback to run before shutdown"""
        self._shutdown_callbacks.append(callback)

    async def execute_shutdown(self, state_manager: "StateManager | None" = None) -> InterruptStatus:
        """Execute graceful shutdown sequence"""
        logger.info(f"Starting graceful shutdown: {self._interrupt_reason.message}")

        # Execute shutdown callbacks
        for callback in self._shutdown_callbacks:
            try:
                await callback()
            except Exception as e:
                logger.error(f"Shutdown callback failed: {e}")

        # Save checkpoint if state manager available
        checkpoint_id = None
        if state_manager:
            try:
                logger.info("Saving checkpoint before shutdown...")
                final_state = await state_manager._capture_state()
                final_state.status = "interrupted"
                final_state.metadata["interrupt_reason"] = asdict(self._interrupt_reason)
                checkpoint_id = await state_manager.checkpoint(final_state)
                logger.info(f"Checkpoint saved: {checkpoint_id}")
            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}")

        return InterruptStatus(
            interrupted=True,
            reason=self._interrupt_reason,
            checkpoint_id=checkpoint_id
        )

    def reset(self) -> None:
        """Reset interrupt state (for testing or resuming)"""
        self._interrupted = anyio.Event()
        self._interrupt_reason = None
```

#### 3. Timeout Interrupt Handler (`kaizen/core/autonomy/interrupts/handlers/timeout.py`)

```python
class TimeoutInterruptHandler:
    """Automatically interrupt after time limit"""

    def __init__(
        self,
        interrupt_manager: InterruptManager,
        timeout_seconds: float
    ):
        self.interrupt_manager = interrupt_manager
        self.timeout_seconds = timeout_seconds
        self._task: anyio.abc.CancelScope | None = None

    async def start(self) -> None:
        """Start timeout monitoring"""
        async def timeout_monitor():
            await anyio.sleep(self.timeout_seconds)
            self.interrupt_manager.request_interrupt(
                mode=InterruptMode.GRACEFUL,
                source=InterruptSource.SYSTEM,
                message=f"Execution timeout: {self.timeout_seconds}s limit exceeded"
            )

        # Start background task
        async with anyio.create_task_group() as tg:
            self._task = tg.start_soon(timeout_monitor)

    async def stop(self) -> None:
        """Stop timeout monitoring"""
        if self._task:
            self._task.cancel()
```

#### 4. Budget Interrupt Handler (`kaizen/core/autonomy/interrupts/handlers/budget.py`)

```python
class BudgetInterruptHandler:
    """Automatically interrupt when budget limit exceeded"""

    def __init__(
        self,
        interrupt_manager: InterruptManager,
        budget_limit_usd: float
    ):
        self.interrupt_manager = interrupt_manager
        self.budget_limit_usd = budget_limit_usd
        self.current_spent_usd = 0.0

    def track_cost(self, cost_usd: float) -> None:
        """Track API cost, interrupt if limit exceeded"""
        self.current_spent_usd += cost_usd

        if self.current_spent_usd >= self.budget_limit_usd:
            self.interrupt_manager.request_interrupt(
                mode=InterruptMode.GRACEFUL,
                source=InterruptSource.SYSTEM,
                message=f"Budget limit exceeded: ${self.current_spent_usd:.2f} >= ${self.budget_limit_usd:.2f}",
                metadata={"spent_usd": self.current_spent_usd, "limit_usd": self.budget_limit_usd}
            )
```

### Integration with BaseAgent

```python
# kaizen/core/base_agent.py

class BaseAgent(Node):
    def __init__(self, config: BaseAgentConfig):
        super().__init__(config)
        self.interrupt_manager = InterruptManager()
        self.interrupt_manager.install_signal_handlers()

    async def run(self, **kwargs) -> dict[str, Any]:
        """Agent execution loop with interrupt checking"""

        result = None

        try:
            while not self.interrupt_manager.is_interrupted():
                # Execute one step
                result = await self._execute_step(**kwargs)

                # Check if step completed successfully
                if self._is_complete(result):
                    break

                # Update step counter
                self._current_step += 1

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            logger.warning("Keyboard interrupt detected")
            self.interrupt_manager.request_interrupt(
                mode=InterruptMode.GRACEFUL,
                source=InterruptSource.USER,
                message="Keyboard interrupt (Ctrl+C)"
            )

        finally:
            # Always execute graceful shutdown if interrupted
            if self.interrupt_manager.is_interrupted():
                interrupt_status = await self.interrupt_manager.execute_shutdown(
                    state_manager=self.state_manager
                )

                logger.info(f"Agent interrupted: {interrupt_status.reason.message}")

                # Return interrupt status in result
                if result is None:
                    result = {}
                result["interrupted"] = True
                result["interrupt_reason"] = interrupt_status.reason.message
                result["checkpoint_id"] = interrupt_status.checkpoint_id

        return result

    def enable_timeout(self, timeout_seconds: float) -> None:
        """Enable automatic timeout interrupt"""
        handler = TimeoutInterruptHandler(self.interrupt_manager, timeout_seconds)
        asyncio.create_task(handler.start())

    def enable_budget_limit(self, budget_limit_usd: float) -> None:
        """Enable automatic budget limit interrupt"""
        handler = BudgetInterruptHandler(self.interrupt_manager, budget_limit_usd)

        # Register hook to track costs
        async def track_cost_hook(context: HookContext) -> HookResult:
            if context.event_type == HookEvent.POST_TOOL_USE:
                cost = context.data.get("estimated_cost_usd", 0.0)
                handler.track_cost(cost)
            return HookResult(success=True)

        self.hook_manager.register(HookEvent.POST_TOOL_USE, track_cost_hook)
```

### User Code Examples

#### Example 1: Basic Interrupt Handling
```python
from kaizen.core.base_agent import BaseAgent

agent = BaseAgent(config=config)
agent.enable_state_persistence()  # Auto-saves checkpoint on interrupt

try:
    # Press Ctrl+C during execution
    result = await agent.run(input="Long-running task")

    if result.get("interrupted"):
        print(f"Agent interrupted: {result['interrupt_reason']}")
        print(f"Checkpoint saved: {result['checkpoint_id']}")

        # Resume later
        await agent.resume_from_checkpoint(result['checkpoint_id'])
        result = await agent.run(input="Continue from where you left off")

except KeyboardInterrupt:
    print("Gracefully shutting down...")
```

#### Example 2: Timeout Limit
```python
agent = BaseAgent(config=config)
agent.enable_state_persistence()
agent.enable_timeout(timeout_seconds=300)  # 5-minute limit

result = await agent.run(input="Complex analysis task")

if result.get("interrupted"):
    print("Task timed out, checkpoint saved")
```

#### Example 3: Budget Limit
```python
agent = BaseAgent(config=config)
agent.enable_state_persistence()
agent.enable_budget_limit(budget_limit_usd=10.0)  # $10 limit

result = await agent.run(input="Expensive task")

if result.get("interrupted"):
    print(f"Budget limit exceeded: {result['interrupt_reason']}")
```

#### Example 4: Programmatic Interrupt
```python
# Custom hook that interrupts on specific condition
class CustomInterruptHook(BaseHook):
    def __init__(self, interrupt_manager: InterruptManager):
        super().__init__(name="custom_interrupt")
        self.interrupt_manager = interrupt_manager

    async def handle(self, context: HookContext) -> HookResult:
        if context.event_type == HookEvent.POST_TOOL_USE:
            # Interrupt if tool returns error
            if context.data.get("result", {}).get("error"):
                self.interrupt_manager.request_interrupt(
                    mode=InterruptMode.GRACEFUL,
                    source=InterruptSource.PROGRAMMATIC,
                    message="Tool returned error, interrupting execution"
                )

        return HookResult(success=True)

agent.hook_manager.register(HookEvent.POST_TOOL_USE, CustomInterruptHook(agent.interrupt_manager))
```

## Consequences

### Positive

1. **✅ User Control**: Users can stop agents safely without data loss
2. **✅ Graceful Shutdown**: Always saves checkpoint before stopping
3. **✅ Resume Support**: Can resume from checkpoint after interrupt
4. **✅ Budget Control**: Automatic interrupts prevent cost overruns
5. **✅ Timeout Control**: Automatic interrupts prevent infinite loops
6. **✅ Debugging**: Checkpoint shows exact state at interrupt point

### Negative

1. **⚠️ Complexity**: More moving parts (signal handlers, callbacks, state)
2. **⚠️ Platform Differences**: Unix signals vs Windows events
3. **⚠️ Shutdown Latency**: Graceful shutdown adds 1-5 seconds
4. **⚠️ Race Conditions**: Signal handlers must be thread-safe

### Mitigations

1. **Complexity**: Clear documentation, default configuration works out-of-the-box
2. **Platform**: Abstract signal handling, test on Windows/Mac/Linux
3. **Shutdown Latency**: Configurable (graceful vs immediate), async checkpointing
4. **Race Conditions**: Use anyio.Event for thread-safe signaling

## Performance Targets

| Metric | Target | Validation |
|--------|--------|------------|
| Interrupt detection latency | <100ms | Press Ctrl+C, measure response |
| Graceful shutdown latency | <5000ms | Measure time from interrupt to shutdown |
| Checkpoint save before shutdown | <1000ms | Measure checkpoint save time |
| Signal handler overhead | <1ms | Measure signal handler execution |

See `PERFORMANCE_PARITY_PLAN.md` for full benchmarking strategy.

## Alternatives Considered

### Alternative 1: No Interrupt Support (Kill Process)
**Rejected**: Data loss, poor user experience, unprofessional

### Alternative 2: Cooperative Cancellation Only (No Signals)
**Rejected**: Doesn't handle Ctrl+C, doesn't work for stuck agents

### Alternative 3: Immediate Shutdown Only (No Graceful)
**Rejected**: Loses in-progress work, no checkpoint saved

## Implementation Plan

**Phase 3 Timeline**: Weeks 28-32 (5 weeks)

| Week | Tasks |
|------|-------|
| 28 | Implement core types, InterruptManager, signal handlers |
| 29 | Timeout and budget interrupt handlers |
| 30 | BaseAgent integration, graceful shutdown |
| 31 | Control Protocol integration (API interrupts) |
| 32 | Testing, documentation, examples |

**Deliverables**:
- [ ] `kaizen/core/autonomy/interrupts/` module (~600 lines)
- [ ] Signal handlers (SIGINT, SIGTERM)
- [ ] 2 built-in interrupt handlers (timeout, budget)
- [ ] BaseAgent integration
- [ ] 30+ unit/integration tests
- [ ] 5 example use cases
- [ ] Comprehensive documentation

## Testing Strategy

### Tier 1: Unit Tests
```python
def test_interrupt_manager_request():
    manager = InterruptManager()
    assert not manager.is_interrupted()

    manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test interrupt"
    )

    assert manager.is_interrupted()
    assert manager._interrupt_reason.message == "Test interrupt"
```

### Tier 2: Integration Tests
```python
@pytest.mark.tier2
async def test_agent_graceful_shutdown():
    agent = BaseAgent(config=config)
    agent.enable_state_persistence()

    # Start agent
    task = asyncio.create_task(agent.run(input="Long task"))

    # Wait 1 second, then interrupt
    await asyncio.sleep(1.0)
    agent.interrupt_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test interrupt"
    )

    # Wait for shutdown
    result = await task

    # Verify checkpoint saved
    assert result["interrupted"] is True
    assert result["checkpoint_id"] is not None
```

### Tier 3: E2E Tests
```python
@pytest.mark.tier3
async def test_ctrl_c_interrupt():
    # Test actual Ctrl+C signal handling
    # (requires subprocess, send SIGINT)
    pass
```

## Documentation Requirements

- [ ] **ADR** (this document)
- [ ] **API Reference**: `docs/reference/interrupt-api.md`
- [ ] **Tutorial**: `docs/guides/interrupt-handling.md`
- [ ] **Troubleshooting**: `docs/reference/interrupt-troubleshooting.md`

## References

1. **Gap Analysis**: `.claude/improvements/CLAUDE_AGENT_SDK_KAIZEN_GAP_ANALYSIS.md`
2. **Implementation Proposal**: `.claude/improvements/KAIZEN_AUTONOMOUS_AGENT_ENHANCEMENT_PROPOSAL.md` (Section 3.6)
3. **Performance Plan**: `.claude/improvements/PERFORMANCE_PARITY_PLAN.md` (Phase 3)

## Dependencies

**This ADR depends on**:
- 014: Hooks System (for interrupt hooks)
- 015: State Persistence (for checkpoint before shutdown)

**Other ADRs depend on this**:
- 017: Observability (for interrupt metrics)

## Approval

**Proposed By**: Kaizen Architecture Team
**Date**: 2025-10-19
**Reviewers**: TBD
**Status**: Proposed (awaiting team review)

---

**Next ADR**: 017: Observability & Performance (monitoring and metrics)
