# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""DataFlow-Nexus event bridge.

Connects the DataFlow Core SDK ``InMemoryEventBus`` (which emits
``DomainEvent`` instances on model writes) to the Nexus ``EventBus``
(which uses ``janus.Queue`` and ``NexusEvent``).

The bridge subscribes to DataFlow events for every registered model
using the 8 ``WRITE_OPERATIONS`` and translates each ``DomainEvent``
into a ``NexusEvent`` that Nexus consumers can handle via
``@app.on_event("dataflow.User.create")``.

Two separate event systems are connected -- they are NOT merged.  Each
maintains its own subscriber lists independently.

Usage::

    bridge = DataFlowEventBridge()
    bridge.install(nexus_event_bus, db)

Or via the Nexus convenience method::

    app.integrate_dataflow(db)

NTR-020
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from nexus.events import EventBus, NexusEvent, NexusEventType

logger = logging.getLogger(__name__)

__all__ = ["DataFlowEventBridge"]

# DataFlow write operations that the bridge subscribes to.
# Matches ``dataflow.core.events.WRITE_OPERATIONS`` exactly (present tense).
_DATAFLOW_WRITE_ACTIONS: List[str] = [
    "create",
    "update",
    "delete",
    "upsert",
    "bulk_create",
    "bulk_update",
    "bulk_delete",
    "bulk_upsert",
]


class DataFlowEventBridge:
    """Bridge between DataFlow Core SDK EventBus and Nexus EventBus.

    DataFlow emits ``DomainEvent`` via the Core SDK ``InMemoryEventBus``.
    This bridge subscribes to those events and re-publishes them as
    ``NexusEvent`` instances on the Nexus ``EventBus``.

    Two separate event systems are connected by this bridge.  They are
    NOT merged -- each maintains its own subscriber lists.
    """

    def __init__(self) -> None:
        self._nexus_bus: EventBus | None = None
        self._subscriptions: List[Tuple[str, Any]] = []
        self._model_names: List[str] = []

    @property
    def model_names(self) -> List[str]:
        """Return the list of model names the bridge is subscribed to."""
        return list(self._model_names)

    @property
    def subscription_count(self) -> int:
        """Total number of Core SDK EventBus subscriptions."""
        return len(self._subscriptions)

    def install(self, nexus_bus: EventBus, db: Any) -> None:
        """Install the bridge between DataFlow and Nexus event buses.

        Subscribes to all 8 write event types for every registered
        DataFlow model.  Core SDK ``InMemoryEventBus.publish()`` does
        exact dict lookup -- no wildcards (R1-1, R2-03).

        Args:
            nexus_bus: The Nexus ``EventBus`` to publish translated events to.
            db: The DataFlow instance (must have ``_models`` dict and
                ``_event_bus`` attribute).
        """
        self._nexus_bus = nexus_bus

        core_event_bus = self._get_core_event_bus(db)
        if core_event_bus is None:
            logger.warning(
                "DataFlow event bridge: Core SDK EventBus not found on "
                "the DataFlow instance.  Bridge will not receive events."
            )
            return

        # Get model names from the DataFlow instance
        models: Dict[str, Any] = getattr(db, "_models", {})
        if not models:
            logger.info(
                "DataFlow event bridge: No models registered -- "
                "no subscriptions created."
            )
            return

        for model_name in models:
            self._model_names.append(model_name)
            for action in _DATAFLOW_WRITE_ACTIONS:
                event_type = f"dataflow.{model_name}.{action}"
                handler = self._make_handler(model_name, action)
                sub_id = core_event_bus.subscribe(event_type, handler)
                self._subscriptions.append((event_type, sub_id))

        logger.info(
            "DataFlow event bridge installed for %d model(s) " "(%d subscriptions).",
            len(self._model_names),
            len(self._subscriptions),
        )

    def _make_handler(self, model_name: str, action: str):
        """Create a handler that translates DomainEvent -> NexusEvent.

        Each handler captures ``model_name`` and ``action`` via closure
        default arguments to avoid late-binding issues.
        """
        nexus_bus = self._nexus_bus

        def handler(domain_event, _model=model_name, _action=action):
            nexus_event = NexusEvent(
                event_type=NexusEventType.CUSTOM,
                data={
                    "type": f"dataflow.{_model}.{_action}",
                    "model": _model,
                    "action": _action,
                    "payload": getattr(domain_event, "payload", {}),
                    "source": "dataflow",
                },
            )
            nexus_bus.publish(nexus_event)

        return handler

    @staticmethod
    def _get_core_event_bus(db: Any):
        """Extract the Core SDK EventBus from a DataFlow instance.

        Tries the canonical ``_event_bus`` attribute first (set by
        ``DataFlowEventMixin._init_events()``), then the public
        ``event_bus`` property.
        """
        # Direct private attribute (canonical, set by DataFlowEventMixin)
        if hasattr(db, "_event_bus") and db._event_bus is not None:
            return db._event_bus

        # Public property (wrapper around _event_bus)
        if hasattr(db, "event_bus"):
            bus = db.event_bus
            if bus is not None:
                return bus

        return None
