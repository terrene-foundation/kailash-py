"""Tests for ShutdownCoordinator (TODO-015: Coordinated Graceful Shutdown).

Verifies:
- Handlers execute in priority order
- Timeout fires for hung handlers
- Error in one handler does not block others
- Double-shutdown is a safe no-op
- Sync and async handlers both work
- Registration validation
- Integration with LocalRuntime.shutdown_coordinator property
- Integration with WorkflowServer.shutdown_coordinator
"""

import asyncio
import math
import time

import pytest

from kailash.runtime.shutdown import ShutdownCoordinator


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """ShutdownCoordinator initialization."""

    def test_default_timeout(self):
        coord = ShutdownCoordinator()
        assert coord._timeout == 30.0
        assert not coord.is_shutting_down

    def test_custom_timeout(self):
        coord = ShutdownCoordinator(timeout=10.0)
        assert coord._timeout == 10.0

    def test_zero_timeout_rejected(self):
        with pytest.raises(ValueError, match="positive finite"):
            ShutdownCoordinator(timeout=0)

    def test_negative_timeout_rejected(self):
        with pytest.raises(ValueError, match="positive finite"):
            ShutdownCoordinator(timeout=-5.0)

    def test_inf_timeout_rejected(self):
        with pytest.raises(ValueError, match="positive finite"):
            ShutdownCoordinator(timeout=math.inf)

    def test_nan_timeout_rejected(self):
        with pytest.raises(ValueError, match="positive finite"):
            ShutdownCoordinator(timeout=math.nan)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Handler registration behaviour."""

    def test_register_sync_handler(self):
        coord = ShutdownCoordinator()
        coord.register("test", lambda: None, priority=2)
        assert len(coord._handlers) == 1
        assert coord._handlers[0][0] == 2
        assert coord._handlers[0][1] == "test"

    def test_register_async_handler(self):
        coord = ShutdownCoordinator()

        async def cleanup():
            pass

        coord.register("async_test", cleanup, priority=1)
        assert len(coord._handlers) == 1

    def test_empty_name_rejected(self):
        coord = ShutdownCoordinator()
        with pytest.raises(ValueError, match="name must not be empty"):
            coord.register("", lambda: None)

    def test_non_callable_rejected(self):
        coord = ShutdownCoordinator()
        with pytest.raises(ValueError, match="callable"):
            coord.register("bad", "not_a_function")  # type: ignore[arg-type]

    def test_handlers_sorted_by_priority(self):
        coord = ShutdownCoordinator()
        coord.register("c", lambda: None, priority=3)
        coord.register("a", lambda: None, priority=1)
        coord.register("b", lambda: None, priority=2)
        priorities = [h[0] for h in coord._handlers]
        assert priorities == [1, 2, 3]

    def test_same_priority_sorted_by_name(self):
        coord = ShutdownCoordinator()
        coord.register("zebra", lambda: None, priority=1)
        coord.register("alpha", lambda: None, priority=1)
        names = [h[1] for h in coord._handlers]
        assert names == ["alpha", "zebra"]


# ---------------------------------------------------------------------------
# Shutdown execution
# ---------------------------------------------------------------------------


class TestShutdownExecution:
    """Core shutdown sequencing."""

    @pytest.mark.asyncio
    async def test_handlers_execute_in_priority_order(self):
        """Handlers with lower priority numbers execute first."""
        call_order = []

        coord = ShutdownCoordinator(timeout=5.0)
        coord.register("third", lambda: call_order.append("third"), priority=3)
        coord.register("first", lambda: call_order.append("first"), priority=1)
        coord.register("second", lambda: call_order.append("second"), priority=2)

        results = await coord.shutdown()

        assert call_order == ["first", "second", "third"]
        assert results == {"first": "ok", "second": "ok", "third": "ok"}

    @pytest.mark.asyncio
    async def test_async_handler_executes(self):
        """Async cleanup handlers are awaited correctly."""
        called = []

        async def async_cleanup():
            await asyncio.sleep(0.01)
            called.append("async")

        coord = ShutdownCoordinator(timeout=5.0)
        coord.register("async_handler", async_cleanup, priority=1)

        results = await coord.shutdown()
        assert called == ["async"]
        assert results["async_handler"] == "ok"

    @pytest.mark.asyncio
    async def test_mixed_sync_async_handlers(self):
        """Both sync and async handlers work in the same shutdown sequence."""
        call_order = []

        async def async_handler():
            await asyncio.sleep(0.01)
            call_order.append("async")

        def sync_handler():
            call_order.append("sync")

        coord = ShutdownCoordinator(timeout=5.0)
        coord.register("sync", sync_handler, priority=1)
        coord.register("async", async_handler, priority=2)

        results = await coord.shutdown()
        assert call_order == ["sync", "async"]
        assert results == {"sync": "ok", "async": "ok"}

    @pytest.mark.asyncio
    async def test_no_handlers_returns_empty(self):
        """Shutdown with no handlers succeeds and returns empty dict."""
        coord = ShutdownCoordinator()
        results = await coord.shutdown()
        assert results == {}
        assert coord.is_shutting_down is True


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Per-handler timeout enforcement."""

    @pytest.mark.asyncio
    async def test_hung_async_handler_times_out(self):
        """A hung async handler is reported as timeout, not blocking forever."""

        async def hung():
            await asyncio.sleep(100)  # Would block forever without timeout

        coord = ShutdownCoordinator(timeout=0.5)
        coord.register("hung", hung, priority=1)

        start = time.monotonic()
        results = await coord.shutdown()
        elapsed = time.monotonic() - start

        assert results["hung"] == "timeout"
        # Should complete well under 5s (the per-handler timeout is 0.5s)
        assert elapsed < 3.0

    @pytest.mark.asyncio
    async def test_timeout_does_not_block_subsequent_handlers(self):
        """A timed-out handler does not prevent later handlers from running."""
        called = []

        async def hung():
            await asyncio.sleep(100)

        coord = ShutdownCoordinator(timeout=1.0)
        coord.register("hung", hung, priority=1)
        coord.register("ok", lambda: called.append("ok"), priority=2)

        results = await coord.shutdown()

        assert results["hung"] == "timeout"
        assert results["ok"] == "ok"
        assert called == ["ok"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Handler errors are isolated."""

    @pytest.mark.asyncio
    async def test_sync_error_does_not_block_others(self):
        """A sync handler that raises does not prevent later handlers."""
        called = []

        def failing():
            raise RuntimeError("boom")

        coord = ShutdownCoordinator(timeout=5.0)
        coord.register("fail", failing, priority=1)
        coord.register("ok", lambda: called.append("ok"), priority=2)

        results = await coord.shutdown()

        assert "error:" in results["fail"]
        assert "boom" in results["fail"]
        assert results["ok"] == "ok"
        assert called == ["ok"]

    @pytest.mark.asyncio
    async def test_async_error_does_not_block_others(self):
        """An async handler that raises does not prevent later handlers."""
        called = []

        async def failing():
            raise ValueError("async boom")

        coord = ShutdownCoordinator(timeout=5.0)
        coord.register("fail", failing, priority=1)
        coord.register("ok", lambda: called.append("ok"), priority=2)

        results = await coord.shutdown()

        assert "error:" in results["fail"]
        assert "async boom" in results["fail"]
        assert results["ok"] == "ok"
        assert called == ["ok"]


# ---------------------------------------------------------------------------
# Double-shutdown
# ---------------------------------------------------------------------------


class TestDoubleShutdown:
    """Double-shutdown safety."""

    @pytest.mark.asyncio
    async def test_double_shutdown_is_noop(self):
        """Calling shutdown() twice returns empty dict the second time."""
        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1

        coord = ShutdownCoordinator(timeout=5.0)
        coord.register("counter", handler, priority=1)

        first = await coord.shutdown()
        second = await coord.shutdown()

        assert first == {"counter": "ok"}
        assert second == {}
        assert call_count == 1  # handler ran only once

    @pytest.mark.asyncio
    async def test_is_shutting_down_flag(self):
        """is_shutting_down transitions from False to True on shutdown."""
        coord = ShutdownCoordinator()
        assert coord.is_shutting_down is False

        await coord.shutdown()
        assert coord.is_shutting_down is True


# ---------------------------------------------------------------------------
# LocalRuntime integration
# ---------------------------------------------------------------------------


class TestLocalRuntimeIntegration:
    """ShutdownCoordinator integration with LocalRuntime."""

    def test_shutdown_coordinator_property_creates_coordinator(self):
        """Accessing shutdown_coordinator lazily creates one."""
        from kailash.runtime.local import LocalRuntime

        runtime = LocalRuntime()
        coord = runtime.shutdown_coordinator

        assert isinstance(coord, ShutdownCoordinator)
        # Should have the runtime's own cleanup handler registered
        handler_names = [h[1] for h in coord._handlers]
        assert "runtime" in handler_names

    def test_shutdown_coordinator_is_cached(self):
        """Same coordinator instance is returned on repeated access."""
        from kailash.runtime.local import LocalRuntime

        runtime = LocalRuntime()
        coord1 = runtime.shutdown_coordinator
        coord2 = runtime.shutdown_coordinator
        assert coord1 is coord2

    def test_runtime_handler_registered_at_priority_1(self):
        """Runtime cleanup is registered at drain priority (1)."""
        from kailash.runtime.local import LocalRuntime

        runtime = LocalRuntime()
        coord = runtime.shutdown_coordinator

        runtime_handler = [h for h in coord._handlers if h[1] == "runtime"]
        assert len(runtime_handler) == 1
        assert runtime_handler[0][0] == 1  # priority 1

    def test_other_subsystems_can_register(self):
        """External subsystems can register on the runtime's coordinator."""
        from kailash.runtime.local import LocalRuntime

        runtime = LocalRuntime()
        runtime.shutdown_coordinator.register(
            "checkpoint_store", lambda: None, priority=2
        )
        runtime.shutdown_coordinator.register("db_pool", lambda: None, priority=3)

        handler_names = [h[1] for h in runtime.shutdown_coordinator._handlers]
        assert "runtime" in handler_names
        assert "checkpoint_store" in handler_names
        assert "db_pool" in handler_names


# ---------------------------------------------------------------------------
# WorkflowServer integration
# ---------------------------------------------------------------------------


class TestWorkflowServerIntegration:
    """ShutdownCoordinator integration with WorkflowServer."""

    def test_server_has_shutdown_coordinator(self):
        """WorkflowServer creates a ShutdownCoordinator on init."""
        from kailash.servers.workflow_server import WorkflowServer

        server = WorkflowServer()
        assert isinstance(server.shutdown_coordinator, ShutdownCoordinator)

    def test_executor_registered_at_priority_0(self):
        """The server's thread pool executor is registered at priority 0."""
        from kailash.servers.workflow_server import WorkflowServer

        server = WorkflowServer()
        executor_handler = [
            h for h in server.shutdown_coordinator._handlers if h[1] == "executor"
        ]
        assert len(executor_handler) == 1
        assert executor_handler[0][0] == 0  # priority 0

    def test_custom_shutdown_timeout(self):
        """Server accepts custom shutdown_timeout kwarg."""
        from kailash.servers.workflow_server import WorkflowServer

        server = WorkflowServer(shutdown_timeout=60.0)
        assert server.shutdown_coordinator._timeout == 60.0

    def test_subsystems_can_register_on_server_coordinator(self):
        """External subsystems can register handlers on the server coordinator."""
        from kailash.servers.workflow_server import WorkflowServer

        server = WorkflowServer()
        server.shutdown_coordinator.register("event_store", lambda: None, priority=2)

        handler_names = [h[1] for h in server.shutdown_coordinator._handlers]
        assert "executor" in handler_names
        assert "event_store" in handler_names
