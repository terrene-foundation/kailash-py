# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NTR-020: DataFlow-Nexus event bridge.

Tests the DataFlowEventBridge class which connects the DataFlow Core
SDK EventBus (InMemoryEventBus + DomainEvent) to the Nexus EventBus
(janus.Queue + NexusEvent).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from nexus.bridges.dataflow import DataFlowEventBridge, _DATAFLOW_WRITE_ACTIONS
from nexus.events import EventBus, NexusEvent, NexusEventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeCoreEventBus:
    """Minimal fake of InMemoryEventBus for unit testing.

    Supports subscribe() and publish() with exact event_type matching.
    Does NOT require kailash to be installed.
    """

    def __init__(self):
        self._handlers: Dict[str, list] = {}
        self._sub_counter = 0

    def subscribe(self, event_type: str, handler) -> str:
        self._sub_counter += 1
        sub_id = f"sub_{self._sub_counter}"
        self._handlers.setdefault(event_type, []).append(handler)
        return sub_id

    def publish(self, event):
        handlers = self._handlers.get(event.event_type, [])
        for h in handlers:
            h(event)


class FakeDomainEvent:
    """Minimal stand-in for kailash DomainEvent."""

    def __init__(self, event_type: str, payload: Dict[str, Any] = None):
        self.event_type = event_type
        self.payload = payload or {}


# ---------------------------------------------------------------------------
# Bridge installation
# ---------------------------------------------------------------------------


class TestBridgeInstallation:
    def test_install_creates_subscriptions_for_all_models(self):
        """Verify 8 subscriptions per model are created."""
        core_bus = FakeCoreEventBus()
        nexus_bus = MagicMock(spec=EventBus)

        db = MagicMock()
        db._event_bus = core_bus
        db._models = {"User": MagicMock(), "Order": MagicMock()}

        bridge = DataFlowEventBridge()
        bridge.install(nexus_bus, db)

        assert bridge.subscription_count == 16  # 8 actions x 2 models
        assert set(bridge.model_names) == {"User", "Order"}

    def test_install_subscribes_to_correct_event_types(self):
        """Verify the exact event types subscribed."""
        core_bus = FakeCoreEventBus()
        nexus_bus = MagicMock(spec=EventBus)

        db = MagicMock()
        db._event_bus = core_bus
        db._models = {"User": MagicMock()}

        bridge = DataFlowEventBridge()
        bridge.install(nexus_bus, db)

        subscribed_types = list(core_bus._handlers.keys())
        expected = [f"dataflow.User.{action}" for action in _DATAFLOW_WRITE_ACTIONS]
        assert sorted(subscribed_types) == sorted(expected)

    def test_install_with_no_models(self):
        """Verify bridge handles empty model registry gracefully."""
        core_bus = FakeCoreEventBus()
        nexus_bus = MagicMock(spec=EventBus)

        db = MagicMock()
        db._event_bus = core_bus
        db._models = {}

        bridge = DataFlowEventBridge()
        bridge.install(nexus_bus, db)

        assert bridge.subscription_count == 0
        assert bridge.model_names == []

    def test_install_without_event_bus(self):
        """Verify bridge handles missing event bus gracefully."""
        nexus_bus = MagicMock(spec=EventBus)

        db = MagicMock(spec=[])  # No _event_bus attribute

        bridge = DataFlowEventBridge()
        bridge.install(nexus_bus, db)

        assert bridge.subscription_count == 0


# ---------------------------------------------------------------------------
# Event translation
# ---------------------------------------------------------------------------


