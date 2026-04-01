# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NTR-003: EventBus implementation.

Tests the EventBus, NexusEvent, and NexusEventType extracted from
core.py into nexus/events.py.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime

import pytest

from nexus.events import EventBus, NexusEvent, NexusEventType


# ---------------------------------------------------------------------------
# NexusEventType tests
# ---------------------------------------------------------------------------


class TestNexusEventType:
    """Tests for the NexusEventType enum."""

    def test_is_str_enum(self):
        """NexusEventType values are strings (str-backed enum)."""
        assert isinstance(NexusEventType.CUSTOM, str)
        assert NexusEventType.CUSTOM == "custom"

    def test_all_values(self):
        expected = {
            "handler.registered",
            "handler.called",
            "handler.completed",
            "handler.error",
            "health.check",
            "custom",
        }
        actual = {e.value for e in NexusEventType}
        assert actual == expected

    def test_from_value(self):
        assert NexusEventType("custom") is NexusEventType.CUSTOM
        assert NexusEventType("handler.registered") is NexusEventType.HANDLER_REGISTERED


# ---------------------------------------------------------------------------
# NexusEvent tests
# ---------------------------------------------------------------------------


class TestNexusEvent:
    """Tests for the NexusEvent dataclass."""

    def test_defaults(self):
        event = NexusEvent(event_type=NexusEventType.CUSTOM)
        assert event.event_type is NexusEventType.CUSTOM
        assert isinstance(event.timestamp, datetime)
        assert event.data == {}
        assert event.handler_name is None
        assert event.request_id is None

    def test_all_fields(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        event = NexusEvent(
            event_type=NexusEventType.HANDLER_CALLED,
            timestamp=ts,
            data={"key": "value"},
            handler_name="greet",
            request_id="req-001",
        )
        assert event.event_type is NexusEventType.HANDLER_CALLED
        assert event.timestamp == ts
        assert event.data == {"key": "value"}
        assert event.handler_name == "greet"
        assert event.request_id == "req-001"

    def test_to_dict(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        event = NexusEvent(
            event_type=NexusEventType.CUSTOM,
            timestamp=ts,
            data={"x": 1},
            handler_name="h",
            request_id="r",
        )
        d = event.to_dict()
        assert d["event_type"] == "custom"
        assert d["timestamp"] == ts.isoformat()
        assert d["data"] == {"x": 1}
        assert d["handler_name"] == "h"
        assert d["request_id"] == "r"

    def test_from_dict(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        d = {
            "event_type": "handler.completed",
            "timestamp": ts.isoformat(),
            "data": {"result": "ok"},
            "handler_name": "greet",
            "request_id": "r-1",
        }
        event = NexusEvent.from_dict(d)
        assert event.event_type is NexusEventType.HANDLER_COMPLETED
        assert event.timestamp == ts
        assert event.data == {"result": "ok"}
        assert event.handler_name == "greet"
        assert event.request_id == "r-1"

    def test_roundtrip(self):
        original = NexusEvent(
            event_type=NexusEventType.HANDLER_ERROR,
            data={"error": "timeout"},
            handler_name="slow_handler",
        )
        restored = NexusEvent.from_dict(original.to_dict())
        assert restored.event_type == original.event_type
        assert restored.data == original.data
        assert restored.handler_name == original.handler_name


# ---------------------------------------------------------------------------
# EventBus tests
# ---------------------------------------------------------------------------


class TestEventBusPublishHistory:
    """Tests for EventBus publish and history via the dispatch loop.

    Events published via publish() are buffered in the janus queue and
    only appear in history after the dispatch loop processes them
    (after start()). These tests use the async dispatch loop.
    """

    @staticmethod
    async def _publish_and_drain(bus, events, sub_q):
        """Publish events and wait for all to be dispatched to subscriber."""
        for event in events:
            bus.publish(event)
        for _ in range(len(events)):
            await asyncio.wait_for(sub_q.get(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_publish_appears_in_history(self):
        """Events published and dispatched appear in history."""
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()
        try:
            event = NexusEvent(
                event_type=NexusEventType.CUSTOM, data={"test": True}
            )
            bus.publish(event)
            await asyncio.wait_for(sub_q.get(), timeout=2.0)

            history = bus.get_history()
            assert len(history) == 1
            assert history[0]["data"]["test"] is True
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_bounded_history(self):
        """History deque is bounded to capacity (oldest dropped first)."""
        capacity = 10
        bus = EventBus(capacity=capacity)
        sub_q = bus.subscribe()
        await bus.start()
        try:
            # Publish and drain one at a time to avoid queue overflow
            for i in range(20):
                bus.publish(
                    NexusEvent(event_type=NexusEventType.CUSTOM, data={"index": i})
                )
                await asyncio.wait_for(sub_q.get(), timeout=2.0)

            history = bus.get_history()
            assert len(history) == capacity
            # Most recent events should be retained
            indices = [e["data"]["index"] for e in history]
            assert indices == list(range(10, 20))
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_get_history_filter_event_type(self):
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()
        try:
            events = [
                NexusEvent(event_type=NexusEventType.CUSTOM, data={"type": "workflow.started"}),
                NexusEvent(event_type=NexusEventType.HANDLER_CALLED),
                NexusEvent(event_type=NexusEventType.CUSTOM, data={"type": "workflow.completed"}),
            ]
            await self._publish_and_drain(bus, events, sub_q)

            results = bus.get_history(event_type="handler.called")
            assert len(results) == 1
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_get_history_filter_session_id(self):
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()
        try:
            events = [
                NexusEvent(event_type=NexusEventType.CUSTOM, data={"session_id": "s1"}),
                NexusEvent(event_type=NexusEventType.CUSTOM, data={"session_id": "s2"}),
                NexusEvent(event_type=NexusEventType.CUSTOM, data={"session_id": "s1"}),
            ]
            await self._publish_and_drain(bus, events, sub_q)

            results = bus.get_history(session_id="s1")
            assert len(results) == 2
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_get_history_limit(self):
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()
        try:
            events = [
                NexusEvent(event_type=NexusEventType.CUSTOM, data={"i": i})
                for i in range(5)
            ]
            await self._publish_and_drain(bus, events, sub_q)

            results = bus.get_history(limit=2)
            assert len(results) == 2
            # Should return the MOST RECENT 2 events
            assert results[0]["data"]["i"] == 3
            assert results[1]["data"]["i"] == 4
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_publish_handler_registered(self):
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()
        try:
            bus.publish_handler_registered("greet")
            await asyncio.wait_for(sub_q.get(), timeout=2.0)

            history = bus.get_history()
            assert len(history) == 1
            assert history[0]["type"] == "handler.registered"
            assert history[0]["data"]["handler_name"] == "greet"
        finally:
            await bus.stop()

    def test_publish_enqueues_without_start(self):
        """Events published without start() sit in the janus queue."""
        bus = EventBus(capacity=256)
        event = NexusEvent(event_type=NexusEventType.CUSTOM, data={"buffered": True})
        bus.publish(event)
        # Events are in the janus queue, not yet in history
        # (history is populated by the dispatch loop)
        assert bus.get_history() == [] or len(bus.get_history()) == 0


class TestEventBusLegacyDict:
    """Tests for the legacy dict format returned by get_history()."""

    @pytest.mark.asyncio
    async def test_legacy_dict_format(self):
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()
        try:
            bus.publish(
                NexusEvent(
                    event_type=NexusEventType.CUSTOM,
                    data={"type": "test_event", "session_id": "s1"},
                )
            )
            await asyncio.wait_for(sub_q.get(), timeout=2.0)

            history = bus.get_history()
            entry = history[0]
            assert "id" in entry  # evt_TIMESTAMP
            assert entry["id"].startswith("evt_")
            assert "type" in entry
            assert "timestamp" in entry
            assert "data" in entry
            assert "session_id" in entry
        finally:
            await bus.stop()


class TestEventBusSubscribe:
    """Tests for EventBus subscribe and dispatch loop (requires event loop)."""

    @pytest.mark.asyncio
    async def test_subscribe_receives_events(self):
        """Subscriber queue receives events dispatched by the loop."""
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()

        try:
            event = NexusEvent(event_type=NexusEventType.CUSTOM, data={"msg": "hello"})
            bus.publish(event)

            # Wait for dispatch (with timeout to prevent hang)
            received = await asyncio.wait_for(sub_q.get(), timeout=2.0)
            assert received.data == {"msg": "hello"}
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_subscribe_filtered(self):
        """Filtered subscriber only receives matching events."""
        bus = EventBus(capacity=256)
        filtered_q = bus.subscribe_filtered(
            lambda e: e.event_type == NexusEventType.HANDLER_CALLED
        )
        all_q = bus.subscribe()
        await bus.start()

        try:
            # Publish two different event types
            bus.publish(NexusEvent(event_type=NexusEventType.CUSTOM))
            bus.publish(NexusEvent(event_type=NexusEventType.HANDLER_CALLED))

            # All subscriber gets both
            e1 = await asyncio.wait_for(all_q.get(), timeout=2.0)
            e2 = await asyncio.wait_for(all_q.get(), timeout=2.0)
            assert e1.event_type == NexusEventType.CUSTOM
            assert e2.event_type == NexusEventType.HANDLER_CALLED

            # Filtered subscriber gets only HANDLER_CALLED
            received = await asyncio.wait_for(filtered_q.get(), timeout=2.0)
            assert received.event_type == NexusEventType.HANDLER_CALLED

            # Filtered queue should be empty
            assert filtered_q.empty()
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_subscriber_count(self):
        bus = EventBus(capacity=256)
        assert bus.subscriber_count == 0
        bus.subscribe()
        assert bus.subscriber_count == 1
        bus.subscribe_filtered(lambda e: True)
        assert bus.subscriber_count == 2

    @pytest.mark.asyncio
    async def test_start_stop_idempotent(self):
        """Calling start() twice or stop() twice should be safe."""
        bus = EventBus(capacity=256)
        await bus.start()
        await bus.start()  # Second call is no-op
        await bus.stop()
        await bus.stop()  # Second call is no-op

    @pytest.mark.asyncio
    async def test_dispatch_loop_stores_history(self):
        """Events processed by the dispatch loop are stored in history."""
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()

        try:
            bus.publish(NexusEvent(event_type=NexusEventType.CUSTOM, data={"k": "v"}))
            await asyncio.wait_for(sub_q.get(), timeout=2.0)

            history = bus.get_history()
            # History should include events dispatched through the loop
            # (may also include pre-start events stored directly)
            assert any(e["data"].get("k") == "v" for e in history)
        finally:
            await bus.stop()


class TestEventBusThreadSafety:
    """Tests for cross-thread publish safety."""

    @pytest.mark.asyncio
    async def test_publish_from_background_thread(self):
        """Publishing from a background thread should be received by async subscribers."""
        bus = EventBus(capacity=256)
        sub_q = bus.subscribe()
        await bus.start()

        try:
            barrier = threading.Event()

            def bg_publish():
                event = NexusEvent(
                    event_type=NexusEventType.CUSTOM,
                    data={"from_thread": True},
                )
                bus.publish(event)
                barrier.set()

            thread = threading.Thread(target=bg_publish, daemon=True)
            thread.start()
            barrier.wait(timeout=2.0)

            received = await asyncio.wait_for(sub_q.get(), timeout=2.0)
            assert received.data["from_thread"] is True
            thread.join(timeout=1.0)
        finally:
            await bus.stop()
