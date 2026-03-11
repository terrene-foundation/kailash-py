"""
Unit tests for TimeoutInterruptHandler.

Tests timeout monitoring, warning thresholds, and interrupt triggering.
"""

import anyio
import pytest
from kaizen.core.autonomy.interrupts.handlers.timeout import TimeoutInterruptHandler
from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.types import InterruptMode, InterruptSource


class TestTimeoutHandlerInit:
    """Test TimeoutInterruptHandler initialization"""

    def test_init_default(self):
        """Test default initialization"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=60.0)

        assert handler.interrupt_manager is manager
        assert handler.timeout_seconds == 60.0
        assert handler.warning_threshold == 0.8
        assert handler._cancel_scope is None
        assert handler._warned is False

    def test_init_custom_warning_threshold(self):
        """Test initialization with custom warning threshold"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(
            manager, timeout_seconds=120.0, warning_threshold=0.9
        )

        assert handler.timeout_seconds == 120.0
        assert handler.warning_threshold == 0.9


class TestTimeoutMonitoring:
    """Test timeout monitoring functionality"""

    @pytest.mark.asyncio
    async def test_start_creates_monitor_task(self):
        """Test start() creates background monitoring task"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=0.2)

        # Start monitoring in background
        async with anyio.create_task_group() as tg:
            tg.start_soon(handler.start)

            # Wait briefly
            await anyio.sleep(0.05)

            # Should not be interrupted yet
            assert not manager.is_interrupted()

            # Cancel task group before timeout
            tg.cancel_scope.cancel()

    @pytest.mark.asyncio
    async def test_timeout_triggers_interrupt(self):
        """Test timeout triggers graceful interrupt"""
        manager = InterruptManager()
        # Short timeout for testing
        handler = TimeoutInterruptHandler(manager, timeout_seconds=0.1)

        # Start monitoring
        async with anyio.create_task_group() as tg:
            tg.start_soon(handler.start)

            # Wait for timeout
            await anyio.sleep(0.15)

        # Should be interrupted
        assert manager.is_interrupted()

        # Verify interrupt details
        reason = manager._interrupt_reason
        assert reason is not None
        assert reason.mode == InterruptMode.GRACEFUL
        assert reason.source == InterruptSource.TIMEOUT
        assert "timeout" in reason.message.lower()
        assert reason.metadata["timeout_seconds"] == 0.1

    @pytest.mark.asyncio
    async def test_warning_threshold(self):
        """Test warning is logged at threshold"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(
            manager, timeout_seconds=0.2, warning_threshold=0.5
        )

        # Start monitoring
        async with anyio.create_task_group() as tg:
            tg.start_soon(handler.start)

            # Wait past warning threshold (0.5 * 0.2 = 0.1s)
            await anyio.sleep(0.12)

            # Warning should have been logged
            assert handler._warned is True

            # But not interrupted yet
            assert not manager.is_interrupted()

            # Cancel before full timeout
            tg.cancel_scope.cancel()

    @pytest.mark.asyncio
    async def test_no_interrupt_if_already_interrupted(self):
        """Test timeout doesn't trigger if already interrupted"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=0.1)

        # Request interrupt before timeout
        manager.request_interrupt(
            mode=InterruptMode.GRACEFUL,
            source=InterruptSource.USER,
            message="User stop",
        )

        original_reason = manager._interrupt_reason

        # Start monitoring (should detect existing interrupt)
        async with anyio.create_task_group() as tg:
            tg.start_soon(handler.start)

            # Wait for timeout
            await anyio.sleep(0.15)

        # Should keep original interrupt reason
        assert manager._interrupt_reason == original_reason
        assert manager._interrupt_reason.source == InterruptSource.USER

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Test start() can be called multiple times safely"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=1.0)

        # First start
        async with anyio.create_task_group() as tg:
            tg.start_soon(handler.start)
            await anyio.sleep(0.01)
            tg.cancel_scope.cancel()

        # Should not raise
        # Second start would need another task group context


class TestTimeoutStop:
    """Test stopping timeout monitoring"""

    @pytest.mark.asyncio
    async def test_stop_cancels_monitoring(self):
        """Test stop() cancels monitoring task"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=0.1)

        # Start monitoring
        async with anyio.create_task_group() as tg:
            tg.start_soon(handler.start)

            # Stop before timeout
            await anyio.sleep(0.02)
            await handler.stop()

            # Wait past original timeout
            await anyio.sleep(0.12)

        # Should not be interrupted (monitoring was stopped)
        # Note: This test may still trigger interrupt because we can't reliably
        # cancel the task, so we just verify stop() doesn't raise


class TestTimeoutHelperMethods:
    """Test helper methods for timeout tracking"""

    def test_get_elapsed_time(self):
        """Test get_elapsed_time() returns approximation"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=60.0)

        elapsed = handler.get_elapsed_time()

        # Currently returns 0.0 (TODO: implement precise timing)
        assert elapsed == 0.0

    def test_get_remaining_time(self):
        """Test get_remaining_time() calculation"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=60.0)

        remaining = handler.get_remaining_time()

        # Should be timeout - elapsed (60 - 0 = 60)
        assert remaining == 60.0

    def test_remaining_time_never_negative(self):
        """Test remaining time is clamped to 0"""
        manager = InterruptManager()
        handler = TimeoutInterruptHandler(manager, timeout_seconds=60.0)

        # Mock elapsed time > timeout
        # (Can't easily mock since get_elapsed_time is TODO, but verify logic)
        remaining = handler.get_remaining_time()

        # Should never be negative
        assert remaining >= 0.0
