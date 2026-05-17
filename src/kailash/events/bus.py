# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Public ``kailash.EventBus`` primitive.

Domain-event publication with pluggable transport backends.  Application
code keeps the same ``publish`` / ``subscribe`` shape whether events
travel in-process (dev/test) or through a broker (production):

    from kailash import EventBus

    bus = EventBus()                       # in-memory (default)
    bus = EventBus(backend="redis")        # Redis Streams (optional extra)

    sub = bus.subscribe("order.created", on_order)
    await bus.publish("order.created", {"id": "o1"}, correlation_id="trace-1")
    await sub.unsubscribe()

Backend selection: explicit ``backend=`` argument →
``KAILASH_EVENTBUS_BACKEND`` env var → ``"memory"`` default.  The same
primitive shape works across every backend (the issue #1054 contract).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from .backends import EventBackend, create_backend
from .domain_event import DomainEvent

logger = logging.getLogger(__name__)

__all__ = ["EventBus", "Subscription"]


class Subscription:
    """Handle returned by :meth:`EventBus.subscribe`.

    Holds the backend subscription id and supports idempotent async
    teardown.  Created internally; users only call :meth:`unsubscribe`.
    """

    def __init__(self, bus: "EventBus", subscription_id: str, event_type: str) -> None:
        self._bus = bus
        self.subscription_id = subscription_id
        self.event_type = event_type
        self._active = True

    @property
    def active(self) -> bool:
        """Whether this subscription is still receiving events."""
        return self._active

    async def unsubscribe(self) -> None:
        """Stop receiving events. Idempotent — safe to call repeatedly."""
        if not self._active:
            return
        self._active = False
        await self._bus._unsubscribe(self.subscription_id)
        logger.debug(
            "eventbus.subscription.closed subscription_id=%s event_type=%s",
            self.subscription_id,
            self.event_type,
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"Subscription(event_type={self.event_type!r}, "
            f"id={self.subscription_id!r}, active={self._active})"
        )


class EventBus:
    """Domain-event publication with pluggable transport backends.

    Args:
        backend: ``"memory"`` (default) or ``"redis"``. When ``None`` the
            ``KAILASH_EVENTBUS_BACKEND`` env var is consulted, then falls
            back to ``"memory"``.  A pre-constructed
            :class:`~kailash.events.backends.EventBackend` instance may
            also be passed for full control.
        redis_url: Connection URL when ``backend="redis"`` (falls back to
            ``KAILASH_EVENTBUS_REDIS_URL`` then
            ``redis://localhost:6379/0``).
        max_subscribers: Upper bound on concurrent subscriptions.

    Example:
        >>> bus = EventBus()
        >>> async def on_evt(payload): print(payload)
        >>> sub = bus.subscribe("user.created", on_evt)
        >>> await bus.publish("user.created", {"id": 1})
        >>> await sub.unsubscribe()
    """

    def __init__(
        self,
        backend: Optional[Union[str, EventBackend]] = None,
        *,
        redis_url: Optional[str] = None,
        max_subscribers: int = 10_000,
    ) -> None:
        if isinstance(backend, EventBackend):
            self._backend: EventBackend = backend
        else:
            self._backend = create_backend(
                backend,
                redis_url=redis_url,
                max_subscribers=max_subscribers,
            )
        self._backend_name = type(self._backend).__name__
        logger.debug("eventbus.init backend=%s", self._backend_name)

    @property
    def backend_name(self) -> str:
        """Class name of the active transport backend."""
        return self._backend_name

    async def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Publish an event to every subscriber of *event_type*.

        Args:
            event_type: Dot-delimited type (e.g. ``"order.created"``).
            payload: JSON-serializable event data.
            correlation_id: Trace id linking related events. Auto-generated
                (UUID4) when omitted; round-trips to subscribers via the
                ``DomainEvent`` envelope (see :meth:`subscribe_events`).
            actor: Optional id of the entity that caused the event.

        Raises:
            ValueError: If *event_type* is empty or *payload* not a dict.
        """
        if not event_type:
            raise ValueError("event_type must be a non-empty string")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        kwargs: Dict[str, Any] = {
            "event_type": event_type,
            "payload": payload,
        }
        if correlation_id is not None:
            kwargs["correlation_id"] = correlation_id
        if actor is not None:
            kwargs["actor"] = actor
        event = DomainEvent(**kwargs)
        logger.debug(
            "eventbus.publish event_type=%s correlation_id=%s backend=%s",
            event_type,
            event.correlation_id,
            self._backend_name,
        )
        await self._backend.publish(event)

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> Subscription:
        """Register an async *handler* for *event_type*.

        The handler is invoked with the event payload dict. Use
        :meth:`subscribe_events` instead when the handler needs the full
        envelope (``correlation_id`` for trace propagation).

        Returns:
            A :class:`Subscription`; call ``await sub.unsubscribe()`` to
            stop receiving events.
        """

        async def _payload_only(event: DomainEvent) -> None:
            await handler(dict(event.payload))

        sub_id = self._backend.register(event_type, _payload_only)
        return Subscription(self, sub_id, event_type)

    def subscribe_events(
        self,
        event_type: str,
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> Subscription:
        """Like :meth:`subscribe` but the handler receives the full
        :class:`DomainEvent` (``event_type`` / ``payload`` /
        ``correlation_id`` / ``timestamp`` / ``actor``).

        Use this when the subscriber needs ``correlation_id`` for trace
        propagation.  The full :class:`DomainEvent` is delivered unchanged
        so ``correlation_id`` / ``actor`` / ``timestamp`` round-trip
        natively (the backend handler signature IS ``DomainEvent``).
        """
        sub_id = self._backend.register(event_type, handler)
        return Subscription(self, sub_id, event_type)

    async def _unsubscribe(self, subscription_id: str) -> None:
        await self._backend.unregister(subscription_id)

    async def close(self) -> None:
        """Release backend resources (broker connections, consumer tasks)."""
        await self._backend.close()
