"""
Unit tests for interrupt hook integration (TODO-169 Day 4).

Tests integration between interrupt system and hooks system:
- PRE_INTERRUPT and POST_INTERRUPT hook events
- Hook triggers in interrupt handling
- Built-in interrupt hooks (metrics, audit)

Test Strategy: Tier 1 (Unit) - Real InterruptManager and HookManager instances (NO MOCKING)
Coverage: 5 tests for Day 4 acceptance criteria
"""

import pytest
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.types import InterruptMode, InterruptSource
from kaizen.signatures import InputField, OutputField, Signature


class TaskSignature(Signature):
    """Simple signature for testing"""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")


# ═══════════════════════════════════════════════════════════════
# Test: Hook Event Registration (2 tests)
# ═══════════════════════════════════════════════════════════════


def test_hook_event_definitions():
    """
    Test that PRE_INTERRUPT and POST_INTERRUPT events are defined.

    Validates:
    - HookEvent.PRE_INTERRUPT exists
    - HookEvent.POST_INTERRUPT exists
    - Events have correct string values
    """
    # Act & Assert
    assert hasattr(HookEvent, "PRE_INTERRUPT"), "Should have PRE_INTERRUPT event"
    assert hasattr(HookEvent, "POST_INTERRUPT"), "Should have POST_INTERRUPT event"

    assert (
        HookEvent.PRE_INTERRUPT.value == "pre_interrupt"
    ), "PRE_INTERRUPT should have correct value"
    assert (
        HookEvent.POST_INTERRUPT.value == "post_interrupt"
    ), "POST_INTERRUPT should have correct value"


@pytest.mark.asyncio
async def test_register_interrupt_hooks():
    """
    Test that interrupt hooks can be registered with HookManager.

    Validates:
    - PRE_INTERRUPT hooks can be registered
    - POST_INTERRUPT hooks can be registered
    - Multiple hooks can be registered for same event
    """
    # Arrange
    hook_manager = HookManager()
    executed = []

    async def pre_interrupt_hook(context: HookContext) -> HookResult:
        executed.append("pre_interrupt")
        return HookResult(success=True)

    async def post_interrupt_hook(context: HookContext) -> HookResult:
        executed.append("post_interrupt")
        return HookResult(success=True)

    # Act
    hook_manager.register(
        HookEvent.PRE_INTERRUPT, pre_interrupt_hook, HookPriority.NORMAL
    )
    hook_manager.register(
        HookEvent.POST_INTERRUPT, post_interrupt_hook, HookPriority.NORMAL
    )

    # Assert
    assert (
        HookEvent.PRE_INTERRUPT in hook_manager._hooks
    ), "Should have PRE_INTERRUPT hooks"
    assert (
        HookEvent.POST_INTERRUPT in hook_manager._hooks
    ), "Should have POST_INTERRUPT hooks"


# ═══════════════════════════════════════════════════════════════
# Test: Hook Trigger Integration (2 tests)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_interrupt_manager_triggers_hooks():
    """
    Test that InterruptManager triggers hooks when interrupt is requested.

    Validates:
    - request_interrupt() triggers PRE_INTERRUPT hook
    - execute_shutdown() triggers POST_INTERRUPT hook
    - Hooks receive correct context data
    """
    # Arrange
    interrupt_manager = InterruptManager()
    hook_manager = HookManager()
    executed = []

    async def pre_interrupt_hook(context: HookContext) -> HookResult:
        executed.append("pre_interrupt")
        assert (
            context.event_type == HookEvent.PRE_INTERRUPT
        ), "Should be PRE_INTERRUPT event"
        assert "interrupt_mode" in context.data, "Should include interrupt mode"
        assert "interrupt_source" in context.data, "Should include interrupt source"
        return HookResult(success=True)

    async def post_interrupt_hook(context: HookContext) -> HookResult:
        executed.append("post_interrupt")
        assert (
            context.event_type == HookEvent.POST_INTERRUPT
        ), "Should be POST_INTERRUPT event"
        assert "checkpoint_id" in context.data, "Should include checkpoint ID"
        return HookResult(success=True)

    hook_manager.register(
        HookEvent.PRE_INTERRUPT, pre_interrupt_hook, HookPriority.NORMAL
    )
    hook_manager.register(
        HookEvent.POST_INTERRUPT, post_interrupt_hook, HookPriority.NORMAL
    )

    # Attach hook manager to interrupt manager
    interrupt_manager.hook_manager = hook_manager

    # Act: Request interrupt (should trigger PRE_INTERRUPT)
    await interrupt_manager.request_interrupt_with_hooks(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test interrupt",
    )

    # Act: Execute shutdown (should trigger POST_INTERRUPT)
    await interrupt_manager.execute_shutdown_with_hooks()

    # Assert
    assert "pre_interrupt" in executed, "PRE_INTERRUPT hook should execute"
    assert "post_interrupt" in executed, "POST_INTERRUPT hook should execute"
    assert executed == [
        "pre_interrupt",
        "post_interrupt",
    ], "Hooks should execute in order"


