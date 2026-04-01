# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
DataFlow Event Mixin -- Core SDK EventBus integration for write events.

Provides ``DataFlowEventMixin`` which adds write-event emission to the
``DataFlow`` class using the Core SDK's ``InMemoryEventBus``.  Events are
emitted after every successful write operation (create, update, delete,
upsert and their bulk counterparts).  When no subscribers are registered
the overhead is negligible (a single dict lookup + early return).

TSG-201
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "DataFlowEventMixin",
    "WRITE_OPERATIONS",
]

WRITE_OPERATIONS: List[str] = [
    "create",
    "update",
    "delete",
    "upsert",
    "bulk_create",
    "bulk_update",
    "bulk_delete",
    "bulk_upsert",
]


class DataFlowEventMixin:
    """Mixin that adds write-event emission to DataFlow via Core SDK EventBus.

    Call ``_init_events()`` in ``DataFlow.__init__`` to set up the bus.
    Write methods call ``_emit_write_event()`` after a successful operation.

    External consumers subscribe through ``db.event_bus`` or the convenience
    helper ``db.on_model_change(model, handler)``.
    """

    _event_bus: Any = None  # Set by _init_events()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_events(self) -> None:
        """Initialize the event bus.  Called once in ``DataFlow.__init__``."""
        try:
            from kailash.middleware.communication.backends.memory import InMemoryEventBus
            self._event_bus = InMemoryEventBus()
        except ImportError:
            self._event_bus = None

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def _emit_write_event(
        self,
        model_name: str,
        operation: str,
        record_id: Optional[str] = None,
    ) -> None:
        """Emit a ``DomainEvent`` for a write operation.

        No-op when the bus is not initialised or when no subscribers are
        registered for this event type (``InMemoryEventBus.publish()``
        returns immediately when the bucket is empty).
        """
        if self._event_bus is None:
            return

        from kailash.middleware.communication.domain_event import DomainEvent

        event_type = f"dataflow.{model_name}.{operation}"
        event = DomainEvent(
            event_type=event_type,
            payload={
                "model": model_name,
                "operation": operation,
                "record_id": record_id,
            },
        )

        try:
            self._event_bus.publish(event)
        except Exception:
            # Fire-and-forget -- never let event emission break a write path.
            logger.debug("Failed to emit event %s", event_type, exc_info=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def event_bus(self) -> Any:
        """Expose the underlying ``EventBus`` for external subscriptions."""
        return self._event_bus

    def on_model_change(
        self,
        model_name: str,
        handler: Callable,
    ) -> List[str]:
        """Subscribe *handler* to all 8 write event types for *model_name*.

        Uses ``WRITE_OPERATIONS`` constant -- no wildcards (R1-1).

        Args:
            model_name: The model to observe (e.g. ``"User"``).
            handler: Callable invoked with a ``DomainEvent`` argument.

        Returns:
            List of subscription IDs (one per write operation type).

        Raises:
            DataFlowConfigError: If called before ``db.initialize()``.
        """
        if not getattr(self, "_connected", False):
            from dataflow.exceptions import DataFlowError

            raise DataFlowError("on_model_change() requires db.initialize() first")

        sub_ids: List[str] = []
        for op in WRITE_OPERATIONS:
            event_type = f"dataflow.{model_name}.{op}"
            sub_id = self._event_bus.subscribe(event_type, handler)
            sub_ids.append(sub_id)
        return sub_ids
