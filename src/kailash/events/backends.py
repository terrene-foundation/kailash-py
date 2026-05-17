# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Pluggable transport backends for the public :class:`kailash.EventBus`.

The public ``EventBus`` primitive is transport-agnostic.  Concrete
backends implement :class:`EventBackend` so that application code keeps
the same ``publish`` / ``subscribe`` shape regardless of whether events
travel in-process (dev/test) or through a broker (production).

Two backends ship in the SDK:

* :class:`InMemoryEventBackend` — zero-dependency, in-process, default.
* :class:`RedisStreamsEventBackend` — Redis Streams, behind the optional
  ``redis`` extra (``pip install 'kailash[redis]'``).

Backends are selected via :func:`create_backend` which reads the
``KAILASH_EVENTBUS_BACKEND`` environment variable (``memory`` | ``redis``)
or an explicit ``backend=`` argument to :class:`kailash.EventBus`.

The registration API is split so the public ``EventBus.subscribe`` can
return a :class:`~kailash.events.bus.Subscription` synchronously (the
issue #1054 contract) while broker consumers run as async tasks:

* ``register(event_type, handler) -> str`` — synchronous; records the
  subscription, returns its id.
* ``unregister(subscription_id)`` — async; tears down the subscription
  and any backend resources (broker consumer task).
* ``publish(event)`` — async; delivers to subscribers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Optional

from .domain_event import DomainEvent

logger = logging.getLogger(__name__)

__all__ = [
    "EventBackend",
    "InMemoryEventBackend",
    "RedisStreamsEventBackend",
    "create_backend",
]

# Async handler signature: receives the full DomainEvent so that
# correlation_id / actor / timestamp propagate natively. The public
# EventBus adapts payload-only user handlers to this shape.
EventHandler = Callable[[DomainEvent], Awaitable[None]]

_DEFAULT_MAX_SUBSCRIBERS = 10_000


class EventBackend(ABC):
    """Transport backend contract for the public EventBus.

    Implementations MUST bound their subscriber registry to
    ``max_subscribers`` to prevent unbounded memory growth in
    long-running processes.
    """

    @abstractmethod
    def register(self, event_type: str, handler: EventHandler) -> str:
        """Synchronously record a subscription; return its id.

        Broker backends MUST NOT block here — defer any consumer task
        startup so this returns immediately.
        """

    @abstractmethod
    async def unregister(self, subscription_id: str) -> None:
        """Remove the subscription and release its backend resources."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Deliver *event* to every handler subscribed to its type."""

    async def close(self) -> None:  # pragma: no cover - default no-op
        """Release any backend resources (connections, tasks)."""
        return None


class InMemoryEventBackend(EventBackend):
    """In-process, zero-dependency backend.

    Suitable for unit/integration tests and single-process applications.
    Handlers are invoked sequentially on the publishing coroutine's event
    loop.  A handler exception is logged and does NOT prevent the
    remaining handlers from running (fail-open per handler).
    """

    def __init__(self, max_subscribers: int = _DEFAULT_MAX_SUBSCRIBERS) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, "OrderedDict[str, EventHandler]"] = {}
        self._sub_index: Dict[str, str] = {}
        self._max_subscribers = max_subscribers
        self._total = 0

    def register(self, event_type: str, handler: EventHandler) -> str:
        if not event_type:
            raise ValueError("event_type must be a non-empty string")
        if not callable(handler):
            raise ValueError("handler must be callable")
        sub_id = str(uuid.uuid4())
        with self._lock:
            if self._total >= self._max_subscribers:
                raise RuntimeError(
                    f"subscriber limit reached ({self._max_subscribers})"
                )
            self._subscribers.setdefault(event_type, OrderedDict())[sub_id] = handler
            self._sub_index[sub_id] = event_type
            self._total += 1
        logger.debug(
            "eventbus.subscribe backend=memory event_type=%s "
            "subscription_id=%s total=%d",
            event_type,
            sub_id,
            self._total,
        )
        return sub_id

    async def unregister(self, subscription_id: str) -> None:
        with self._lock:
            event_type = self._sub_index.pop(subscription_id, None)
            if event_type is None:
                raise KeyError(f"unknown subscription id: {subscription_id}")
            bucket = self._subscribers.get(event_type)
            if bucket is not None:
                bucket.pop(subscription_id, None)
                if not bucket:
                    del self._subscribers[event_type]
            self._total -= 1
        logger.debug(
            "eventbus.unsubscribe backend=memory subscription_id=%s "
            "event_type=%s total=%d",
            subscription_id,
            event_type,
            self._total,
        )

    async def publish(self, event: DomainEvent) -> None:
        with self._lock:
            bucket = self._subscribers.get(event.event_type)
            handlers = list(bucket.items()) if bucket else []
        for sub_id, handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "event_handler.error subscription_id=%s event_type=%s",
                    sub_id,
                    event.event_type,
                )


