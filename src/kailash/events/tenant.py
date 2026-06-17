# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tenant-scoped wrapper for the public :class:`kailash.EventBus`.

Multi-tenant applications need pub/sub isolation: a publish on tenant
``acme``'s bus MUST fan out only to ``acme``'s subscribers, never to
tenant ``globex``'s. The :class:`EventBus` transport dispatches by exact
``event_type`` match (the in-memory backend keys a dict on the type; the
Redis Streams backend uses one stream per type), so prefixing every topic
with the tenant id — ``"acme:order.created"`` vs ``"globex:order.created"``
— yields complete, backend-agnostic isolation with zero changes to the
transport.

:class:`TenantScopedEventBus` is that prefixing, packaged so applications
do not re-implement it (and drift on the isolation guarantee):

    from kailash.events import EventBus, TenantScopedEventBus

    bus = EventBus()                       # one shared transport
    acme = TenantScopedEventBus("acme", bus)
    globex = TenantScopedEventBus("globex", bus)

    acme.subscribe("order.created", on_acme_order)
    await globex.publish("order.created", {"id": "g1"})   # acme never sees it
    await acme.publish("order.created", {"id": "a1"})     # only on_acme_order fires

The wrapper keeps the same ``publish`` / ``subscribe`` / ``subscribe_events``
shape as :class:`EventBus`; the tenant prefix is transparent to handlers
(they receive the ORIGINAL payload, and via :meth:`subscribe_events` a
:class:`DomainEvent` whose ``event_type`` is the LOGICAL, un-prefixed type).

The same wrapper works over the Redis Streams backend, where prefixing is
the ONLY way to isolate tenants sharing one broker — a shared
``EventBus(backend="redis")`` plus one :class:`TenantScopedEventBus` per
tenant keeps every tenant's events on its own stream key.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Awaitable, Callable, Dict, Optional

from .bus import EventBus, Subscription
from .domain_event import DomainEvent

__all__ = ["TenantScopedEventBus"]

# Sentinel for "argument not supplied" so bus-construction kwargs can be
# rejected (rather than silently ignored) when a shared bus is passed.
_UNSET: Any = object()

# Attribute stamped on a shared EventBus recording the separator the first
# wrapper scoped it with. A later wrapper passing a DIFFERENT separator on the
# same bus is refused — mixed separators can map two distinct tenants onto the
# same topic (e.g. ("a","::") and ("a:",":x") both yield prefix "a::x").
_SEPARATOR_STAMP_ATTR = "_kailash_tenant_separator"