class TestEventTranslation:
    def test_domain_event_translated_to_nexus_event(self):
        """Verify DomainEvent is translated to NexusEvent with correct data."""
        core_bus = FakeCoreEventBus()
        nexus_bus = MagicMock(spec=EventBus)

        db = MagicMock()
        db._event_bus = core_bus
        db._models = {"User": MagicMock()}

        bridge = DataFlowEventBridge()
        bridge.install(nexus_bus, db)

        # Simulate a DataFlow write event
        domain_event = FakeDomainEvent(
            event_type="dataflow.User.create",
            payload={"model": "User", "operation": "create", "record_id": "u1"},
        )
        core_bus.publish(domain_event)

        # Verify Nexus EventBus received the translated event
        nexus_bus.publish.assert_called_once()
        nexus_event: NexusEvent = nexus_bus.publish.call_args[0][0]

        assert nexus_event.event_type == NexusEventType.CUSTOM
        assert nexus_event.data["type"] == "dataflow.User.create"
        assert nexus_event.data["model"] == "User"
        assert nexus_event.data["action"] == "create"
        assert nexus_event.data["payload"]["record_id"] == "u1"
        assert nexus_event.data["source"] == "dataflow"

    def test_all_8_actions_translate_correctly(self):
        """Verify all 8 write operations produce correct NexusEvents."""
        core_bus = FakeCoreEventBus()
        nexus_bus = MagicMock(spec=EventBus)

        db = MagicMock()
        db._event_bus = core_bus
        db._models = {"Order": MagicMock()}

        bridge = DataFlowEventBridge()
        bridge.install(nexus_bus, db)

        for action in _DATAFLOW_WRITE_ACTIONS:
            nexus_bus.reset_mock()

            domain_event = FakeDomainEvent(
                event_type=f"dataflow.Order.{action}",
                payload={"model": "Order", "operation": action, "record_id": "x"},
            )
            core_bus.publish(domain_event)

            nexus_bus.publish.assert_called_once()
            nexus_event: NexusEvent = nexus_bus.publish.call_args[0][0]
            assert nexus_event.data["type"] == f"dataflow.Order.{action}"
            assert nexus_event.data["action"] == action

    def test_unsubscribed_event_type_not_bridged(self):
        """Verify events for unsubscribed types are not bridged."""
        core_bus = FakeCoreEventBus()
        nexus_bus = MagicMock(spec=EventBus)

        db = MagicMock()
        db._event_bus = core_bus
        db._models = {"User": MagicMock()}

        bridge = DataFlowEventBridge()
        bridge.install(nexus_bus, db)

        # Emit event for a model not in _models
        domain_event = FakeDomainEvent(
            event_type="dataflow.Product.create",
            payload={"model": "Product", "operation": "create", "record_id": "p1"},
        )
        core_bus.publish(domain_event)

        nexus_bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# Nexus.integrate_dataflow() convenience method
# ---------------------------------------------------------------------------


class TestIntegrateDataflow:
    def test_integrate_dataflow_returns_self(self):
        """Verify integrate_dataflow returns Nexus instance for chaining."""
        from nexus.core import Nexus

        app = Nexus()

        db = MagicMock()
        db._event_bus = FakeCoreEventBus()
        db._models = {}

        result = app.integrate_dataflow(db)
        assert result is app

    def test_integrate_dataflow_creates_bridge(self):
        """Verify integrate_dataflow installs bridge subscriptions."""
        from nexus.core import Nexus

        core_bus = FakeCoreEventBus()
        app = Nexus()

        db = MagicMock()
        db._event_bus = core_bus
        db._models = {"User": MagicMock(), "Order": MagicMock()}

        app.integrate_dataflow(db)

        # Verify Core SDK bus has subscriptions for both models
        all_types = list(core_bus._handlers.keys())
        user_types = [t for t in all_types if "User" in t]
        order_types = [t for t in all_types if "Order" in t]
        assert len(user_types) == 8
        assert len(order_types) == 8


# ---------------------------------------------------------------------------
# Write actions constant alignment
# ---------------------------------------------------------------------------


class TestWriteActionsAlignment:
    def test_bridge_actions_match_dataflow_write_operations(self):
        """Verify bridge actions match DataFlow WRITE_OPERATIONS constant."""
        # The canonical list of write operations (must match dataflow.core.events.WRITE_OPERATIONS)
        expected_write_ops = [
            "create",
            "update",
            "delete",
            "upsert",
            "bulk_create",
            "bulk_update",
            "bulk_delete",
            "bulk_upsert",
        ]
        assert _DATAFLOW_WRITE_ACTIONS == expected_write_ops
