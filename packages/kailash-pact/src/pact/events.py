# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Event bus for PactEngine -- publish-subscribe event system with bounded history.

EventBus provides a simple in-process pub/sub mechanism for governance events.
History is bounded to maxlen entries (default 10000) per trust-plane-security.md
rule 4 (bounded collections). Thread-safe per pact-governance.md rule 8.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = ["EventBus"]


class EventBus:
    """In-process event bus with bounded history and thread safety.

    Events are typed strings. Subscribers receive the event data dict.
    All emitted events are stored in a bounded history deque for later
    retrieval.

    Args:
        maxlen: Maximum number of events to retain in history.
            Defaults to 10000 per trust-plane-security.md rule 4.
        max_subscribers: Maximum subscribers per event type.
            Defaults to 1000. Prevents unbounded growth.
    """

    def __init__(self, maxlen: int = 10000, max_subscribers: int = 1000) -> None:
        self._maxlen = maxlen
        self._max_subscribers = max_subscribers
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def subscribe(
        self, event_type: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback for an event type.

        Args:
            event_type: The event type string to subscribe to.
            callback: A callable that receives the event data dict.

        Raises:
            ValueError: If max subscribers reached for this event type.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if len(self._subscribers[event_type]) >= self._max_subscribers:
                raise ValueError(
                    f"Max subscribers ({self._max_subscribers}) reached for '{event_type}'"
                )
            self._subscribers[event_type].append(callback)

    def unsubscribe(
        self, event_type: str, callback: Callable[[dict[str, Any]], None]
    ) -> bool:
        """Remove a callback for an event type.

        Args:
            event_type: The event type string.
            callback: The callback to remove.

        Returns:
            True if the callback was found and removed, False otherwise.
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                    return True
                except ValueError:
                    return False
            return False

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event to all subscribers and record in history.

        Args:
            event_type: The event type string.
            data: Event data dict (passed to subscribers and stored in history).
        """
        record = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._history.append(record)
            subscribers = list(self._subscribers.get(event_type, []))

        # Call subscribers outside lock to avoid deadlock
        for callback in subscribers:
            try:
                callback(data)
            except Exception:
                logger.exception(
                    "EventBus subscriber raised exception for event_type=%s -- "
                    "continuing with remaining subscribers",
                    event_type,
                )

    def get_history(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """Retrieve event history, optionally filtered by type.

        Args:
            event_type: If provided, return only events of this type.
                If None, return all events.

        Returns:
            A list of event dicts (copies from the history deque).
        """
        with self._lock:
            if event_type is None:
                return list(self._history)
            return [e for e in self._history if e["event_type"] == event_type]
