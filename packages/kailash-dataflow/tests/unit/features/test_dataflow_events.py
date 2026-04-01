# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for TSG-201: DataFlowEventMixin -- Core SDK EventBus integration.

Tests:
- Event bus initialization
- DomainEvent emission with correct payload field
- WRITE_OPERATIONS constant
- on_model_change subscription
- Zero-subscriber no-op behavior
- hasattr guard for backward compat
"""

from __future__ import annotations

import pytest

from dataflow.core.events import WRITE_OPERATIONS, DataFlowEventMixin


# ---------------------------------------------------------------------------
# WRITE_OPERATIONS constant
# ---------------------------------------------------------------------------


def test_write_operations_constant_has_exactly_8_entries():
    """WRITE_OPERATIONS must list all 8 write operation names."""
    assert len(WRITE_OPERATIONS) == 8
    expected = {
        "create",
        "update",
        "delete",
        "upsert",
        "bulk_create",
        "bulk_update",
        "bulk_delete",
        "bulk_upsert",
    }
    assert set(WRITE_OPERATIONS) == expected


# ---------------------------------------------------------------------------
# Mixin lifecycle
# ---------------------------------------------------------------------------


class FakeDataFlow(DataFlowEventMixin):
    """Minimal stand-in that mimics the pieces of DataFlow the mixin needs."""

    _connected = False


class TestEventMixinInit:
    def test_init_events_creates_bus(self):
        obj = FakeDataFlow()
        assert obj._event_bus is None  # before init
        obj._init_events()
        assert obj._event_bus is not None

    def test_event_bus_property(self):
        obj = FakeDataFlow()
        obj._init_events()
        assert obj.event_bus is obj._event_bus


# ---------------------------------------------------------------------------
# _emit_write_event
# ---------------------------------------------------------------------------


class TestEmitWriteEvent:
    def test_emit_publishes_domain_event_with_payload(self):
        """DomainEvent must use the `payload` field (NOT `data` -- R2-01)."""
        obj = FakeDataFlow()
        obj._init_events()

        captured = []
        obj._event_bus.subscribe(
            "dataflow.User.create", lambda evt: captured.append(evt)
        )

        obj._emit_write_event("User", "create", record_id="u1")

        assert len(captured) == 1
        evt = captured[0]
        assert evt.event_type == "dataflow.User.create"
        assert evt.payload == {
            "model": "User",
            "operation": "create",
            "record_id": "u1",
        }

    def test_emit_correct_field_name_is_payload(self):
        """Regression: payload field must not be 'data' (R2-01)."""
        obj = FakeDataFlow()
        obj._init_events()

        captured = []
        obj._event_bus.subscribe(
            "dataflow.Order.update", lambda evt: captured.append(evt)
        )

        obj._emit_write_event("Order", "update", record_id="o1")

        evt = captured[0]
        # DomainEvent stores in .payload, not .data
        assert hasattr(evt, "payload")
        assert evt.payload["operation"] == "update"

    def test_zero_subscriber_noop(self):
        """Emit with no subscribers must not raise."""
        obj = FakeDataFlow()
        obj._init_events()
        # No subscribers -- should silently return
        obj._emit_write_event("User", "create", record_id="u1")

    def test_emit_when_bus_is_none(self):
        """If event bus was never initialised, emit must be a no-op."""
        obj = FakeDataFlow()
        assert obj._event_bus is None
        obj._emit_write_event("User", "create", record_id="u1")  # no error


# ---------------------------------------------------------------------------
# on_model_change
# ---------------------------------------------------------------------------


class TestOnModelChange:
    def test_subscribes_all_8_write_operations(self):
        obj = FakeDataFlow()
        obj._init_events()
        obj._connected = True

        handler = lambda evt: None  # noqa: E731
        sub_ids = obj.on_model_change("User", handler)

        assert len(sub_ids) == 8

    def test_on_model_change_before_connected_raises(self):
        obj = FakeDataFlow()
        obj._init_events()
        obj._connected = False

        with pytest.raises(Exception, match="requires db.initialize"):
            obj.on_model_change("User", lambda evt: None)

    def test_on_model_change_receives_events(self):
        obj = FakeDataFlow()
        obj._init_events()
        obj._connected = True

        captured = []
        obj.on_model_change("User", lambda evt: captured.append(evt))

        # Emit all 8 operations
        for op in WRITE_OPERATIONS:
            obj._emit_write_event("User", op, record_id=None)

        assert len(captured) == 8
        received_ops = [e.payload["operation"] for e in captured]
        assert set(received_ops) == set(WRITE_OPERATIONS)


# ---------------------------------------------------------------------------
# hasattr guard (backward compat)
# ---------------------------------------------------------------------------


def test_hasattr_guard_no_mixin():
    """A DataFlow-like class without the mixin must not crash on the guard."""

    class PlainObj:
        pass

    obj = PlainObj()
    # The pattern used in Express write methods:
    if hasattr(obj, "_emit_write_event"):
        obj._emit_write_event("User", "create", record_id="u1")
    # If we get here, the guard worked correctly -- no AttributeError.
