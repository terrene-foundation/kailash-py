"""
Unit tests for InterruptManager.

Tests signal handling, interrupt coordination, shutdown callbacks, and checkpoint integration.
"""

import signal
from unittest.mock import AsyncMock, MagicMock

import anyio
import pytest
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.types import InterruptMode, InterruptSource


class TestInterruptManagerInit:
    """Test InterruptManager initialization"""

    def test_init_default(self):
        """Test default initialization"""
        manager = InterruptManager()

        assert manager.is_interrupted() is False
        assert manager._interrupt_reason is None
        assert len(manager._shutdown_callbacks) == 0
        assert len(manager._original_handlers) == 0

    def test_init_creates_event(self):
        """Test initialization creates anyio.Event"""
        manager = InterruptManager()

        # The event should be an anyio.Event (can't check directly, but verify behavior)
        assert not manager.is_interrupted()


class TestSignalHandlers:
    """Test signal handler installation and uninstallation"""

    def test_install_signal_handlers(self):
        """Test installing signal handlers"""
        manager = InterruptManager()

        # Should not raise
        manager.install_signal_handlers()

        # Should save original handlers
        assert signal.SIGINT in manager._original_handlers
        assert signal.SIGTERM in manager._original_handlers

    def test_uninstall_signal_handlers(self):
        """Test uninstalling signal handlers"""
        manager = InterruptManager()

        # Install first
        manager.install_signal_handlers()

        # Then uninstall
        manager.uninstall_signal_handlers()

        # Original handlers should be cleared
        assert len(manager._original_handlers) == 0

    def test_signal_handler_triggers_interrupt(self):
        """Test signal handler triggers graceful interrupt"""
        manager = InterruptManager()
        manager.install_signal_handlers()

        try:
            # Simulate SIGINT
            manager._handle_signal(signal.SIGINT, None)

            # Should trigger interrupt
            assert manager.is_interrupted() is True

            # Should have reason
            reason = manager._interrupt_reason
            assert reason is not None
            assert reason.source == InterruptSource.SIGNAL
            assert reason.mode == InterruptMode.GRACEFUL
            assert "SIGINT" in reason.message

        finally:
            manager.uninstall_signal_handlers()

    def test_signal_handler_with_sigterm(self):
        """Test SIGTERM signal handler"""
        manager = InterruptManager()
        manager.install_signal_handlers()

        try:
            # Simulate SIGTERM
            manager._handle_signal(signal.SIGTERM, None)

            # Should trigger interrupt
            assert manager.is_interrupted() is True

            # Should have reason
            reason = manager._interrupt_reason
            assert reason is not None
            assert reason.source == InterruptSource.SIGNAL
            assert "SIGTERM" in reason.message

        finally:
            manager.uninstall_signal_handlers()


class TestInterruptRequests:
    """Test interrupt request functionality"""

    def test_request_interrupt_graceful(self):
        """Test requesting graceful interrupt"""
        manager = InterruptManager()

        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="User stop",
        )

        assert manager.is_interrupted() is True
        assert manager._interrupt_reason.mode == InterruptMode.GRACEFUL
        assert manager._interrupt_reason.source == InterruptSource.USER
        assert manager._interrupt_reason.message == "User stop"

    def test_request_interrupt_immediate(self):
        """Test requesting immediate interrupt"""
        manager = InterruptManager()

        manager.request_interrupt(
            mode=InterruptMode.IMMEDIATE,
            source=InterruptSource.TIMEOUT,
            message="Timeout",
        )

        assert manager.is_interrupted() is True
        assert manager._interrupt_reason.mode == InterruptMode.IMMEDIATE
        assert manager._interrupt_reason.source == InterruptSource.TIMEOUT

    def test_request_interrupt_with_metadata(self):
        """Test interrupt request with metadata"""
        manager = InterruptManager()

        metadata = {"timeout_seconds": 300, "elapsed": 301}
        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.TIMEOUT,
            message="Timeout exceeded",
            metadata=metadata,
        )

        assert manager._interrupt_reason.metadata == metadata

    def test_request_interrupt_idempotent(self):
        """Test requesting interrupt multiple times is idempotent"""
        manager = InterruptManager()

        # First interrupt
        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="First",
        )

        first_reason = manager._interrupt_reason

        # Second interrupt (should be ignored)
        manager.request_interrupt(
            mode=InterruptMode.IMMEDIATE,
            source=InterruptSource.TIMEOUT,
            message="Second",
        )

        # Should keep first interrupt
        assert manager._interrupt_reason == first_reason
        assert manager._interrupt_reason.message == "First"


class TestIsInterrupted:
    """Test is_interrupted() method"""

    def test_is_interrupted_initially_false(self):
        """Test is_interrupted() is False initially"""
        manager = InterruptManager()
        assert manager.is_interrupted() is False

    def test_is_interrupted_after_request(self):
        """Test is_interrupted() is True after interrupt request"""
        manager = InterruptManager()

        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test",
        )

        assert manager.is_interrupted() is True


