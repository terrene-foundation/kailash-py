"""
Integration tests for interrupt mechanism.

Tests interrupt handling with real timing and coordination (NO MOCKING of interrupts).
Simplified to focus on handler integration rather than full autonomous execution.
"""

import asyncio
import os
import signal
import time

import pytest
from kaizen.core.autonomy.interrupts.handlers import (
    BudgetInterruptHandler,
    ControlProtocolInterruptHandler,
    TimeoutInterruptHandler,
)
from kaizen.core.autonomy.interrupts.manager import (
    InterruptManager,
    InterruptMode,
    InterruptSource,
)


@pytest.fixture
def interrupt_manager():
    """Create InterruptManager for testing."""
    manager = InterruptManager()
    manager.reset()
    return manager


class TestTimeoutHandlerIntegration:
    """Test TimeoutInterruptHandler with real timing."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_timeout_handler_triggers_after_duration(self, interrupt_manager):
        """Test timeout handler triggers interrupt after specified duration."""

        # Create timeout handler (1 second)
        timeout_handler = TimeoutInterruptHandler(
            interrupt_manager=interrupt_manager, timeout_seconds=1.0
        )

        # Start timeout monitoring
        asyncio.create_task(timeout_handler.start())

        # Wait for timeout to trigger
        await asyncio.sleep(1.2)

        # Verify interrupted
        assert interrupt_manager.is_interrupted()

        reason = interrupt_manager.get_interrupt_reason()
        assert reason is not None
        assert reason.source == InterruptSource.TIMEOUT
        assert "timeout" in reason.message.lower()
        assert reason.mode == InterruptMode.GRACEFUL

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_timeout_handler_does_not_trigger_early(self, interrupt_manager):
        """Test timeout handler does not trigger before timeout."""

        # Create timeout handler (2 seconds)
        timeout_handler = TimeoutInterruptHandler(
            interrupt_manager=interrupt_manager, timeout_seconds=2.0
        )

        # Start timeout monitoring
        asyncio.create_task(timeout_handler.start())

        # Wait less than timeout
        await asyncio.sleep(0.5)

        # Verify NOT interrupted yet
        assert not interrupt_manager.is_interrupted()

        # Stop handler to clean up
        await timeout_handler.stop()


class TestBudgetHandlerIntegration:
    """Test BudgetInterruptHandler with real cost tracking."""

    @pytest.mark.integration
    def test_budget_handler_triggers_when_exceeded(self, interrupt_manager):
        """Test budget handler triggers interrupt when budget exceeded."""

        # Create budget handler ($0.10 limit)
        budget_handler = BudgetInterruptHandler(
            interrupt_manager=interrupt_manager, budget_usd=0.10
        )

        # Track costs below budget
        budget_handler.track_cost(0.03)
        assert not interrupt_manager.is_interrupted()

        budget_handler.track_cost(0.04)
        assert not interrupt_manager.is_interrupted()

        # Track cost that exceeds budget
        budget_handler.track_cost(0.05)  # Total: $0.12

        # Verify interrupted
        assert interrupt_manager.is_interrupted()

        reason = interrupt_manager.get_interrupt_reason()
        assert reason is not None
        assert reason.source == InterruptSource.BUDGET
        assert "budget" in reason.message.lower()
        assert reason.mode == InterruptMode.GRACEFUL

    @pytest.mark.integration
    def test_budget_handler_tracks_cumulative_cost(self, interrupt_manager):
        """Test budget handler tracks cumulative costs correctly."""

        budget_handler = BudgetInterruptHandler(
            interrupt_manager=interrupt_manager, budget_usd=1.0
        )

        # Track multiple costs
        budget_handler.track_cost(0.25)
        assert budget_handler.get_current_cost() == 0.25

        budget_handler.track_cost(0.30)
        assert budget_handler.get_current_cost() == 0.55

        budget_handler.track_cost(0.15)
        assert (
            abs(budget_handler.get_current_cost() - 0.70) < 0.0001
        )  # Float comparison

        # Verify remaining budget
        assert abs(budget_handler.get_remaining_budget() - 0.30) < 0.0001

        # Verify not interrupted yet
        assert not interrupt_manager.is_interrupted()


class TestControlProtocolHandlerIntegration:
    """Test ControlProtocolInterruptHandler with API requests."""

    @pytest.mark.integration
    def test_control_protocol_handler_graceful_interrupt(self, interrupt_manager):
        """Test control protocol handler triggers graceful interrupt."""

        protocol_handler = ControlProtocolInterruptHandler(
            interrupt_manager=interrupt_manager
        )

        # Request interrupt
        protocol_handler.request_interrupt("User requested stop")

        # Verify interrupted
        assert interrupt_manager.is_interrupted()

        reason = interrupt_manager.get_interrupt_reason()
        assert reason is not None
        assert reason.source == InterruptSource.USER
        assert "requested stop" in reason.message.lower()
        assert reason.mode == InterruptMode.GRACEFUL

    @pytest.mark.integration
    def test_control_protocol_handler_immediate_interrupt(self, interrupt_manager):
        """Test control protocol handler supports immediate interrupt."""

        protocol_handler = ControlProtocolInterruptHandler(
            interrupt_manager=interrupt_manager, default_mode=InterruptMode.IMMEDIATE
        )

        # Request immediate interrupt
        protocol_handler.request_interrupt(
            "Emergency stop", mode=InterruptMode.IMMEDIATE
        )

        # Verify interrupted
        assert interrupt_manager.is_interrupted()

        reason = interrupt_manager.get_interrupt_reason()
        assert reason is not None
        assert reason.mode == InterruptMode.IMMEDIATE


class TestInterruptPropagation:
    """Test interrupt propagation in multi-agent systems."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_interrupt_propagation_parent_to_children(self):
        """Test interrupt propagates from parent to child managers."""

        # Create parent and children
        parent = InterruptManager()
        child1 = InterruptManager()
        child2 = InterruptManager()
        child3 = InterruptManager()

        # Link children to parent
        parent.add_child_manager(child1)
        parent.add_child_manager(child2)
        parent.add_child_manager(child3)

        # Parent requests interrupt
        parent.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Parent interrupted",
        )

        # Propagate to children
        parent.propagate_to_children()

        # Give propagation time
        await asyncio.sleep(0.1)

        # Verify all interrupted
        assert parent.is_interrupted()
        assert child1.is_interrupted()
        assert child2.is_interrupted()
        assert child3.is_interrupted()

        # Verify reasons propagated
        parent_reason = parent.get_interrupt_reason()
        child1_reason = child1.get_interrupt_reason()
        child2_reason = child2.get_interrupt_reason()
        child3_reason = child3.get_interrupt_reason()

        assert parent_reason.message == "Parent interrupted"
        assert "Parent interrupted" in child1_reason.message
        assert "Parent interrupted" in child2_reason.message
        assert "Parent interrupted" in child3_reason.message