class TenantScopedEventBus:
    """Tenant-isolating facade over a shared :class:`EventBus`.

    Every ``event_type`` is namespaced as ``f"{tenant_id}{separator}{event_type}"``
    before it reaches the underlying bus, so publishes and subscriptions on
    one tenant never cross into another. Because the wrapped bus dispatches
    by exact type, isolation is structural — not a runtime filter that could
    be bypassed.

    Args:
        tenant_id: Stable identifier for the tenant. MUST be a non-empty
            string and MUST NOT contain *separator* (a separator inside the
            id would make ``f"{tenant}{sep}{type}"`` ambiguous and allow a
            crafted id to address another tenant's topics).
        bus: A shared :class:`EventBus` to wrap. When omitted, a private
            in-memory :class:`EventBus` is constructed and owned by this
            wrapper (closed by :meth:`close`). Pass a shared bus to isolate
            multiple tenants on one transport — the common multi-tenant case.
            ``backend`` / ``redis_url`` / ``max_subscribers`` are valid ONLY
            when constructing a new bus (``bus=None``); supplying them
            alongside a shared *bus* raises ``ValueError`` rather than
            silently ignoring them.
        separator: Delimiter between tenant id and event type. Defaults to
            ``":"``. MUST be a non-empty string. The event type MAY itself
            contain the separator; un-prefixing strips the known
            ``f"{tenant_id}{separator}"`` prefix by length, not by splitting.
            Every wrapper sharing one bus MUST use the SAME separator — the
            first wrapper stamps it on the bus and a later wrapper passing a
            different separator is refused (mixed separators can map two
            distinct tenants onto the same topic).

    Example:
        >>> bus = EventBus()
        >>> acme = TenantScopedEventBus("acme", bus)
        >>> async def on_order(payload): ...
        >>> sub = acme.subscribe("order.created", on_order)
        >>> await acme.publish("order.created", {"id": "a1"})
        >>> await sub.unsubscribe()
    """

    def __init__(
        self,
        tenant_id: str,
        bus: Optional[EventBus] = None,
        *,
        separator: str = ":",
        backend: Optional[str] = None,
        redis_url: Optional[str] = None,
        max_subscribers: Any = _UNSET,
    ) -> None:
        if not isinstance(separator, str) or not separator:
            raise ValueError("separator must be a non-empty string")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("tenant_id must be a non-empty string")
        if separator in tenant_id:
            raise ValueError(
                f"tenant_id must not contain the separator {separator!r}; "
                f"got {tenant_id!r} (a separator inside the id would let a "
                f"crafted tenant_id address another tenant's topics)"
            )
        self._tenant_id = tenant_id
        self._separator = separator
        self._prefix = f"{tenant_id}{separator}"
        if bus is None:
            self._bus = EventBus(
                backend=backend,
                redis_url=redis_url,
                max_subscribers=(
                    10_000 if max_subscribers is _UNSET else max_subscribers
                ),
            )
            self._owns_bus = True
        else:
            # A shared bus carries its own transport config; bus-construction
            # kwargs would be silently dropped, so reject them loudly instead
            # (zero-tolerance Rule 3c — accepted-but-unused kwargs are BLOCKED).
            if (
                backend is not None
                or redis_url is not None
                or max_subscribers is not _UNSET
            ):
                raise ValueError(
                    "backend/redis_url/max_subscribers are only valid when "
                    "constructing a new bus (bus=None); a shared bus carries "
                    "its own config — configure it on the EventBus instead"
                )
            self._bus = bus
            self._owns_bus = False
        # Enforce one separator per bus: mixed separators on a shared bus can
        # map two distinct tenants onto the same topic (cross-tenant leak).
        stamped = getattr(self._bus, _SEPARATOR_STAMP_ATTR, None)
        if stamped is None:
            setattr(self._bus, _SEPARATOR_STAMP_ATTR, separator)
        elif stamped != separator:
            raise ValueError(
                f"bus is already tenant-scoped with separator {stamped!r}; "
                f"refusing to wrap it with a different separator {separator!r} "
                f"— mixed separators on one bus can collide distinct tenants "
                f"onto the same topic"
            )

    @property
    def tenant_id(self) -> str:
        """The tenant this wrapper scopes every topic to."""
        return self._tenant_id

    @property
    def separator(self) -> str:
        """The delimiter between tenant id and event type."""
        return self._separator

    @property
    def bus(self) -> EventBus:
        """The underlying (possibly shared) transport bus."""
        return self._bus

    @property
    def owns_bus(self) -> bool:
        """Whether :meth:`close` will close the underlying bus.

        ``True`` when this wrapper constructed its own bus (no *bus* arg);
        ``False`` when a shared bus was passed in (the caller owns its
        lifecycle).
        """
        return self._owns_bus

    def _scoped(self, event_type: str) -> str:
        if not event_type:
            raise ValueError("event_type must be a non-empty string")
        return f"{self._prefix}{event_type}"

    def _logical(self, scoped_event_type: str) -> str:
        if scoped_event_type.startswith(self._prefix):
            return scoped_event_type[len(self._prefix) :]
        return scoped_event_type  # pragma: no cover - defensive

    async def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> None:
        """Publish to this tenant's namespace only.

        Same contract as :meth:`EventBus.publish`; the event reaches only
        subscribers registered through a :class:`TenantScopedEventBus` with
        the SAME ``tenant_id`` (and separator) on the same bus.
        """
        await self._bus.publish(
            self._scoped(event_type),
            payload,
            correlation_id=correlation_id,
            actor=actor,
        )

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> Subscription:
        """Subscribe within this tenant's namespace.

        The *handler* receives the ORIGINAL payload dict, exactly as with
        :meth:`EventBus.subscribe`. It is invoked ONLY for publishes made
        through a wrapper with the same ``tenant_id``.
        """
        return self._bus.subscribe(self._scoped(event_type), handler)

    def subscribe_events(
        self,
        event_type: str,
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> Subscription:
        """Like :meth:`subscribe` but the handler receives the full
        :class:`DomainEvent`.

        The delivered event's ``event_type`` is the LOGICAL (un-prefixed)
        type the subscriber asked for — the tenant prefix is an isolation
        detail of the transport, not something handlers parse. All other
        envelope fields (``payload`` / ``correlation_id`` / ``timestamp`` /
        ``actor``) round-trip unchanged.
        """

        async def _unscope(event: DomainEvent) -> None:
            await handler(replace(event, event_type=self._logical(event.event_type)))

        return self._bus.subscribe_events(self._scoped(event_type), _unscope)

    async def close(self) -> None:
        """Release the underlying bus IF this wrapper owns it.

        A wrapper constructed without a *bus* arg owns its private bus and
        closes it here. A wrapper over a shared bus leaves the bus open —
        the caller owns the shared transport's lifecycle.
        """
        if self._owns_bus:
            await self._bus.close()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"TenantScopedEventBus(tenant_id={self._tenant_id!r}, "
            f"separator={self._separator!r}, backend={self._bus.backend_name!r}, "
            f"owns_bus={self._owns_bus})"
        )
