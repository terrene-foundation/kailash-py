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

import functools
import logging
import threading
from collections import defaultdict
from typing import Any, Callable

from kaizen.l3.events import L3Event, L3EventType
from kaizen.utils.credential_scrub import scrub_remote_error

__all__ = [
    "L3EventBus",
]

logger = logging.getLogger(__name__)

_MAX_LISTENERS_PER_KEY = 1000
_WILDCARD_KEY = "__all__"

# Bound on how far ``_safe_listener_name`` will unwrap a partial chain. Deep
# nesting is pathological, not idiomatic; the bound keeps the helper O(1) and
# terminating on any custom ``partial`` subclass.
_MAX_PARTIAL_UNWRAP_DEPTH = 8


def _safe_listener_name(listener: object) -> str:
    """Return a diagnostic identifier for a listener that cannot carry its state.

    Deliberately duplicates ``kaizen.core.autonomy.hooks.manager``'s
    ``safe_handler_name`` rather than importing it: the L3 governance event bus
    must not acquire a dependency on the autonomy hook manager for a naming
    helper. The two definitions are pinned to identical behaviour by
    ``tests/regression/test_f11_caller_repr_does_not_leak.py``, so they cannot
    silently diverge.

    ``functools.partial`` wrappers are unwrapped because ``partial`` is the
    idiomatic way to register a listener that needs bound config -- the exact
    shape whose identity matters most -- and ``type(p).__name__`` is the
    constant ``"partial"`` for every one of them. ``__qualname__`` is trusted
    only when it is actually a string; it is a SOURCE-level identifier fixed at
    ``def``/``class`` time, not runtime state, so unlike ``repr`` it cannot pick
    up a bound credential.
    """
    inner = listener
    unwrapped = 0
    while (
        isinstance(inner, functools.partial) and unwrapped < _MAX_PARTIAL_UNWRAP_DEPTH
    ):
        inner = inner.func
        unwrapped += 1

    qualname = getattr(inner, "__qualname__", None)
    base = qualname if isinstance(qualname, str) else type(inner).__name__
    return f"partial({base})" if unwrapped else base


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
            except Exception as exc:
                # ``logger.error``, NOT ``logger.exception``: the traceback's
                # final frame renders the caller's raised exception raw, which
                # would re-leak what the scrub below removes.
                #
                # Three fields are retained -- they identify WHICH listener
                # failed on WHICH event, which is the whole diagnostic. Each is
                # retained because it CANNOT carry caller-supplied state, which
                # is the test that matters here; "not exception-derived" is NOT
                # that test, and an earlier revision of this comment used it to
                # justify rendering ``listener`` via ``%r``. A listener is
                # arbitrary user code that can close over or hold credentials,
                # so its repr was exactly as unsafe as the exception text on
                # the same line:
                #
                #   Listener functools.partial(<function forward>,
                #     url='https://svc:<CREDENTIAL>@sink.example.invalid')
                #     raised during event ...
                #
                # * ``_safe_listener_name(listener)`` -- a source-level
                #   identifier (see its docstring), never runtime state.
                # * ``event.event_type`` -- a bus key, set by the emitting
                #   primitive, not by a listener.
                # * ``event.agent_id`` -- validated non-empty in
                #   ``L3Event.__post_init__``; an agent instance ID.
                #
                # ``event.details`` is NOT logged: it is the one event field
                # that carries primitive-supplied payload.
                logger.error(
                    "Listener %s raised during event %s for agent %s: %s",
                    _safe_listener_name(listener),
                    event.event_type,
                    event.agent_id,
                    scrub_remote_error(exc),
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