class TestWaitForInterrupt:
    """Test wait_for_interrupt() async method"""

    @pytest.mark.asyncio
    async def test_wait_for_interrupt_when_already_interrupted(self):
        """Test wait_for_interrupt() returns immediately if already interrupted"""
        manager = InterruptManager()

        # Request interrupt first
        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test",
        )

        # Should return immediately
        await manager.wait_for_interrupt()
        assert manager.is_interrupted() is True

    @pytest.mark.asyncio
    async def test_wait_for_interrupt_blocks_until_interrupt(self):
        """Test wait_for_interrupt() blocks until interrupt requested"""
        manager = InterruptManager()

        async def trigger_interrupt_after_delay():
            await anyio.sleep(0.1)
            manager.request_interrupt(
                mode=InterruptMode.GRACEFUL,
                source=InterruptSource.USER,
                message="Delayed",
            )

        # Start both tasks
        async with anyio.create_task_group() as tg:
            tg.start_soon(trigger_interrupt_after_delay)
            tg.start_soon(manager.wait_for_interrupt)

        # Should be interrupted now
        assert manager.is_interrupted() is True


class TestShutdownCallbacks:
    """Test shutdown callback registration and execution"""

    @pytest.mark.asyncio
    async def test_register_shutdown_callback_sync(self):
        """Test registering synchronous shutdown callback"""
        manager = InterruptManager()
        called = False

        def callback():
            nonlocal called
            called = True

        manager.register_shutdown_callback(callback)

        await manager.execute_shutdown_callbacks()

        assert called is True

    @pytest.mark.asyncio
    async def test_register_shutdown_callback_async(self):
        """Test registering async shutdown callback"""
        manager = InterruptManager()
        called = False

        async def callback():
            nonlocal called
            called = True

        manager.register_shutdown_callback(callback)

        await manager.execute_shutdown_callbacks()

        assert called is True

    @pytest.mark.asyncio
    async def test_register_multiple_callbacks(self):
        """Test registering multiple shutdown callbacks"""
        manager = InterruptManager()
        call_order = []

        async def callback1():
            call_order.append(1)

        async def callback2():
            call_order.append(2)

        manager.register_shutdown_callback(callback1)
        manager.register_shutdown_callback(callback2)

        await manager.execute_shutdown_callbacks()

        assert call_order == [1, 2]

    @pytest.mark.asyncio
    async def test_shutdown_callback_error_isolation(self):
        """Test shutdown callback errors don't prevent other callbacks"""
        manager = InterruptManager()
        call_order = []

        async def callback1():
            call_order.append(1)

        async def callback2():
            raise ValueError("Test error")

        async def callback3():
            call_order.append(3)

        manager.register_shutdown_callback(callback1)
        manager.register_shutdown_callback(callback2)
        manager.register_shutdown_callback(callback3)

        # Should not raise
        await manager.execute_shutdown_callbacks()

        # Callbacks 1 and 3 should have executed
        assert call_order == [1, 3]


class TestExecuteShutdown:
    """Test execute_shutdown() coordination"""

    @pytest.mark.asyncio
    async def test_execute_shutdown_no_state_manager(self):
        """Test shutdown without state manager"""
        manager = InterruptManager()

        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test stop",
        )

        status = await manager.execute_shutdown()

        assert status.interrupted is True
        assert status.reason.message == "Test stop"
        assert status.checkpoint_id is None

    @pytest.mark.asyncio
    async def test_execute_shutdown_with_checkpoint(self):
        """Test shutdown creates checkpoint when state manager provided"""
        manager = InterruptManager()

        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test stop",
        )

        # Mock state manager
        state_manager = AsyncMock()
        state_manager.save_checkpoint = AsyncMock(return_value="ckpt_abc123")

        # Mock agent state
        agent_state = MagicMock()

        status = await manager.execute_shutdown(state_manager, agent_state)

        assert status.interrupted is True
        assert status.checkpoint_id == "ckpt_abc123"

        # Should have called save_checkpoint with force=True
        state_manager.save_checkpoint.assert_called_once()
        call_args = state_manager.save_checkpoint.call_args
        assert call_args.kwargs.get("force") is True

    @pytest.mark.asyncio
    async def test_execute_shutdown_runs_callbacks(self):
        """Test shutdown executes callbacks"""
        manager = InterruptManager()
        called = False

        async def callback():
            nonlocal called
            called = True

        manager.register_shutdown_callback(callback)

        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test",
        )

        await manager.execute_shutdown()

        assert called is True

    @pytest.mark.asyncio
    async def test_execute_shutdown_updates_agent_state(self):
        """Test shutdown updates agent state status"""
        manager = InterruptManager()

        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.TIMEOUT,
            message="Timeout",
        )

        state_manager = AsyncMock()
        state_manager.save_checkpoint = AsyncMock(return_value="ckpt_xyz")

        agent_state = MagicMock()
        agent_state.status = "running"

        await manager.execute_shutdown(state_manager, agent_state)

        # Should update status to interrupted
        assert agent_state.status == "interrupted"


class TestReset:
    """Test reset() functionality"""

    def test_reset_clears_interrupt_state(self):
        """Test reset clears interrupt state"""
        manager = InterruptManager()

        # Request interrupt
        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="Test",
        )

        assert manager.is_interrupted() is True

        # Reset
        manager.reset()

        # Should be cleared
        assert manager.is_interrupted() is False
        assert manager._interrupt_reason is None

    def test_reset_preserves_callbacks(self):
        """Test reset preserves shutdown callbacks"""
        manager = InterruptManager()

        def callback():
            pass

        manager.register_shutdown_callback(callback)

        manager.reset()

        # Callbacks should still be registered
        assert len(manager._shutdown_callbacks) == 1