class RedisStreamsEventBackend(EventBackend):
    """Broker-backed backend using Redis Streams.

    One Redis Stream per ``event_type`` (key ``kailash:events:<type>``).
    Each subscription spawns a background consumer task (lazily, on the
    running event loop) that blocks on ``XREAD`` and dispatches decoded
    payloads to the handler.  The ``redis`` package is an OPTIONAL extra
    — constructing this class without it installed raises a clear,
    actionable error.

    Args:
        url: Redis connection URL (default ``redis://localhost:6379/0``).
            Falls back to ``KAILASH_EVENTBUS_REDIS_URL`` env var.
        max_subscribers: Upper bound on concurrent consumer tasks.
        block_ms: ``XREAD`` block timeout in milliseconds.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        max_subscribers: int = _DEFAULT_MAX_SUBSCRIBERS,
        block_ms: int = 1000,
    ) -> None:
        try:
            import redis.asyncio as _redis_async
        except ImportError as exc:  # pragma: no cover - exercised w/o extra
            raise ImportError(
                "RedisStreamsEventBackend requires the 'redis' extra. "
                "Install with: pip install 'kailash[redis]'"
            ) from exc
        self._redis_async = _redis_async
        self._url = (
            url
            or os.environ.get("KAILASH_EVENTBUS_REDIS_URL")
            or "redis://localhost:6379/0"
        )
        self._client = _redis_async.from_url(self._url, decode_responses=True)
        self._max_subscribers = max_subscribers
        self._block_ms = block_ms
        self._key_prefix = "kailash:events:"
        # subscription_id -> (event_type, handler)
        self._pending: Dict[str, tuple[str, EventHandler]] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._stop_flags: Dict[str, asyncio.Event] = {}
        self._lock = threading.Lock()

    def _stream_key(self, event_type: str) -> str:
        return f"{self._key_prefix}{event_type}"

    def register(self, event_type: str, handler: EventHandler) -> str:
        if not event_type:
            raise ValueError("event_type must be a non-empty string")
        if not callable(handler):
            raise ValueError("handler must be callable")
        with self._lock:
            if (len(self._pending) + len(self._tasks)) >= self._max_subscribers:
                raise RuntimeError(
                    f"subscriber limit reached ({self._max_subscribers})"
                )
            sub_id = str(uuid.uuid4())
            self._pending[sub_id] = (event_type, handler)
        # Try to start the consumer immediately if a loop is running;
        # otherwise it starts on first publish/loop interaction.
        try:
            asyncio.get_running_loop()
            self._ensure_consumer(sub_id)
        except RuntimeError:
            pass
        logger.debug(
            "eventbus.subscribe backend=redis event_type=%s " "subscription_id=%s",
            event_type,
            sub_id,
        )
        return sub_id

    def _ensure_consumer(self, sub_id: str) -> None:
        with self._lock:
            if sub_id in self._tasks or sub_id not in self._pending:
                return
            event_type, handler = self._pending.pop(sub_id)
            stop = asyncio.Event()
            self._stop_flags[sub_id] = stop
            task = asyncio.create_task(self._consume(event_type, handler, stop, sub_id))
            self._tasks[sub_id] = task

    def _ensure_all_consumers(self) -> None:
        for sub_id in list(self._pending):
            self._ensure_consumer(sub_id)

    async def _consume(
        self,
        event_type: str,
        handler: EventHandler,
        stop: asyncio.Event,
        sub_id: str,
    ) -> None:
        key = self._stream_key(event_type)
        last_id = "$"  # only events published after subscription
        while not stop.is_set():
            try:
                resp = await self._client.xread(
                    {key: last_id}, count=10, block=self._block_ms
                )
            except asyncio.CancelledError:
                break
            except Exception:
                if stop.is_set():
                    break
                logger.exception(
                    "eventbus.redis.xread_error event_type=%s " "subscription_id=%s",
                    event_type,
                    sub_id,
                )
                await asyncio.sleep(0.5)
                continue
            if not resp:
                continue
            for _stream, entries in resp:
                for entry_id, fields in entries:
                    last_id = entry_id
                    raw = fields.get("event")
                    if raw is None:
                        continue
                    try:
                        event = DomainEvent.from_dict(json.loads(raw))
                    except Exception:
                        logger.exception(
                            "eventbus.redis.decode_error subscription_id=%s",
                            sub_id,
                        )
                        continue
                    try:
                        await handler(event)
                    except Exception:
                        logger.exception(
                            "event_handler.error subscription_id=%s " "event_type=%s",
                            sub_id,
                            event_type,
                        )

    async def unregister(self, subscription_id: str) -> None:
        with self._lock:
            pending = self._pending.pop(subscription_id, None)
            stop = self._stop_flags.pop(subscription_id, None)
            task = self._tasks.pop(subscription_id, None)
        if pending is None and task is None:
            raise KeyError(f"unknown subscription id: {subscription_id}")
        if stop is not None:
            stop.set()
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        logger.debug(
            "eventbus.unsubscribe backend=redis subscription_id=%s",
            subscription_id,
        )

    async def publish(self, event: DomainEvent) -> None:
        # Ensure any consumers registered before a loop existed are live
        # so they observe events published after this point.
        self._ensure_all_consumers()
        await self._client.xadd(
            self._stream_key(event.event_type),
            {"event": json.dumps(event.to_dict())},
            maxlen=10_000,
            approximate=True,
        )

    async def close(self) -> None:
        for sub_id in list(self._tasks) + list(self._pending):
            try:
                await self.unregister(sub_id)
            except KeyError:
                pass
        try:
            await self._client.aclose()
        except Exception:  # pragma: no cover - best-effort cleanup
            logger.debug("eventbus.redis.close_error", exc_info=True)


def create_backend(
    backend: Optional[str] = None,
    *,
    redis_url: Optional[str] = None,
    max_subscribers: int = _DEFAULT_MAX_SUBSCRIBERS,
) -> EventBackend:
    """Instantiate a backend by name with env-var fallback.

    Selection order: explicit ``backend`` arg →
    ``KAILASH_EVENTBUS_BACKEND`` env var → ``"memory"``.

    Args:
        backend: ``"memory"`` or ``"redis"``. ``None`` reads the env var.
        redis_url: Redis URL for the ``redis`` backend.
        max_subscribers: Subscriber-registry bound.

    Returns:
        A concrete :class:`EventBackend`.

    Raises:
        ValueError: If *backend* is an unknown name.
    """
    name = (backend or os.environ.get("KAILASH_EVENTBUS_BACKEND") or "memory").lower()
    if name == "memory":
        return InMemoryEventBackend(max_subscribers=max_subscribers)
    if name == "redis":
        return RedisStreamsEventBackend(url=redis_url, max_subscribers=max_subscribers)
    raise ValueError(f"unknown eventbus backend {name!r}; expected 'memory' or 'redis'")