class TestShutdownCallbacks:
    """Test cleanup callbacks are executed."""

    @pytest.mark.integration
    def test_cleanup_callbacks_executed_in_order(self, interrupt_manager):
        """Test cleanup callbacks executed in registration order."""

        execution_order = []

        def callback1():
            execution_order.append(1)

        def callback2():
            execution_order.append(2)

        def callback3():
            execution_order.append(3)

        # Register callbacks
        interrupt_manager.register_shutdown_callback(callback1)
        interrupt_manager.register_shutdown_callback(callback2)
        interrupt_manager.register_shutdown_callback(callback3)

        # Request interrupt
        interrupt_manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test cleanup",
        )

        # Execute cleanup (async method)
        import asyncio

        asyncio.run(interrupt_manager.execute_shutdown_callbacks())

        # Verify all executed in order
        assert execution_order == [1, 2, 3]


class TestInterruptError:
    """Test InterruptedError is raised when requested."""

    @pytest.mark.integration
    def test_interrupted_error_can_be_raised(self, interrupt_manager):
        """Test InterruptedError can be raised with reason."""

        # Request interrupt
        interrupt_manager.request_interrupt(
            mode=InterruptMode.IMMEDIATE,
            source=InterruptSource.USER,
            message="Stop now",
        )

        # Verify error can be raised with reason
        from kaizen.core.autonomy.interrupts.types import InterruptedError

        if interrupt_manager.is_interrupted():
            reason = interrupt_manager.get_interrupt_reason()
            with pytest.raises(InterruptedError) as exc_info:
                raise InterruptedError("Interrupted", reason=reason)

            assert exc_info.value.reason is not None
            assert exc_info.value.reason.message == "Stop now"

    @pytest.mark.integration
    def test_no_interrupt_when_not_requested(self, interrupt_manager):
        """Test no interrupt when not requested."""

        # Should not be interrupted
        assert not interrupt_manager.is_interrupted()
        assert interrupt_manager.get_interrupt_reason() is None


class TestSignalHandling:
    """Test signal handler integration."""

    @pytest.mark.integration
    def test_sigint_handler_registration(self, interrupt_manager):
        """Test SIGINT handler can be registered."""

        signal_received = {"value": False}

        def sigint_handler(signum, frame):
            signal_received["value"] = True
            interrupt_manager.request_interrupt(
                mode=InterruptMode.GRACEFUL,
                source=InterruptSource.SIGNAL,
                message="SIGINT received",
            )

        # Register handler
        old_handler = signal.signal(signal.SIGINT, sigint_handler)

        try:
            # Simulate SIGINT
            os.kill(os.getpid(), signal.SIGINT)

            # Give signal time to process
            time.sleep(0.1)

            # Verify signal received and interrupt triggered
            assert signal_received["value"]
            assert interrupt_manager.is_interrupted()

            reason = interrupt_manager.get_interrupt_reason()
            assert reason is not None
            assert reason.source == InterruptSource.SIGNAL

        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, old_handler)
