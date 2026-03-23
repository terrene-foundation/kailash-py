# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 event bus — central pub/sub for governance events.

The L3EventBus provides thread-safe subscription and emission of L3
governance events. Primitives call ``emit()`` to publish events; listeners
(such as the EATP translator) subscribe to specific event types or to all
events via ``subscribe_all()``.

Thread safety: All listener registration and emission is protected by a
threading.Lock. The L3 primitives themselves use asyncio.Lock (per
AD-L3-04-AMENDED), but the event bus is designed to also work from
synchronous call sites (test harnesses, CLI tools) so it uses
threading.Lock.

Bounded listeners: Each event type key is capped at 1000 listeners to
prevent unbounded memory growth from leaked subscriptions.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

from kaizen.l3.events import L3Event, L3EventType

__all__ = [
    "L3EventBus",
]

logger = logging.getLogger(__name__)

_MAX_LISTENERS_PER_KEY = 1000
_WILDCARD_KEY = "__all__"


class L3EventBus:
    """Central event bus for L3 governance events.

    Usage::

        bus = L3EventBus()
        bus.subscribe(L3EventType.AGENT_SPAWNED, my_handler)
        bus.subscribe_all(audit_handler)

        # Primitives emit events:
        bus.emit(L3Event.create(L3EventType.AGENT_SPAWNED, "agent-1", {...}))
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[L3Event], None]]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(
        self,
        event_type: str | L3EventType,
        listener: Callable[[L3Event], None],
    ) -> None:
        """Subscribe to a specific event type.

        Args:
            event_type: The event type string or L3EventType enum member.
            listener: Callable that receives an L3Event.

        Raises:
            ValueError: If listener limit for this event type is exceeded.
        """
        key = event_type.value if isinstance(event_type, L3EventType) else event_type
        with self._lock:
            current = self._listeners[key]
            if len(current) >= _MAX_LISTENERS_PER_KEY:
                raise ValueError(
                    f"Listener limit ({_MAX_LISTENERS_PER_KEY}) reached for "
                    f"event type {key!r}. Possible listener leak."
                )
            current.append(listener)

    def subscribe_all(self, listener: Callable[[L3Event], None]) -> None:
        """Subscribe to ALL event types via the wildcard key.

        Args:
            listener: Callable that receives every L3Event.

        Raises:
            ValueError: If listener limit for the wildcard key is exceeded.
        """
        self.subscribe(_WILDCARD_KEY, listener)

    def emit(self, event: L3Event) -> None:
        """Emit an event to all matching subscribers.

        Listeners are called synchronously in registration order. If a
        listener raises an exception, it is logged and the remaining
        listeners still receive the event (fail-open on individual
        listener errors; the event bus itself never suppresses emission).

        Args:
            event: The L3Event to dispatch.
        """
        with self._lock:
            # Snapshot listener lists under lock to avoid mutation during iteration
            specific = list(self._listeners.get(event.event_type, []))
            wildcard = list(self._listeners.get(_WILDCARD_KEY, []))

        # Dispatch outside the lock to prevent deadlock if a listener
        # tries to subscribe/unsubscribe.
        for listener in specific + wildcard:
            try:
                listener(event)
            except Exception:
                logger.exception(
                    "Listener %r raised during event %s for agent %s",
                    listener,
                    event.event_type,
                    event.agent_id,
                )

    def unsubscribe(
        self,
        event_type: str | L3EventType,
        listener: Callable[[L3Event], None],
    ) -> bool:
        """Remove a listener from a specific event type.

        Args:
            event_type: The event type to unsubscribe from.
            listener: The listener to remove.

        Returns:
            True if the listener was found and removed, False otherwise.
        """
        key = event_type.value if isinstance(event_type, L3EventType) else event_type
        with self._lock:
            current = self._listeners.get(key, [])
            try:
                current.remove(listener)
                return True
            except ValueError:
                return False

    def unsubscribe_all(self, listener: Callable[[L3Event], None]) -> bool:
        """Remove a wildcard listener.

        Args:
            listener: The listener to remove from the wildcard key.

        Returns:
            True if found and removed, False otherwise.
        """
        return self.unsubscribe(_WILDCARD_KEY, listener)

    def clear(self) -> None:
        """Remove all listeners. Useful for test teardown."""
        with self._lock:
            self._listeners.clear()

    @property
    def listener_count(self) -> int:
        """Total number of registered listeners across all event types."""
        with self._lock:
            return sum(len(v) for v in self._listeners.values())
