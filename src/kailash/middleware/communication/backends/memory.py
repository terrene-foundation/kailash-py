# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
In-memory EventBus backend.

Thread-safe, zero-dependency implementation backed by a dict of handler
lists protected by a :class:`threading.Lock`. Suitable for single-process
applications, unit/integration tests, and local development.

Design notes
------------
* Subscriber list is bounded to ``max_subscribers`` (default 10 000) to
  prevent unbounded memory growth.  See ``dataflow-pool.md`` Rule 4
  (bounded collections) and ``trust-plane-security.md`` Rule 4.
* All mutations and reads of the subscription registry acquire
  ``self._lock`` to guarantee thread safety.
* Handler invocation happens **outside** the lock so that slow handlers
  cannot starve other publishers.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Tuple

from ..domain_event import DomainEvent
from ..event_bus import EventBus, PublishError, SubscriptionError

logger = logging.getLogger(__name__)

__all__ = ["InMemoryEventBus"]

_DEFAULT_MAX_SUBSCRIBERS = 10_000


class InMemoryEventBus(EventBus):
    """Thread-safe, bounded, in-memory event bus.

    Args:
        max_subscribers: Upper bound on total subscriptions across all
            event types.  When the limit is reached, new :meth:`subscribe`
            calls raise :class:`SubscriptionError`.
    """

    def __init__(self, max_subscribers: int = _DEFAULT_MAX_SUBSCRIBERS) -> None:
        self._lock = threading.Lock()
        # event_type -> OrderedDict[subscription_id, handler]
        # OrderedDict preserves insertion order and allows O(1) delete.
        self._subscribers: Dict[
            str, OrderedDict[str, Callable[[DomainEvent], None]]
        ] = {}
        # subscription_id -> event_type  (reverse index for fast unsubscribe)
        self._sub_index: Dict[str, str] = {}
        self._max_subscribers = max_subscribers
        self._total_subscriptions = 0

    # ------------------------------------------------------------------
    # EventBus interface
    # ------------------------------------------------------------------

    def publish(self, event: DomainEvent) -> None:
        """Publish *event* to all handlers registered for its type.

        Handlers are invoked **synchronously** in subscription order.  If
        a handler raises, the exception is logged and the remaining
        handlers still execute (fail-open per handler, not per publish).

        Raises:
            PublishError: If *event* is ``None`` or not a
                :class:`DomainEvent`.
        """
        if not isinstance(event, DomainEvent):
            raise PublishError(
                "event must be a DomainEvent instance",
                details={"received_type": type(event).__name__},
            )

        # Snapshot handlers under the lock so we can invoke outside it.
        handlers: List[Tuple[str, Callable[[DomainEvent], None]]] = []
        with self._lock:
            bucket = self._subscribers.get(event.event_type)
            if bucket:
                handlers = list(bucket.items())

        for sub_id, handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Handler %s for event %s raised an exception",
                    sub_id,
                    event.event_type,
                )

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[DomainEvent], None],
    ) -> str:
        """Register *handler* for *event_type*.

        Returns:
            A unique subscription ID.

        Raises:
            SubscriptionError: If *event_type* is empty, *handler* is not
                callable, or the subscriber limit has been reached.
        """
        if not event_type:
            raise SubscriptionError(
                "event_type must be a non-empty string",
                details={"event_type": event_type},
            )
        if not callable(handler):
            raise SubscriptionError(
                "handler must be callable",
                details={"handler_type": type(handler).__name__},
            )

        sub_id = str(uuid.uuid4())

        with self._lock:
            if self._total_subscriptions >= self._max_subscribers:
                raise SubscriptionError(
                    f"Subscriber limit reached ({self._max_subscribers})",
                    details={
                        "max_subscribers": self._max_subscribers,
                        "current": self._total_subscriptions,
                    },
                )

            if event_type not in self._subscribers:
                self._subscribers[event_type] = OrderedDict()

            self._subscribers[event_type][sub_id] = handler
            self._sub_index[sub_id] = event_type
            self._total_subscriptions += 1

        logger.debug(
            "Subscription %s registered for event_type=%s (total=%d)",
            sub_id,
            event_type,
            self._total_subscriptions,
        )
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove the subscription identified by *subscription_id*.

        Raises:
            SubscriptionError: If the ID does not correspond to an active
                subscription.
        """
        with self._lock:
            event_type = self._sub_index.pop(subscription_id, None)
            if event_type is None:
                raise SubscriptionError(
                    f"Unknown subscription ID: {subscription_id}",
                    details={"subscription_id": subscription_id},
                )

            bucket = self._subscribers.get(event_type)
            if bucket is not None:
                bucket.pop(subscription_id, None)
                if not bucket:
                    del self._subscribers[event_type]

            self._total_subscriptions -= 1

        logger.debug(
            "Subscription %s removed for event_type=%s (total=%d)",
            subscription_id,
            event_type,
            self._total_subscriptions,
        )
