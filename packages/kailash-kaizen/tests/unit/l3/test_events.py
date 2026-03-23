# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for L3 event types and event bus.

Covers:
- L3Event creation, frozen invariant, validation
- L3EventType enum membership
- L3EventBus subscribe/emit/unsubscribe
- L3EventBus thread safety
- L3EventBus subscribe_all wildcard
- L3EventBus listener limit enforcement
- NaN/Inf sanitization in event details
"""

from __future__ import annotations

import math
import threading
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from kaizen.l3.events import L3Event, L3EventType, _sanitize_details
from kaizen.l3.event_hooks import L3EventBus


# ---------------------------------------------------------------------------
# L3EventType tests
# ---------------------------------------------------------------------------


class TestL3EventType:
    """L3EventType enum: 15 canonical governance event types."""

    def test_all_members_exist(self):
        expected = {
            "ENVELOPE_VIOLATION",
            "ENVELOPE_REGISTERED",
            "ENVELOPE_SPLIT",
            "AGENT_SPAWNED",
            "AGENT_TERMINATED",
            "AGENT_STATE_CHANGED",
            "MESSAGE_ROUTED",
            "MESSAGE_DEAD_LETTERED",
            "PLAN_VALIDATED",
            "PLAN_EXECUTED",
            "PLAN_NODE_COMPLETED",
            "PLAN_NODE_FAILED",
            "PLAN_NODE_HELD",
            "CONTEXT_SCOPE_CREATED",
            "CONTEXT_ACCESS_DENIED",
        }
        actual = {m.name for m in L3EventType}
        assert actual == expected

    def test_is_str_enum(self):
        """L3EventType members are usable as strings."""
        assert isinstance(L3EventType.AGENT_SPAWNED, str)
        assert L3EventType.AGENT_SPAWNED == "agent_spawned"

    def test_member_count(self):
        assert len(L3EventType) == 15


# ---------------------------------------------------------------------------
# L3Event tests
# ---------------------------------------------------------------------------


class TestL3Event:
    """L3Event frozen dataclass: validation and serialization."""

    def test_create_basic(self):
        event = L3Event(
            event_type="agent_spawned",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"spec_id": "researcher"},
        )
        assert event.event_type == "agent_spawned"
        assert event.agent_id == "agent-001"
        assert event.details == {"spec_id": "researcher"}

    def test_frozen_invariant(self):
        event = L3Event(
            event_type="agent_spawned",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
        )
        with pytest.raises(AttributeError):
            event.agent_id = "agent-002"  # type: ignore[misc]

    def test_empty_event_type_rejected(self):
        with pytest.raises(ValueError, match="event_type must not be empty"):
            L3Event(event_type="", agent_id="a", timestamp="t")

    def test_empty_agent_id_rejected(self):
        with pytest.raises(ValueError, match="agent_id must not be empty"):
            L3Event(event_type="x", agent_id="", timestamp="t")

    def test_empty_timestamp_rejected(self):
        with pytest.raises(ValueError, match="timestamp must not be empty"):
            L3Event(event_type="x", agent_id="a", timestamp="")

    def test_to_dict_round_trip(self):
        event = L3Event(
            event_type="envelope_violation",
            agent_id="agent-002",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"dimension": "financial", "usage_pct": 0.95},
        )
        d = event.to_dict()
        restored = L3Event.from_dict(d)
        assert restored == event

    def test_from_dict_missing_details(self):
        d = {
            "event_type": "agent_spawned",
            "agent_id": "agent-001",
            "timestamp": "2026-03-23T12:00:00+00:00",
        }
        event = L3Event.from_dict(d)
        assert event.details == {}

    def test_create_factory_method(self):
        event = L3Event.create(
            L3EventType.AGENT_SPAWNED,
            "agent-001",
            {"spec_id": "researcher"},
        )
        assert event.event_type == "agent_spawned"
        assert event.agent_id == "agent-001"
        assert event.details == {"spec_id": "researcher"}
        # Timestamp should be a valid ISO 8601 string
        datetime.fromisoformat(event.timestamp)

    def test_create_factory_no_details(self):
        event = L3Event.create(L3EventType.PLAN_VALIDATED, "agent-001")
        assert event.details == {}

    def test_nan_in_details_sanitized(self):
        event = L3Event(
            event_type="envelope_violation",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"cost": float("nan"), "limit": 100.0},
        )
        # NaN should be replaced with a sentinel string
        assert isinstance(event.details["cost"], str)
        assert "non-finite" in event.details["cost"]
        # Normal float should be preserved
        assert event.details["limit"] == 100.0

    def test_inf_in_details_sanitized(self):
        event = L3Event(
            event_type="envelope_violation",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"cost": float("inf")},
        )
        assert isinstance(event.details["cost"], str)
        assert "non-finite" in event.details["cost"]

    def test_negative_inf_in_details_sanitized(self):
        event = L3Event(
            event_type="envelope_violation",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"cost": float("-inf")},
        )
        assert isinstance(event.details["cost"], str)
        assert "non-finite" in event.details["cost"]

    def test_nested_dict_nan_sanitized(self):
        event = L3Event(
            event_type="envelope_violation",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"inner": {"bad_value": float("nan")}},
        )
        assert isinstance(event.details["inner"]["bad_value"], str)
        assert "non-finite" in event.details["inner"]["bad_value"]


# ---------------------------------------------------------------------------
# _sanitize_details tests
# ---------------------------------------------------------------------------


class TestSanitizeDetails:
    """Direct tests for the sanitization helper."""

    def test_normal_values_unchanged(self):
        d = {"a": 1, "b": "hello", "c": 3.14, "d": True, "e": None}
        assert _sanitize_details(d) == d

    def test_nan_replaced(self):
        result = _sanitize_details({"x": float("nan")})
        assert isinstance(result["x"], str)

    def test_inf_replaced(self):
        result = _sanitize_details({"x": float("inf")})
        assert isinstance(result["x"], str)

    def test_nested_dict_sanitized(self):
        result = _sanitize_details({"outer": {"inner": float("nan")}})
        assert isinstance(result["outer"]["inner"], str)

    def test_empty_dict(self):
        assert _sanitize_details({}) == {}


# ---------------------------------------------------------------------------
# L3EventBus tests
# ---------------------------------------------------------------------------


class TestL3EventBus:
    """L3EventBus: subscribe, emit, unsubscribe, thread safety."""

    def _make_event(self, event_type: str = "agent_spawned") -> L3Event:
        return L3Event(
            event_type=event_type,
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"test": True},
        )

    def test_subscribe_and_emit(self):
        bus = L3EventBus()
        received: list[L3Event] = []
        bus.subscribe(L3EventType.AGENT_SPAWNED, received.append)

        event = self._make_event("agent_spawned")
        bus.emit(event)

        assert len(received) == 1
        assert received[0] is event

    def test_subscribe_by_string(self):
        bus = L3EventBus()
        received: list[L3Event] = []
        bus.subscribe("agent_spawned", received.append)

        bus.emit(self._make_event("agent_spawned"))
        assert len(received) == 1

    def test_no_cross_delivery(self):
        """Events for one type should not be delivered to another type's subscribers."""
        bus = L3EventBus()
        received: list[L3Event] = []
        bus.subscribe(L3EventType.AGENT_SPAWNED, received.append)

        bus.emit(self._make_event("agent_terminated"))
        assert len(received) == 0

    def test_subscribe_all(self):
        bus = L3EventBus()
        received: list[L3Event] = []
        bus.subscribe_all(received.append)

        bus.emit(self._make_event("agent_spawned"))
        bus.emit(self._make_event("envelope_violation"))
        bus.emit(self._make_event("plan_executed"))

        assert len(received) == 3

    def test_subscribe_all_plus_specific(self):
        """Wildcard and specific listeners both receive the event."""
        bus = L3EventBus()
        all_received: list[L3Event] = []
        specific_received: list[L3Event] = []

        bus.subscribe_all(all_received.append)
        bus.subscribe(L3EventType.AGENT_SPAWNED, specific_received.append)

        bus.emit(self._make_event("agent_spawned"))

        assert len(all_received) == 1
        assert len(specific_received) == 1

    def test_unsubscribe(self):
        bus = L3EventBus()
        received: list[L3Event] = []
        bus.subscribe(L3EventType.AGENT_SPAWNED, received.append)

        result = bus.unsubscribe(L3EventType.AGENT_SPAWNED, received.append)
        assert result is True

        bus.emit(self._make_event("agent_spawned"))
        assert len(received) == 0

    def test_unsubscribe_nonexistent(self):
        bus = L3EventBus()
        result = bus.unsubscribe(L3EventType.AGENT_SPAWNED, lambda e: None)
        assert result is False

    def test_unsubscribe_all(self):
        bus = L3EventBus()
        received: list[L3Event] = []
        bus.subscribe_all(received.append)
        bus.unsubscribe_all(received.append)

        bus.emit(self._make_event("agent_spawned"))
        assert len(received) == 0

    def test_clear(self):
        bus = L3EventBus()
        bus.subscribe(L3EventType.AGENT_SPAWNED, lambda e: None)
        bus.subscribe_all(lambda e: None)
        assert bus.listener_count > 0

        bus.clear()
        assert bus.listener_count == 0

    def test_listener_count(self):
        bus = L3EventBus()
        bus.subscribe(L3EventType.AGENT_SPAWNED, lambda e: None)
        bus.subscribe(L3EventType.AGENT_SPAWNED, lambda e: None)
        bus.subscribe(L3EventType.PLAN_EXECUTED, lambda e: None)
        assert bus.listener_count == 3

    def test_listener_error_does_not_suppress_others(self):
        """A failing listener must not prevent other listeners from receiving the event."""
        bus = L3EventBus()
        received: list[L3Event] = []

        def bad_listener(event: L3Event) -> None:
            raise RuntimeError("boom")

        bus.subscribe(L3EventType.AGENT_SPAWNED, bad_listener)
        bus.subscribe(L3EventType.AGENT_SPAWNED, received.append)

        bus.emit(self._make_event("agent_spawned"))
        assert len(received) == 1

    def test_listener_limit_enforced(self):
        bus = L3EventBus()
        for _ in range(1000):
            bus.subscribe(L3EventType.AGENT_SPAWNED, lambda e: None)

        with pytest.raises(ValueError, match="Listener limit"):
            bus.subscribe(L3EventType.AGENT_SPAWNED, lambda e: None)

    def test_thread_safety_concurrent_emit(self):
        """Multiple threads emitting concurrently must not corrupt state."""
        bus = L3EventBus()
        received: list[L3Event] = []
        lock = threading.Lock()

        def safe_append(event: L3Event) -> None:
            with lock:
                received.append(event)

        bus.subscribe_all(safe_append)

        threads = []
        events_per_thread = 100
        num_threads = 10

        def emit_batch(thread_id: int) -> None:
            for i in range(events_per_thread):
                event = L3Event(
                    event_type="agent_spawned",
                    agent_id=f"thread-{thread_id}-event-{i}",
                    timestamp="2026-03-23T12:00:00+00:00",
                )
                bus.emit(event)

        for t_id in range(num_threads):
            t = threading.Thread(target=emit_batch, args=(t_id,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(received) == num_threads * events_per_thread

    def test_thread_safety_concurrent_subscribe_and_emit(self):
        """Subscribing and emitting concurrently must not raise."""
        bus = L3EventBus()
        errors: list[Exception] = []

        def subscriber_thread() -> None:
            try:
                for _ in range(50):
                    bus.subscribe("agent_spawned", lambda e: None)
            except Exception as exc:
                errors.append(exc)

        def emitter_thread() -> None:
            try:
                for _ in range(50):
                    bus.emit(
                        L3Event(
                            event_type="agent_spawned",
                            agent_id="test",
                            timestamp="2026-03-23T12:00:00+00:00",
                        )
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=subscriber_thread),
            threading.Thread(target=emitter_thread),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