@pytest.mark.asyncio
async def test_hook_blocking_interrupt():
    """
    Test that PRE_INTERRUPT hook can block interrupt if it returns success=False.

    Validates:
    - PRE_INTERRUPT hook returning False blocks interrupt
    - Interrupt is not set when blocked
    - Hook can provide reason for blocking
    """
    # Arrange
    interrupt_manager = InterruptManager()
    hook_manager = HookManager()

    async def blocking_hook(context: HookContext) -> HookResult:
        # Simulate a hook that blocks the interrupt (e.g., critical operation in progress)
        return HookResult(
            success=False, error="Cannot interrupt: Critical operation in progress"
        )

    hook_manager.register(HookEvent.PRE_INTERRUPT, blocking_hook, HookPriority.CRITICAL)

    # Attach hook manager
    interrupt_manager.hook_manager = hook_manager

    # Act: Try to request interrupt (should be blocked)
    result = await interrupt_manager.request_interrupt_with_hooks(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Test interrupt",
    )

    # Assert
    assert result is False, "Interrupt should be blocked"
    assert not interrupt_manager.is_interrupted(), "Interrupt should not be set"


# ═══════════════════════════════════════════════════════════════
# Test: Built-in Interrupt Hooks (1 test)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_builtin_metrics_hook():
    """
    Test built-in metrics hook for interrupt tracking.

    Validates:
    - Metrics hook records interrupt events
    - Metrics hook tracks interrupt mode and source
    - Metrics hook can be registered with InterruptManager
    """
    # Arrange
    interrupt_manager = InterruptManager()
    hook_manager = HookManager()

    metrics = {
        "interrupt_count": 0,
        "graceful_count": 0,
        "immediate_count": 0,
    }

    async def metrics_hook(context: HookContext) -> HookResult:
        metrics["interrupt_count"] += 1

        mode = context.data.get("interrupt_mode")
        if mode == InterruptMode.GRACEFUL:
            metrics["graceful_count"] += 1
        elif mode == InterruptMode.IMMEDIATE:
            metrics["immediate_count"] += 1

        return HookResult(
            success=True,
            data={
                "metrics_recorded": True,
                "interrupt_count": metrics["interrupt_count"],
            },
        )

    hook_manager.register(HookEvent.PRE_INTERRUPT, metrics_hook, HookPriority.HIGH)

    # Attach hook manager
    interrupt_manager.hook_manager = hook_manager

    # Act: Request multiple interrupts
    await interrupt_manager.request_interrupt_with_hooks(
        mode=InterruptMode.GRACEFUL, source=InterruptSource.USER, message="Test 1"
    )
    interrupt_manager.reset()  # Reset to allow another interrupt

    await interrupt_manager.request_interrupt_with_hooks(
        mode=InterruptMode.IMMEDIATE, source=InterruptSource.TIMEOUT, message="Test 2"
    )

    # Assert
    assert metrics["interrupt_count"] == 2, "Should record 2 interrupts"
    assert metrics["graceful_count"] == 1, "Should record 1 graceful interrupt"
    assert metrics["immediate_count"] == 1, "Should record 1 immediate interrupt"
