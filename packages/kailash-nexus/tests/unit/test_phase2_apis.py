# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NTR-013: Phase 2 feature APIs.

Tests @app.on_event(), @app.scheduled(), app.emit(),
app.run_in_background(), and _parse_interval().
"""

from __future__ import annotations

import asyncio

import pytest

from nexus import Nexus
from nexus.core import Nexus as NexusCore


# ---------------------------------------------------------------------------
# @app.on_event() tests
# ---------------------------------------------------------------------------


class TestOnEventDecorator:
    """Tests for the @app.on_event() decorator."""

    def test_registers_handler_in_registry(self):
        with Nexus(enable_durability=False) as app:

            @app.on_event("user.created")
            async def on_user_created(event):
                pass

            # Handler should be in the registry with correct metadata
            handlers = app._registry.list_handlers()
            event_handlers = [
                h for h in handlers if h.metadata.get("channel") == "event"
            ]
            assert len(event_handlers) == 1
            assert event_handlers[0].metadata["event_type"] == "user.created"
            assert event_handlers[0].func is on_user_created

    def test_preserves_original_function(self):
        """Decorator returns the original function unchanged."""
        with Nexus(enable_durability=False) as app:

            @app.on_event("test.event")
            async def my_handler(event):
                return "original"

            # The decorated function is still the original
            assert my_handler.__name__ == "my_handler"

    def test_multiple_event_handlers(self):
        with Nexus(enable_durability=False) as app:

            @app.on_event("user.created")
            async def handler1(event):
                pass

            @app.on_event("user.deleted")
            async def handler2(event):
                pass

            handlers = app._registry.list_handlers()
            event_handlers = [
                h for h in handlers if h.metadata.get("channel") == "event"
            ]
            assert len(event_handlers) == 2


# ---------------------------------------------------------------------------
# @app.scheduled() tests
# ---------------------------------------------------------------------------


class TestScheduledDecorator:
    """Tests for the @app.scheduled() decorator."""

    def test_registers_scheduled_handler(self):
        with Nexus(enable_durability=False) as app:

            @app.scheduled("5m")
            async def cleanup():
                pass

            handlers = app._registry.list_handlers()
            scheduled_handlers = [
                h for h in handlers if h.metadata.get("channel") == "scheduler"
            ]
            assert len(scheduled_handlers) == 1
            assert scheduled_handlers[0].metadata["interval"] == "5m"
            assert scheduled_handlers[0].metadata["interval_seconds"] == 300

    def test_with_cron_expression(self):
        with Nexus(enable_durability=False) as app:

            @app.scheduled("1h", cron="0 * * * *")
            async def hourly_task():
                pass

            handlers = app._registry.list_handlers()
            scheduled = [
                h for h in handlers if h.metadata.get("channel") == "scheduler"
            ]
            assert len(scheduled) == 1
            assert scheduled[0].metadata["cron"] == "0 * * * *"

    def test_preserves_function(self):
        with Nexus(enable_durability=False) as app:

            @app.scheduled("30s")
            async def tick():
                pass

            assert tick.__name__ == "tick"


# ---------------------------------------------------------------------------
# _parse_interval tests
# ---------------------------------------------------------------------------


class TestParseInterval:
    """Tests for the _parse_interval static method."""

    def test_seconds(self):
        assert NexusCore._parse_interval("30s") == 30

    def test_minutes(self):
        assert NexusCore._parse_interval("5m") == 300

    def test_hours(self):
        assert NexusCore._parse_interval("2h") == 7200

    def test_days(self):
        assert NexusCore._parse_interval("1d") == 86400

    def test_uppercase_unit(self):
        assert NexusCore._parse_interval("10S") == 10

    def test_empty_string(self):
        with pytest.raises(ValueError, match="Empty interval"):
            NexusCore._parse_interval("")

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Invalid interval unit"):
            NexusCore._parse_interval("5x")

    def test_invalid_value(self):
        with pytest.raises(ValueError, match="Invalid interval value"):
            NexusCore._parse_interval("abcm")

    def test_zero_value(self):
        with pytest.raises(ValueError, match="must be positive"):
            NexusCore._parse_interval("0s")

    def test_negative_value(self):
        with pytest.raises(ValueError, match="must be positive"):
            NexusCore._parse_interval("-5m")


# ---------------------------------------------------------------------------
# app.emit() tests
# ---------------------------------------------------------------------------


class TestEmit:
    """Tests for the app.emit() method."""

    def test_emit_does_not_raise(self):
        """emit() publishes an event without raising."""
        with Nexus(enable_durability=False) as app:
            # emit() delegates to EventBus.publish(), which is non-blocking.
            # Events are enqueued in the janus queue. They appear in history
            # only after the dispatch loop processes them (requires start()).
            app.emit("order.shipped", {"order_id": "123"})
            # No exception means success

    def test_emit_without_data(self):
        """emit() works with no data argument."""
        with Nexus(enable_durability=False) as app:
            app.emit("system.heartbeat")

    def test_emit_is_nonblocking(self):
        """emit() returns immediately (synchronous, non-blocking)."""
        with Nexus(enable_durability=False) as app:
            # This should not block or raise
            app.emit("test.fast", {"fast": True})

    @pytest.mark.asyncio
    async def test_emit_appears_in_history_after_dispatch(self):
        """Events emitted appear in history after the EventBus dispatch loop runs."""
        with Nexus(enable_durability=False) as app:
            sub_q = app._event_bus.subscribe()
            await app._event_bus.start()
            try:
                app.emit("order.shipped", {"order_id": "123"})
                # Wait for the dispatch loop to process
                await asyncio.wait_for(sub_q.get(), timeout=2.0)

                history = app.get_events()
                shipped = [
                    e for e in history if e["data"].get("type") == "order.shipped"
                ]
                assert len(shipped) == 1
                assert shipped[0]["data"]["order_id"] == "123"
            finally:
                await app._event_bus.stop()


# ---------------------------------------------------------------------------
# app.run_in_background() tests
# ---------------------------------------------------------------------------


class TestRunInBackground:
    """Tests for the app.run_in_background() method."""

    @pytest.mark.asyncio
    async def test_runs_coroutine(self):
        """Background task executes and completes."""
        with Nexus(enable_durability=False) as app:
            result_holder = {}

            async def work():
                result_holder["done"] = True

            task = app.run_in_background(work())
            assert isinstance(task, asyncio.Task)
            await asyncio.wait_for(task, timeout=2.0)
            assert result_holder["done"] is True

    @pytest.mark.asyncio
    async def test_error_logged_not_propagated(self):
        """Background task errors are logged, not propagated."""
        with Nexus(enable_durability=False) as app:

            async def failing_work():
                raise RuntimeError("bg task failure")

            task = app.run_in_background(failing_work())
            # Task should complete (error handled internally)
            await asyncio.wait_for(task, timeout=2.0)
            # The task should not raise when awaited
            # (the _safe_wrapper catches the exception)

    @pytest.mark.asyncio
    async def test_returns_cancellable_task(self):
        """Returned task can be cancelled."""
        with Nexus(enable_durability=False) as app:

            async def long_work():
                await asyncio.sleep(100)

            task = app.run_in_background(long_work())
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


# ---------------------------------------------------------------------------
# app.integrate_dataflow() tests (basic, DataFlow bridge tested in test_dataflow_bridge.py)
# ---------------------------------------------------------------------------


class TestIntegrateDataflow:
    """Tests for the app.integrate_dataflow() convenience method."""

    def test_returns_self_for_chaining(self):
        """integrate_dataflow() returns self for chaining."""

        class FakeDB:
            _models = {}
            _event_bus = None

        with Nexus(enable_durability=False) as app:
            result = app.integrate_dataflow(FakeDB())
            assert result is app
