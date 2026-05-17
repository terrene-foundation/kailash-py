# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kailash domain-event publication primitive.

Public surface:

* :class:`EventBus` — async ``publish`` / sync ``subscribe`` with
  pluggable transport backends (in-memory default, Redis Streams via the
  optional ``redis`` extra).
* :class:`Subscription` — handle returned by ``EventBus.subscribe``;
  ``await sub.unsubscribe()`` to stop receiving events.
* :class:`DomainEvent` — JSON-serializable event envelope carrying
  ``correlation_id`` for trace propagation.
* :class:`EventBackend` / :class:`InMemoryEventBackend` /
  :class:`RedisStreamsEventBackend` — backend contract + implementations.

These are also re-exported from the top-level ``kailash`` namespace::

    from kailash import EventBus, Subscription
"""

from __future__ import annotations

from .backends import (
    EventBackend,
    InMemoryEventBackend,
    RedisStreamsEventBackend,
    create_backend,
)
from .bus import EventBus, Subscription
from .domain_event import DomainEvent

__all__ = [
    "EventBus",
    "Subscription",
    "DomainEvent",
    "EventBackend",
    "InMemoryEventBackend",
    "RedisStreamsEventBackend",
    "create_backend",
]
